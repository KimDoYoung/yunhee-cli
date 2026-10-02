"""AS-IS DB 스키마(DBML markdown)를 도메인/함수별 소형 마크다운으로 분할 색인하는 도구."""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from yunhee.tools.base import ToolResult

BACKUP_DOMAIN = "_backup"
ETC_DOMAIN = "_etc"

TABLE_RE = re.compile(r'^Table "public"\."([^"]+)" \{$', re.MULTILINE)
NOTE_RE = re.compile(r"^  Note: '((?:[^'\\]|\\.)*)'", re.MULTILINE)
COLUMN_RE = re.compile(r'^  "[^"]+" ', re.MULTILINE)
ROUTINE_HEAD_RE = re.compile(r"^### public\.([A-Za-z0-9_]+)\((.*)\)\s*$")
# pgcrypto encrypt()/decrypt()의 키 문자열을 가린다. 비밀번호 복호화 키가 문서에 남지 않게 한다
# 키는 암호 방식 인자('aes', 'bf', 'aes-cbc/pad:pkcs' 등) 바로 앞의 문자열 리터럴이다: encrypt(data, '키', 'aes')
CRYPTO_KEY_RE = re.compile(r"'[^']*'(\s*,\s*'(?:aes|bf)[^']*'\s*\))", re.IGNORECASE)
MASKED_KEY = "'***'"


def split_sections(text: str) -> dict[str, str]:
    """'## 제목' 단위로 나눈다. 첫 섹션 앞부분(머리말)은 '_header' 키로 둔다."""
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    sections = {"_header": parts[0]}
    for part in parts[1:]:
        title, _, body = part.partition("\n")
        sections[title.strip()] = body
    return sections


def table_domain(name: str) -> str:
    if re.search(r"bak|_back$|_backup$", name):
        return BACKUP_DOMAIN
    m = re.match(r"([a-z]+)\d", name)
    return m.group(1) if m else ETC_DOMAIN


def parse_tables(dbml_section: str) -> list[tuple[str, str]]:
    """DBML 섹션에서 Table 블록을 (이름, 블록 원문) 목록으로 뽑는다. 블록은 첫 열의 '}'로 끝난다."""
    tables = []
    for m in TABLE_RE.finditer(dbml_section):
        end = dbml_section.find("\n}\n", m.start())
        if end == -1:
            end = len(dbml_section)
        else:
            end += 2
        tables.append((m.group(1), dbml_section[m.start():end]))
    return tables


def table_summary(block: str) -> tuple[str, int]:
    note = NOTE_RE.search(block)
    note_str = note.group(1).replace("\\'", "'") if note else ""
    return note_str, len(COLUMN_RE.findall(block))


def parse_subsections(section: str) -> list[tuple[str, str]]:
    """'### 이름' 단위 블록 목록 (제목 줄, 본문)"""
    blocks = []
    for part in re.split(r"^### ", section, flags=re.MULTILINE)[1:]:
        head, _, body = part.partition("\n")
        blocks.append((head.strip(), body.strip("\n")))
    return blocks


def mask_secrets(body: str) -> str:
    return CRYPTO_KEY_RE.sub(lambda m: MASKED_KEY + m.group(1), body)


def routine_info(kind: str, head: str, body: str) -> dict[str, Any]:
    body = mask_secrets(body)
    m = ROUTINE_HEAD_RE.match("### " + head)
    name, args = (m.group(1), m.group(2)) if m else (head, "")
    returns = re.search(r"^\s*RETURNS (.+)$", body, re.MULTILINE)
    return {
        "kind": kind,
        "name": name,
        "args": args,
        "returns": returns.group(1).strip() if returns else ("-" if kind == "PROCEDURE" else "?"),
        "lines": body.count("\n") + 1,
        "head": head,
        "body": body,
    }


def md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def clean_generated(out: Path) -> tuple[bool, str]:
    if not out.is_dir():
        return True, ""
    readme = out / "README.md"
    existing_md = list(out.glob("*.md")) + list(out.glob("*/*.md"))
    if existing_md and not readme.is_file():
        return False, f"안전 가드: '{out}' 폴더에 기존 마크다운 파일이 있으나 README.md가 없습니다. 엉뚱한 폴더 삭제 방지를 위해 중단합니다."
    if readme.is_file():
        content = readme.read_text(encoding="utf-8", errors="replace")
        if "index-db" not in content and "dbml-index.py" not in content and "AS-IS DB 스키마 색인" not in content:
            return False, f"안전 가드: '{out}/README.md'에 AS-IS DB 색인 생성기 표식이 없습니다. 엉뚱한 폴더 삭제 방지를 위해 중단합니다."

    for sub in ("tables", "functions"):
        d = out / sub
        if d.is_dir():
            for f in d.glob("*.md"):
                f.unlink()
    for f in ("README.md", "views.md", "triggers.md"):
        (out / f).unlink(missing_ok=True)
    return True, ""


def write_tables(out: Path, tables: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    by_domain: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name, block in tables:
        by_domain[table_domain(name)].append((name, block))

    (out / "tables").mkdir(parents=True, exist_ok=True)
    for domain, items in sorted(by_domain.items()):
        items.sort()
        lines = [
            f"# 테이블: {domain}",
            "",
            f"{len(items)}개. 컬럼 주석은 DBML의 `note`에 있다. FK(ref)는 DB에 정의돼 있지 않다.",
            "",
            "| 테이블 | 설명 | 컬럼 수 |",
            "|:---|:---|---:|",
        ]
        for name, block in items:
            note, cols = table_summary(block)
            lines.append(f"| `{name}` | {md_cell(note)} | {cols} |")
        lines += ["", "## DBML", "", "```dbml"]
        lines += [block.rstrip("\n") + "\n" for _, block in items]
        lines.append("```")
        (out / "tables" / f"{domain}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return by_domain


def write_views(out: Path, views: list[tuple[str, str]]) -> None:
    lines = ["# 뷰", "", f"{len(views)}개.", ""]
    for head, body in views:
        lines += [f"## {head}", "", mask_secrets(body), ""]
    (out / "views.md").write_text("\n".join(lines), encoding="utf-8")


def write_routines(out: Path, routines: list[dict[str, Any]], trigger_fn_count: int) -> None:
    fdir = out / "functions"
    fdir.mkdir(parents=True, exist_ok=True)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in routines:
        by_name[r["name"]].append(r)

    for name, items in by_name.items():
        lines = [f"# {name}", ""]
        for r in items:
            lines += [
                f"## {r['kind']} {r['head']}",
                "",
                f"- 반환: `{r['returns']}`",
                f"- 줄 수: {r['lines']}",
                "",
                r["body"],
                "",
            ]
        (fdir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")

    lines = [
        "# 함수·프로시저 색인",
        "",
        (
            f"함수 {sum(1 for r in routines if r['kind'] == 'FUNCTION')}개, 프로시저 {sum(1 for r in routines if r['kind'] == 'PROCEDURE')}개. "
            f"트리거 함수(`RETURNS trigger`, 주로 `*_backup()`) {trigger_fn_count}개는 제외했다 (`../triggers.md` 참고)."
        ),
        "",
        "본문은 `functions/{이름}.md`. 오버로드는 같은 파일에 있다.",
        "",
        "| 이름 | 종류 | 인자 | 반환 | 줄 수 |",
        "|:---|:---|:---|:---|---:|",
    ]
    for r in sorted(routines, key=lambda x: (x["name"], x["args"])):
        lines.append(
            f"| [`{r['name']}`]({r['name']}.md) | {r['kind']} | {md_cell(r['args'])} | {md_cell(r['returns'])} | {r['lines']} |"
        )
    (fdir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_triggers(out: Path, triggers_section: str) -> None:
    body = triggers_section.strip("\n")
    count = len(re.findall(r"^CREATE TRIGGER", body, re.MULTILINE))
    text = "\n".join([
        "# 트리거",
        "",
        f"{count}개. 대부분 변경 이력을 `*_back`/`*bak*` 테이블에 남기는 `*_backup()` 함수 호출이다.",
        "",
        body,
        "",
    ])
    (out / "triggers.md").write_text(text, encoding="utf-8")


def write_readme(
    out: Path,
    source_label: str,
    header: str,
    by_domain: dict[str, list[tuple[str, str]]],
    views: list[tuple[str, str]],
    routines: list[dict[str, Any]],
    sequences: str,
) -> None:
    meta = [line for line in header.splitlines() if line.startswith("- ")]
    domains = sorted(by_domain.items(), key=lambda kv: (kv[0].startswith("_"), kv[0]))
    lines = [
        "# AS-IS DB 스키마 색인",
        "",
        f"`yunhee index-db`가 `{source_label}`에서 생성했다. 직접 수정하지 말고 명령어를 다시 실행한다.",
        "",
        "## 원본",
        "",
        *meta,
        "",
        "## 읽는 방법",
        "",
        "- 테이블: `tables/{도메인}.md` — 도메인은 테이블명 접두어 (`emp01_person` → `emp`). 맨 위 요약 표로 먼저 찾는다.",
        "- 함수: `functions/README.md` 색인에서 찾고 `functions/{이름}.md`만 읽는다.",
        "- 뷰: `views.md`, 트리거: `triggers.md`",
        "- FK(ref)는 DB에 없다. 테이블 간 관계는 AS-IS 매퍼 SQL에서 확인한다.",
        "",
        "## 도메인별 테이블",
        "",
        "| 도메인 | 테이블 수 | 파일 |",
        "|:---|---:|:---|",
    ]
    for domain, items in domains:
        lines.append(f"| `{domain}` | {len(items)} | [tables/{domain}.md](tables/{domain}.md) |")
    lines += [
        "",
        "## 그 밖의 객체",
        "",
        f"- 뷰 {len(views)}개: [views.md](views.md) ({', '.join('`' + h.removeprefix('public.') + '`' for h, _ in views)})",
        f"- 함수·프로시저 {len(routines)}개: [functions/README.md](functions/README.md)",
        "- 트리거: [triggers.md](triggers.md)",
        "",
        "## 시퀀스",
        "",
        sequences.strip("\n"),
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def index_dbml(source_path: Path, target_dir: Path) -> ToolResult:
    """DBML 마크다운 파일을 도메인별 소형 파일로 분할하여 target_dir에 생성한다."""
    if not source_path.is_file():
        return ToolResult(ok=False, error=f"DBML 파일이 없습니다: {source_path}")

    text = source_path.read_text(encoding="utf-8")
    sections = split_sections(text)
    for required in ("DBML", "Functions"):
        if required not in sections:
            return ToolResult(
                ok=False,
                error=f"'## {required}' 섹션이 없습니다. DBML markdown 형식이 맞는지 확인하세요.",
            )

    target_dir.mkdir(parents=True, exist_ok=True)
    clean_ok, clean_err = clean_generated(target_dir)
    if not clean_ok:
        return ToolResult(ok=False, error=clean_err)

    tables = parse_tables(sections["DBML"])
    views = parse_subsections(sections.get("Views", ""))
    functions = [routine_info("FUNCTION", h, b) for h, b in parse_subsections(sections["Functions"])]
    procedures = [routine_info("PROCEDURE", h, b) for h, b in parse_subsections(sections.get("Procedures", ""))]
    trigger_fns = [
        r for r in functions if r["returns"] == "trigger" or r["returns"].lower().startswith("trigger")
    ]
    routines = [r for r in functions if r not in trigger_fns] + procedures

    by_domain = write_tables(target_dir, tables)
    write_views(target_dir, views)
    write_routines(target_dir, routines, len(trigger_fns))
    write_triggers(target_dir, sections.get("Triggers", ""))

    source_label = str(source_path)
    write_readme(
        target_dir,
        source_label,
        sections["_header"],
        by_domain,
        views,
        routines,
        sections.get("Sequences", ""),
    )

    return ToolResult(
        ok=True,
        data={
            "target_dir": str(target_dir),
            "tables_count": len(tables),
            "domains_count": len(by_domain),
            "views_count": len(views),
            "routines_count": len(routines),
            "trigger_fns_count": len(trigger_fns),
        },
    )
