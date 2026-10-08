"""TOBE 화면 파일의 패턴 골격 요약 도구."""

import re
from pathlib import Path
from typing import Any

NAME = "tobe"
DESCRIPTION = "TOBE 소스 파일(TSX/TS/Java)의 패턴 골격 및 주요 호출 요약"
TARGET_HELP = "<TOBE 파일·폴더…>"
FORMATS = ("md",)
EXAMPLES = [
    "yunhee analysis tobe AssetERP_1/frontend/src/pages/sys/Sys01_Tab_Company.tsx",
    "yunhee analysis tobe AssetERP_1/frontend/src/hooks/useGridCrud.ts",
    "yunhee analysis tobe backend/src/main/java/.../EmpTransInfoService.java",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """대상 파일 또는 디렉터리를 분석한다."""
    path = Path(target)
    if not path.exists():
        raise ValueError(f"파일 또는 디렉터리를 찾을 수 없습니다: {target}")

    files: list[Path] = []
    if path.is_file():
        files = [path]
    else:
        files = sorted(f for f in path.rglob("*") if f.is_file() and f.suffix in (".tsx", ".ts", ".java"))

    file_summaries = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if f.suffix == ".tsx":
            file_summaries.append(_summarize_tsx(f, text))
        elif f.suffix == ".ts":
            file_summaries.append(_summarize_ts(f, text))
        elif f.suffix == ".java":
            file_summaries.append(_summarize_java(f, text))

    return {"files": file_summaries}


def _parse_jsx_tags(jsx: str) -> list[tuple[str, bool, bool, str]]:
    """JSX 태그(여는 태그, 닫는 태그, 자체 닫힘 태그, Fragment)를 파싱한다.

    반환: [(tag_name, is_closing, is_self_closing, attrs)]
    """
    i = 0
    n = len(jsx)
    tags = []
    while i < n:
        if jsx[i : i + 3] == "</>":
            tags.append(("Fragment", True, False, ""))
            i += 3
            continue
        if jsx[i : i + 2] == "<>":
            tags.append(("Fragment", False, False, ""))
            i += 2
            continue
        if jsx[i] == "<":
            is_closing = False
            if i + 1 < n and jsx[i + 1] == "/":
                is_closing = True
                i += 2
            else:
                i += 1
            m = re.match(r"([A-Za-z0-9_.]+)", jsx[i:])
            if not m:
                i += 1
                continue
            tag_name = m.group(1)
            i += len(tag_name)
            # Generic support like <SingleGrid<Company>
            if not is_closing and i < n and jsx[i] == "<":
                gen_end = jsx.find(">", i)
                if gen_end != -1:
                    i = gen_end + 1
            attr_start = i
            brace_depth = 0
            in_str = None
            while i < n:
                ch = jsx[i]
                if in_str:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == in_str:
                        in_str = None
                else:
                    if ch in ('"', "'", "`"):
                        in_str = ch
                    elif ch == "{":
                        brace_depth += 1
                    elif ch == "}":
                        brace_depth = max(0, brace_depth - 1)
                    elif brace_depth == 0:
                        if ch == "/" and i + 1 < n and jsx[i + 1] == ">":
                            attrs = jsx[attr_start:i].strip()
                            tags.append((tag_name, is_closing, True, attrs))
                            i += 2
                            break
                        if ch == ">":
                            attrs = jsx[attr_start:i].strip()
                            tags.append((tag_name, is_closing, False, attrs))
                            i += 1
                            break
                i += 1
            continue
        i += 1
    return tags


def _summarize_tsx(path: Path, text: str) -> dict[str, Any]:
    # 1. 첫 주석
    first_comment = ""
    m_c = re.match(r"^\s*/\*+(.*?)\*/", text, re.DOTALL)
    if m_c:
        first_comment = "\n".join(l.strip(" *") for l in m_c.group(1).splitlines() if l.strip(" *"))

    # 2. export 컴포넌트
    exports = re.findall(r"export\s+const\s+(\w+)(?::\s*React\.FC(?:<([^>]+)>)?)?", text)

    # 3. useState
    states = re.findall(r"const\s*\[(\w+),\s*set\w+\]\s*=\s*useState(?:<[^>]*>)?\(([^)]*)\)", text)

    # 4. useGridCrud 옵션 키
    hooks = []
    m_crud = re.search(r"useGridCrud\s*\(\s*\{([^}]+)\}", text, re.DOTALL)
    if m_crud:
        crud_keys = [k.strip().split(":")[0].strip() for k in m_crud.group(1).split(",") if k.strip()]
        hooks.append(f"useGridCrud({{{', '.join(crud_keys)}}})")

    # 5. API 호출
    api_calls = sorted(set(re.findall(r"\b(\w+Api\.\w+)\s*\(", text)))

    # 6. // [E...] 또는 {/* [E...] */} 주석
    events = re.findall(r"(?:/{/\*\s*|//\s*)(\[E\d+[^\]\n]*\][^\n]*?)(?:\s*\*/|\n|$)", text)

    # 7. 렌더 트리 뼈대
    tree_lines = []
    # return (...) 구문 찾기
    m_ret = re.search(r"return\s*\(\s*(<[\s\S]+?)\n\s*\);", text)
    if m_ret:
        jsx_block = m_ret.group(1)
        tags = _parse_jsx_tags(jsx_block)
        depth = 0
        for tag, closing, self_closing, attrs in tags:
            # 소문자 HTML 태그 중 레이아웃 컨테이너(div 등)는 생략
            if tag in ("div", "span", "p", "b", "strong", "i"):
                continue

            if closing:
                depth = max(0, depth - 1)
            else:
                indent = "  " * min(depth, 5)
                btn_info = ""
                if tag == "Button":
                    btn_m = re.search(r'type=["\'](\w+)["\']', attrs)
                    if btn_m:
                        btn_info = f" type={btn_m.group(1)}"
                tree_lines.append(f"{indent}- `<{tag}>{btn_info}`")
                if not self_closing:
                    depth += 1

    return {
        "file": str(path),
        "kind": "tsx",
        "comment": first_comment,
        "exports": exports,
        "states": states,
        "hooks": hooks,
        "apis": api_calls,
        "events": events,
        "tree": tree_lines,
    }


def _summarize_ts(path: Path, text: str) -> dict[str, Any]:
    # export interface (제네릭 포함)
    interfaces = []
    for m in re.finditer(r"export\s+interface\s+(\w+)(?:<[^>]+>)?\s*\{([^}]+)\}", text):
        name = m.group(1)
        raw_body = m.group(2)
        clean_body = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", raw_body)
        fields = [f.strip().split(":")[0].strip().rstrip("?") for f in clean_body.split(";") if f.strip() and ":" in f]
        interfaces.append(f"interface {name}: {', '.join(fields)}")

    functions = []
    for m in re.finditer(r"export\s+(?:const|function)\s+(\w+)", text):
        functions.append(m.group(1))

    # 훅 반환값 추출
    return_keys = []
    m_ret = re.search(r"return\s*\{([^}]+)\};", text)
    if m_ret:
        raw_keys = m_ret.group(1)
        return_keys = [k.strip().split(":")[0].strip() for k in raw_keys.split(",") if k.strip()]

    return {
        "file": str(path),
        "kind": "ts",
        "interfaces": interfaces,
        "functions": functions,
        "return_keys": return_keys,
    }


def _summarize_java(path: Path, text: str) -> dict[str, Any]:
    cls_m = re.search(r"\b(?:class|interface|record)\s+(\w+)", text)
    cls_name = cls_m.group(1) if cls_m else path.stem

    clean_text = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", text)

    methods = []
    method_pat = re.compile(
        r"(?:(?:public|protected|private|static|final|synchronized)\s+)+[\w<>\[\], ?]+\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w.,\s]+)?\s*\{"
    )

    for m in method_pat.finditer(clean_text):
        m_name = m.group(1)
        open_brace = m.end() - 1
        depth = 1
        k = open_brace + 1
        n = len(clean_text)
        end_pos = open_brace

        while k < n:
            c = clean_text[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end_pos = k
                    break
            k += 1

        body = clean_text[open_brace + 1 : end_pos]

        calls = []
        for cm in re.finditer(r"(?:(\w+)\.)?(\w+)\s*\(", body):
            recv = cm.group(1) or ""
            c_name = cm.group(2)
            if c_name[0].isupper():
                continue
            if c_name in ("if", "for", "while", "switch", "catch", "new", "return", "throw", "null", "super", "this"):
                continue
            if recv in ("req", "user", "LocalDate", "String", "Math", "System"):
                continue
            if c_name.startswith(("get", "set", "is")) and "mapper" not in recv.lower():
                continue
            if c_name.startswith("of") or c_name in (
                "trim", "isBlank", "isEmpty", "toString", "now", "equals",
                "builder", "build", "format", "empNo", "korNm", "hireDate",
                "hireCd", "emailAddr", "officeTelNo", "officeDetail", "mobileTelNo",
                "note", "expiryDate", "orgCodeId", "titleCd", "posCd", "kindCd", "map", "filter",
            ):
                continue
            calls.append(c_name)

        dedup_calls = []
        for c in calls:
            if not dedup_calls or dedup_calls[-1] != c:
                dedup_calls.append(c)

        exceptions = []
        for em in re.finditer(r"throw\s+new\s+BusinessException\s*\(([^;]+)\);", body):
            arg_str = em.group(1).strip()
            msg_m = re.search(r'["\']([^"\']+)["\']', arg_str)
            err_m = re.search(r"ErrorCode\.(\w+)", arg_str)
            parts = []
            if err_m:
                parts.append(err_m.group(1))
            if msg_m:
                parts.append(f'"{msg_m.group(1)}"')
            elif not err_m:
                parts.append(arg_str)
            exceptions.append(" ".join(parts))

        methods.append({
            "name": m_name,
            "calls": " → ".join(dedup_calls),
            "exceptions": exceptions,
        })

    return {
        "file": str(path),
        "kind": "java",
        "class": cls_name,
        "methods": methods,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    files = obj["files"]
    if not files:
        return "분석된 파일이 없습니다."

    out = []
    for f in files:
        out.append(f"### `{f['file']}`")
        if f["kind"] == "tsx":
            if f["comment"]:
                out.append(f"> {f['comment'].replace(chr(10), ' ')}")
            if f["hooks"]:
                out.append(f"- **훅**: {', '.join(f['hooks'])}")
            if f["apis"]:
                out.append(f"- **API**: {', '.join(f['apis'])}")
            if f["events"]:
                out.append(f"- **이벤트 주석**: {', '.join(f['events'][:8])}")
            if f["tree"]:
                out.append("- **렌더 트리 뼈대**:\n" + "\n".join(f['tree']))
        elif f["kind"] == "ts":
            if f["interfaces"]:
                out.append("- **인터페이스**:\n" + "\n".join(f"  - {i}" for i in f["interfaces"]))
            if f["functions"]:
                out.append(f"- **함수**: {', '.join(f['functions'])}")
            if f.get("return_keys"):
                out.append(f"- **반환값**: {', '.join(f['return_keys'])}")
        elif f["kind"] == "java":
            out.append(f"- **클래스**: `{f['class']}`")
            for m in f["methods"]:
                exc_str = f" (예외: {', '.join(m['exceptions'])})" if m["exceptions"] else ""
                out.append(f"  - `{m['name']}`: {m['calls']}{exc_str}")
        out.append("")

    return "\n".join(out)
