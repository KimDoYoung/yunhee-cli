"""공통코드 조회 도구 (`biz-code`).

sys08_code_kind 및 sys09_code 테이블을 조회하여 공통코드 목록과 사용 여부,
회사별 우선 적용 규칙(f_cdnm 호환)을 출력하고, 존재하지 않는 코드종류에 대한 유사 추천을 제공한다.
"""

from __future__ import annotations

import re
from typing import Any

from yunhee.tools.sql_runner import get_connection_string


def get_code_rows(
    kind_code: str,
    company_code: str | None = None,
    db_name: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    """공통코드 종류를 조회하고 행 목록 또는 유사 종류 추천 목록을 반환한다."""
    import psycopg
    from psycopg.rows import dict_row

    db_url = get_connection_string(db_name)
    if not db_url:
        raise ValueError("DB 연결 정보(YUNHEE_DB)가 설정되지 않았습니다.")

    with psycopg.connect(db_url, autocommit=False) as conn:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            # 1. sys08_code_kind 조회
            cur.execute(
                """
                SELECT sys08_code_kind_id, sys08_kind_cd, sys08_kind_nm, sys08_sys_yn
                FROM sys08_code_kind
                WHERE sys08_kind_cd = %s
                LIMIT 1;
                """,
                (kind_code,),
            )
            kind_row = cur.fetchone()

            # 2. 존재하지 않는 경우 유사 코드종류 검색
            if not kind_row:
                stem = re.sub(r"(?:TypeCode|Code|Type|Cd)+$", "", kind_code, flags=re.IGNORECASE)
                search_word = f"%{stem}%" if len(stem) >= 2 else f"%{kind_code}%"
                cur.execute(
                    """
                    SELECT sys08_kind_cd
                    FROM sys08_code_kind
                    WHERE sys08_kind_cd ILIKE %s
                    ORDER BY sys08_kind_cd
                    LIMIT 5;
                    """,
                    (search_word,),
                )
                similar_rows = cur.fetchall()
                similar = [r["sys08_kind_cd"] for r in similar_rows if r.get("sys08_kind_cd")]
                return None, [], similar

            kind_info = dict(kind_row)
            kind_id = kind_info["sys08_code_kind_id"]

            # 3. 회사 코드 -> 회사 ID 변환
            company_id: int | None = None
            if company_code:
                cur.execute(
                    "SELECT sys01_company_id FROM sys01_company WHERE sys01_loc_nm = %s LIMIT 1;",
                    (company_code,),
                )
                comp_row = cur.fetchone()
                if comp_row and comp_row.get("sys01_company_id"):
                    company_id = int(comp_row["sys01_company_id"])

            # 4. sys09_code 목록 조회
            if company_id is not None:
                cur.execute(
                    """
                    SELECT c.sys09_company_id, c.sys09_code, c.sys09_name, c.sys09_seq, c.sys09_close_yn, c.sys09_apply_date
                    FROM sys09_code c
                    WHERE c.sys09_code_kind_id = %s AND c.sys09_company_id IN (0, %s)
                    ORDER BY c.sys09_company_id, c.sys09_seq, c.sys09_code;
                    """,
                    (kind_id, company_id),
                )
            else:
                cur.execute(
                    """
                    SELECT c.sys09_company_id, c.sys09_code, c.sys09_name, c.sys09_seq, c.sys09_close_yn, c.sys09_apply_date
                    FROM sys09_code c
                    WHERE c.sys09_code_kind_id = %s
                    ORDER BY c.sys09_company_id, c.sys09_seq, c.sys09_code;
                    """,
                    (kind_id,),
                )

            rows = [dict(r) for r in cur.fetchall()]
            kind_info["company_id"] = company_id
            return kind_info, rows, []


def search_code_kinds(like_word: str, db_name: str | None = None) -> list[dict[str, Any]]:
    """단어가 포함된 공통코드 종류 목록을 검색한다."""
    import psycopg
    from psycopg.rows import dict_row

    db_url = get_connection_string(db_name)
    if not db_url:
        raise ValueError("DB 연결 정보(YUNHEE_DB)가 설정되지 않았습니다.")

    with psycopg.connect(db_url, autocommit=False) as conn:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sys08_kind_cd, sys08_kind_nm, sys08_sys_yn
                FROM sys08_code_kind
                WHERE sys08_kind_cd ILIKE %s OR sys08_kind_nm ILIKE %s
                ORDER BY sys08_kind_cd
                LIMIT 20;
                """,
                (f"%{like_word}%", f"%{like_word}%"),
            )
            return [dict(r) for r in cur.fetchall()]


def format_code_table(
    kind_info: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    """공통코드 목록을 마크다운 표로 변환한다."""
    comp_id = kind_info.get("company_id")
    has_comp = comp_id is not None
    sys_yn = kind_info.get("sys08_sys_yn") == "true"

    headers = ["회사", "코드", "이름", "순서", "사용", "적용일"]
    if has_comp:
        headers.append("쓰임")

    lines = [
        f"### {kind_info['sys08_kind_cd']} ({kind_info.get('sys08_kind_nm', '')})",
        f"| {' | '.join(headers)} |",
        f"|{':---|' * len(headers)}",
    ]

    # 회사 전용 행이 존재하는 코드 집합
    comp_specific_codes = {r["sys09_code"] for r in rows if r["sys09_company_id"] == comp_id}

    for r in rows:
        cid = r["sys09_company_id"]
        c_disp = "0(공통)" if cid == 0 else str(cid)
        use_str = "Y" if r["sys09_close_yn"] == "false" else "N"
        apply_dt = str(r["sys09_apply_date"] or "")

        row_cells = [
            c_disp,
            str(r["sys09_code"]),
            str(r["sys09_name"] or ""),
            str(r["sys09_seq"] or ""),
            use_str,
            apply_dt,
        ]

        if has_comp:
            # f_cdnm 규칙: sys_yn == True 이면 0(공통) 행 우선, False 이면 회사 행 우선
            is_used = False
            if sys_yn:
                is_used = (cid == 0)
            elif cid == comp_id or (cid == 0 and r["sys09_code"] not in comp_specific_codes):
                is_used = True

            used_str = "V" if is_used else ""
            row_cells.append(used_str)

        lines.append(f"| {' | '.join(row_cells)} |")

    return "\n".join(lines)
