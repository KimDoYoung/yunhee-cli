"""trace-code: 공통 코드 그룹의 코드값·명칭과 사용처.

코드값은 DB(`sys08_code_kind` 종류, `sys09_code` 값)에서 읽기 전용으로 구한다. 사용처는 ASIS·TOBE 소스에서 코드 그룹 이름이
따옴표 문자열로 적힌 곳을 찾는다 (mapper의 SQL 리터럴, 콤보·조회 코드, 상수 비교). DB를 쓸 수 없으면 값은 건너뛰고 사용처만 낸다.
"""

from __future__ import annotations

import re
from pathlib import Path

from yunhee.tools.analysis.common import AmbiguousTargetError
from yunhee.tools.trace import db
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    TraceContext,
    wants_asis,
    wants_tobe,
)
from yunhee.tools.trace.tobe import find_layout

MAX_CODES = 60
MAX_HITS = 15
SKIP_DIRS = {"target", "build", "bin", "node_modules", ".git", "dist", "out"}
SOURCE_SUFFIXES = {".java", ".xml", ".ts", ".tsx"}
_GROUP = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,60}")


def _kinds(group: str) -> list[tuple]:
    exact = db.fetch(
        "SELECT sys08_code_kind_id, sys08_kind_cd, sys08_kind_nm FROM sys08_code_kind WHERE lower(sys08_kind_cd) = lower(%s)", (group,)
    )
    if exact:
        return exact
    like = f"%{group}%"
    return db.fetch(
        "SELECT sys08_code_kind_id, sys08_kind_cd, sys08_kind_nm FROM sys08_code_kind WHERE sys08_kind_cd ILIKE %s OR sys08_kind_nm ILIKE %s ORDER BY sys08_kind_cd",
        (like, like),
    )


def _values(kind_id: object) -> list[tuple]:
    return db.fetch(
        "SELECT sys09_code, sys09_name, count(DISTINCT sys09_company_id), bool_or(coalesce(sys09_close_yn, 'false') = 'true') "
        "FROM sys09_code WHERE sys09_code_kind_id = %s GROUP BY sys09_code, sys09_name ORDER BY sys09_code, sys09_name",
        (kind_id,),
    )


def _source_files(root: Path):
    for p in root.rglob("*"):
        if p.suffix in SOURCE_SUFFIXES and p.is_file() and not (SKIP_DIRS & set(p.relative_to(root).parts)):
            yield p


def _without_comments(text: str, suffix: str) -> str:
    """주석을 공백으로 지운다 (줄 수 보존). 주석 처리된 코드의 참조는 사용처가 아니다."""
    from yunhee.tools.trace.branch import _blank_comments

    if suffix == ".xml":
        return re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    return _blank_comments(text)


def _kind_of(line: str, suffix: str) -> str:
    if suffix == ".xml":
        return "SQL 리터럴(mapper)"
    if re.search(r"Combo|combo|Select\b|options", line):
        return "콤보·선택 목록"
    if re.search(r"==|!=|equals|===", line):
        return "상수 비교"
    return "그 밖의 참조"


def find_usages(group: str, roots: dict[str, Path]) -> dict[str, dict[str, list[str]]]:
    """roots: {표시 이름: 소스 루트}. 반환: {표시 이름: {사용 종류: ['파일:줄 코드', …]}}"""
    rx = re.compile(rf"""["']{re.escape(group)}["']""")
    out: dict[str, dict[str, list[str]]] = {}
    for label, root in roots.items():
        hits: dict[str, list[str]] = {}
        for p in _source_files(root):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if group not in text:
                continue
            original = text.splitlines()
            for i, line in enumerate(_without_comments(text, p.suffix).splitlines(), 1):
                if rx.search(line):
                    hits.setdefault(_kind_of(line, p.suffix), []).append(f"{p.relative_to(root)}:{i}  {original[i - 1].strip()[:90]}")
        out[label] = hits
    return out


def trace_code(group: str, ctx: TraceContext, tobe: Path | None = None) -> TraceResult:
    group = group.strip()
    if not _GROUP.fullmatch(group):
        raise ValueError(f"코드 그룹 이름은 영문자·숫자·_ 만 쓸 수 있습니다 (예: AprStatusCode, USE_YN): {group}")
    res = TraceResult(
        command="trace-code",
        description="코드값과 명칭, 사용처(콤보, SQL 리터럴, Java/TS 상수 비교)",
        side=ctx.side,
        params={"code_group": group},
    )
    res.unresolved += ctx.unresolved
    resolved = group
    try:
        kinds = _kinds(group)
        if not kinds:
            raise TargetNotFoundError(group)
        if len(kinds) > 1:
            raise AmbiguousTargetError([f"{k[1]} — {k[2]}" for k in kinds[:10]], group)
        kind_id, resolved, kind_nm = kinds[0]
        res.params["resolved"] = resolved
        values = _values(kind_id)
        shown = values[:MAX_CODES]
        res.facts.append(
            f"코드 그룹: {resolved} — {kind_nm} (코드 {len(values)}개)\n"
            + "\n".join(f"  {c} {n}" + (f"  [회사 {cc}곳]" if cc > 1 else "") + ("  (사용 중지)" if closed else "") for c, n, cc, closed in shown)
            + (f"\n  … 외 {len(values) - MAX_CODES}개" if len(values) > MAX_CODES else "")
        )
        res.evidence.append(f"DB sys08_code_kind id={kind_id} / sys09_code {len(values)}행")
    except db.DbUnavailable as exc:
        res.unresolved.append(f"DB를 쓸 수 없어 코드값을 구하지 못함 ({exc}) — 이름 '{group}'이 적힌 사용처만 찾는다")

    roots: dict[str, Path] = {}
    if wants_asis(ctx.side) and ctx.src_root and Path(ctx.src_root).is_dir():
        from yunhee.tools.as_is.src_indexer import find_app

        roots["ASIS"] = find_app(Path(ctx.src_root)) or Path(ctx.src_root)
    elif wants_asis(ctx.side):
        res.unresolved.append("ASIS 소스를 찾지 못해 ASIS 사용처를 구하지 못함 (YUNHEE_ASIS_SRC_DIR)")
    if wants_tobe(ctx.side):
        layout = find_layout(tobe)
        if layout.usable:
            roots["TOBE"] = layout.root
        else:
            res.unresolved.append(f"TOBE 소스를 찾지 못해 TOBE 사용처를 구하지 못함 ({layout.root}) — --tobe로 지정")
    for label, hits in find_usages(resolved, roots).items():
        total = sum(len(v) for v in hits.values())
        body = []
        for kind, items in sorted(hits.items(), key=lambda kv: -len(kv[1])):
            body.append(f"  {kind}({len(items)}):")
            body += [f"    - {i}" for i in items[:MAX_HITS]]
            if len(items) > MAX_HITS:
                body.append(f"    … 외 {len(items) - MAX_HITS}개")
        res.facts.append(f"{label} 사용처 {total}곳" + ("\n" + "\n".join(body) if body else " (코드 그룹 이름이 따옴표로 적힌 곳이 없음)"))
        res.evidence += [f"{label} {i.split('  ')[0]}" for items in hits.values() for i in items[:3]]
    res.unresolved.append("코드 '값'(예: \"900\")을 직접 비교하는 곳은 그룹 이름이 적히지 않아 찾지 못한다 — 해당 컬럼은 trace-column·trace-state로 본다")
    return res
