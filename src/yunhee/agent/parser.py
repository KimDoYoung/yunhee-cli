"""
yunhee-cli Agentic Fallback Parser
로컬 14B 모델의 비표준 / 텍스트 내포 도구 호출을 복구하기 위한 4중 Fallback 파서.
"""

from __future__ import annotations

import json
import re
from typing import Any

# 로컬 모델이 자주 혼동하는 도구 이름 별칭(Alias) 매핑
TOOL_ALIASES: dict[str, str] = {
    "grep": "grep_search",
    "search": "grep_search",
    "find": "find_files",
    "locate": "find_files",
    "cat": "read_file",
    "view": "read_file",
    "read": "read_file",
    "ls": "list_files",
    "dir": "list_files",
    "bash": "run_command",
    "sh": "run_command",
    "exec": "run_command",
    "terminal": "run_command",
    "write": "write_file",
    "edit": "edit_file",
    "memory": "save_rule",
    "save_memory": "save_rule",
    "rule": "save_rule",
    "remember": "save_rule",
    "knowledge": "save_knowledge",
    "store_knowledge": "save_knowledge",
    "find_knowledge": "search_knowledge",
    "query_knowledge": "search_knowledge",
    "config": "lookup_config",
    "get_config": "lookup_config",
    "errors": "read_recent_errors",
    "get_errors": "read_recent_errors",
    "recent_errors": "read_recent_errors",
}


def sanitize_json_text(text: str) -> str:
    """유니코드 따옴표 및 비표준 공백을 표준 ASCII로 정규화."""
    # 유니코드 큰따옴표 정규화
    text = re.sub(r"[\u201C\u201D\u201E\u201F\u2033\u2036]", '"', text)
    # 유니코드 작은따옴표 정규화
    text = re.sub(r"[\u2018\u2019\u201A\u201B\u2032\u2035]", "'", text)
    # 비표준 공백(NBSP, 전각 공백 등) 정규화
    text = re.sub(r"[\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]", " ", text)
    return text


def _extract_args_from_list(name: str, args_list: list[Any]) -> dict[str, Any]:
    """리눅스 CLI 스타일 인자 리스트(예: ['-rnw', '.', '-e', 'class AgentLoop'])를 딕셔너리로 구출."""
    str_list = [str(x).strip() for x in args_list]

    if name == "grep_search":
        # -e 뒤의 인자 탐색
        if "-e" in str_list:
            idx = str_list.index("-e")
            if idx + 1 < len(str_list):
                return {"query": str_list[idx + 1]}
        # 옵션 플래그(-)가 아닌 인자 중 가장 유력한 문자열 채택
        non_flags = [x for x in str_list if not x.startswith("-") and x != "."]
        if non_flags:
            return {"query": non_flags[-1]}
        return {"query": " ".join(str_list)}

    if name == "find_files":
        # -name 뒤의 인자 탐색
        if "-name" in str_list:
            idx = str_list.index("-name")
            if idx + 1 < len(str_list):
                return {"pattern": str_list[idx + 1]}
        non_flags = [x for x in str_list if not x.startswith("-") and x != "."]
        if non_flags:
            return {"pattern": non_flags[-1]}
        return {"pattern": "*"}

    if name == "run_command":
        return {"command": " ".join(str_list)}

    if name == "read_file":
        non_flags = [x for x in str_list if not x.startswith("-")]
        return {"filename": non_flags[0]} if non_flags else {}

    if name == "list_files":
        non_flags = [x for x in str_list if not x.startswith("-")]
        return {"directory": non_flags[0]} if non_flags else {"directory": "."}

    return {}


def _normalize_call_item(item: Any) -> tuple[str, dict] | None:
    """파싱된 JSON 객체에서 도구 이름과 인자 딕셔너리를 추출 및 별칭 구출."""
    if not isinstance(item, dict):
        return None

    raw_name = ""
    raw_args: Any = {}

    # Case 1: 표준 형태 {"name": "...", "arguments": ...}
    if "name" in item:
        raw_name = str(item["name"]).strip()
        raw_args = item.get("arguments", {})

    # Case 2: OpenAI tool_call 스키마 중첩 {"type": "function", "function": {"name": ...}}
    elif item.get("type") == "function" and isinstance(item.get("function"), dict):
        fn = item["function"]
        raw_name = str(fn.get("name", "")).strip()
        raw_args = fn.get("arguments", {})

    # Case 3: {"tool": "...", "parameters": ...} 또는 {"action": "...", "action_input": ...}
    else:
        alt_name = item.get("tool") or item.get("action")
        if alt_name:
            raw_name = str(alt_name).strip()
            raw_args = item.get("parameters") or item.get("action_input") or item.get("args") or {}

    if not raw_name:
        return None

    # 별칭(Alias) 변환 (예: 'grep' -> 'grep_search', 'find' -> 'find_files')
    normalized_name = TOOL_ALIASES.get(raw_name.lower(), raw_name)

    # arguments 문자열인 경우 JSON 파싱 시도
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            # 일반 평문 문자열인 경우 도구별 기본 키 매핑
            if normalized_name == "grep_search":
                raw_args = {"query": raw_args}
            elif normalized_name == "find_files":
                raw_args = {"pattern": raw_args}
            elif normalized_name == "read_file":
                raw_args = {"filename": raw_args}
            elif normalized_name == "run_command":
                raw_args = {"command": raw_args}
            else:
                raw_args = {}

    # arguments가 리스트 형태인 경우 (예: ['-rnw', '.', '-e', 'class AgentLoop'])
    if isinstance(raw_args, list):
        args = _extract_args_from_list(normalized_name, raw_args)
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        args = {}

    return (normalized_name, args)


def extract_tool_calls_from_text(text: str) -> list[tuple[str, dict]]:
    """
    LLM의 텍스트 응답에서 도구 호출 목록[(name, arguments)]을 다중 패턴으로 추출.

    탐색 우선순위:
    1. 전체 텍스트 직접 JSON 파싱
    2. 마크다운 코드 블록 (```json ... ```)
    3. JSON 배열 블록 ([{ ... }])
    4. 괄호 깊이 추적 파서 (Depth-bracket parsing)
    """
    if not text or not text.strip():
        return []

    text = sanitize_json_text(text.strip())
    calls: list[tuple[str, dict]] = []

    # 1. 텍스트 전체가 바로 완결된 JSON인 경우
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            norm = _normalize_call_item(data)
            if norm:
                return [norm]
        elif isinstance(data, list):
            for item in data:
                norm = _normalize_call_item(item)
                if norm:
                    calls.append(norm)
            if calls:
                return calls
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. 마크다운 코드 블록 (```json ... ``` 또는 ``` ... ```)
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        block_clean = block.strip()
        try:
            data = json.loads(block_clean)
            if isinstance(data, dict):
                norm = _normalize_call_item(data)
                if norm:
                    calls.append(norm)
            elif isinstance(data, list):
                for item in data:
                    norm = _normalize_call_item(item)
                    if norm:
                        calls.append(norm)
        except (json.JSONDecodeError, TypeError):
            pass

    if calls:
        return calls

    # 3. JSON 배열 블록 탐색: [ { ... }, ... ]
    for match in re.finditer(r"\[\s*\{[\s\S]*?\}\s*\]", text):
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                for item in data:
                    norm = _normalize_call_item(item)
                    if norm:
                        calls.append(norm)
        except (json.JSONDecodeError, TypeError):
            pass

    if calls:
        return calls

    # 4. JSON 단일 객체 블록 탐색: 괄호 깊이(depth) 추적 파서
    start_idx = 0
    text_len = len(text)
    while start_idx < text_len:
        pos = text.find("{", start_idx)
        if pos == -1:
            break

        depth = 0
        in_string = False
        escape = False
        end_pos = -1

        for i in range(pos, text_len):
            c = text[i]
            if c == '"' and not escape:
                in_string = not in_string
            elif c == "\\" and in_string:
                escape = not escape
                continue
            elif not in_string:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break
            escape = False

        if end_pos != -1:
            snippet = text[pos:end_pos]
            try:
                data = json.loads(snippet)
                norm = _normalize_call_item(data)
                if norm:
                    calls.append(norm)
            except (json.JSONDecodeError, TypeError):
                pass
            start_idx = end_pos
        else:
            start_idx = pos + 1

    return calls
