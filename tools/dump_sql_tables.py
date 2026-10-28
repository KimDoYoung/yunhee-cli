"""mapper SQL의 테이블·CTE 해석 결과를 JSON으로 덤프하고, 두 덤프를 비교한다 (SQL 해석 코드 교체 회귀 방지용).

실행:
    uv run tools/dump_sql_tables.py dump OUT.json          # 현재 코드의 결과를 저장
    uv run tools/dump_sql_tables.py diff A.json B.json     # 교체 전(A)·후(B) 차이 분류

세 경로를 같은 방식으로 덤프한다.
  parse_mapper  : tools/parse_mapper.py (mapper_index에 들어가는 테이블 목록)
  src_indexer   : as_is.src_indexer.parse_mappers (호출 경로 색인의 tables/ctes)
  analysis_sql  : `analysis sql` md 출력의 테이블·CTE 줄
"""

import json
import re
import sys
from pathlib import Path

from yunhee import config
from yunhee.tools.as_is.mybatis_render import get_all_statements
from yunhee.tools.as_is.src_indexer import find_app, parse_mappers
from yunhee.tools.schema_snapshot import load_snapshot


def _dump_parse_mapper(src: Path) -> dict[str, list[str]]:
    import parse_mapper  # tools/parse_mapper.py (스크립트 폴더가 sys.path에 있다)

    out: dict[str, list[str]] = {}
    statements = get_all_statements(src)
    for path in sorted(src.rglob("mapper/*.xml")):
        if "target" in path.parts:
            continue
        try:
            rows = parse_mapper._parse_mapper_file(str(path), statements)
        except Exception as exc:  # noqa: BLE001 - 덤프 중 한 파일의 실패가 전체를 막지 않게 한다
            print(f"경고: {path} 건너뜀 ({exc})", file=sys.stderr)
            continue
        for ns, sql_id, _tag, tables in rows:
            out[f"{ns}.{sql_id}"] = [t for t in tables.split(",") if t]
    return out


def _dump_src_indexer(src: Path) -> dict[str, dict[str, list[str]]]:
    app = find_app(src)
    if app is None:
        return {}
    snap = load_snapshot(config.SCHEMA_ENV)
    tables: dict[str, str] = {}
    functions: set[str] = set()
    columns: set[str] = set()
    if snap.ok:
        for t in snap.data.get("tables", []):
            tables[t["name"].lower()] = "x"
            columns |= {c["name"].lower() for c in t.get("columns", [])}
        functions = {r["name"].lower() for r in snap.data.get("routines", []) if r.get("name")}
    statements, _ = parse_mappers(app, tables, functions, columns)
    return {k: {"tables": sorted(s.tables), "ctes": sorted(s.ctes)} for k, s in statements.items() if s.kind != "sql"}


def _dump_analysis_sql(src: Path) -> dict[str, dict[str, list[str]]]:
    from yunhee.tools.analysis import sql as analysis_sql

    stmts = get_all_statements(src)
    out: dict[str, dict[str, list[str]]] = {}
    for key in sorted({s.key for s in stmts.values() if s.kind != "sql"}):
        obj = {"key": key, "statement": stmts[key], "params": {}, "src_root": src, "statements": stmts}
        text = analysis_sql.render(obj, "md")
        entry: dict[str, list[str]] = {}
        for label in ("테이블", "CTE"):
            m = re.search(rf"^- \*\*{label}\*\*: (.*)$", text, re.MULTILINE)
            entry[label] = sorted(x.strip().lower() for x in m.group(1).split(",")) if m else []
        out[key] = entry
    return out


def dump(out_path: Path) -> None:
    src, _ = (config.ASIS_SRC_DIR, None)
    data = {
        "src": str(src),
        "parse_mapper": _dump_parse_mapper(src),
        "src_indexer": _dump_src_indexer(src),
        "analysis_sql": _dump_analysis_sql(src),
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, dict)})


def _as_set(v) -> set[str]:
    return set(v) if isinstance(v, list) else set()


def diff(a_path: Path, b_path: Path) -> None:
    a, b = json.loads(a_path.read_text()), json.loads(b_path.read_text())
    for section in ("parse_mapper", "src_indexer", "analysis_sql"):
        changed = 0
        added_only = removed_only = both = 0
        lines: list[str] = []
        for key in sorted(set(a[section]) | set(b[section])):
            va, vb = a[section].get(key), b[section].get(key)
            if va == vb:
                continue
            changed += 1
            fields = ("tables", "ctes") if section == "src_indexer" else ("테이블", "CTE") if section == "analysis_sql" else (None,)
            for f in fields:
                sa = _as_set(va if f is None else (va or {}).get(f))
                sb = _as_set(vb if f is None else (vb or {}).get(f))
                if sa == sb:
                    continue
                gone, new = sorted(sa - sb), sorted(sb - sa)
                if gone and new:
                    both += 1
                elif gone:
                    removed_only += 1
                else:
                    added_only += 1
                lines.append(f"{key} [{f or 'tables'}] -{gone} +{new}")
        print(f"## {section}: 변경 {changed}건 (빠짐만 {removed_only} / 늘어남만 {added_only} / 둘 다 {both})")
        for line in lines[:60]:
            print("  ", line)
        if len(lines) > 60:
            print(f"   … 외 {len(lines) - 60}건")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "dump":
        dump(Path(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == "diff":
        diff(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
