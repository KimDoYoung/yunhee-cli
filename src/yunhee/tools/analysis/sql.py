import re
import sys
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.mybatis_render import get_all_statements
from yunhee.tools.as_is.mybatis_render import render as mr_render

NAME = "sql"
DESCRIPTION = "MyBatis 매퍼 statement 분석 및 실행 가능 SQL 펼치기"
TARGET_HELP = "<ns.id>"
FORMATS = ("md", "sql", "code")
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
        # include 조각 검색
        includes = re.findall(r'<include\s+refid="([^"]+)"', raw_xml)
        inc_comments = []
        for inc in includes:
            target_st = stmts.get(inc) or stmts.get(f"{st.ns}.{inc}") or next((s for s in stmts.values() if s.sid == inc), None)
            if target_st:
                inc_comments.append(f"<!-- include {inc} → {target_st.rel}:{target_st.line} -->")
            else:
                inc_comments.append(f"<!-- include {inc} (미발견) -->")

        header = f"<!-- {st.key} ({xml_path}:{st.line}) -->\n"
        if inc_comments:
            header += "\n".join(inc_comments) + "\n"
        # statement 본문
        m = re.search(rf'<{st.kind}\b[^>]*\bid="{re.escape(st.sid)}"[^>]*>.*?</{st.kind}>', raw_xml, re.DOTALL)
        body = m.group(0) if m else raw_xml
        return header + body

    # 2. sql 모드 또는 --count
    if fmt == "sql" or count_opt:
        sql, missing = mr_render(key, params=params, mode="params", statements=stmts)
        for m_p in missing:
            sys.stderr.write(f"⚠ 값 없음: {m_p}\n")

        if count_opt:
            import psycopg

            from yunhee.tools.sql_runner import get_connection_string

            count_sql = f"SELECT count(*) FROM (\n{sql}\n) z"
            db_name = opts.get("db", "asseterpdb")
            conn_str = get_connection_string(db_name)
            try:
                with psycopg.connect(conn_str, autocommit=False) as conn:
                    conn.read_only = True
                    with conn.cursor() as cur:
                        cur.execute(count_sql)
                        row = cur.fetchone()
                        return str(row[0]) if row else "0"
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"SQL 실행 실패: {e}\n")
                return "0"

        return sql

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

    # 테이블 / DB 함수
    tables = sorted(set(re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)|\bJOIN\s+([a-zA-Z0-9_]+)", body, re.IGNORECASE)))
    table_names = [t[0] or t[1] for t in tables if (t[0] or t[1]).lower() not in ("where", "select", "set")]
    funcs = sorted(set(re.findall(r"\b(f_\w+|to_\w+|coalesce)\s*\(", body, re.IGNORECASE)))

    # 최상위 별칭 목록
    from yunhee.tools.as_is.sql_checker import select_output_names
    output_names = select_output_names(body) or []

    # ORDER BY
    order_m = re.search(r"\bORDER\s+BY\s+([^;\n<]+)", body, re.IGNORECASE)
    order_by = order_m.group(1).strip() if order_m else None

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
    if funcs:
        lines.append(f"- **함수**: {', '.join(funcs)}")
    if output_names:
        clean_names = [str(n) for n in output_names if n]
        if clean_names:
            lines.append(f"- **출력 별칭**: {', '.join(clean_names[:10])}{' ...' if len(clean_names) > 10 else ''}")
    if order_by:
        lines.append(f"- **ORDER BY**: `{order_by}`")

    return "\n".join(lines)
