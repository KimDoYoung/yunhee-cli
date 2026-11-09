"""
yunhee-cli Agent Loop Engine
로컬 모델(Qwen 14B)을 위한 다단계 자율 에이전트 루프 및 Fallback 실행 엔진.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AsyncOpenAI

from yunhee import config
from yunhee.agent.knowledge import prefetch_relevant_knowledge
from yunhee.agent.memory import get_rules_prompt_section
from yunhee.agent.parser import extract_tool_calls_from_text
from yunhee.agent.registry import ToolRegistry, create_default_registry
from yunhee.agent.session import SessionLogger
from yunhee.tools.trace.tobe_rag import find_deterministic_matches, prefetch_tobe_rag


@dataclass
class _NativeFunctionCall:
    name: str
    arguments: str


@dataclass
class _NativeToolCall:
    id: str
    function: _NativeFunctionCall
    type: str = "function"


@dataclass
class _NativeChatMessage:
    role: str = "assistant"
    content: str | None = ""
    tool_calls: list[_NativeToolCall] = field(default_factory=list)


@dataclass
class _NativeChoice:
    message: _NativeChatMessage


@dataclass
class _NativeChatResponse:
    choices: list[_NativeChoice]


def _serialize_message_for_ollama(msg: Any) -> dict[str, Any]:
    """OpenAI 메시지 객체 또는 dict를 Ollama /api/chat 포맷으로 변환한다."""
    if isinstance(msg, dict):
        out: dict[str, Any] = {
            "role": msg.get("role", "user"),
            "content": msg.get("content") or "",
        }
        if msg.get("tool_calls"):
            tcs = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", None)
                if fn:
                    fname = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "")
                    fargs = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", {})
                    if isinstance(fargs, str):
                        try:
                            fargs = json.loads(fargs)
                        except Exception:  # noqa: BLE001
                            fargs = {}
                    tcs.append({"function": {"name": fname, "arguments": fargs or {}}})
            if tcs:
                out["tool_calls"] = tcs
        return out

    # _NativeChatMessage 또는 OpenAI ChatCompletionMessage 객체인 경우
    role = getattr(msg, "role", "assistant")
    content = getattr(msg, "content", "") or ""
    out = {"role": role, "content": content}
    raw_tcs = getattr(msg, "tool_calls", None) or []
    if raw_tcs:
        tcs = []
        for tc in raw_tcs:
            fn = getattr(tc, "function", None)
            if fn:
                fargs = getattr(fn, "arguments", "{}")
                if isinstance(fargs, str):
                    try:
                        fargs = json.loads(fargs)
                    except Exception:  # noqa: BLE001
                        fargs = {}
                tcs.append({"function": {"name": getattr(fn, "name", ""), "arguments": fargs or {}}})
        if tcs:
            out["tool_calls"] = tcs
    return out


class _OllamaCompletionsEndpoint:
    """Ollama /api/chat 엔드포인트를 호출하여 num_ctx가 잘리지 않도록 보장하는 래퍼."""

    def __init__(self, base_host: str, timeout: float = 120.0) -> None:
        self.base_host = base_host.rstrip("/")
        self.timeout = timeout

    def create(
        self,
        model: str,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        extra_body: dict[str, Any] | None = None,
    ) -> _NativeChatResponse:
        opts = {"num_ctx": config.NUM_CTX, "temperature": temperature}
        if extra_body and isinstance(extra_body.get("options"), dict):
            opts.update(extra_body["options"])

        payload: dict[str, Any] = {
            "model": model,
            "messages": [_serialize_message_for_ollama(m) for m in messages],
            "stream": False,
            "options": opts,
        }
        if tools:
            payload["tools"] = tools

        resp = httpx.post(
            f"{self.base_host}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_msg = data.get("message", {})
        content = raw_msg.get("content") or ""
        raw_tcs = raw_msg.get("tool_calls") or []

        parsed_tcs: list[_NativeToolCall] = []
        for i, tc in enumerate(raw_tcs):
            fn = tc.get("function", {})
            fname = fn.get("name", "")
            fargs = fn.get("arguments", {})
            fargs_str = fargs if isinstance(fargs, str) else json.dumps(fargs, ensure_ascii=False)
            parsed_tcs.append(
                _NativeToolCall(
                    id=tc.get("id") or f"call_{i + 1}",
                    function=_NativeFunctionCall(name=fname, arguments=fargs_str),
                )
            )

        return _NativeChatResponse(
            choices=[
                _NativeChoice(
                    message=_NativeChatMessage(
                        role=raw_msg.get("role", "assistant"),
                        content=content,
                        tool_calls=parsed_tcs,
                    )
                )
            ]
        )


class _OllamaChatNamespace:
    def __init__(self, base_host: str, timeout: float = 120.0) -> None:
        self.completions = _OllamaCompletionsEndpoint(base_host, timeout=timeout)


class _OllamaNativeClient:
    """OpenAI SDK의 client.chat.completions.create 인터페이스를 유지하면서 /api/chat을 사용하는 클라이언트."""

    def __init__(self, base_host: str, timeout: float = 120.0) -> None:
        self.chat = _OllamaChatNamespace(base_host, timeout=timeout)

DEFAULT_SYSTEM_PROMPT = """\
당신은 "절약정신이 투철한 한국여자이고 이름은 'yunhee'"인 전문 마이그레이션 에이전트입니다.
당신은 범용 코딩 에이전트가 아니며, AssetERP 프레임워크를 GWT/GXT에서 Spring Boot/React로 전환하고, 테스트하고, 새로 생긴 프레임워크의 테스트 및 문서화 등에 특화되어 있습니다.
작업 디렉터리 내의 파일들을 확인하고, 내용을 읽고, 수정하거나 명령어를 실행하여 사용자의 요청을 해결하세요.

[사전 구축된 TOBE & AS-IS 학습 자료 우선 활용 (토큰 절약 핵심)]
프로젝트에는 TOBE 및 AS-IS 소스와 DB를 초압축 색인해 둔 자료들이 이미 준비되어 있습니다:
0. **TOBE RAG 자동 주입 및 `lookup_tobe` 도구**:
   - 사용자 메시지 상단에 `[참고 가능한 TOBE 화면·API·백엔드 학습 지식 (TOBE RAG)]` 블록이 주입되어 있고, 그 안에 사용자가 질문한 화면번호(예: `#1002`), 파일 경로, 컴포넌트, API, 백엔드 정보가 이미 들어 있다면 **절대로 추가 도구를 호출하지 말고 즉시 해당 팩트를 바탕으로 답변**하세요.
   - 만약 특정 화면번호(예: `1002`), 메뉴명(예: `업무별 문서작성`), 컴포넌트명, API URL, 테이블명을 단건으로 찾고 싶다면 `lookup_tobe(query="...")` 도구를 최우선 호출하세요.
1. 메뉴 전체 매핑: `docs/to-be/menus.md` (TOBE 메뉴/파일 매핑) 및 `docs/as-is/menus.tsv` (원본 메뉴 매핑)
2. 화면/UI/이벤트 색인: `docs/to-be/domains/{domain}.md` (TOBE 도메인별 화면 카드) 및 `docs/as-is/src/{domain}/{Screen}.md`
3. DB 테이블/함수 분할 색인: `docs/as-is/db/tables/{domain}.md`, `docs/as-is/db/functions/{name}.md`
4. DB 스키마 스냅샷: `.yunhee/*.json` (get_db_definition 또는 get_table_schema 도구로 즉시 조회)
5. 전문 분석 CLI: 필요 시 `run_command`로 `yunhee table <패턴>`, `yunhee trace-menu <경로>`, `yunhee trace-screen <화면>`, `yunhee outline <경로>` 등을 호출하여 팩트를 수집하세요.

사용자가 화면 구성, 메뉴 위치, 테이블 구조, 이벤트/그리드, SQL 등을 질문하거나 분석을 요청하면 거대한 원본 소스를 직접 헤매지 말고, 반드시 위 사전 색인 자료(`docs/as-is/...`)를 `read_file`로 먼저 열람하거나 `get_db_definition` 도구를 호출하여 팩트를 인용해 답변하세요.

[핵심 행동 지침]
1. [결과 전달 필수]: 사용자가 파일 목록, 디렉터리 구조, 파일 내용, 명령어 실행 결과 등을 물어보거나 조회를 요청한 경우, 절대로 "확인했습니다"나 "조회했습니다"라는 단순 확인 멘트로만 끝내지 마십시오. 도구를 통해 얻은 실제 내용(파일명 목록, 읽은 코드 내용, 명령어 출력 등)을 사용자 답변 본문에 마크다운 목록이나 코드블록으로 빠짐없이 정리하여 보여주어야 합니다.
2. [과도한 재귀 탐색 금지]: 사용자가 특정 디렉터리의 파일 목록을 요청했을 때는 해당 디렉터리 직계 목록만 1회 조회(`list_files`)한 후 즉시 그 목록을 답변에 정리하여 출력하세요. 사용자가 명시적으로 하위 폴더 조사를 요구하지 않는 한, 발견된 하위 디렉터리들을 재귀적으로 계속 파고들지 마세요.
3. [도구 활용]: 등록된 전문 도구들을 능동적으로 호출하세요:
   - 파일/코드 탐색: list_files, read_file, write_file, edit_file, find_files, grep_search
   - 데이터베이스: run_sql (PostgreSQL asseterpdb 데이터베이스 안전 조회), get_db_definition (테이블 DDL, 스토어드 함수/프로시저 소스 본체, 뷰 정의 조회). 사용자가 테이블 DDL이나 DB 함수(예: `act02_journal_backup`, `f_...` 등)의 소스코드/본체를 요청하면 파일 시스템에서 찾지 말고 반드시 `get_db_definition(name="...")` 도구를 호출하세요. AssetERP의 테이블 컬럼명은 테이블 접두사 규칙(예: `sys01_company_nm`, `sys01_biz_no` 등)을 갖습니다. 테이블명이 부분 이름(예: `sys01`)으로 주어지더라도 `get_db_definition`이 자동으로 접두사 매칭하여 해당 테이블을 찾아줍니다.
   - 실행: execute_python (파이썬 스크립트 즉석 작성·실행), run_command (빌드, 테스트 등 일반 셸 명령 및 yunhee CLI 실행)
   - 장기 기억: save_rule(프로젝트 헌법/규칙 저장), save_knowledge(해결 노하우/특이사항 저장), search_knowledge(과거 노하우 벡터 검색)
   - 환경/로그: lookup_config(작업경로/DB/설정 확인), read_recent_errors(최근 서버 에러 확인)
   - 산출물 발간: export_spec (화면 마이그레이션 기술 명세서 마크다운 및 Gotenberg PDF 발간)
4. [조건부 화면/모달/그리드/컴포넌트 탐색 지침 (execute_python 최우선 활용)]:
   - 사용자가 특정 조건(예: "제목이 '계정과목'인 모달 찾아줘", "그리드 컬럼 중 체크박스이면서 제목이 한글 3글자인 화면 찾아줘", "특정 버튼이나 API를 호출하는 화면 찾아줘" 등)에 해당하는 화면을 찾아달라고 요청하면:
     1) 별도로 'AS-IS'나 '원본'을 언급하지 않으면 **기본 대상은 항상 TOBE (`side="tobe"`)**입니다.
     2) 사용자가 frontend/backend를 구분하지 않아도 `iter_screens()`는 프론트엔드(모달, 그리드 컬럼, 버튼, TSX 본문)와 백엔드(API URL, SQL ID, 백엔드 파일) 및 상위 `_Tab_` 메뉴 번호를 모두 담고 있습니다.
     3) 존재하지 않는 임의 함수(예: `yunhee.find_modal_by_title` 등)를 지어내지 말고, 반드시 `execute_python` 도구로 `from yunhee.tools.trace.screen_catalog import iter_screens`를 사용하는 아래 실행 코드를 작성하세요:
     - 예시 A (모달 제목 검색):
```python
from yunhee.tools.trace.screen_catalog import iter_screens
for s in iter_screens():
    for m in s.modals:
        if '계정과목' in m.title:
            print(s.format_hit(f'{m.kind}: {m.title} (L{m.line})'))
```
     - 예시 B (그리드 컬럼 타입 및 한글 글자수/정규식 조건 검색 — 한글은 반드시 `[가-힣]` 정규식을 사용하세요):
```python
import re
from yunhee.tools.trace.screen_catalog import iter_screens
for s in iter_screens():
    for c in s.grid_cols:
        if c.col_type in ('boolean', 'booleanYn2') and re.fullmatch(r'[가-힣]{3}', c.label):
            print(s.format_hit(f'gb.{c.col_type}({c.field}, {c.width}, {c.label})'))
```
     4) 사용자가 "파일명, 메뉴명, 화면번호를 알려줘"라고 명시하지 않더라도, 화면 검색 결과는 **항상 `[화면번호(#), 메뉴명(경로), 화면/컴포넌트명, 파일 경로, 일치 상세]` 컬럼을 갖춘 마크다운 표**로 빠짐없이 정리하여 답변하세요.
     5) **환각 절대 금지**: 도구 실행 결과가 `(출력 없음)`일 때 절대로 가짜 `[execute_python 결과]:` 블록이나 존재하지 않는 화면번호(`#123` 등)·가짜 파일 경로(`src/law/...` 등)를 지어내지 마세요.
5. [도구 이름 및 인자 규격]: 반드시 등록된 정확한 도구 이름을 호출하세요. arguments는 반드시 올바른 JSON 키-값 객체 형태여야 합니다.
6. [루프 방지]: 동일한 인자로 동일한 도구를 무의미하게 반복 호출하지 마세요.
"""


def build_system_prompt(base_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    """기본 시스템 프롬프트에 .yunhee/memory.md의 L1 핵심 규칙을 자동 주입합니다."""
    rules_section = get_rules_prompt_section()
    if rules_section:
        return f"{base_prompt.strip()}\n\n{rules_section}".strip()
    return base_prompt.strip()


class AgentLoop:
    """자율 에이전트 실행 루프."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        registry: ToolRegistry | None = None,
        system_prompt: str | None = None,
        max_steps: int = 10,
        session_logger: SessionLogger | None = None,
        auto_log: bool = True,
    ) -> None:
        self.model = model or config.OLLAMA_MODEL
        url = base_url or getattr(config, "OLLAMA_URL", getattr(config, "OLLAMA_HOST", "http://localhost:11434"))
        self.v1_url = f"{str(url).rstrip('/')}/v1"
        self.registry = registry or create_default_registry()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_steps = max_steps

        # 세션 로거 초기화
        if session_logger:
            self.session_logger: SessionLogger | None = session_logger
        elif auto_log:
            self.session_logger = SessionLogger()
        else:
            self.session_logger = None

        # 클라이언트 초기화 (/api/chat 네이티브 래퍼로 num_ctx 16384 보장)
        self._async_client = AsyncOpenAI(base_url=self.v1_url, api_key="ollama", max_retries=2, timeout=60.0)
        self._sync_client: Any = _OllamaNativeClient(str(url), timeout=120.0)

    def get_active_system_prompt(self) -> str:
        """기본 시스템 프롬프트에 동적 L1 규칙을 주입한 최종 프롬프트 반환."""
        return build_system_prompt(self.system_prompt)

    @staticmethod
    def _tool_followup_hint(result: str) -> str:
        if "[Exit Code: 1" in result or result.startswith("error:") or "Traceback (most recent call last)" in result:
            return "[안내]: 도구 실행 중 에러가 발생했습니다. 에러 원인을 파악하여 올바른 함수(`from yunhee.tools.trace.screen_catalog import iter_screens` 등)나 인자로 수정한 뒤 도구를 다시 호출하세요."
        if "(출력 없음" in result:
            return (
                "[안내]: 스크립트 실행 결과 일치하는 출력이 없습니다(출력 없음). "
                "절대로 가짜 `[execute_python 결과]`나 존재하지 않는 화면번호(#123 등)·파일 경로를 지어내어(환각) 표를 만들지 마세요! "
                "조건을 완화하거나 `s.text` 본문 검색으로 넓혀 다시 실행하려면 반드시 JSON 도구 호출만 출력하고, "
                "더 이상 찾을 수 없으면 '조건에 일치하는 화면을 찾지 못했습니다.'라고만 답변하세요."
            )
        if "[Exit Code: 0" in result and "STDOUT:" in result:
            return "[안내]: 도구 실행이 성공하여 위와 같이 STDOUT 결과가 확보되었습니다. 절대로 도구를 다시 호출하지 마시고(JSON 출력 금지), 즉시 위 STDOUT의 모든 행을 '| 화면번호(#) | 메뉴명 | 컴포넌트명 | 파일 경로 | 일치 상세 |' 형식의 마크다운 표로 변환하여 최종 답변만 작성하세요."
        return "[안내]: 사용자가 조회를 요청한 정보라면 위 도구 결과의 상세 내용(화면번호 #, 메뉴명, 컴포넌트명, 파일 경로, 일치 내역 등)을 생략하지 말고 사용자 최종 답변 본문에 마크다운 표로 직접 정리하여 보여주세요."

    def _finalize_without_tools(self, messages: list[dict[str, Any]]) -> str:
        """도구 반복 호출 감지 시 tools=None으로 최종 요약 답변을 강제 생성합니다."""
        final_messages = list(messages) + [
            {
                "role": "user",
                "content": (
                    "이미 도구 실행 결과가 위에 모두 주어졌습니다. "
                    "더 이상 도구(JSON)를 호출하지 말고, 위 실행 결과(STDOUT 등)의 모든 항목을 "
                    "'| 화면번호(#) | 메뉴명 | 컴포넌트명 | 파일 경로 | 일치 상세 |' 형식의 마크다운 표로 정리하여 한국어로 답변하세요."
                ),
            }
        ]
        resp = self._sync_client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            tools=None,
            temperature=0.0,
            extra_body={"options": {"num_ctx": config.NUM_CTX}},
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or "동일한 작업이 반복 감지되어 작업을 종료합니다."

    def run(
        self,
        user_message: str,
        messages_history: list[dict[str, Any]] | None = None,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        동기 방식으로 에이전트 루프를 실행합니다.

        Returns:
            (최종 응답 텍스트, 갱신된 메시지 히스토리)
        """
        schemas = self.registry.get_schemas()
        messages: list[dict[str, Any]] = []

        if messages_history:
            messages = list(messages_history)
        else:
            messages.append({"role": "system", "content": self.get_active_system_prompt()})

        # L2 시맨틱 지식 + TOBE RAG 사전 검색 (Prefetch RAG)
        is_live_ollama = isinstance(self._sync_client, _OllamaNativeClient)
        det_matches = find_deterministic_matches(user_message, max_cards=4) if is_live_ollama else []
        tobe_rag_ctx = (
            prefetch_tobe_rag(user_message, enable_vector=is_live_ollama)
            if is_live_ollama
            else ""
        )
        context_knowledge = prefetch_relevant_knowledge(user_message)
        combined_ctx = f"{tobe_rag_ctx}{context_knowledge}"
        effective_message = f"{combined_ctx}{user_message}" if combined_ctx else user_message

        # 화면번호(#1002)나 컴포넌트명이 결정적으로 매칭되었고 단순 정보 질문인 경우 첫 턴 도구 호출 생략
        is_direct_fact_query = bool(det_matches) and not any(
            kw in user_message
            for kw in ("수정해", "고쳐", "작성해", "생성해", "실행해", "모달을 찾", "모달 찾", "컬럼 중", "체크박스")
        )

        messages.append({"role": "user", "content": effective_message})

        if self.session_logger:
            self.session_logger.log_user_message(user_message)

        step = 0
        last_calls_signature: Any = None
        has_stdout_result = is_direct_fact_query

        while step < self.max_steps:
            step += 1

            # OpenAI Completion API 호출 (Ollama num_ctx 보장)
            active_tools = None if has_stdout_result else (schemas if schemas else None)
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=active_tools,
                temperature=0.0,
                extra_body={"options": {"num_ctx": config.NUM_CTX}},
            )
            message = response.choices[0].message

            # -------------------------------------------------------------
            # Case 1: OpenAI SDK 표준 tool_calls 응답
            # -------------------------------------------------------------
            if message.tool_calls:
                current_sig = tuple(
                    (c.function.name, c.function.arguments) for c in message.tool_calls
                )
                if current_sig == last_calls_signature:
                    if has_stdout_result:
                        final_md = self._finalize_without_tools(messages)
                        if self.session_logger:
                            self.session_logger.log_assistant_message(final_md)
                        return final_md, messages
                    # 동일 호출 무한루프 가드
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append(message)

                for call in message.tool_calls:
                    fn_name = call.function.name
                    raw_args = call.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    if on_tool_call:
                        on_tool_call(fn_name, args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, args)

                    result = self.registry.dispatch(fn_name, args)
                    if "[Exit Code: 0" in result and "STDOUT:\n(출력 없음)" not in result:
                        has_stdout_result = True

                    if on_tool_result:
                        on_tool_result(fn_name, result)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, result)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": f"{result}\n\n{self._tool_followup_hint(result)}",
                        }
                    )
                continue

            # -------------------------------------------------------------
            # Case 2: 본문 텍스트 내 Fallback 도구 호출 탐색
            # -------------------------------------------------------------
            content = (message.content or "").strip()
            extracted_calls = extract_tool_calls_from_text(content)
            valid_calls = [
                (name, args) for name, args in extracted_calls if self.registry.has_tool(name)
            ]

            if valid_calls:
                current_sig = tuple(
                    (name, json.dumps(args, sort_keys=True)) for name, args in valid_calls
                )
                if current_sig == last_calls_signature:
                    if has_stdout_result:
                        final_md = self._finalize_without_tools(messages)
                        if self.session_logger:
                            self.session_logger.log_assistant_message(final_md)
                        return final_md, messages
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append(
                    {
                        "role": "assistant",
                        "content": f"도구({', '.join(n for n, _ in valid_calls)})를 실행하여 조건에 맞는 항목을 조회합니다.",
                    }
                )
                feedbacks = []

                for fn_name, fn_args in valid_calls:
                    if on_tool_call:
                        on_tool_call(fn_name, fn_args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, fn_args)

                    res = self.registry.dispatch(fn_name, fn_args)
                    if "[Exit Code: 0" in res and "STDOUT:\n(출력 없음)" not in res:
                        has_stdout_result = True

                    if on_tool_result:
                        on_tool_result(fn_name, res)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, res)

                    feedbacks.append(f"[{fn_name} 결과]:\n{res}")

                # Fallback 피드백을 사용자 메시지로 주입
                joined_fb = "\n\n".join(feedbacks)
                feedback_content = f"{joined_fb}\n\n{self._tool_followup_hint(joined_fb)}"
                messages.append({"role": "user", "content": feedback_content})
                continue

            # -------------------------------------------------------------
            # Case 3: 도구 호출이 없는 최종 텍스트 응답
            # -------------------------------------------------------------
            messages.append({"role": "assistant", "content": content})
            if self.session_logger:
                self.session_logger.log_assistant_message(content)
            return content, messages

        max_msg = f"최대 스텝 수({self.max_steps})를 초과하여 실행이 중단되었습니다."
        if self.session_logger:
            self.session_logger.log_assistant_message(max_msg)
        return max_msg, messages

    async def run_async(
        self,
        user_message: str,
        messages_history: list[dict[str, Any]] | None = None,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """비동기 방식으로 에이전트 루프를 실행합니다."""
        schemas = self.registry.get_schemas()
        messages: list[dict[str, Any]] = []

        if messages_history:
            messages = list(messages_history)
        else:
            messages.append({"role": "system", "content": self.get_active_system_prompt()})

        # L2 시맨틱 지식 + TOBE RAG 사전 검색 (Prefetch RAG)
        tobe_rag_ctx = prefetch_tobe_rag(
            user_message,
            enable_vector=isinstance(self._sync_client, _OllamaNativeClient),
        )
        context_knowledge = prefetch_relevant_knowledge(user_message)
        combined_ctx = f"{tobe_rag_ctx}{context_knowledge}"
        effective_message = f"{combined_ctx}{user_message}" if combined_ctx else user_message

        messages.append({"role": "user", "content": effective_message})

        if self.session_logger:
            self.session_logger.log_user_message(user_message)

        step = 0
        last_calls_signature: Any = None

        while step < self.max_steps:
            step += 1

            response = await self._async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=schemas if schemas else None,
                temperature=0.0,
                extra_body={"options": {"num_ctx": config.NUM_CTX}},
            )
            message = response.choices[0].message

            if message.tool_calls:
                current_sig = tuple(
                    (c.function.name, c.function.arguments) for c in message.tool_calls
                )
                if current_sig == last_calls_signature:
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append(message)

                for call in message.tool_calls:
                    fn_name = call.function.name
                    raw_args = call.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    if on_tool_call:
                        on_tool_call(fn_name, args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, args)

                    result = self.registry.dispatch(fn_name, args)

                    if on_tool_result:
                        on_tool_result(fn_name, result)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, result)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": f"{result}\n\n[안내]: 사용자가 조회를 요청한 정보라면 위 도구 결과의 상세 내용(목록/코드/로그 등)을 생략하지 말고 사용자 최종 답변 본문에 마크다운으로 직접 나열하여 보여주세요.",
                        }
                    )
                continue

            content = (message.content or "").strip()
            extracted_calls = extract_tool_calls_from_text(content)
            valid_calls = [
                (name, args) for name, args in extracted_calls if self.registry.has_tool(name)
            ]

            if valid_calls:
                current_sig = tuple(
                    (name, json.dumps(args, sort_keys=True)) for name, args in valid_calls
                )
                if current_sig == last_calls_signature:
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append({"role": "assistant", "content": content})
                feedbacks = []

                for fn_name, fn_args in valid_calls:
                    if on_tool_call:
                        on_tool_call(fn_name, fn_args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, fn_args)

                    res = self.registry.dispatch(fn_name, fn_args)

                    if on_tool_result:
                        on_tool_result(fn_name, res)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, res)

                    feedbacks.append(f"[{fn_name} 결과]:\n{res}")

                feedback_content = (
                    "\n\n".join(feedbacks)
                    + "\n\n[안내]: 사용자가 조회를 요청한 정보라면 위 결과의 상세 내용을 생략하지 말고 최종 답변 본문에 직접 마크다운으로 나열하여 보여주세요."
                )
                messages.append({"role": "user", "content": feedback_content})
                continue

            messages.append({"role": "assistant", "content": content})
            if self.session_logger:
                self.session_logger.log_assistant_message(content)
            return content, messages

        max_msg = f"최대 스텝 수({self.max_steps})를 초과하여 실행이 중단되었습니다."
        if self.session_logger:
            self.session_logger.log_assistant_message(max_msg)
        return max_msg, messages
