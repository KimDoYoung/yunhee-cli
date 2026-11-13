"""DB 함수(스토어드 함수) 색인 및 본문 분석 모듈 (`analysis function`).

docs/as-is/db/functions/<이름>.md 색인 파일로부터
인자, 반환, 줄 수, CUD 테이블, 호출 함수, RAISE/RETURN, 본문 코드를 추출한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yunhee import config

NAME = "function"
DESCRIPTION = "DB 함수(PostgreSQL Function/Procedure) 분석 및 본문 조회"
TARGET_HELP = "<함수명> (예: f_create_depositBook_run, f_create_seq)"
FORMATS = ("md", "code")
EXAMPLES = [
    "yunhee analysis function f_create_depositBook_run",
    "yunhee analysis function f_create_journalExpense -o code --lines 1-50",
    "yunhee analysis function f_create_seq --grep EXCEPTION",
]


def _find_function_doc(name: str, root_dir: Path | None = None) -> Path | None:
    """docs/as-is/db/functions/<name>.md 파일을 검색한다."""
    work = root_dir or config.WORK_DIR
    clean_name = name.removesuffix(".md").removesuffix(".sql")
    candidates = [
        work / "docs" / "as-is" / "db" / "functions" / f"{clean_name}.md",
        work / "docs" / "as-is" / "db" / "functions" / f"{clean_name.lower()}.md",
        config.YUNHEE_DIR / "docs" / "as-is" / "db" / "functions" / f"{clean_name}.md",
        config.YUNHEE_DIR / "docs" / "as-is" / "db" / "functions" / f"{clean_name.lower()}.md",
    ]
    for c in candidates:
        if c.is_file():
            return c

    for base_dir in [work / "docs" / "as-is" / "db" / "functions", config.YUNHEE_DIR / "docs" / "as-is" / "db" / "functions"]:
        if base_dir.is_dir():
            for p in base_dir.glob("*.md"):
                if p.stem.lower() == clean_name.lower():
                    return p
    return None


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """DB 함수 색인 문서를 찾아 파싱한다."""
    target_clean = target.strip()
    src_root = opts.get("src")
    doc_path = _find_function_doc(target_clean, src_root)
    if not doc_path:
        raise ValueError(f"DB 함수 문서를 찾을 수 없습니다: '{target_clean}' (docs/as-is/db/functions/{target_clean}.md 없음)")

    content = doc_path.read_text(encoding="utf-8", errors="replace")

    code_match = re.search(r"```(?:sql|plpgsql)?\s*\n(.*?)\n```", content, re.DOTALL | re.IGNORECASE)
    raw_code = code_match.group(1) if code_match else content

    code_lines = raw_code.splitlines()
    total_lines = len(code_lines)

    read_tables: set[str] = set()
    write_tables: set[str] = set()
    called_funcs: set[str] = set()
    raises: list[str] = []
    returns: list[str] = []
    has_silent_exception = False

    for line in code_lines:
        line_clean = line.strip()
        for m in re.finditer(r"\bFROM\s+([a-zA-Z0-9_]+)", line, re.IGNORECASE):
            tbl = m.group(1).lower()
            if not tbl.startswith(("f_", "pg_")):
                read_tables.add(tbl)
        for m in re.finditer(r"\bJOIN\s+([a-zA-Z0-9_]+)", line, re.IGNORECASE):
            tbl = m.group(1).lower()
            if not tbl.startswith(("f_", "pg_")):
                read_tables.add(tbl)

        for m in re.finditer(r"\bINSERT\s+INTO\s+([a-zA-Z0-9_]+)", line, re.IGNORECASE):
            write_tables.add(m.group(1).lower())
        for m in re.finditer(r"\bUPDATE\s+([a-zA-Z0-9_]+)", line, re.IGNORECASE):
            write_tables.add(m.group(1).lower())
        for m in re.finditer(r"\bDELETE\s+FROM\s+([a-zA-Z0-9_]+)", line, re.IGNORECASE):
            write_tables.add(m.group(1).lower())

        for m in re.finditer(r"\b(f_[a-zA-Z0-9_]+|nextval|setval)\s*\(", line, re.IGNORECASE):
            fn = m.group(1)
            if fn.lower() != target_clean.lower():
                called_funcs.add(fn)

        if re.search(r"\bRAISE\s+EXCEPTION\b", line, re.IGNORECASE):
            raises.append(line_clean)
        elif re.search(r"\bRETURN\b", line, re.IGNORECASE) and len(returns) < 5:
            returns.append(line_clean)

        if "when others then return null" in line_clean.lower() or "exception when others then" in line_clean.lower():
            has_silent_exception = True

    sig_match = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([^(]+)\s*\((.*?)\)\s+RETURNS\s+([a-zA-Z0-9_]+)", raw_code, re.DOTALL | re.IGNORECASE)
    args_str = "(정보 없음)"
    return_type = "(정보 없음)"
    if sig_match:
        args_str = " ".join(sig_match.group(2).split()) or "(없음)"
        return_type = sig_match.group(3).strip()

    return {
        "target": target_clean,
        "doc_path": str(doc_path),
        "total_lines": total_lines,
        "args_str": args_str,
        "return_type": return_type,
        "code_lines": code_lines,
        "read_tables": sorted(read_tables),
        "write_tables": sorted(write_tables),
        "called_funcs": sorted(called_funcs),
        "raises": raises,
        "returns": returns,
        "has_silent_exception": has_silent_exception,
    }


def render(data: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """분석 결과를 지정 형식으로 렌더링한다."""
    opts = opts or {}
    target = data["target"]
    code_lines = data["code_lines"]
    total_lines = data["total_lines"]

    if fmt == "code":
        start_idx = 1
        end_idx = total_lines

        lines_arg = opts.get("lines")
        if lines_arg:
            parts = str(lines_arg).split("-", 1)
            try:
                start_idx = max(1, int(parts[0]))
                if len(parts) > 1 and parts[1].strip():
                    end_idx = min(total_lines, int(parts[1]))
            except ValueError:
                pass

        numbered_lines: list[tuple[int, str]] = []
        for i, l in enumerate(code_lines, start=1):
            if start_idx <= i <= end_idx:
                numbered_lines.append((i, l))

        grep_pat = opts.get("grep")
        if grep_pat:
            pat = re.compile(grep_pat, re.IGNORECASE)
            matched_indices = {i for i, l in numbered_lines if pat.search(l)}
            if not matched_indices:
                return f"검색어 '{grep_pat}'에 일치하는 줄이 없습니다."

            context_lines = opts.get("context_lines", 2)
            show_indices: set[int] = set()
            for mi in matched_indices:
                for ctx in range(mi - context_lines, mi + context_lines + 1):
                    show_indices.add(ctx)

            numbered_lines = [(i, l) for i, l in numbered_lines if i in show_indices]

        out_lines = [f"{i:4d} | {l}" for i, l in numbered_lines]
        return f"### DB 함수 코드: {target} (총 {total_lines}줄)\n" + "\n".join(out_lines)

    # 기본 md 모드
    md_lines: list[str] = [
        f"### DB 함수 분석: `{target}`",
        f"- **색인 파일**: `{data['doc_path']}`",
        f"- **전체 줄 수**: {total_lines}줄",
        f"- **인자**: `{data['args_str']}`",
        f"- **반환형**: `{data['return_type']}`",
    ]

    if data.get("has_silent_exception"):
        md_lines.append("- **오류 처리**: ⚠ `EXCEPTION WHEN OTHERS THEN RETURN NULL` (오류 삼킴 감지됨 — 읽기 전용 실행 시 NULL 반환 주의)")

    md_lines.append("\n#### 관련 객체")
    md_lines.append(f"- **쓰는 테이블(CUD)**: {', '.join(f'`{t}`' for t in data['write_tables']) if data['write_tables'] else '(없음)'}")
    md_lines.append(f"- **읽는 테이블(R)**: {', '.join(f'`{t}`' for t in data['read_tables']) if data['read_tables'] else '(없음)'}")
    md_lines.append(f"- **호출 함수**: {', '.join(f'`{f}`' for f in data['called_funcs']) if data['called_funcs'] else '(없음)'}")

    if data.get("raises"):
        md_lines.append("\n#### 예외 발생 (RAISE EXCEPTION)")
        for r in data["raises"][:5]:
            md_lines.append(f"- `{r}`")

    if data.get("returns"):
        md_lines.append("\n#### 주요 반환 (RETURN)")
        for ret in data["returns"][:5]:
            md_lines.append(f"- `{ret}`")

    md_lines.append(f"\n💡 전체 본문 보기: `yunhee analysis function {target} -o code`")
    return "\n".join(md_lines)
