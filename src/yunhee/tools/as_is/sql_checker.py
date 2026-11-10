"""AS-IS MyBatis 매퍼 SQL을 대상 DB에서 EXPLAIN으로 정합성 검증하는 도구."""

import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from yunhee.config import LOCAL_DB, SCHEMA_ENV
from yunhee.tools.as_is.sql_drift import check_sql_drift
from yunhee.tools.as_is.src_indexer import find_app
from yunhee.tools.base import ToolResult

__all__ = [
    "check_sql",
    "check_sql_drift",
    "check_statement_db_objects",
    "check_tobe_sql",
    "resolve_service_to_sql_id",
]

ENV_ERROR_RE = re.compile(r'collation "[^"]+" for encoding "[^"]+" does not exist', re.IGNORECASE)
SCHEMA_ERROR_RE = re.compile(
    r'(column|relation|function|type|schema) (?:"?[\w.]+"?\s*\(.*?\)|"[^"]+"|\S+) does not exist|missing FROM-clause entry for table "[^"]+"',
    re.IGNORECASE,
)


from yunhee.tools.as_is.mybatis_render import (
    STATEMENT_TAGS,
    Node,
    Statement,
    load_statements,
    parse_xml,
    render_node,
)


def render(node: Node, ns: str, statements: dict[str, Statement], seen: tuple[str, ...] = ()) -> str:
    return render_node(node, ns, statements, {}, mode="explain", seen=seen)


def to_sql(st: Any, statements: dict[str, Any]) -> str:
    import re

    from yunhee.tools.as_is.mybatis_render import render as mr_render

    if hasattr(st, "node"):
        try:
            sql, _ = mr_render(st.key, mode="explain", statements=statements)
            return sql
        except Exception:  # noqa: BLE001, S110
            pass
    raw = getattr(st, "raw", "") or ""
    return re.sub(r"<[^>]+>", " ", raw).strip()



def parse_pg_url(url: str | None) -> dict[str, str]:
    """PostgreSQL URL에서 psql 환경변수 사전(PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)을 추출한다."""
    if not url:
        return {}
    try:
        parsed = urlsplit(url)
        env: dict[str, str] = {}
        if parsed.hostname:
            env["PGHOST"] = parsed.hostname
        if parsed.port:
            env["PGPORT"] = str(parsed.port)
        if parsed.username:
            env["PGUSER"] = unquote(parsed.username)
        if parsed.password:
            env["PGPASSWORD"] = unquote(parsed.password)
        if parsed.path and parsed.path.lstrip("/"):
            env["PGDATABASE"] = unquote(parsed.path.lstrip("/"))
        return env
    except Exception:  # noqa: BLE001
        return {}


def get_db_env(db_name: str | None = None) -> tuple[str, dict[str, str]]:
    """db_name과 .env.local의 설정(SCHEMA_ENV, LOCAL_DB)을 결합하여 (최종 DB명, PG 환경변수) 반환."""
    url = os.getenv(SCHEMA_ENV) or LOCAL_DB or os.getenv("LOCAL_DB") or os.getenv("TEST_DB")
    pg_env = parse_pg_url(url)

    final_db = db_name or "asseterpdb"
    if (db_name is None or db_name == "asseterpdb") and pg_env.get("PGDATABASE"):
        final_db = pg_env["PGDATABASE"]

    return final_db, pg_env


# ---------------------------------------------------------------- 실행

def explain(sql: str, db: str, extra_env: dict[str, str] | None = None) -> str | None:
    script = f"BEGIN READ ONLY;\nSET statement_timeout = '10s';\nEXPLAIN {sql};\nROLLBACK;\n"
    env = {
        **os.environ,
        **(extra_env or {}),
        "LC_MESSAGES": "C",
        "PGOPTIONS": "-c lc_messages=C",
    }
    try:
        res = subprocess.run(
            ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db, "-f", "-"],
            input=script,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return "[ERROR] psql 명령어를 찾을 수 없습니다. PostgreSQL 클라이언트가 설치되어 있는지 확인하세요."

    if res.returncode == 0:
        return None
    lines = res.stderr.splitlines()
    idx = next(
        (i for i, l in enumerate(lines) if "ERROR" in l or "오류" in l or "FATAL" in l or "error:" in l.lower()),
        None,
    )
    if idx is None:
        return res.stderr.strip() or f"psql 실행 실패 (종료 코드 {res.returncode})"
    err = re.sub(r"^psql:<stdin>:\d+:\s*", "", lines[idx]).strip()
    near = next((l.strip() for l in lines[idx + 1: idx + 2] if l.strip().startswith("LINE")), "")
    return f"{err} — {near[:160]}" if near else err


def _restore_obj_case(obj_err: str, sql_text: str) -> str:
    """PostgreSQL 오류 메시지의 소문자 식별자를 원본 SQL의 대소문자로 복원한다."""
    m = re.match(r"^(function|column|relation|type|schema)\s+\"?([a-zA-Z0-9_.]+)\"?(.*)$", obj_err, re.IGNORECASE)
    if not m or not sql_text:
        return obj_err
    kind, ident, tail = m.group(1), m.group(2), m.group(3)
    base_ident = ident.split(".")[-1]
    orig_m = re.search(rf"\b({re.escape(base_ident)})\b", sql_text, re.IGNORECASE)
    if orig_m:
        orig_ident = orig_m.group(1)
        if "." in ident:
            prefix = ident.rsplit(".", 1)[0]
            ident_restored = f"{prefix}.{orig_ident}"
        else:
            ident_restored = orig_ident
        quote = '"' if f'"{ident}"' in obj_err else ""
        return f"{kind} {quote}{ident_restored}{quote}{tail}"
    return obj_err


def _class_to_snake_ns(cls_name: str) -> str:
    parts = cls_name.split("_")
    conv = [re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", p).lower() for p in parts if p]
    return "_".join(conv)


def resolve_service_to_sql_id(
    target: str,
    src_root: Path | None,
    statements: dict[str, Statement] | None = None,
) -> tuple[str | None, str | None, list[str], list[str]]:
    """매퍼 문장 ID 또는 서비스 메서드(dom.Class.method)를 해석한다.

    반환: (resolved_key, service_note, multi_called_ids, candidate_keys)
    """
    import difflib

    from yunhee.tools.as_is.mybatis_render import get_all_statements
    from yunhee.tools.as_is.src_indexer import (
        SEQ_SQL_ID,
        SQL_CALL_RE,
        call_argument,
        eval_string,
        find_methods,
        strip_java,
    )

    stmts = statements if statements is not None else get_all_statements(src_root)
    target_clean = target.strip()

    # 1. 매퍼 문장 ID로 직접 존재하는 경우
    st = stmts.get(target_clean)
    if not st and "." not in target_clean:
        st = next((s for s in stmts.values() if s.sid == target_clean), None)
    if st:
        return st.key, None, [], []

    # 2. 서비스 메서드 이름 (dom.ClassName.method 또는 ClassName.method) 해석 시도
    tokens = target_clean.split(".")
    cand_ns = ""
    cand_sid = tokens[-1] if tokens else target_clean
    server_file: Path | None = None
    cls_name = ""
    meth_name = ""

    if len(tokens) >= 2:
        meth_name = tokens[-1]
        cls_name = tokens[-2]
        dom_parts = tokens[:-2]
        if cls_name and cls_name[0].isupper():
            cand_ns = _class_to_snake_ns(cls_name)
        else:
            cand_ns = cls_name

        app = (find_app(src_root) or src_root) if src_root and src_root.is_dir() else None
        if app and app.is_dir():
            sdir = app / "server" if (app / "server").is_dir() else app
            if dom_parts:
                cand_path = sdir / Path(*dom_parts) / f"{cls_name}.java"
                if cand_path.is_file():
                    server_file = cand_path
            if not server_file and cls_name and cls_name[0].isupper():
                found = [f for f in sdir.rglob(f"{cls_name}.java") if "target" not in f.parts]
                if found:
                    server_file = found[0]

    if server_file and server_file.is_file():
        try:
            raw_java = server_file.read_text(encoding="utf-8", errors="replace")
            no_comment, bare = strip_java(raw_java)
            mapper_vals = eval_string("mapperName", [no_comment])
            if mapper_vals:
                cand_ns = min(mapper_vals)

            methods_map: dict[str, tuple[str, str]] = {}
            for m_name, _npos, b_start, b_end, _is_pub, _params in find_methods(bare):
                body = no_comment[b_start : b_end + 1]
                body_bare = bare[b_start : b_end + 1]
                methods_map.setdefault(m_name, (body, body_bare))

            if meth_name in methods_map:
                all_m_names = set(methods_map.keys())
                visited: set[str] = set()
                called_sqls: list[str] = []

                def _collect(m_nm: str) -> None:
                    if m_nm in visited or m_nm not in methods_map:
                        return
                    visited.add(m_nm)
                    b_text, b_bare = methods_map[m_nm]
                    for m_call in SQL_CALL_RE.finditer(b_text):
                        arg = call_argument(b_text, m_call.end() - 1)
                        vals = eval_string(arg, [b_text, no_comment])
                        if vals:
                            for v in sorted(vals):
                                sid_val = SEQ_SQL_ID if v == "getSeq" else v
                                if sid_val not in called_sqls:
                                    called_sqls.append(sid_val)
                    for sub_m in re.findall(r"(?<![\w.])(\w+)\s*\(", b_bare):
                        if sub_m in all_m_names and sub_m != m_nm:
                            _collect(sub_m)

                _collect(meth_name)
                non_seq = [s for s in called_sqls if s != SEQ_SQL_ID]
                effective = non_seq or called_sqls
                valid = [s for s in effective if s in stmts] or effective
                if len(valid) == 1 and valid[0] in stmts:
                    mapped = valid[0]
                    return mapped, f"서비스 {target_clean} → 매퍼 {mapped}", [], []
                if len(valid) > 1:
                    return None, None, valid, []
        except OSError:
            pass

    # 3. 후보 문장 목록 생성
    candidates: list[str] = []
    if cand_ns:
        direct_cand = f"{cand_ns}.{cand_sid}"
        if direct_cand in stmts:
            candidates.append(direct_cand)
        ns_stmts = [s for s in stmts.values() if s.ns.lower() == cand_ns.lower() and s.kind != "sql" and s.key == f"{s.ns}.{s.sid}"]
        if ns_stmts:
            close_sids = difflib.get_close_matches(cand_sid, [s.sid for s in ns_stmts], n=5, cutoff=0.35)
            for c_sid in close_sids:
                full_k = f"{ns_stmts[0].ns}.{c_sid}"
                if full_k not in candidates:
                    candidates.append(full_k)
            if not candidates:
                for s in ns_stmts[:8]:
                    if s.key not in candidates:
                        candidates.append(s.key)

    if not candidates:
        all_keys = [s.key for s in stmts.values() if s.kind != "sql" and s.key == f"{s.ns}.{s.sid}"]
        candidates = difflib.get_close_matches(target_clean, all_keys, n=5, cutoff=0.4)

    return None, None, [], candidates


def check_statement_db_objects(
    st: Statement,
    statements: dict[str, Statement],
    db: str | None = None,
    src_root: Path | None = None,
    src_index: Path | None = None,
) -> dict[str, Any]:
    """단일 statement의 DB 객체 존재 여부(EXPLAIN)와 sql-check.md 상태를 반환한다."""
    from datetime import UTC, datetime

    from yunhee.tools.as_is import find_as_is_dir

    if st.kind == "sql":
        return {"warning": None, "explain_status": "조각", "sql_check_line": None}

    raw_sql = to_sql(st, statements)
    target_db, pg_env = get_db_env(db)
    err = explain(raw_sql, target_db, extra_env=pg_env)

    warning: str | None = None
    if err is None:
        explain_status = "통과"
    else:
        m_schema = SCHEMA_ERROR_RE.search(err)
        if m_schema:
            obj_err = _restore_obj_case(m_schema.group(0), raw_sql)
            warning = f"⚠ DB에 없는 객체: {obj_err} — 변환 가이드 1절에 따라 보류 검토"
            explain_status = f"없는 객체({obj_err})"
        elif "psql 명령어를 찾을 수 없습니다" in err or "connection to server" in err.lower() or "could not connect" in err.lower():
            explain_status = "미검증"
        else:
            explain_status = "확인 못 함"

    # sql-check.md 상태 확인
    sql_check_file: Path | None = None
    if src_index and (src_index.parent / "sql-check.md").is_file():
        sql_check_file = src_index.parent / "sql-check.md"
    else:
        cand_file = find_as_is_dir() / "sql-check.md"
        if cand_file.is_file():
            sql_check_file = cand_file

    sql_check_status = explain_status
    if sql_check_file and sql_check_file.is_file():
        try:
            md_text = sql_check_file.read_text(encoding="utf-8", errors="replace")
            check_mtime = sql_check_file.stat().st_mtime
            check_date = datetime.fromtimestamp(check_mtime, tz=UTC).astimezone().strftime("%Y-%m-%d")

            row_re = re.compile(rf"^\|\s*`{re.escape(st.key)}`\s*\|\s*`[^`]+`\s*\|\s*[^|]+\|\s*(.+?)\s*\|$", re.MULTILINE)
            m_row = row_re.search(md_text)
            if m_row:
                err_col = m_row.group(1)
                m_sc = SCHEMA_ERROR_RE.search(err_col)
                if m_sc:
                    obj_err = _restore_obj_case(m_sc.group(0), raw_sql)
                    sql_check_status = f"없는 객체({obj_err})"
                elif ENV_ERROR_RE.search(err_col):
                    sql_check_status = "DB 환경 차이"
                else:
                    sql_check_status = "확인 못 함"
            else:
                # sql-check.md 실패 목록에 없음 -> 생성일과 SQL 추가 시점/현재 EXPLAIN 비교
                is_older = False
                if warning is not None:
                    # 현재 DB에는 없는 객체인데 sql-check.md 실패 표에 없다면 sql-check.md가 오래된 것
                    is_older = True
                elif src_root and src_root.is_dir():
                    app = find_app(src_root) or src_root
                    xml_full = app / st.rel
                    if xml_full.is_file():
                        try:
                            git_res = subprocess.run(
                                ["git", "-C", str(src_root), "log", "-S", st.sid, "-1", "--format=%ct", "--", str(xml_full)],
                                capture_output=True,
                                text=True,
                                check=False,
                                timeout=2.0,
                            )
                            ts_str = git_res.stdout.strip()
                            if ts_str.isdigit() and int(ts_str) > int(check_mtime):
                                is_older = True
                        except Exception:  # noqa: BLE001, S110
                            pass
                if is_older:
                    sql_check_status = f"결과 없음(sql-check.md가 이 SQL보다 오래됨 — {check_date} 생성)"
                else:
                    sql_check_status = "통과"
        except OSError:
            pass

    return {
        "warning": warning,
        "explain_status": explain_status,
        "sql_check_line": sql_check_status,
    }


def screens_using(src_index: Path | None, keys: list[str]) -> dict[str, set[str]]:
    """src-index 화면 파일에서 SQL ID를 쓰는 화면"""
    result: dict[str, set[str]] = defaultdict(set)
    if not src_index or not src_index.is_dir():
        return result
    for f in src_index.glob("*/screens/*.md"):
        text = f.read_text(encoding="utf-8")
        for key in keys:
            if f"`{key}`" in text:
                result[key].add(f.stem)
    return result


def md_cell(v: Any) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def check_sql(
    src_root: Path,
    target_file: Path,
    db: str = "asseterpdb",
    src_index_dir: Path | None = None,
    new_since_index: bool = False,
) -> ToolResult:
    """AS-IS MyBatis 매퍼 SQL을 대상 DB에서 EXPLAIN으로 정합성을 검증한다."""
    if not src_root.is_dir():
        return ToolResult(ok=False, error=f"AS-IS 소스 디렉터리를 찾을 수 없습니다: {src_root}")

    app = find_app(src_root)
    if not app:
        return ToolResult(
            ok=False,
            error=f"{src_root} 아래에서 앱 패키지를 찾지 못했습니다.",
        )

    statements = load_statements(app)
    targets = [s for s in statements.values() if s.kind != "sql"]
    if not targets:
        return ToolResult(ok=False, error=f"{app} 아래에서 실행 대상 SQL을 찾지 못했습니다.")

    if new_since_index:
        import json

        indexed_keys: set[str] = set()
        if src_index_dir and (src_index_dir / "_index.json").is_file():
            try:
                idx_json = json.loads((src_index_dir / "_index.json").read_text(encoding="utf-8"))
                indexed_keys = set((idx_json.get("statements") or {}).keys())
            except Exception:  # noqa: BLE001, S110
                pass

        changed_rels: set[str] = set()
        since_arg = "14 days ago"
        if target_file and target_file.is_file():
            import time
            from datetime import UTC, datetime

            mtime = target_file.stat().st_mtime
            if (time.time() - mtime) > 86400:
                since_arg = datetime.fromtimestamp(mtime, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        try:
            git_res = subprocess.run(
                ["git", "-C", str(src_root), "log", f"--since={since_arg}", "--name-only", "--pretty=format:", "--", "*.xml"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
            app_rel = app.relative_to(src_root).as_posix() if app != src_root else ""
            for line in git_res.stdout.splitlines():
                line_s = line.strip()
                if not line_s:
                    continue
                if app_rel and line_s.startswith(app_rel + "/"):
                    changed_rels.add(line_s[len(app_rel) + 1 :])
                else:
                    changed_rels.add(line_s)
        except Exception:  # noqa: BLE001, S110
            pass

        filtered = [
            s
            for s in targets
            if (indexed_keys and s.key not in indexed_keys) or (s.rel.as_posix() in changed_rels)
        ]
        if filtered:
            targets = filtered

    target_db, db_env = get_db_env(db)

    # psql 연결성 사전 테스트
    test_err = explain("SELECT 1", target_db, extra_env=db_env)
    if test_err is not None:
        return ToolResult(
            ok=False,
            error=f"대상 DB({target_db}) 접속 실패: {test_err}\n"
                  f"DB가 실행 중인지 확인하고, .env.local의 LOCAL_DB 또는 PGHOST/PGUSER/PGPASSWORD 설정을 확인하세요.",
        )

    ok_list, schema_list, env_list, other_list = [], [], [], []
    for st in sorted(targets, key=lambda s: s.key):
        err = explain(to_sql(st, statements), target_db, extra_env=db_env)
        if err is None:
            ok_list.append(st)
        elif SCHEMA_ERROR_RE.search(err):
            schema_list.append((st, err))
        elif ENV_ERROR_RE.search(err):
            env_list.append((st, err))
        else:
            other_list.append((st, err))

    used_by = screens_using(src_index_dir, [s.key for s, _ in schema_list + env_list + other_list])
    missing: dict[str, list[Statement]] = defaultdict(list)
    for st, err in schema_list:
        m = SCHEMA_ERROR_RE.search(err)
        if m:
            missing[m.group(0)].append(st)

    target_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 매퍼 SQL ↔ DB 정합성 (EXPLAIN)",
        "",
        "`yunhee sql-check`가 생성했다. 직접 수정하지 말고 명령어를 다시 실행한다.",
        "",
        f"- 소스: `{src_root}` (`{app.relative_to(src_root).as_posix() if app != src_root else '.'}`)",
        f"- DB: `{target_db}`",
        f"- SQL {len(targets)}개(`<sql>` 조각 제외): **통과 {len(ok_list)}**, **스키마 차이 {len(schema_list)}**, DB 환경 차이 {len(env_list)}, 펼치기 한계·기타 {len(other_list)}",
        "",
        '통과는 "그 DB에 그 SQL이 쓰는 테이블·컬럼·함수가 모두 있다"는 뜻이다(결과 정합성까지 보장하지 않음).',
        "",
    ]
    lines += ["## 없는 DB 객체", "", "| 오류 | SQL 수 | SQL |", "|:---|---:|:---|"]
    for msg, sts in sorted(missing.items(), key=lambda x: -len(x[1])):
        lines.append(f"| `{md_cell(msg)}` | {len(sts)} | " + ", ".join(f"`{s.key}`" for s in sts) + " |")

    for title, rows in (
        ("스키마 차이", schema_list),
        ("DB 환경 차이", env_list),
        ("펼치기 한계·기타 (직접 확인 필요)", other_list),
    ):
        lines += ["", f"## {title}", "", "| SQL | 파일:줄 | 화면 | 오류 |", "|:---|:---|:---|:---|"]
        for st, err in sorted(rows, key=lambda x: x[0].key):
            screens = ", ".join(sorted(used_by.get(st.key, []))) or "-"
            lines.append(f"| `{st.key}` | `{st.rel}:{st.line}` | {screens} | {md_cell(err)} |")

    affected: dict[str, list[str]] = defaultdict(list)
    for st, _ in schema_list:
        for scr in used_by.get(st.key, []):
            affected[scr].append(st.key)
    lines += ["", "## 스키마 차이가 있는 화면", "", "| 화면 | SQL |", "|:---|:---|"]
    for scr, keys in sorted(affected.items()):
        lines.append(f"| `{scr}` | " + ", ".join(f"`{k}`" for k in sorted(keys)) + " |")

    report_md = "\n".join(lines) + "\n"
    if not new_since_index:
        target_file.write_text(report_md, encoding="utf-8")

    return ToolResult(
        ok=True,
        data={
            "target_file": str(target_file),
            "target_db": target_db,
            "total_sql": len(targets),
            "passed_count": len(ok_list),
            "schema_diff_count": len(schema_list),
            "env_diff_count": len(env_list),
            "other_count": len(other_list),
            "affected_screens_count": len(affected),
            "report_md": report_md,
        },
    )


def check_proc_exists(proc_name: str, db: str, extra_env: dict[str, str] | None = None) -> bool:
    """pg_proc에서 프로시저가 존재하는지 확인한다."""
    script = f"SELECT 1 FROM pg_proc WHERE proname = '{proc_name}';\n"
    env = {**os.environ, **(extra_env or {})}
    try:
        res = subprocess.run(
            ["psql", "-X", "-q", "-At", "-d", db, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        return "1" in res.stdout
    except Exception:  # noqa: BLE001
        return False


def java_source_roots(mapper_dir: Path) -> list[Path]:
    """매퍼 폴더(…/src/main/resources/mapper)에서 Java 소스 루트(…/src/main/java)를 찾는다."""
    roots: list[Path] = []
    for d in [mapper_dir, *mapper_dir.parents]:
        if d.name == "resources" and (d.parent / "java").is_dir():
            roots.append(d.parent / "java")
            break
    for d in (Path.cwd() / "src" / "main" / "java", Path.cwd()):
        if d.is_dir() and d not in roots:
            roots.append(d)
    return roots


def _record_fields(path: Path, cls_name: str) -> set[str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(rf"\brecord\s+{re.escape(cls_name)}\s*(?:<[^>]*>)?\s*\(", text)
    if not m:
        return None
    end = _close_paren(text, m.end() - 1)
    fields = set()
    for p in split_top_level(text[m.end():end], "()<>"):
        p = re.sub(r"@\w+(?:\([^)]*\))?", " ", p)  # 애노테이션 제거
        parts = p.strip().split()
        if len(parts) >= 2:
            fields.add(parts[-1])
    return fields


def _close_brace(text: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def _class_fields(text: str, cls_name: str) -> set[str] | None:
    """일반(setter) Java 클래스의 필드/setter 프로퍼티 목록을 추출한다."""
    clean = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    clean = re.sub(r"//[^\n]*", " ", clean)
    m = re.search(rf"\bclass\s+{re.escape(cls_name)}\b[^{{]*\{{", clean)
    if not m:
        return None
    open_pos = m.end() - 1
    end_pos = _close_brace(clean, open_pos)
    body = clean[open_pos + 1 : end_pos]

    top_chars: list[str] = []
    depth = 0
    for ch in body:
        if ch == "{":
            depth += 1
            if depth == 1:
                top_chars.append(";")
        elif ch == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            top_chars.append(ch)
    top_body = "".join(top_chars)

    fields: set[str] = set()
    for sm in re.finditer(r"\bvoid\s+set([A-Z]\w*)\s*\(", top_body):
        prop = sm.group(1)
        fields.add(prop[0].lower() + prop[1:])

    for stmt in top_body.split(";"):
        stmt = re.sub(r"@\w+(?:\([^)]*\))?", " ", stmt).strip()
        if not stmt or "(" in stmt:
            continue
        if re.search(r"\b(static|final|class|record|interface|enum)\b", stmt):
            continue
        decl = stmt.split("=", 1)[0].strip()
        parts = decl.split()
        if len(parts) >= 2:
            fname = parts[-1].strip()
            if re.match(r"^[a-zA-Z_]\w*$", fname) and fname not in ("return", "void", "new"):
                fields.add(fname)

    return fields if fields else None


_DTO_CACHE: dict[tuple[Path, str, int], tuple[set[str] | None, bool]] = {}


def _dto_fields(path: Path, cls_name: str) -> tuple[set[str] | None, bool]:
    """Java 소스 파일에서 DTO 필드 집합과 record 여부를 (fields, is_record)로 반환한다 (파일별 캐시)."""
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return None, False
    cache_key = (path, cls_name, mtime_ns)
    if cache_key in _DTO_CACHE:
        return _DTO_CACHE[cache_key]
    rec = _record_fields(path, cls_name)
    if rec is not None:
        res = (rec, True)
        _DTO_CACHE[cache_key] = res
        return res
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, False
    cls_f = _class_fields(text, cls_name)
    res = (cls_f, False)
    _DTO_CACHE[cache_key] = res
    return res


def find_dto_fields(result_type: str, search_roots: list[Path]) -> tuple[set[str] | None, bool, str | None]:
    """DTO(record 또는 일반 setter 클래스)를 찾아 (필드 목록, is_record, 경고)를 반환한다."""
    name = result_type.replace("$", ".")
    parts = name.split(".")
    cls_name = parts[-1]
    if len(parts) > 1:
        for cut in range(len(parts), 1, -1):
            rel = Path(*parts[:cut]).with_suffix(".java")
            for r in search_roots:
                f = r / rel
                if f.is_file():
                    fields, is_rec = _dto_fields(f, cls_name)
                    return fields, is_rec, None
        return None, False, None
    found: list[Path] = []
    for r in search_roots:
        if r.is_dir():
            found += [f for f in r.glob(f"**/{cls_name}.java") if "target" not in f.parts and f not in found]
    if len(found) > 1:
        return None, False, f"{cls_name} 후보 {len(found)}개 — FQN으로 써야 대조"
    if found:
        fields, is_rec = _dto_fields(found[0], cls_name)
        return fields, is_rec, None
    return None, False, None


def find_record_fields(result_type: str, search_roots: list[Path]) -> tuple[set[str] | None, str | None]:
    """record DTO를 찾아 (필드 목록, 경고)를 반환한다.

    FQN(kr.co...dto.CompanyRes)이면 소스 루트 아래 정확한 경로에서만 찾는다 (같은 이름의 다른 패키지 record와 섞이지 않게).
    짧은 이름(typeAlias)이면 glob하고, 여러 개면 경고하고 대조를 건너뛴다.
    """
    fields, is_rec, warn = find_dto_fields(result_type, search_roots)
    if warn:
        return None, warn
    return (fields if is_rec else None), None


def _close_paren(text: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def split_top_level(text: str, brackets: str = "()") -> list[str]:
    """괄호 깊이 0의 콤마로만 나눈다. brackets는 여는·닫는 문자 쌍의 나열 (예: "()<>")."""
    opens, closes = brackets[0::2], brackets[1::2]
    out, cur, depth = [], [], 0
    for ch in text:
        if ch in opens:
            depth += 1
        elif ch in closes:
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


# AS 없는 별칭으로 오인하면 안 되는 끝 단어 (CASE … END, x IS NULL 등)
SQL_KEYWORDS = {
    "END", "NULL", "TRUE", "FALSE", "DESC", "ASC", "AND", "OR", "NOT", "THEN", "ELSE",
    "DISTINCT", "ALL", "FROM", "AS", "IS", "IN", "LIKE", "BETWEEN",
}


def _mask_sql(sql: str) -> str:
    """주석을 지우고 문자열 리터럴 내용을 비운다."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def _depth0_matches(sql: str, pattern: str) -> list[re.Match]:
    """괄호 깊이 0에 있는 매치만 돌려준다."""
    depth_at = []
    depth = 0
    for ch in sql:
        if ch == "(":
            depth += 1
        depth_at.append(depth)
        if ch == ")":
            depth = max(0, depth - 1)
    return [m for m in re.finditer(pattern, sql, re.IGNORECASE) if depth_at[m.start()] == 0]


def select_output_names(sql: str) -> list[str | None] | None:
    """최상위 SELECT 목록의 출력 이름들. 이름을 정할 수 없는 식은 None, `*`가 있으면 전체가 None.

    PostgreSQL 파서(AST)로 해석하고, 파싱할 수 없는 SQL(`#{}`가 남은 TOBE mapper 등)은 정규식 추정으로 되돌린다.
    """
    from yunhee.tools.sql_parse import parse_sql_text

    parsed = parse_sql_text(sql)
    if not parsed.fallback and parsed.kind == "select":
        return parsed.output_names
    return _select_output_names_regex(sql)


def _select_output_names_regex(sql: str) -> list[str | None] | None:
    """정규식 추정: 깊이 0의 첫 SELECT 목록을 직접 잘라 이름을 구한다. WITH … AS (…)·서브쿼리 SELECT는 괄호 안이라 건너뛴다."""
    sql = _mask_sql(sql)
    sel = _depth0_matches(sql, r"\bSELECT\b")
    if not sel:
        return []
    start = sel[0].end()
    stop = next(
        (
            m.start()
            for m in _depth0_matches(sql, r"\b(FROM|INTO|WHERE|UNION|EXCEPT|INTERSECT|ORDER|GROUP|LIMIT)\b")
            if m.start() > start
        ),
        len(sql),
    )
    body = sql[start:stop].strip()
    body = re.sub(r"^DISTINCT\s+ON\s*\([^)]*\)|^(DISTINCT|ALL)\b", "", body, flags=re.IGNORECASE).strip()
    names: list[str | None] = []
    for item in split_top_level(body):
        item = item.strip()
        if not item:
            continue
        if re.search(r"(^|\.)\*$", item):
            return None
        m = re.search(r"\bAS\s+(\"[^\"]+\"|\w+)$", item, re.IGNORECASE)
        if m:
            names.append(m.group(1))
            continue
        # AS 없이 붙인 별칭: count(*) cnt, t.col c
        m = re.search(r"[\w)\"]\s+(\"[^\"]+\"|[A-Za-z_]\w*)$", item)
        if m and m.group(1).upper() not in SQL_KEYWORDS:
            names.append(m.group(1))
            continue
        item = re.sub(r"::\s*[\w ]+(\([^)]*\))?(\[\])?$", "", item).strip()  # 캐스트는 원래 이름
        m = re.fullmatch(r"(?:\w+\.)?(\"[^\"]+\"|[A-Za-z_]\w*)", item)
        if m:
            names.append(m.group(1))  # t.col, col
            continue
        m = re.fullmatch(r"(?:\w+\.)?([A-Za-z_]\w*)\s*\(.*\)", item, re.DOTALL)
        names.append(m.group(1) if m else None)  # 함수 호출은 함수명, 그 밖의 식은 이름 없음
    return names


def to_camel(name: str) -> str:
    """MyBatis mapUnderscoreToCamelCase와 같은 규칙. 따옴표 별칭은 그대로."""
    if name.startswith('"'):
        return name.strip('"')
    parts = name.lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def to_snake(name: str) -> str:
    """camelCase를 snake_case로 변환한다."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return s.lower()


def extract_select_aliases_from_sql(sql: str) -> set[str] | None:
    """최상위 SELECT 목록의 출력 이름을 camelCase 집합으로 반환한다. `*`가 있어 알 수 없으면 None."""
    names = select_output_names(sql)
    if names is None:
        return None
    return {to_camel(n) for n in names if n}


def check_tobe_sql(
    mapper_dir: Path,
    db: str = "asseterpdb",
    only: list[str] | None = None,
    changed: bool = False,
    summary: bool = False,
) -> ToolResult:
    """TOBE 매퍼 XML을 대상 DB에서 EXPLAIN 및 검증한다."""
    import fnmatch
    import subprocess

    if not mapper_dir.is_dir() and not mapper_dir.is_file():
        return ToolResult(ok=False, error=f"TOBE 매퍼 경로를 찾을 수 없습니다: {mapper_dir}")

    target_db, db_env = get_db_env(db)
    test_err = explain("SELECT 1", target_db, extra_env=db_env)
    if test_err is not None:
        return ToolResult(
            ok=False,
            error=f"대상 DB({target_db}) 접속 실패: {test_err}",
        )

    # --changed 대상 XML 파일 수집
    changed_xml_paths: set[Path] | None = None
    if changed:
        changed_xml_paths = set()
        repo_dir = mapper_dir.resolve()
        while repo_dir != repo_dir.parent and not (repo_dir / ".git").is_dir():
            repo_dir = repo_dir.parent

        if (repo_dir / ".git").is_dir():
            try:
                # 1. git diff (unstaged)
                p1 = subprocess.run(["git", "diff", "--name-only"], cwd=repo_dir, capture_output=True, text=True, check=False)
                # 2. git diff --cached (staged)
                p2 = subprocess.run(["git", "diff", "--name-only", "--cached"], cwd=repo_dir, capture_output=True, text=True, check=False)
                # 3. git ls-files --others (untracked)
                p3 = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_dir, capture_output=True, text=True, check=False)
                combined_diff = (p1.stdout + "\n" + p2.stdout + "\n" + p3.stdout).strip()
                if not combined_diff:
                    p4 = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], cwd=repo_dir, capture_output=True, text=True, check=False)
                    combined_diff = p4.stdout.strip()

                for line in combined_diff.splitlines():
                    line = line.strip()
                    if line and line.endswith(".xml"):
                        abs_p = (repo_dir / line).resolve()
                        if abs_p.is_file():
                            changed_xml_paths.add(abs_p)
            except Exception:  # noqa: BLE001, S110
                pass

    statements: dict[str, Statement] = {}
    result_maps_by_ns: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    xml_errors_by_cls: dict[str, list[str]] = defaultdict(list)
    has_failure = bool(xml_errors_by_cls)

    if mapper_dir.is_file():
        xml_files = [mapper_dir]
        base_dir = mapper_dir.parent
    else:
        xml_files = sorted(mapper_dir.rglob("*.xml"))
        base_dir = mapper_dir

    all_candidates = [p.stem for p in xml_files]

    for path in xml_files:
        full_path = path.resolve()
        if changed_xml_paths is not None and full_path not in changed_xml_paths:
            continue

        raw_bytes = path.read_bytes()
        raw = raw_bytes.decode("utf-8", errors="replace")
        ns_m = re.search(r'<mapper\s+namespace="([^"]+)"', raw)
        ns = ns_m.group(1) if ns_m else path.stem
        cls_name = ns.split(".")[-1]
        xml_stem = path.stem

        if only:
            matched_cls = any(
                pat.lower() in cls_name.lower()
                or pat.lower() in xml_stem.lower()
                or fnmatch.fnmatch(cls_name.lower(), pat.lower())
                or fnmatch.fnmatch(xml_stem.lower(), pat.lower())
                or fnmatch.fnmatch(cls_name.lower(), f"*{pat.lower()}*")
                for pat in only
            )
            raw_ids = re.findall(r'<[a-zA-Z0-9_]+\b[^>]*\bid\s*=\s*"([^"]+)"', raw)
            matched_id = any(
                pat.lower() in sid.lower()
                or fnmatch.fnmatch(sid.lower(), pat.lower())
                or fnmatch.fnmatch(f"{ns}.{sid}".lower(), pat.lower())
                for pat in only
                for sid in raw_ids
            )
            if not matched_cls and not matched_id:
                continue

        # XML well-formed 검증 (외부 DTD fetch 없이 로컬 구문만 검사)
        import xml.etree.ElementTree as ET
        try:
            ET.fromstring(raw_bytes)
        except ET.ParseError as e:
            line, col = e.position if hasattr(e, "position") and e.position else (0, 0)
            rel_path = path.relative_to(base_dir) if path.is_relative_to(base_dir) else path.name
            err_msg = str(e)
            hint = " (힌트: 본문의 <, <=, <>, & 는 &lt;, &lt;=, &lt;&gt;, &amp; 또는 <![CDATA[ … ]]> 로 이스케이프 필요)"
            xml_errors_by_cls[cls_name].append(f"❌ XML 오류: {rel_path}:{line}:{col} {err_msg}{hint}")
            has_failure = True
            continue

        if not ns_m:
            continue
        root = parse_xml(raw)
        mapper = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), None)
        if not mapper:
            continue
        for child in mapper.children:
            if isinstance(child, Node) and child.tag == "resultMap" and "id" in child.attrs:
                rm_id = child.attrs["id"]
                rm_type = child.attrs.get("type", "")
                col_map: dict[str, str] = {}
                for sub in child.children:
                    if isinstance(sub, Node):
                        if sub.tag in ("id", "result"):
                            c_attr = sub.attrs.get("column", "")
                            p_attr = sub.attrs.get("property", "")
                            if c_attr and p_attr:
                                col_map[c_attr.lower()] = p_attr
                        elif sub.tag == "constructor":
                            for arg_node in sub.children:
                                if isinstance(arg_node, Node) and arg_node.tag in ("idArg", "arg"):
                                    c_attr = arg_node.attrs.get("column", "")
                                    p_attr = arg_node.attrs.get("name", "") or arg_node.attrs.get("property", "")
                                    if c_attr and p_attr:
                                        col_map[c_attr.lower()] = p_attr
                result_maps_by_ns[ns][rm_id] = {"type": rm_type, "col_map": col_map}
            elif isinstance(child, Node) and child.tag in STATEMENT_TAGS and "id" in child.attrs:
                pos = re.search(rf'<{child.tag}\b[^>]*\bid\s*=\s*"{re.escape(child.attrs["id"])}"', raw)
                line = raw.count("\n", 0, pos.start()) + 1 if pos else 0
                st = Statement(ns, child.attrs["id"], child.tag, child, path.relative_to(base_dir), line)
                statements[st.key] = st

    all_targets = [s for s in statements.values() if s.kind != "sql"]
    if not all_targets and not xml_errors_by_cls:
        if only:
            cand_list = sorted(dict.fromkeys(all_candidates))[:10]
            cand_str = f" (후보: {', '.join(cand_list)})" if cand_list else ""
            return ToolResult(
                ok=False,
                error=f"--only '{only[0]}' 와 일치하는 매퍼가 없습니다{cand_str}",
            )
        return ToolResult(ok=False, error=f"{mapper_dir} 아래에서 검증할 매퍼 SQL을 찾지 못했습니다.")

    # 필터링 적용 (--changed, --only)
    targets = []
    for st in all_targets:
        full_path = (base_dir / st.rel).resolve()
        if changed_xml_paths is not None and full_path not in changed_xml_paths:
            continue

        cls_name = st.ns.split(".")[-1]
        xml_stem = Path(st.rel).stem
        if only:
            matched = any(
                fnmatch.fnmatch(cls_name, pat)
                or fnmatch.fnmatch(xml_stem, pat)
                or fnmatch.fnmatch(st.sid, pat)
                or fnmatch.fnmatch(st.key, pat)
                for pat in only
            )
            if not matched:
                continue

        targets.append(st)

    if not targets and not xml_errors_by_cls:
        if only:
            cand_list = sorted(dict.fromkeys(all_candidates))[:10]
            cand_str = f" (후보: {', '.join(cand_list)})" if cand_list else ""
            return ToolResult(
                ok=False,
                error=f"--only '{only[0]}' 와 일치하는 매퍼가 없습니다{cand_str}",
                data={
                    "summary": f"[ERROR] --only '{only[0]}' 와 일치하는 매퍼가 없습니다{cand_str}",
                    "total": 0,
                    "results": {},
                },
            )
        return ToolResult(
            ok=True,
            data={
                "summary": "검증 대상 매퍼 없음 (필터 조건에 일치하는 매퍼가 없습니다)",
                "total": 0,
                "results": {},
            },
        )

    search_roots = java_source_roots(mapper_dir.resolve())

    results_by_cls: dict[str, list[str]] = defaultdict(list)
    failure_details_by_cls: dict[str, list[str]] = defaultdict(list)
    success_count_by_cls: dict[str, int] = defaultdict(int)
    failure_count_by_cls: dict[str, int] = defaultdict(int)
    has_failure = bool(xml_errors_by_cls)

    for st in sorted(targets, key=lambda s: (s.ns, s.line)):
        cls_name = st.ns.split(".")[-1]
        raw_sql = to_sql(st, statements)
        has_unresolved_include = bool(re.search(r"/\*\s*include\s+.*?\s+없음\s*\*/", raw_sql))

        call_m = re.match(r"^\s*call\s+([a-zA-Z0-9_]+)", raw_sql, re.IGNORECASE)
        err = None
        if call_m:
            proc_name = call_m.group(1)
            if not check_proc_exists(proc_name, target_db, extra_env=db_env):
                err = f'procedure "{proc_name}" does not exist'
        else:
            err = explain(raw_sql, target_db, extra_env=db_env)

        if has_unresolved_include and err is not None:
            results_by_cls[cls_name].append(f"{st.sid} ? include 미해결 — mapper-run으로 확인")
            success_count_by_cls[cls_name] += 1
            continue

        warn = ""
        record_err = None
        result_type = st.node.attrs.get("resultType", "")
        result_map_id = st.node.attrs.get("resultMap", "")
        rm_info: dict[str, Any] = {}
        if not result_type and result_map_id:
            rm_key = result_map_id.split(".")[-1]
            rm_info = result_maps_by_ns.get(st.ns, {}).get(result_map_id) or result_maps_by_ns.get(st.ns, {}).get(rm_key) or {}
            result_type = rm_info.get("type", "")

        if not err and st.kind == "select":
            if has_unresolved_include:
                warn = " (? include 미해결 — mapper-run으로 확인)"
            elif result_type:
                fields, is_record, find_warn = find_dto_fields(result_type, search_roots)
                aliases = extract_select_aliases_from_sql(raw_sql) if fields else None
                if aliases is not None and rm_info.get("col_map"):
                    col_map = rm_info["col_map"]
                    raw_names = select_output_names(raw_sql) or []
                    for rn in raw_names:
                        if rn and rn.strip('"').lower() in col_map:
                            aliases.add(col_map[rn.strip('"').lower()])
                if find_warn:
                    warn = f" ⚠ ({find_warn})"
                elif fields and aliases is not None:
                    # MyBatis 자동 매핑은 대소문자를 가리지 않는다.
                    alias_lc = {a.lower() for a in aliases}
                    missing_in_select = {f for f in fields if f.lower() not in alias_lc}
                    if missing_in_select:
                        sorted_missing = sorted(missing_in_select)
                        missing_str = ", ".join(sorted_missing)
                        if is_record:
                            dto_cls = result_type.replace("$", ".").split(".")[-1]
                            first_snake = to_snake(sorted_missing[0])
                            record_err = (
                                f"record {dto_cls} 열 누락: {missing_str} — "
                                f"결과에 열이 없으면 행이 있을 때 MyBatis가 'Constructor auto-mapping … not found in the result set'으로 500을 낸다. "
                                f"SELECT에 'NULL AS {first_snake}'을 더하거나 열 목록 <sql>을 공유하세요."
                            )
                        else:
                            warn = f" ⚠ (필드 누락: {missing_str})"

        if err is None and record_err is None:
            results_by_cls[cls_name].append(f"{st.sid} ✅{warn}")
            success_count_by_cls[cls_name] += 1
        elif record_err is not None:
            has_failure = True
            fail_msg = f"{st.sid} ❌ {record_err}"
            results_by_cls[cls_name].append(fail_msg)
            failure_details_by_cls[cls_name].append(fail_msg)
            failure_count_by_cls[cls_name] += 1
        else:
            has_failure = True
            fail_msg = f"{st.sid} ❌ {err} (L{st.line})"
            results_by_cls[cls_name].append(fail_msg)
            failure_details_by_cls[cls_name].append(fail_msg)
            failure_count_by_cls[cls_name] += 1

    lines = []
    all_classes = sorted(set(list(results_by_cls.keys()) + list(xml_errors_by_cls.keys())))
    if summary:
        for cls_name in all_classes:
            succ = success_count_by_cls.get(cls_name, 0)
            fail = failure_count_by_cls.get(cls_name, 0)
            xml_errs = xml_errors_by_cls.get(cls_name, [])
            if xml_errs:
                lines.append(f"{cls_name}: XML ❌ {len(xml_errs)} / ✅ {succ} / ❌ {fail}")
                for err_detail in xml_errs:
                    lines.append(f"  - {err_detail}")
            else:
                lines.append(f"{cls_name}: ✅ {succ} / ❌ {fail}")
            for fail_detail in failure_details_by_cls.get(cls_name, []):
                lines.append(f"  - {fail_detail}")
    else:
        for cls_name in all_classes:
            xml_errs = xml_errors_by_cls.get(cls_name, [])
            items = results_by_cls.get(cls_name, [])
            lines.append(f"{cls_name}: " + " / ".join(xml_errs + items))

    summary_text = "\n".join(lines)
    return ToolResult(
        ok=not has_failure,
        data={
            "summary": summary_text,
            "total": len(targets) + sum(len(v) for v in xml_errors_by_cls.values()),
            "results": results_by_cls,
            "xml_errors": xml_errors_by_cls,
        },
        error=None if not has_failure else "일부 SQL 또는 매퍼 XML 검증 실패",
    )
