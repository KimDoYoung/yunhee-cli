import re
import sys
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.mybatis_render import get_all_statements
from yunhee.tools.as_is.mybatis_render import render as mr_render

NAME = "sql"
DESCRIPTION = "MyBatis 매퍼 statement 분석 및 실행 가능 SQL 펼치기"
TARGET_HELP = "<ns.id>"
FORMATS = ("md", "sql", "code", "json")
EXAMPLES = [
    "yunhee analysis sql emp00_trans_info.selectByText",
    "yunhee analysis sql emp00_trans_info.selectByText --param companyId=28000 --param transCode=100 -o sql",
    "yunhee analysis sql sys05_user_role.selectByRoleId --param roleId=28120 --count",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """대상 statement를 찾아 준비한다."""
    src_root, _ = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    stmts = get_all_statements(src_root)

    st = stmts.get(target)
    if not st:
        st = next((s for s in stmts.values() if s.sid == target), None)
    if not st:
        raise ValueError(f"statement를 찾을 수 없습니다: {target}")

    # 파라미터 수집
    raw_params = opts.get("param", [])
    params_dict: dict[str, Any] = {}
    if isinstance(raw_params, list):
        for p in raw_params:
            if "=" in p:
                k, v = p.split("=", 1)
                params_dict[k.strip()] = v.strip()

    return {
        "key": st.key,
        "statement": st,
        "params": params_dict,
        "src_root": src_root,
        "statements": stmts,
    }


def _fold_cte_and_section(sql: str, no_cte: bool = False, section: str = "") -> str:
    """CTE를 접거나 WHERE 절 이후만 분리하여 반환한다 (#16)."""
    m_with = re.search(r"^\s*WITH\b", sql, re.IGNORECASE)
    cte_names = []
    main_sql = sql
    if m_with:
        depth = 0
        in_str = False
        k = m_with.end()
        n = len(sql)
        main_start = -1
        while k < n:
            c = sql[k]
            if c == "'":
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif depth == 0:
                    m_kw = re.match(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", sql[k:], re.IGNORECASE)
                    if m_kw:
                        main_start = k
                        break
            k += 1
        if main_start != -1:
            cte_part = sql[m_with.end() : main_start]
            cte_names = re.findall(r"\b([a-zA-Z0-9_]+)\s+(?:\([^)]*\)\s+)?AS\s*\(", cte_part, re.IGNORECASE)
            main_sql = sql[main_start:]

    if (no_cte or section in ("where", "no-cte", "no_cte")) and cte_names:
        cte_summary = f"-- CTE {', '.join(cte_names)} (생략)\n"
        sql = cte_summary + main_sql

    if section == "where":
        depth = 0
        in_str = False
        k = 0
        n = len(main_sql)
        where_start = -1
        while k < n:
            c = main_sql[k]
            if c == "'":
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif depth == 0:
                    m_wh = re.match(r"\bWHERE\b", main_sql[k:], re.IGNORECASE)
                    if m_wh:
                        where_start = k
                        break
            k += 1
        if where_start != -1:
            cte_prefix = f"-- CTE {', '.join(cte_names)} (생략)\n" if cte_names else ""
            return cte_prefix + main_sql[where_start:].strip()

    return sql


def _regex_ctes(body: str, includes: list[str], st: Any, stmts: dict[str, Any]) -> tuple[list[str], set[str]]:
    """정규식 추정: include 조각과 본문의 CTE 이름 (AST 해석에 실패했을 때만 쓴다)."""
    cte_names: list[str] = []
    cte_set: set[str] = set()

    def _extract_ctes(text: str) -> None:
        for m in re.finditer(r"\bWITH\s+(?:RECURSIVE\s+)?([a-zA-Z0-9_]+)\s+AS\s*\(|,\s*([a-zA-Z0-9_]+)\s+AS\s*\(", text, re.IGNORECASE):
            c_name = m.group(1) or m.group(2)
            if c_name and c_name.lower() not in cte_set:
                cte_names.append(c_name)
                cte_set.add(c_name.lower())

    for inc in includes:
        target_st = stmts.get(inc) or stmts.get(f"{st.ns}.{inc}") or next((s for s in stmts.values() if s.sid == inc), None)
        if target_st:
            fm = re.search(rf'<{target_st.kind}\b[^>]*\bid="{re.escape(target_st.sid)}"[^>]*>(.*?)</{target_st.kind}>', target_st.raw, re.DOTALL)
            if fm:
                _extract_ctes(fm.group(1))

    _extract_ctes(body)
    return cte_names, cte_set


def _regex_tables(body: str, cte_set: set[str]) -> tuple[list[str], list[str]]:
    """정규식 추정: (테이블, 테이블 자리에 쓰인 함수). AST 해석에 실패했을 때만 쓴다."""
    table_matches = re.finditer(
        r"\b(?:FROM|JOIN|UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+([a-zA-Z0-9_]+)(\s*\()?",
        body,
        re.IGNORECASE,
    )
    table_names: list[str] = []
    seen_tables: set[str] = set()
    table_funcs: list[str] = []
    for tm in table_matches:
        t = tm.group(1)
        is_func_call = bool(tm.group(2))
        t_lower = t.lower()
        if t_lower in ("where", "select", "set", "values", "into", "dual"):
            continue
        if is_func_call:
            if t not in table_funcs:
                table_funcs.append(t)
            continue
        if t_lower in cte_set:
            continue
        if t_lower not in seen_tables:
            seen_tables.add(t_lower)
            table_names.append(t)
    return table_names, table_funcs


def _regex_changes(body: str) -> list[str]:
    """정규식 추정: 변경 대상(INSERT/UPDATE/DELETE 테이블). AST 해석에 실패했을 때만 쓴다."""
    change_targets: list[str] = []
    seen_changes: set[str] = set()
    for cm in re.finditer(r"\b(UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+([a-zA-Z0-9_]+)", body, re.IGNORECASE):
        act = cm.group(1).upper()
        if act.startswith("INSERT"):
            act = "INSERT"
        elif act.startswith("DELETE"):
            act = "DELETE"
        item = f"{act} {cm.group(2)}"
        if item not in seen_changes:
            seen_changes.add(item)
            change_targets.append(item)
    return change_targets


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if opts is None:
        opts = {}

    st = obj["statement"]
    params = obj["params"]
    stmts = obj["statements"]
    key = obj["key"]
    count_opt = opts.get("count", False)

    # 1. code 모드
    if fmt == "code":
        # XML 원문 및 include 조각 주석
        xml_path = st.rel
        raw_xml = st.raw
        # statement 본문 먼저 추출
        m = re.search(rf'<{st.kind}\b[^>]*\bid="{re.escape(st.sid)}"[^>]*>.*?</{st.kind}>', raw_xml, re.DOTALL)
        body = m.group(0) if m else raw_xml

        # include 조각 검색은 본문 내에서만 수행
        includes = re.findall(r'<include\s+refid="([^"]+)"', body)
        inc_comments = []
        missing_inc = []
        for inc in includes:
            target_st = stmts.get(inc) or stmts.get(f"{st.ns}.{inc}") or next((s for s in stmts.values() if s.sid == inc), None)
            if target_st:
                inc_comments.append(f"<!-- include {inc} → {target_st.rel}:{target_st.line} -->")
            else:
                missing_inc.append(inc)

        header = f"<!-- {st.key} ({xml_path}:{st.line}) -->\n"
        if inc_comments:
            header += "\n".join(inc_comments) + "\n"

        full_code = header + body
        if missing_inc:
            full_code += "\n" + "\n".join(f"⚠ include 미발견: {inc}" for inc in sorted(set(missing_inc)))

        grep_pat = opts.get("grep")
        if grep_pat:
            c_ctx = int(opts.get("context") or opts.get("context_lines") or opts.get("C") or 2)
            code_lines = full_code.splitlines()
            matching_indices: set[int] = set()
            for idx, line in enumerate(code_lines):
                if re.search(grep_pat, line):
                    for j in range(max(0, idx - c_ctx), min(len(code_lines), idx + c_ctx + 1)):
                        matching_indices.add(j)

            if not matching_indices:
                return ""

            out_blocks = []
            curr_block = []
            prev_idx = None
            for idx in sorted(matching_indices):
                if prev_idx is not None and idx > prev_idx + 1:
                    out_blocks.append("\n".join(curr_block))
                    curr_block = []
                curr_block.append(code_lines[idx])
                prev_idx = idx
            if curr_block:
                out_blocks.append("\n".join(curr_block))
            return "\n---\n".join(out_blocks)

        return full_code

    # 2. sql 모드 또는 --count
    if fmt == "sql" or count_opt:
        sql, missing = mr_render(key, params=params, mode="params", statements=stmts)
        for m_p in missing:
            sys.stderr.write(f"⚠ 값 없음: {m_p}\n")

        if count_opt:
            import psycopg

            from yunhee.tools.sql_runner import get_connection_string

            db_name = opts.get("db", "asseterpdb")
            conn_str = get_connection_string(db_name)
            try:
                with psycopg.connect(conn_str, autocommit=False) as conn:
                    conn.read_only = True
                    with conn.cursor() as cur:
                        is_single_agg = bool(re.search(r"^\s*SELECT\s+(?:count|sum|avg|max|min)\s*\(", sql, re.IGNORECASE))
                        if is_single_agg:
                            cur.execute(sql)
                            rows = cur.fetchall()
                            if len(rows) == 1 and cur.description and len(cur.description) == 1:
                                val = rows[0][0]
                                col_name = cur.description[0][0].lower()
                                if col_name.startswith("count") or col_name == "count":
                                    label = "count"
                                elif col_name.startswith("sum") or col_name == "sum":
                                    label = "sum"
                                else:
                                    label = col_name
                                return f"rows=1 {label}={val}"
                            return str(len(rows))

                        count_sql = f"SELECT count(*) FROM (\n{sql}\n) z"
                        cur.execute(count_sql)
                        row = cur.fetchone()
                        return str(row[0]) if row else "0"
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"SQL 실행 실패: {e}\n")
                return "0"

        no_cte_opt = bool(opts.get("no_cte"))
        section_opt = str(opts.get("section") or "").lower()
        return _fold_cte_and_section(sql, no_cte=no_cte_opt, section=section_opt)

    # 3. md 모드 (요약)
    raw_xml = st.raw
    m = re.search(rf'<{st.kind}\b[^>]*\bid="{re.escape(st.sid)}"[^>]*>(.*?)</{st.kind}>', raw_xml, re.DOTALL)
    body = m.group(1) if m else raw_xml

    # 파라미터 목록
    found_params = sorted(set(re.findall(r"[#$]\{(\w+)\}", body)))
    bind_vars = re.findall(r'<bind\s+name="([^"]+)"\s+value="([^"]+)"', body)

    # include 목록
    includes = re.findall(r'<include\s+refid="([^"]+)"', body)
    inc_list = []
    for inc in includes:
        target_st = stmts.get(inc) or stmts.get(f"{st.ns}.{inc}") or next((s for s in stmts.values() if s.sid == inc), None)
        if target_st:
            inc_list.append(f"`{inc}` ({target_st.rel}:{target_st.line})")
        else:
            inc_list.append(f"`{inc}`")

    # choose / if 분기
    branches = []
    for w in re.finditer(r'<when\s+test="([^"]+)"', body):
        branches.append(f"when: `{w.group(1)}`")
    for i in re.finditer(r'<if\s+test="([^"]+)"', body):
        branches.append(f"if: `{i.group(1)}`")

    # 테이블·CTE·변경 대상: include까지 전개한 SQL을 AST로 해석한다. 해석할 수 없으면 정규식으로 추정한다.
    from yunhee.tools.sql_parse import parse_statement

    res = parse_statement(st.key, stmts)
    parsed = res.data if res.ok and not res.data.fallback else None
    if parsed is not None:
        cte_names = list(parsed.ctes)
        cte_set = {c.lower() for c in cte_names}
        table_names = list(parsed.tables)
        table_funcs = list(parsed.table_functions)
        change_targets = [f"{act} {tbl}" for act, tbl in parsed.writes]
    else:
        cte_names, cte_set = _regex_ctes(body, includes, st, stmts)
        table_names, table_funcs = _regex_tables(body, cte_set)
        change_targets = _regex_changes(body)

    funcs = sorted(set(re.findall(r"\b(f_\w+|to_\w+|coalesce|get\w+|find_\w+)\s*\(", body, re.IGNORECASE)))
    for tf in table_funcs:
        if tf not in funcs and tf.lower() not in {f.lower() for f in funcs}:
            funcs.append(tf)

    # 최상위 별칭 목록 (select 전용)
    output_names = []
    if st.kind == "select":
        if parsed is not None:
            output_names = parsed.output_names or []
        else:
            from yunhee.tools.as_is.sql_checker import select_output_names
            output_names = select_output_names(body) or []

    # ORDER BY
    order_m = re.search(r"\bORDER\s+BY\s+([^;\n<]+)", body, re.IGNORECASE)
    order_by = order_m.group(1).strip() if order_m else None

    if fmt == "json":
        import json

        return json.dumps(
            {
                "id": st.key,
                "file": str(st.rel),
                "line": st.line,
                "kind": st.kind,
                "params": found_params,
                "tables": table_names,
                "functions": funcs,
                "order_by": order_by,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    lines = [f"### `{st.key}` ({st.rel}:{st.line})"]
    if inc_list:
        lines.append(f"- **include**: {', '.join(inc_list)}")
    if bind_vars:
        b_str = ", ".join(f"{b[0]} ← `{b[1]}`" for b in bind_vars)
        lines.append(f"- **bind**: {b_str}")
    if found_params:
        lines.append(f"- **파라미터**: {', '.join(found_params)}")
    if branches:
        lines.append(f"- **조건 분기**: {', '.join(branches)}")
    if table_names:
        lines.append(f"- **테이블**: {', '.join(table_names)}")
    if cte_names:
        lines.append(f"- **CTE**: {', '.join(cte_names)}")
    if funcs:
        tf_lower = {tf.lower() for tf in table_funcs}
        func_displays = [
            f"{fn} (열은 yunhee table {fn})" if fn.lower() in tf_lower or fn.lower().startswith("get") else fn
            for fn in funcs
        ]
        lines.append(f"- **함수**: {', '.join(func_displays)}")
    if st.kind in ("insert", "update", "delete"):
        if change_targets:
            lines.append(f"- **변경 대상**: {', '.join(change_targets)}")
    elif output_names:
        clean_names = [str(n) for n in output_names if n]
        if clean_names:
            lines.append(f"- **출력 별칭**: {', '.join(clean_names[:10])}{' ...' if len(clean_names) > 10 else ''}")
    if order_by:
        lines.append(f"- **ORDER BY**: `{order_by}`")
    if st.kind != "select":
        lines.append(f"- 본문: yunhee analysis sql {st.key} -o code")

    return "\n".join(lines)
