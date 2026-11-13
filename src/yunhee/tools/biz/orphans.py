"""고아 행(삭제 후 남아있는 부모 없는 자식 데이터) 탐지 도구."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from yunhee.tools.sql_runner import get_connection_string


def get_table_metadata(conn: psycopg.Connection) -> tuple[dict[str, str], dict[str, list[str]]]:
    """모든 테이블의 PK 컬럼명과 전체 컬럼명 목록을 반환한다."""
    pk_map: dict[str, str] = {}
    cols_map: dict[str, list[str]] = {}

    with conn.cursor(row_factory=dict_row) as cur:
        # 1. 컬럼 목록
        cur.execute(
            """
            SELECT c.relname, a.attname
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p')
              AND n.nspname = 'public'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum;
            """
        )
        for row in cur.fetchall():
            tbl = row["relname"]
            col = row["attname"]
            cols_map.setdefault(tbl, []).append(col)

        # 2. PK 목록
        cur.execute(
            """
            SELECT c.relname, a.attname
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
            WHERE con.contype = 'p'
              AND n.nspname = 'public'
              AND c.relkind IN ('r', 'p');
            """
        )
        for row in cur.fetchall():
            tbl = row["relname"]
            col = row["attname"]
            if tbl not in pk_map:  # 복합키의 경우 첫 번째 컬럼
                pk_map[tbl] = col

    return pk_map, cols_map


def get_fk_relations(
    conn: psycopg.Connection,
    target_table: str | None = None,
) -> list[dict[str, Any]]:
    """테이블 간의 외래키성 참조 관계 (child_table, fk_col, parent_table, parent_pk, child_pk)를 수집한다."""
    pk_map, cols_map = get_table_metadata(conn)
    relations: list[dict[str, Any]] = []

    # 1. 공식 FK 제약조건
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.relname AS child_tbl,
                   ca.attname AS fk_col,
                   p.relname AS parent_tbl,
                   pa.attname AS parent_pk
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_class p ON p.oid = con.confrelid
            JOIN pg_attribute ca ON ca.attrelid = con.conrelid AND ca.attnum = con.conkey[1]
            JOIN pg_attribute pa ON pa.attrelid = con.confrelid AND pa.attnum = con.confkey[1]
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE con.contype = 'f' AND n.nspname = 'public';
            """
        )
        for r in cur.fetchall():
            c_tbl = r["child_tbl"]
            if target_table and c_tbl != target_table:
                continue
            child_pk = pk_map.get(c_tbl, r["fk_col"])
            relations.append({
                "child_table": c_tbl,
                "fk_col": r["fk_col"],
                "parent_table": r["parent_tbl"],
                "parent_pk": r["parent_pk"],
                "child_pk": child_pk,
            })

    # 2. 명명 규칙 기반 FK 탐색 (FK 제약조건이 없는 AssetERP 레거시 테이블 대응)
    seen_pairs = {(rel["child_table"], rel["fk_col"]) for rel in relations}

    for child_tbl, cols in cols_map.items():
        if target_table and child_tbl != target_table:
            continue
        child_pk = pk_map.get(child_tbl)
        for col in cols:
            if col == child_pk or not col.endswith("_id") or col in ("company_id", "org_id", "user_id"):
                continue
            if (child_tbl, col) in seen_pairs:
                continue

            # col이 다른 테이블의 PK와 일치하는지 확인
            # 예: ics21_checklist_l_class_id == ics21_checklist_l_class.ics21_checklist_l_class_id
            for p_tbl, p_pk in pk_map.items():
                if p_tbl == child_tbl:
                    continue
                if col == p_pk or col == f"{p_tbl}_id":
                    relations.append({
                        "child_table": child_tbl,
                        "fk_col": col,
                        "parent_table": p_tbl,
                        "parent_pk": p_pk,
                        "child_pk": child_pk or col,
                    })
                    seen_pairs.add((child_tbl, col))
                    break

    return relations


def find_child_tables(parent_table: str, db_name: str | None = None) -> list[str]:
    """특정 테이블을 부모로 참조하는 연관 자식 테이블 목록을 반환한다."""
    conn_str = get_connection_string(db_name)
    if not conn_str:
        return []

    try:
        with psycopg.connect(conn_str, autocommit=False) as conn:
            conn.read_only = True
            rels = get_fk_relations(conn)
            children = {r["child_table"] for r in rels if r["parent_table"] == parent_table and r["child_table"] != parent_table}
            return sorted(children)
    except Exception:  # noqa: BLE001
        return []


def find_orphans(
    table: str | None = None,
    company: str | None = None,
    db_name: str | None = None,
) -> list[dict[str, Any]]:
    """부모 행이 없는 고아 행들을 탐지하여 목록과 삭제 SQL을 반환한다 (읽기 전용)."""
    conn_str = get_connection_string(db_name)
    if not conn_str:
        return []

    results: list[dict[str, Any]] = []

    try:
        with psycopg.connect(conn_str, autocommit=False) as conn:
            conn.read_only = True
            relations = get_fk_relations(conn, target_table=table)

            # company_id 결정
            company_id_val: int | None = None
            if company:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT company_id FROM sys01_company WHERE company_cd = %s OR company_nm = %s LIMIT 1", (company, company))
                        row = cur.fetchone()
                        if row:
                            company_id_val = int(row[0])
                except Exception:  # noqa: BLE001, S110
                    pass

            with conn.cursor(row_factory=dict_row) as cur:
                for rel in relations:
                    c_tbl = rel["child_table"]
                    fk_col = rel["fk_col"]
                    p_tbl = rel["parent_table"]
                    p_pk = rel["parent_pk"]
                    c_pk = rel["child_pk"]

                    where_extra = ""
                    # 자식 테이블에 company_id 컬럼이 있는지 확인
                    if company_id_val is not None:
                        cur.execute(
                            "SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid WHERE c.relname=%s AND a.attname='company_id'",
                            (c_tbl,),
                        )
                        if cur.fetchone():
                            where_extra = f" AND c.company_id = {company_id_val}"

                    query = f"""
                        SELECT c.{c_pk} AS orphan_id
                        FROM {c_tbl} c
                        LEFT JOIN {p_tbl} p ON c.{fk_col} = p.{p_pk}
                        WHERE c.{fk_col} IS NOT NULL AND p.{p_pk} IS NULL{where_extra}
                        LIMIT 11;
                    """
                    try:
                        cur.execute(query)
                        rows = cur.fetchall()
                        if rows:
                            count_query = f"""
                                SELECT count(*)
                                FROM {c_tbl} c
                                LEFT JOIN {p_tbl} p ON c.{fk_col} = p.{p_pk}
                                WHERE c.{fk_col} IS NOT NULL AND p.{p_pk} IS NULL{where_extra};
                            """
                            cur.execute(count_query)
                            cnt_row = cur.fetchone()
                            total_cnt = cnt_row["count"] if cnt_row else len(rows)

                            orphan_ids = [r["orphan_id"] for r in rows[:10]]
                            ids_str = ", ".join(str(i) for i in orphan_ids)
                            del_sql = f"DELETE FROM {c_tbl} WHERE {c_pk} IN ({ids_str});"

                            results.append({
                                "child_table": c_tbl,
                                "fk_col": fk_col,
                                "parent_table": p_tbl,
                                "parent_pk": p_pk,
                                "child_pk": c_pk,
                                "count": total_cnt,
                                "ids": orphan_ids,
                                "delete_sql": del_sql,
                            })
                    except Exception:  # noqa: BLE001, S112
                        continue
    except Exception:  # noqa: BLE001, S110
        pass

    return results
