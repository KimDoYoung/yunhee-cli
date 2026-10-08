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

    # 6. // [E...] 주석
    events = re.findall(r"//\s*(\[E\d+[^\]\n]*\][^\n]*)", text)

    # 7. 렌더 트리 뼈대 (깊이 4)
    tree_lines = []
    m_ret = re.search(r"return\s*\(\s*(<[\s\S]+?>)\s*\);", text)
    if m_ret:
        jsx_block = m_ret.group(1)
        # 태그만 추출
        tags = re.findall(r"<(/?)(\w+)([^>]*)>", jsx_block)
        depth = 0
        for closing, tag, attrs in tags:
            if tag in ("div", "span", "p"):
                continue
            if closing:
                depth = max(0, depth - 1)
            else:
                if depth < 4:
                    btn_label = ""
                    if tag == "Button":
                        btn_label = f" ({attrs.strip()[:20]})"
                    tree_lines.append(f"{'  ' * depth}- `<{tag}>{btn_label}`")
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
        "tree": tree_lines[:15],
    }


def _summarize_ts(path: Path, text: str) -> dict[str, Any]:
    # export 함수 / 인터페이스 필드
    interfaces = []
    for m in re.finditer(r"export\s+interface\s+(\w+)\s*\{([^}]+)\}", text):
        fields = [f.strip().split(":")[0].strip() for f in m.group(2).split(";") if f.strip()]
        interfaces.append(f"interface {m.group(1)}: {', '.join(fields[:10])}")

    functions = []
    for m in re.finditer(r"export\s+(?:const|function)\s+(\w+)", text):
        functions.append(m.group(1))

    return {
        "file": str(path),
        "kind": "ts",
        "interfaces": interfaces,
        "functions": functions,
    }


def _summarize_java(path: Path, text: str) -> dict[str, Any]:
    # 클래스명
    cls_m = re.search(r"\b(?:class|interface|record)\s+(\w+)", text)
    cls_name = cls_m.group(1) if cls_m else path.stem

    # 서비스 메서드 본문 호출 순서 및 BusinessException
    methods = []
    # public ... method(...) {
    for m in re.finditer(r"public\s+[\w<>\[\], ?]+\s+(\w+)\s*\([^)]*\)\s*\{([^}]+)\}", text):
        m_name = m.group(1)
        body = m.group(2)
        # 호출 순서 식별
        calls = re.findall(r"\b([a-zA-Z0-9_]+)\s*\(", body)
        call_seq = [c for c in calls if c not in ("if", "for", "return", "new", "get", "set", "builder")][:8]
        # BusinessException
        exceptions = re.findall(r"throw\s+new\s+BusinessException\s*\(\s*([^)]+)\)", body)
        methods.append({
            "name": m_name,
            "calls": " → ".join(call_seq),
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
        elif f["kind"] == "java":
            out.append(f"- **클래스**: `{f['class']}`")
            for m in f["methods"][:6]:
                exc_str = f" (예외: {', '.join(m['exceptions'])})" if m["exceptions"] else ""
                out.append(f"  - `{m['name']}`: {m['calls']}{exc_str}")
        out.append("")

    return "\n".join(out)
