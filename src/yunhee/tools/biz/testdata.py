"""화면별 테스트 데이터 생성(`test-insert-data`) 및 트랜잭션 코드 기반 롤백(`test-rollback-data`) 도구.

동작 개요:
1. `<login>` (예: `kfstest-121-1111` 또는 `kfstest/121/1111`)에서 회사(company_id)·사원(emp_id/person_id)·부서(org_id) 컨텍스트를 해석한다.
2. `<screen_no>` (예: `1234`)에서 화면의 메인/상세 대상 테이블과 조회 API/SQL을 정적으로 추출한다.
3. 대상 테이블의 기존 샘플 행을 복제·변형(Clone & Mutate)하거나 스키마·공통코드 기반으로 합성하여
   로그인 계정과 오늘 날짜 컨텍스트에 맞는 테스트 행을 `INSERT ... RETURNING <pk>`로 삽입한다.
4. 발급된 `transaction-code` 매니페스트를 `.yunhee/test-data/<tx_code>.json`에 저장한다.
5. `test-rollback-data` 호출 시 매니페스트 역순(자식 → 부모)으로 삽입된 행(및 파생 자식 행)을 원자적으로 삭제한다.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from yunhee import config
from yunhee.tools.base import ToolResult
from yunhee.tools.sql_runner import get_connection_string

# 일반 업무 화면에서 단순 조인/코드 참조용으로만 쓰여 INSERT 대상에서 제외할 시스템·공통 마스터 테이블
SYSTEM_MASTER_TABLES: frozenset[str] = frozenset(
    {
        "sys01_company",
        "sys02_config",
        "sys02_company_config",
        "sys03_company_menu",
        "sys04_role",
        "sys05_user_role",
        "sys06_menu",
        "sys07_menu_btn",
        "sys08_code_kind",
        "sys09_code",
        "sys10_file",
        "sys11_log",
        "sys12_login_log",
        "emp00_trans_info",
        "org00_org",
        "tdm30_role_allc",
        "dual",
    }
)

# 타 도메인(예: ast, fnd, pay, att 등)에서 단순 사원/조직 조인용으로 쓰일 때 제외할 인사/조직 기본 마스터
CROSS_DOMAIN_MASTER_TABLES: frozenset[str] = frozenset(
    {
        "emp01_person",
        "emp02_emp",
        "emp04_add_title",
        "org01_org",
        "org01_org_code",
        "org02_org_tree",
    }
)

# 매뉴얼·테스트 겸용 상시 가명 풀 (실제 회사/펀드명과 겹치지 않는 가상임이 명백한 단어만 사용)
PSEUDO_KO_POOL: tuple[str, ...] = (
    "샘플",
    "예시",
    "데모",
    "가나다",
    "ABC",
    "견본",
    "가상",
    "임시",
    "예제",
    "모의",
    "알파",
    "베타",
    "모모",
    "테스트",
    "XYZ",
    "XX",
)

PSEUDO_EN_POOL: tuple[str, ...] = (
    "Sample",
    "Demo",
    "Example",
    "ABC",
    "XYZ",
    "Alpha",
    "Beta",
    "Test",
)

PSEUDO_PERSON_POOL: tuple[str, ...] = (
    "홍길동",
    "김샘플",
    "이예시",
    "박데모",
    "최가상",
    "정임시",
    "김철수",
    "이영희",
)

# 금융/업무 공통 키워드 (길이 내림차순으로 매칭해 앞부분 고유명사만 가명으로 치환)
_DOMAIN_KEYWORDS: tuple[str, ...] = tuple(
    sorted(
        (
            "전문투자형사모투자신탁",
            "일반사모투자신탁",
            "전문투자형",
            "일반사모",
            "사모투자신탁",
            "사모투자",
            "투자신탁",
            "투자자산운용",
            "자산운용",
            "투자증권",
            "투자회사",
            "부동산신탁",
            "부동산",
            "특별자산",
            "혼합자산",
            "인베스트먼트",
            "파트너스",
            "캐피탈",
            "홀딩스",
            "어드바이저스",
            "자산관리",
            "펀드",
            "신탁",
            "투자",
            "증권",
            "운용",
            "조합",
            "빌딩",
            "타워",
            "센터",
            "프로젝트",
            "계약",
            "제1호",
            "제2호",
            "제3호",
            "1호",
            "2호",
            "3호",
        ),
        key=len,
        reverse=True,
    )
)

_CORP_PREFIX_RE = re.compile(
    r"^(?P<corp>(?:\(주\)|㈜|\(유\)|주식회사\s*|유한회사\s*|\(사\)|\(재\)|\[[^\]]+\]\s*))(?P<rest>.*)$"
)
_HANGUL_RE = re.compile(r"[가-힣]")
_LEADING_EN_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9&._-]*")
_LEADING_HANGUL_BEFORE_NUM_RE = re.compile(r"^[가-힣A-Za-z]{2,6}(?=\d|제\d|호|차|\()")

_PERSON_NAME_SUFFIXES: tuple[str, ...] = (
    "_emp_nm",
    "_person_nm",
    "_user_nm",
    "_ceo_nm",
    "_mngr_nm",
    "_writer_nm",
    "_reg_nm",
    "_mod_nm",
    "_owner_nm",
    "_repr_nm",
    "_chrg_nm",
    "_appr_nm",
    "_req_nm",
)

_TEXT_NAME_SUFFIXES: tuple[str, ...] = (
    "_nm",
    "_name",
    "_title",
    "_title_text",
    "_subj",
    "_subject",
    "_rmk",
    "_remark",
    "_note",
    "_desc",
    "_memo",
    "_reason",
    "_content",
    "_contents",
    "_summary",
)

_AMOUNT_SUFFIXES: tuple[str, ...] = (
    "_amt",
    "_amount",
    "_bal",
    "_balance",
    "_cost",
    "_fee",
    "_tax",
    "_price",
    "_eval_amt",
    "_book_amt",
    "_acq_amt",
    "_settle_amt",
)

_QTY_SUFFIXES: tuple[str, ...] = ("_qty", "_cnt", "_count", "_vol", "_volume")
_RATE_SUFFIXES: tuple[str, ...] = ("_rate", "_ratio", "_pct", "_rt")


@dataclass
class LoginContext:
    raw: str
    company_cd: str
    user: str
    password: str | None
    company_id: int = 28000
    emp_id: int = 0
    emp_no: str = ""
    emp_nm: str = ""
    emp_email: str = ""
    org_id: int = 0
    today: datetime.date = field(default_factory=datetime.date.today)

    @property
    def login_key(self) -> str:
        """소유자 대조용 정규화 키 (`company_cd-user`)."""
        return f"{self.company_cd.lower()}-{self.user.lower()}"

    @property
    def yyyymmdd(self) -> str:
        return self.today.strftime("%Y%m%d")

    @property
    def yyyymm(self) -> str:
        return self.today.strftime("%Y%m")

    @property
    def yyyy(self) -> str:
        return self.today.strftime("%Y")


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    udt_name: str
    max_length: int | None
    is_nullable: bool
    column_default: str | None
    is_pk: bool = False


@dataclass
class TableMeta:
    name: str
    columns: list[ColumnMeta]
    pk_cols: list[str]
    unique_cols: set[str] = field(default_factory=set)
    fk_map: dict[str, tuple[str, str]] = field(default_factory=dict)  # col -> (parent_table, parent_pk)


def get_test_data_dir(work_dir: Path | None = None) -> Path:
    """트랜잭션 매니페스트 저장 디렉터리(`.yunhee/test-data`)를 반환한다."""
    base = Path(work_dir) if work_dir else config.WORK_DIR
    d = base / ".yunhee" / "test-data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_local_db_write_safe(db_url: str) -> None:
    """원격 DB 쓰기를 차단하고 로컬(또는 명시 허용된 호스트) DB만 허용한다."""
    parsed = urlparse(db_url)
    host = parsed.hostname or "localhost"

    allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    extra_hosts = os.getenv("YUNHEE_DB_WRITE_HOSTS", "")
    if extra_hosts:
        allowed_hosts.update(h.strip() for h in extra_hosts.split(",") if h.strip())

    if host not in allowed_hosts:
        raise ValueError(
            f"오류: 원격 DB({host})에는 테스트 데이터를 생성/삭제할 수 없습니다. 로컬 DB 환경에서만 실행 가능합니다."
        )


def parse_login_spec(raw_login: str) -> tuple[str, str, str | None]:
    """`kfstest-121-1111`, `kfstest/121/1111`, `login=kfstest-121-1111` 등을 (company, user, password)로 분리한다."""
    clean = raw_login.strip()
    if clean.lower().startswith("login="):
        clean = clean[6:].strip()

    if "/" in clean:
        parts = [p.strip() for p in clean.split("/") if p.strip()]
    elif "-" in clean:
        parts = [p.strip() for p in clean.split("-") if p.strip()]
    else:
        raise ValueError(
            f"오류: 로그인 인자 형식이 올바르지 않습니다 ({raw_login}). 예: kfstest-121-1111 또는 kfstest/121/1111"
        )

    if len(parts) < 2:
        raise ValueError(
            f"오류: 로그인 인자에는 최소 회사코드와 사번이 포함되어야 합니다 ({raw_login}). 예: kfstest-121-1111"
        )

    company = parts[0]
    user = parts[1]
    password = "-".join(parts[2:]) if "-" in clean and len(parts) > 2 else (parts[2] if len(parts) > 2 else None)
    return company, user, password


def resolve_login_context(
    raw_login: str,
    conn: psycopg.Connection | None = None,
    db_name: str | None = None,
) -> LoginContext:
    """로그인 스펙 문자열을 해석하고 DB에서 회사 ID·사원 ID·부서 ID를 조회한다."""
    company_cd, user, password = parse_login_spec(raw_login)
    ctx = LoginContext(
        raw=raw_login,
        company_cd=company_cd,
        user=user,
        password=password,
        emp_no=user,
    )

    own_conn = False
    if conn is None:
        db_url = get_connection_string(db_name)
        if not db_url:
            return ctx
        conn = psycopg.connect(db_url, autocommit=False)
        conn.read_only = True
        own_conn = True

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            # 1. 회사 조회 (sys01_company)
            cur.execute(
                """
                SELECT sys01_company_id, sys01_loc_nm
                FROM sys01_company
                WHERE LOWER(sys01_loc_nm) = LOWER(%s)
                   OR sys01_company_id::text = %s
                LIMIT 1;
                """,
                (company_cd, company_cd),
            )
            comp_row = cur.fetchone()
            if not comp_row:
                raise ValueError(f"존재하지 않는 회사 코드입니다: {company_cd}")
            ctx.company_id = int(comp_row["sys01_company_id"])

            # 2. 사원 조회 (emp01_person)
            cur.execute(
                """
                SELECT emp01_person_id, emp01_emp_no, emp01_kor_nm, emp01_email_addr
                FROM emp01_person
                WHERE emp01_company_id = %s
                  AND (emp01_emp_no = %s OR emp01_person_id::text = %s)
                LIMIT 1;
                """,
                (ctx.company_id, user, user),
            )
            emp_row = cur.fetchone()
            if not emp_row:
                # 회사 내 해당 사번이 없으면 같은 회사의 임의 재직 사원 폴백 조회 전에 에러 안내
                raise ValueError(f"사원을 찾을 수 없습니다: 사번/ID={user} (회사: {company_cd}, company_id={ctx.company_id})")

            ctx.emp_id = int(emp_row["emp01_person_id"])
            ctx.emp_no = str(emp_row.get("emp01_emp_no") or user)
            ctx.emp_nm = str(emp_row.get("emp01_kor_nm") or "테스트사원")
            ctx.emp_email = str(emp_row.get("emp01_email_addr") or "").strip()

            # 3. 부서/겸직 조회 (emp04_add_title 또는 emp00_trans_info)
            try:
                cur.execute(
                    """
                    SELECT emp00_org_code_id
                    FROM emp00_trans_info
                    WHERE emp00_person_id = %s
                    ORDER BY emp00_trans_date DESC
                    LIMIT 1;
                    """,
                    (ctx.emp_id,),
                )
                org_row = cur.fetchone()
                if org_row and org_row.get("emp00_org_code_id"):
                    ctx.org_id = int(org_row["emp00_org_code_id"])
            except Exception:  # noqa: BLE001
                conn.rollback()

            if not ctx.org_id:
                try:
                    cur.execute(
                        """
                        SELECT org01_org_code_id
                        FROM org01_org_code
                        WHERE org01_company_id = %s
                        ORDER BY org01_org_code_id ASC
                        LIMIT 1;
                        """,
                        (ctx.company_id,),
                    )
                    org_fallback = cur.fetchone()
                    if org_fallback and org_fallback.get("org01_org_code_id"):
                        ctx.org_id = int(org_fallback["org01_org_code_id"])
                except Exception:  # noqa: BLE001
                    conn.rollback()
    finally:
        if own_conn:
            conn.close()

    return ctx


def filter_candidate_tables(
    raw_tables: list[str],
    screen_name: str = "",
) -> list[str]:
    """화면 연관 테이블 목록에서 공통/마스터 테이블을 제외하고 도메인 우선순위로 정렬한다."""
    # 화면 이름에서 도메인 접두사 추출 (예: Ast01_Tab_Asset -> ast01, ast)
    m_prefix = re.match(r"^([a-zA-Z]+)(\d+)?", screen_name or "")
    dom_alpha = m_prefix.group(1).lower() if m_prefix else ""
    dom_full = f"{dom_alpha}{m_prefix.group(2)}" if (m_prefix and m_prefix.group(2)) else dom_alpha

    cleaned: list[str] = []
    seen: set[str] = set()
    for t in raw_tables:
        tl = t.strip().lower()
        if not tl or tl in seen:
            continue
        if "." in tl:
            tl = tl.split(".")[-1]
        seen.add(tl)

        # sys10_file 등 무조건 제외할 가상/시스템 테이블
        if tl in ("dual", "emp00_trans_info", "org00_org", "tdm30_role_allc", "sys10_file"):
            continue

        # 화면 자체가 sys 도메인이 아닌데 sys 마스터 테이블인 경우 제외
        if dom_alpha != "sys" and (tl in SYSTEM_MASTER_TABLES or tl.startswith(("sys0", "sys1"))):
            continue

        # 화면 자체가 emp/org 도메인이 아닌데 인사/조직 기본 테이블인 경우 제외
        if dom_alpha not in ("emp", "org") and tl in CROSS_DOMAIN_MASTER_TABLES:
            continue

        cleaned.append(tl)

    # 정렬 우선순위:
    # 0순위: 화면 접두어(예: ast01_)와 정확히 일치하는 테이블
    # 1순위: 도메인 영문 접두어(예: ast*)와 일치하는 테이블
    # 2순위: 그 외 업무 테이블 (테이블 번호 오름차순으로 부모가 자식보다 앞에 오도록 정렬)
    def _sort_key(tbl: str) -> tuple[int, str]:
        if dom_full and tbl.startswith(f"{dom_full}_"):
            return (0, tbl)
        if dom_alpha and tbl.startswith(dom_alpha):
            return (1, tbl)
        return (2, tbl)

    cleaned.sort(key=_sort_key)
    return cleaned


def analyze_screen_targets(
    screen_no: str,
    conn: psycopg.Connection | None = None,
    root_dir: Path | None = None,
    override_tables: list[str] | None = None,
) -> dict[str, Any]:
    """화면번호(또는 화면 클래스명)로부터 대상 테이블 목록과 메타정보, 조회 API 경로를 추출한다."""
    clean_no = screen_no.strip().lstrip("#")
    screen_name = ""
    menu_title = ""
    apis: list[str] = []
    sql_ids: list[str] = []
    raw_tables: list[str] = []

    try:
        from yunhee.tools.trace.screen_desc import describe_screens

        desc_data = describe_screens(clean_no, tobe=root_dir)
        screens = desc_data.get("screens") or []
        if screens and screens[0].get("found"):
            item = screens[0]
            menu = item.get("menu") or {}
            tobe = item.get("tobe") or {}
            asis = item.get("asis") or {}

            screen_name = (
                tobe.get("main_screen")
                or menu.get("tobe_screen")
                or menu.get("asis_screen")
                or ""
            )
            menu_title = menu.get("name") or ""
            apis = list(tobe.get("apis") or [])
            sql_ids = list(tobe.get("sql_ids") or [])

            # TOBE 테이블 + ASIS 테이블 결합
            for t in (tobe.get("tables") or []) + (asis.get("tables") or []):
                if t not in raw_tables:
                    raw_tables.append(t)
    except Exception:  # noqa: BLE001, S110
        pass

    # 사용자가 --table로 명시 지정한 경우 최우선 적용
    if override_tables:
        target_tables = [t.strip().lower() for t in override_tables if t.strip()]
    else:
        target_tables = filter_candidate_tables(raw_tables, screen_name=screen_name)

    # 만약 정적 분석 색인에서 테이블을 못 찾았지만 화면 클래스명 접두어(예: Ast01_...)가 있고 DB 연결이 있는 경우
    if not target_tables and screen_name and conn is not None:
        m_prefix = re.match(r"^([a-zA-Z]+\d+)_", screen_name)
        if m_prefix:
            prefix_lower = m_prefix.group(1).lower() + "_"
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'r'
                      AND n.nspname = 'public'
                      AND c.relname LIKE %s
                    ORDER BY c.relname ASC;
                    """,
                    (f"{prefix_lower}%",),
                )
                target_tables = [r["relname"] for r in cur.fetchall()]

    # 실제 DB에 존재하는 물리 테이블만 남기고 FK 부모→자식 순서로 정렬
    if conn is not None and target_tables:
        existing_tables: list[str] = []
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'p')
                  AND n.nspname = 'public'
                  AND c.relname = ANY(%s);
                """,
                (target_tables,),
            )
            valid_set = {r["relname"] for r in cur.fetchall()}
            existing_tables = [t for t in target_tables if t in valid_set]

        target_tables = _order_tables_by_dependency(conn, existing_tables)

    # 너무 많은 보조 테이블에 불필요하게 넣지 않도록 제한 (단, override_tables 제외)
    # 특히 화면 접두어(예: dcr10_)와 일치하는 메인 테이블이 존재하면 그 테이블(및 동일 접두어 테이블)만 선택하여
    # 팝업에서 딸려온 무관한 테이블(예: dcr01_class_tree)에 불필요한 INSERT가 일어나는 것을 방지한다.
    if not override_tables and target_tables:
        m_scr = re.match(r"^([a-zA-Z]+\d+)_", screen_name or "")
        if m_scr:
            exact_prefix = m_scr.group(1).lower() + "_"
            exact_matches = [t for t in target_tables if t.startswith(exact_prefix)]
            if exact_matches:
                target_tables = exact_matches
        if len(target_tables) > 2:
            target_tables = target_tables[:2]

    return {
        "screen_no": clean_no,
        "screen_name": screen_name,
        "menu_title": menu_title,
        "target_tables": target_tables,
        "all_candidate_tables": raw_tables,
        "apis": apis,
        "sql_ids": sql_ids,
    }


def _order_tables_by_dependency(conn: psycopg.Connection, tables: list[str]) -> list[str]:
    """부모 테이블이 자식 테이블보다 먼저 오도록 정렬한다."""
    if len(tables) <= 1:
        return tables

    try:
        from yunhee.tools.biz.orphans import get_fk_relations

        rels = get_fk_relations(conn)
        table_set = set(tables)
        # parent -> children
        deps: dict[str, set[str]] = {t: set() for t in tables}
        for r in rels:
            c_tbl = r["child_table"]
            p_tbl = r["parent_table"]
            if c_tbl in table_set and p_tbl in table_set and c_tbl != p_tbl:
                deps[c_tbl].add(p_tbl)  # c_tbl depends on p_tbl

        ordered: list[str] = []
        visited: set[str] = set()

        def _visit(t: str) -> None:
            if t in visited:
                return
            visited.add(t)
            for parent in deps.get(t, ()):
                _visit(parent)
            ordered.append(t)

        for t in tables:
            _visit(t)
        return ordered
    except Exception:  # noqa: BLE001
        return tables


def inspect_table_meta(conn: psycopg.Connection, table_name: str) -> TableMeta:
    """PostgreSQL 카탈로그에서 대상 테이블의 컬럼·PK·Unique·FK 메타데이터를 조회한다."""
    with conn.cursor(row_factory=dict_row) as cur:
        # 1. PK 컬럼 조회
        cur.execute(
            """
            SELECT a.attname
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
            WHERE con.contype = 'p'
              AND n.nspname = 'public'
              AND c.relname = %s
            ORDER BY array_position(con.conkey, a.attnum);
            """,
            (table_name,),
        )
        pk_cols = [r["attname"] for r in cur.fetchall()]

        # 2. Unique 제약 컬럼 조회
        cur.execute(
            """
            SELECT a.attname
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
            WHERE con.contype = 'u'
              AND n.nspname = 'public'
              AND c.relname = %s;
            """,
            (table_name,),
        )
        unique_cols = {r["attname"] for r in cur.fetchall()}

        # 3. FK 제약 조회
        cur.execute(
            """
            SELECT ca.attname AS fk_col,
                   p.relname AS parent_tbl,
                   pa.attname AS parent_pk
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_class p ON p.oid = con.confrelid
            JOIN pg_attribute ca ON ca.attrelid = con.conrelid AND ca.attnum = con.conkey[1]
            JOIN pg_attribute pa ON pa.attrelid = con.confrelid AND pa.attnum = con.confkey[1]
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE con.contype = 'f'
              AND n.nspname = 'public'
              AND c.relname = %s;
            """,
            (table_name,),
        )
        fk_map = {r["fk_col"]: (r["parent_tbl"], r["parent_pk"]) for r in cur.fetchall()}

        # 4. 전체 컬럼 메타 조회
        cur.execute(
            """
            SELECT column_name,
                   data_type,
                   udt_name,
                   character_maximum_length,
                   is_nullable,
                   column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position;
            """,
            (table_name,),
        )
        col_rows = cur.fetchall()

    columns: list[ColumnMeta] = []
    for r in col_rows:
        cname = r["column_name"]
        columns.append(
            ColumnMeta(
                name=cname,
                data_type=r["data_type"],
                udt_name=r["udt_name"],
                max_length=r["character_maximum_length"],
                is_nullable=(r["is_nullable"] == "YES"),
                column_default=r["column_default"],
                is_pk=(cname in pk_cols),
            )
        )

    # PK 제약조건이 카탈로그에 없을 때 첫 번째 *_id 컬럼을 PK로 추론
    if not pk_cols and columns:
        id_cols = [c.name for c in columns if c.name.endswith("_id")]
        pk_cols = [id_cols[0]] if id_cols else [columns[0].name]
        for c in columns:
            if c.name in pk_cols:
                c.is_pk = True

    return TableMeta(
        name=table_name,
        columns=columns,
        pk_cols=pk_cols,
        unique_cols=unique_cols,
        fk_map=fk_map,
    )


def _fetch_sample_rows(
    conn: psycopg.Connection,
    meta: TableMeta,
    company_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """테이블에서 기존 샘플 행을 조회한다 (동일 회사 행 우선, 없으면 전체에서 최신 행)."""
    comp_cols = [
        c.name
        for c in meta.columns
        if c.name.endswith(("_company_id", "_comp_id")) or c.name in ("company_id", "comp_id")
    ]
    order_clause = ", ".join(f'"{pk}" DESC' for pk in meta.pk_cols) if meta.pk_cols else "1"

    with conn.cursor(row_factory=dict_row) as cur:
        if comp_cols:
            comp_col = comp_cols[0]
            cur.execute(
                f'SELECT * FROM "{meta.name}" WHERE "{comp_col}" = %s ORDER BY {order_clause} LIMIT %s;',
                (company_id, limit),
            )
            rows = cur.fetchall()
            if rows:
                return [dict(r) for r in rows]

        cur.execute(f'SELECT * FROM "{meta.name}" ORDER BY {order_clause} LIMIT %s;', (limit,))
        return [dict(r) for r in cur.fetchall()]


def _allocate_next_numeric_pk(
    conn: psycopg.Connection,
    table_name: str,
    pk_col: str,
    count: int,
) -> list[int]:
    """수동 채번 정수형 PK 컬럼에 대해 충돌 없는 새 PK 목록을 할당한다."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f'SELECT COALESCE(MAX("{pk_col}"), 0) AS max_pk FROM "{table_name}";')
        row = cur.fetchone()
        max_pk = int(row["max_pk"]) if row and row["max_pk"] is not None else 0
        base = max(max_pk, 900000)
        return [base + i + 1 for i in range(count)]


def _truncate_str(val: str, max_len: int | None) -> str:
    if max_len is not None and max_len > 0 and len(val) > max_len:
        return val[:max_len]
    return val


def _normalize_json_val(val: Any) -> Any:
    """psycopg 반환값(Decimal, date, datetime 등)을 JSON 직렬화 가능한 기본 타입으로 변환한다."""
    if isinstance(val, Decimal):
        return int(val) if val == int(val) else float(val)
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    return val


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)


def _fetch_company_names(conn: psycopg.Connection) -> list[str]:
    """sys01_company에 등록된 실제 고객사명/약칭 목록을 길이 내림차순으로 조회한다."""
    names: set[str] = set()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'sys01_company'
                  AND data_type IN ('character varying', 'character', 'text');
                """
            )
            col_rows = cur.fetchall()
            target_cols = [
                r["column_name"]
                for r in col_rows
                if isinstance(r, dict)
                and isinstance(r.get("column_name"), str)
                and any(k in r["column_name"].lower() for k in ("nm", "name", "loc"))
            ]
            if not target_cols:
                return []

            cols_sql = ", ".join(f'"{c}"' for c in target_cols)
            cur.execute(f"SELECT {cols_sql} FROM sys01_company;")
            for row in cur.fetchall():
                if not isinstance(row, dict):
                    continue
                for val in row.values():
                    if not isinstance(val, str):
                        continue
                    cleaned = val.strip()
                    if len(cleaned) < 2:
                        continue
                    names.add(cleaned)
                    # 법인 표기 및 금융 접미어를 떼어낸 브랜드 코어도 함께 수집
                    core = _CORP_PREFIX_RE.sub(lambda m: m.group("rest"), cleaned).strip()
                    for kw in ("투자자산운용", "자산운용", "투자증권", "인베스트먼트", "파트너스", "캐피탈", "홀딩스"):
                        if core.endswith(kw) and len(core) > len(kw) + 1:
                            names.add(core[: -len(kw)].strip())
                    if len(core) >= 2:
                        names.add(core)
    except Exception:  # noqa: BLE001
        return []

    pseudo_lower = {p.lower() for p in PSEUDO_KO_POOL + PSEUDO_EN_POOL}
    filtered = [n for n in names if len(n) >= 2 and n.lower() not in pseudo_lower]
    filtered.sort(key=len, reverse=True)
    return filtered


def _is_person_name_col(col_name: str) -> bool:
    clower = col_name.lower()
    if clower.endswith(_PERSON_NAME_SUFFIXES):
        return True
    return clower in ("emp_nm", "person_nm", "user_nm", "ceo_nm", "mngr_nm", "writer_nm")


def _is_english_name_col(col_name: str) -> bool:
    clower = col_name.lower()
    return any(k in clower for k in ("_eng_", "_en_")) or clower.endswith(("_eng_nm", "_en_nm"))


def pseudonymize_text(
    orig: str,
    idx: int,
    *,
    col_name: str = "",
    company_names: Sequence[str] = (),
    max_length: int | None = None,
) -> str:
    """원본 텍스트의 업무 구조는 살리면서 고유명사/앞부분만 가상임이 명백한 가명으로 살짝 치환한다."""
    tag_ko = PSEUDO_KO_POOL[idx % len(PSEUDO_KO_POOL)]
    tag_en = PSEUDO_EN_POOL[idx % len(PSEUDO_EN_POOL)]
    person_nm = PSEUDO_PERSON_POOL[idx % len(PSEUDO_PERSON_POOL)]

    if _is_person_name_col(col_name):
        if _is_english_name_col(col_name):
            return _truncate_str(f"{tag_en} User {idx + 1}", max_length)
        return _truncate_str(person_nm, max_length)

    text = orig.strip()
    is_en_col = _is_english_name_col(col_name)

    if not text:
        fallback = f"{tag_en} Item {idx + 1}" if is_en_col else f"{tag_ko} 항목 {idx + 1}"
        return _truncate_str(fallback, max_length)

    # 1순위: DB에 등록된 실제 고객사명/약칭이 문자열 어디에 있든 가명으로 치환
    replaced_company = False
    is_en_text = is_en_col or (not _HANGUL_RE.search(text) and bool(re.search(r"[A-Za-z]", text)))
    repl_tag = tag_en if is_en_text else tag_ko

    for comp_nm in company_names:
        if len(comp_nm) < 2:
            continue
        pattern = re.compile(re.escape(comp_nm), re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(repl_tag, text)
            replaced_company = True

    # 이미 가명 풀 단어로 시작하고 회사명 치환도 끝났다면 그대로 유지
    all_tags = PSEUDO_KO_POOL + PSEUDO_EN_POOL
    m_corp = _CORP_PREFIX_RE.match(text)
    corp_prefix = m_corp.group("corp") if m_corp else ""
    rest = m_corp.group("rest").strip() if m_corp else text

    if any(rest.startswith(t) for t in all_tags):
        return _truncate_str(f"{corp_prefix}{rest}", max_length)

    # 2순위: 영문 명칭/문장 — 첫 영문 단어를 영문 가명으로 교체
    if is_en_text:
        if not replaced_company:
            if _LEADING_EN_WORD_RE.match(rest):
                rest = _LEADING_EN_WORD_RE.sub(tag_en, rest, count=1)
            else:
                rest = f"{tag_en} {rest}"
        return _truncate_str(f"{corp_prefix}{rest}", max_length)

    # 3순위: 한글 금융/업무 공통 키워드 앞부분(고유명사)만 가명으로 살짝 교체
    # 예: '엘엔에스전문투자형사모투자신탁 제1호(부동산)_제2종' -> '샘플전문투자형사모투자신탁 제1호(부동산)_제2종'
    best_pos: int | None = None
    for kw in _DOMAIN_KEYWORDS:
        pos = rest.find(kw)
        if pos > 0 and (best_pos is None or pos < best_pos):
            best_pos = pos

    if best_pos is not None:
        had_space = rest[best_pos - 1].isspace()
        sep = " " if had_space else ""
        result = f"{corp_prefix}{tag_ko}{sep}{rest[best_pos:]}"
        return _truncate_str(result, max_length)

    # 4순위: 일반 한글/혼합 문자열 살짝 바꾸기
    if not replaced_company:
        tokens = rest.split()
        if len(tokens) >= 2:
            rest = " ".join([tag_ko, *tokens[1:]])
        else:
            m_lead = _LEADING_HANGUL_BEFORE_NUM_RE.match(rest)
            if m_lead:
                rest = f"{tag_ko}{rest[m_lead.end():]}"
            elif len(rest) >= 4:
                cut = 2 if len(rest) <= 5 else 3
                rest = f"{tag_ko}{rest[cut:]}"
            else:
                rest = f"{tag_ko}{idx + 1}"

    return _truncate_str(f"{corp_prefix}{rest}", max_length)


def pseudonymize_identifier(
    col_name: str,
    orig: Any,
    idx: int,
    max_length: int | None = None,
) -> str | None:
    """전화번호·계좌번호·사업자번호·이메일·주소 등 민감 식별 컬럼이면 포맷을 유지한 더미 값으로 치환한다."""
    clower = col_name.lower()
    orig_str = str(orig or "").strip()
    has_hyphen = "-" in orig_str

    if clower.endswith(("_email", "_email_addr", "_mail", "_mail_addr")) or clower in ("email", "email_addr"):
        return _truncate_str(f"sample{idx + 1}@example.com", max_length)

    if clower.endswith(("_url", "_homepage", "_home_url", "_web_url")) or clower in ("url", "homepage"):
        return _truncate_str(f"https://sample{idx + 1}.example.com", max_length)

    if clower.endswith(("_zip", "_zip_cd", "_zip_no", "_post_no", "_post_cd")):
        return _truncate_str(f"0730{idx + 1}", max_length)

    if clower.endswith(("_addr2", "_dtl_addr", "_detail_addr", "_addr_dtl")):
        return _truncate_str(f"샘플빌딩 {idx + 1}층", max_length)
    if clower.endswith(("_addr", "_addr1", "_address")) or clower in ("addr", "address"):
        return _truncate_str(f"서울특별시 영등포구 샘플로 {100 + idx}", max_length)

    if (
        clower.endswith(("_hp", "_hp_no", "_mobile", "_mobile_no", "_cell_no")) or orig_str.startswith("010")
    ) and any(k in clower for k in ("_tel", "_hp", "_phone", "_mobile", "_cell", "_fax")):
        val = f"010-0000-{idx + 1:04d}" if (has_hyphen or not orig_str) else f"0100000{idx + 1:04d}"
        return _truncate_str(val, max_length)

    if clower.endswith(("_tel", "_tel_no", "_phone", "_phone_no", "_fax", "_fax_no")) or clower in (
        "tel",
        "tel_no",
        "phone",
        "fax",
    ):
        val = f"02-0000-{idx + 1:04d}" if (has_hyphen or not orig_str) else f"020000{idx + 1:04d}"
        return _truncate_str(val, max_length)

    if clower.endswith(("_biz_no", "_saup_no", "_bsn_no", "_bizno", "_business_no")):
        val = f"123-45-{idx + 1:05d}" if (has_hyphen or not orig_str) else f"12345{idx + 1:05d}"
        return _truncate_str(val, max_length)

    if clower.endswith(("_corp_no", "_corp_reg_no", "_jumin_no", "_res_no", "_rrn", "_ssn")):
        val = f"110111-{idx + 1:07d}" if (has_hyphen or not orig_str) else f"110111{idx + 1:07d}"
        return _truncate_str(val, max_length)

    if clower.endswith(("_acct_no", "_acc_no", "_account_no", "_bank_acct", "_bank_acct_no")):
        val = f"100-000-{idx + 1:06d}" if (has_hyphen or not orig_str) else f"100000{idx + 1:06d}"
        return _truncate_str(val, max_length)

    return None


def pseudonymize_numeric(
    col_name: str,
    orig: Any,
    idx: int,
    dtype: str,
) -> int | float | Decimal | None:
    """금액·수량·비율 컬럼의 실제 규모 유추를 막기 위해 자릿수만 비슷하게 유지한 깔끔한 라운드 값으로 변형한다."""
    clower = col_name.lower()
    is_amt = clower.endswith(_AMOUNT_SUFFIXES) or clower in ("amt", "amount", "price", "balance")
    is_qty = clower.endswith(_QTY_SUFFIXES) or clower in ("qty", "cnt", "count")
    is_rate = clower.endswith(_RATE_SUFFIXES) or clower in ("rate", "ratio")

    if not (is_amt or is_qty or is_rate):
        return None

    is_int_type = dtype in ("integer", "bigint", "smallint")
    is_decimal = isinstance(orig, Decimal)

    if orig is not None:
        try:
            num = float(orig)
        except (TypeError, ValueError):
            num = 0.0
        if num == 0:
            return 0 if is_int_type else (Decimal(0) if is_decimal else 0)
        sign = -1 if num < 0 else 1
        abs_num = abs(num)
    else:
        sign = 1
        abs_num = 0.0

    if is_rate:
        val = round(1.5 + (idx % 7) * 1.0, 2) * sign
        if is_int_type:
            return round(val)
        return Decimal(str(val)) if is_decimal else val

    if is_qty:
        if abs_num >= 1000:
            base = 10 ** max(2, len(str(int(abs_num))) - 1)
            q_val = sign * base * ((idx % 5) + 1)
        else:
            q_val = sign * 10 * ((idx % 9) + 1)
        return Decimal(q_val) if is_decimal else q_val

    # is_amt: 원본 자릿수(규모감)를 비슷하게 유지하되 깔끔한 라운드 금액으로 치환
    if abs_num >= 10:
        digits = len(str(int(abs_num)))
        unit = 10 ** max(3, digits - 1)
        a_val = sign * unit * ((idx % 5) + 1)
    else:
        a_val = sign * 1_000_000 * ((idx % 5) + 1)
    return Decimal(a_val) if is_decimal else a_val


def _lookup_company_parent_ids(
    conn: psycopg.Connection,
    parent_table: str,
    parent_pk: str,
    company_id: int,
    cache: dict[tuple[str, str], tuple[bool, list[Any]]],
) -> tuple[bool, list[Any]]:
    """부모 테이블이 회사 ID 컬럼을 가지면 현재 회사 소속 PK 목록을 조회해 반환한다.

    Returns:
        (has_company_col, pk_values)
    """
    key = (parent_table, parent_pk)
    if key in cache:
        return cache[key]

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s;
                """,
                (parent_table,),
            )
            cols = [
                r["column_name"]
                for r in cur.fetchall()
                if isinstance(r, dict) and isinstance(r.get("column_name"), str)
            ]
            comp_cols = [
                c for c in cols if c.endswith(("_company_id", "_comp_id")) or c in ("company_id", "comp_id")
            ]
            if not comp_cols:
                cache[key] = (False, [])
                return cache[key]

            comp_col = comp_cols[0]
            cur.execute(
                f'SELECT "{parent_pk}" FROM "{parent_table}" WHERE "{comp_col}" = %s ORDER BY "{parent_pk}" DESC LIMIT 5;',
                (company_id,),
            )
            vals = [
                r[parent_pk]
                for r in cur.fetchall()
                if isinstance(r, dict) and r.get(parent_pk) is not None
            ]
            cache[key] = (True, vals)
            return cache[key]
    except Exception:  # noqa: BLE001
        cache[key] = (False, [])
        return cache[key]


def synthesize_table_rows(
    conn: psycopg.Connection,
    meta: TableMeta,
    ctx: LoginContext,
    screen_no: str,
    count: int = 3,
    parent_inserted_pks: dict[str, list[Any]] | None = None,
    company_names: Sequence[str] | None = None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Clone & Mutate(1순위) 및 스키마 합성(2순위) 전략으로 삽입할 행 데이터를 생성하며, 항상 가명화를 적용한다."""
    samples = _fetch_sample_rows(conn, meta, ctx.company_id, limit=max(count, 5))
    parent_inserted_pks = parent_inserted_pks or {}
    comp_names = list(company_names) if company_names is not None else _fetch_company_names(conn)
    fk_parent_cache: dict[tuple[str, str], tuple[bool, list[Any]]] = {}
    warned_fks: set[str] = set()

    # PK가 단일 숫자형 컬럼인지 확인
    numeric_pk_values: dict[str, list[int]] = {}
    for pk_col in meta.pk_cols:
        col_meta = next((c for c in meta.columns if c.name == pk_col), None)
        if col_meta and col_meta.data_type in ("integer", "bigint", "smallint", "numeric"):
            numeric_pk_values[pk_col] = _allocate_next_numeric_pk(conn, meta.name, pk_col, count)

    short_tag = secrets.token_hex(2)
    synthesized: list[dict[str, Any]] = []

    for idx in range(count):
        base_row = dict(samples[idx % len(samples)]) if samples else {}
        new_row: dict[str, Any] = {}

        for col in meta.columns:
            cname = col.name
            clower = cname.lower()
            dtype = col.data_type.lower()
            is_str_type = dtype in ("character varying", "varchar", "character", "char", "text")
            is_num_type = dtype in ("integer", "bigint", "smallint", "numeric", "decimal", "real", "double precision")

            # 0. PK 컬럼
            if col.is_pk:
                if cname in numeric_pk_values:
                    new_row[cname] = numeric_pk_values[cname][idx]
                else:
                    # 문자열 PK
                    candidate = f"S{screen_no}_{short_tag}_{idx + 1}"
                    new_row[cname] = _truncate_str(candidate, col.max_length)
                continue

            # 1. 방금 상위 테이블에서 삽입한 부모 PK 참조 컬럼인 경우 연결
            matched_parent_val = None
            if cname in meta.fk_map:
                ptbl, _ = meta.fk_map[cname]
                if parent_inserted_pks.get(ptbl):
                    p_vals = parent_inserted_pks[ptbl]
                    matched_parent_val = p_vals[idx % len(p_vals)]
            else:
                # 명명 규칙으로 직전 부모 테이블 PK와 매칭되는지 확인
                for ptbl, p_vals in parent_inserted_pks.items():
                    if p_vals and (clower.endswith("_id") and ptbl.split("_")[0] in clower):
                        matched_parent_val = p_vals[idx % len(p_vals)]
                        break

            if matched_parent_val is not None:
                new_row[cname] = matched_parent_val
                continue

            # 2. 회사 ID / 회사 코드 컬럼 치환
            if (
                clower.endswith(("_company_id", "_comp_id")) or clower in ("company_id", "comp_id")
            ) and dtype in ("integer", "bigint", "smallint", "numeric"):
                new_row[cname] = ctx.company_id
                continue
            if clower.endswith(("_company_cd", "_comp_cd")) or clower in ("company_cd", "comp_cd"):
                new_row[cname] = _truncate_str(ctx.company_cd, col.max_length)
                continue

            # 3. 사원 ID / 등록자 / 담당자 / 사번 치환 (텍스트 이름·이메일은 아래 가명화 단계에서 처리)
            if (
                (
                    clower.endswith(
                        (
                            "_emp_id",
                            "_person_id",
                            "_user_id",
                            "_reg_emp_id",
                            "_mod_emp_id",
                            "_req_emp_id",
                            "_chrg_emp_id",
                            "_mngr_emp_id",
                            "_writer_id",
                        )
                    )
                    or clower in ("emp_id", "person_id", "user_id", "reg_emp_id", "mod_emp_id")
                )
                and dtype in ("integer", "bigint", "smallint", "numeric")
                and ctx.emp_id
            ):
                new_row[cname] = ctx.emp_id
                continue
            if clower.endswith("_emp_no") or clower == "emp_no":
                new_row[cname] = _truncate_str(ctx.emp_no, col.max_length)
                continue

            # 4. 부서 / 조직 ID 치환
            if (
                (
                    clower.endswith(("_org_id", "_org_code_id", "_dept_id"))
                    or clower in ("org_id", "org_code_id", "dept_id")
                )
                and ctx.org_id
                and dtype in ("integer", "bigint", "smallint", "numeric")
            ):
                new_row[cname] = ctx.org_id
                continue

            # 5. 삭제 여부 / 사용 여부 정규화 (화면 조회 필터에 걸리지 않도록 보장)
            if clower.endswith("_del_yn") or clower == "del_yn":
                if dtype == "boolean":
                    new_row[cname] = False
                else:
                    new_row[cname] = _truncate_str("N", col.max_length)
                continue
            if clower.endswith("_use_yn") or clower == "use_yn":
                if dtype == "boolean":
                    new_row[cname] = True
                else:
                    new_row[cname] = _truncate_str("Y", col.max_length)
                continue

            # 6. 날짜 / 기간 컬럼: 오늘 기준 최근 1개월(오늘-28일 ~ 오늘-1일) 내로 행별 분산
            # - 일반일/종료일: 오늘 - (1, 3, 5...)일
            # - 시작일(_start_, _from_, _strt_, _bgn_): 종료일보다 앞선 오늘 - (10, 13, 16...)일
            is_start_date = any(k in clower for k in ("_start_", "_from_", "_strt_", "_bgn_", "_open_"))
            days_ago = min(10 + idx * 3, 28) if is_start_date else min(1 + idx * 2, 25)
            target_date = ctx.today - datetime.timedelta(days=days_ago)

            if dtype == "date":
                new_row[cname] = target_date
                continue
            if "timestamp" in dtype:
                new_row[cname] = datetime.datetime.combine(target_date, datetime.time(9, 0, 0))
                continue
            if is_str_type:
                sample_val = str(base_row.get(cname) or "")
                if (
                    clower.endswith(("_dt", "_date", "_ymd")) or re.fullmatch(r"20\d{6}", sample_val)
                ) and (col.max_length is None or col.max_length >= 8):
                    new_row[cname] = (
                        target_date.strftime("%Y-%m-%d")
                        if ("-" in sample_val and (col.max_length is None or col.max_length >= 10))
                        else target_date.strftime("%Y%m%d")
                    )
                    continue
                if (
                    clower.endswith(("_ym", "_yymm", "_yyyymm")) or re.fullmatch(r"20\d{4}", sample_val)
                ) and (col.max_length is None or col.max_length >= 6):
                    new_row[cname] = target_date.strftime("%Y%m")
                    continue
                if clower.endswith(("_year", "_yyyy", "_yy")) and (
                    col.max_length == 4 or re.fullmatch(r"20\d{2}", sample_val)
                ):
                    new_row[cname] = target_date.strftime("%Y")
                    continue

            # 7. 민감 식별번호·이메일·전화·주소 컬럼 더미 치환 (원본 포맷 유지)
            if is_str_type and (cname in base_row or not col.is_nullable):
                ident_val = pseudonymize_identifier(cname, base_row.get(cname), idx, col.max_length)
                if ident_val is not None:
                    # 원본이 NULL이고 nullable 컬럼이면 NULL 유지
                    if cname in base_row and base_row[cname] is None and col.is_nullable:
                        new_row[cname] = None
                    else:
                        new_row[cname] = ident_val
                    continue

            # 8. 제목/명칭/비고/인명 컬럼 상시 가명화 (원본 구조 유지 + 고유명사만 살짝 교체)
            if is_str_type and (clower.endswith(_TEXT_NAME_SUFFIXES) or _is_person_name_col(cname)):
                orig_raw = base_row.get(cname)
                if cname in base_row and orig_raw is None and col.is_nullable:
                    new_row[cname] = None
                else:
                    new_row[cname] = pseudonymize_text(
                        str(orig_raw or ""),
                        idx,
                        col_name=cname,
                        company_names=comp_names,
                        max_length=col.max_length,
                    )
                continue

            # 9. 금액/수량/비율 컬럼 자릿수 유지 라운드 변형
            if is_num_type and (cname in base_row or not col.is_nullable):
                orig_num = base_row.get(cname)
                if cname in base_row and orig_num is None and col.is_nullable:
                    new_row[cname] = None
                else:
                    p_num = pseudonymize_numeric(cname, orig_num, idx, dtype)
                    if p_num is not None:
                        new_row[cname] = p_num
                        continue

            # 10. Unique 제약이 걸린 컬럼은 행마다 고유값 변형
            if cname in meta.unique_cols:
                if is_str_type:
                    u_val = f"S{screen_no}_{short_tag}_{idx + 1}"
                    new_row[cname] = _truncate_str(u_val, col.max_length)
                    continue
                if dtype in ("integer", "bigint", "smallint", "numeric"):
                    new_row[cname] = 90000 + idx + 1
                    continue

            # 11. 타 회사 마스터를 가리킬 수 있는 FK 컬럼은 현재 회사 소속 부모 ID로 자동 재매핑
            if cname in meta.fk_map and base_row.get(cname) is not None:
                ptbl, ppk = meta.fk_map[cname]
                if ptbl not in SYSTEM_MASTER_TABLES:
                    has_comp_col, comp_parent_ids = _lookup_company_parent_ids(
                        conn, ptbl, ppk, ctx.company_id, fk_parent_cache
                    )
                    if has_comp_col:
                        if comp_parent_ids:
                            new_row[cname] = comp_parent_ids[idx % len(comp_parent_ids)]
                            continue
                        if warnings is not None and cname not in warned_fks:
                            warned_fks.add(cname)
                            warnings.append(
                                f"{meta.name}.{cname} → 부모 테이블({ptbl})에 현재 회사({ctx.company_cd}) "
                                f"데이터가 없어 원본 참조를 유지했습니다 (실제 마스터 명칭 노출 주의)."
                            )

            # 12. 기존 샘플 행에 값이 있으면 계승 (단, 문자열에 실제 회사명이 포함돼 있으면 치환)
            if cname in base_row and base_row[cname] is not None:
                val = base_row[cname]
                if is_str_type and isinstance(val, str) and comp_names:
                    tag_ko = PSEUDO_KO_POOL[idx % len(PSEUDO_KO_POOL)]
                    for comp_nm in comp_names:
                        if len(comp_nm) >= 2 and comp_nm.lower() in val.lower():
                            val = re.sub(re.escape(comp_nm), tag_ko, val, flags=re.IGNORECASE)
                    val = _truncate_str(val, col.max_length)
                new_row[cname] = val
                continue

            # 13. 샘플 행이 없거나 NULL인데 NOT NULL 제약이 있는 컬럼 폴백 합성
            if not col.is_nullable and col.column_default is None:
                new_row[cname] = _fallback_value_for_column(conn, meta, col, ctx, screen_no, idx)
            elif cname in base_row:
                new_row[cname] = None

        synthesized.append(new_row)

    return synthesized


def _fallback_value_for_column(
    conn: psycopg.Connection,
    meta: TableMeta,
    col: ColumnMeta,
    ctx: LoginContext,
    screen_no: str,
    idx: int,
) -> Any:
    """샘플 데이터가 없는 테이블에서 NOT NULL 컬럼의 기본값을 합성한다."""
    cname = col.name
    dtype = col.data_type.lower()

    # FK 제약조건이 있으면 부모 테이블에서 1건 조회
    if cname in meta.fk_map:
        ptbl, ppk = meta.fk_map[cname]
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f'SELECT "{ppk}" FROM "{ptbl}" LIMIT 1;')
            prow = cur.fetchone()
            if prow and prow.get(ppk) is not None:
                return prow[ppk]

    if dtype in ("integer", "bigint", "smallint"):
        return idx + 1
    if dtype in ("numeric", "decimal", "real", "double precision"):
        return 1000
    if dtype == "boolean":
        return True
    if dtype == "date":
        return ctx.today
    if "timestamp" in dtype:
        return datetime.datetime.now(tz=datetime.UTC)
    if col.max_length == 1:
        return "Y"
    tag_ko = PSEUDO_KO_POOL[idx % len(PSEUDO_KO_POOL)]
    return _truncate_str(f"{tag_ko}_{screen_no}_{idx + 1}", col.max_length)


def insert_test_data(
    raw_login: str,
    screen_no: str,
    count: int = 3,
    override_tables: list[str] | None = None,
    dry_run: bool = False,
    verify_api: bool = True,
    db_name: str | None = None,
    work_dir: Path | None = None,
) -> ToolResult:
    """화면번호에 해당하는 테이블에 테스트 데이터를 생성하고 transaction-code를 반환한다."""
    db_url = get_connection_string(db_name)
    if not db_url:
        return ToolResult(ok=False, error="DB 연결 정보를 찾을 수 없습니다 (LOCAL_DB / YUNHEE_DB 환경변수 확인).")

    try:
        ensure_local_db_write_safe(db_url)
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))

    clean_screen = screen_no.strip().lstrip("#")
    now = datetime.datetime.now().astimezone()
    tx_code = f"tx-{clean_screen}-{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"

    with psycopg.connect(db_url, autocommit=False) as conn:
        try:
            # 1. 로그인 컨텍스트 해석
            ctx = resolve_login_context(raw_login, conn=conn, db_name=db_name)

            # 2. 화면 타깃 테이블 분석
            screen_info = analyze_screen_targets(
                clean_screen,
                conn=conn,
                root_dir=work_dir or config.WORK_DIR,
                override_tables=override_tables,
            )
            target_tables = screen_info["target_tables"]
            if not target_tables:
                return ToolResult(
                    ok=False,
                    error=(
                        f"화면 [{clean_screen}]에 연결된 물리 대상 테이블을 찾지 못했습니다. "
                        f"--table 옵션으로 테이블명을 직접 지정해 보세요."
                    ),
                )

            operations: list[dict[str, Any]] = []
            parent_inserted_pks: dict[str, list[Any]] = {}
            generated_sql_preview: list[str] = []
            warnings: list[str] = []
            company_names = _fetch_company_names(conn)

            # 3. 테이블별 행 합성 및 INSERT ... RETURNING 실행
            with conn.cursor(row_factory=dict_row) as cur:
                for seq_idx, tbl_name in enumerate(target_tables, start=1):
                    t_meta = inspect_table_meta(conn, tbl_name)
                    rows_to_insert = synthesize_table_rows(
                        conn=conn,
                        meta=t_meta,
                        ctx=ctx,
                        screen_no=clean_screen,
                        count=count,
                        parent_inserted_pks=parent_inserted_pks,
                        company_names=company_names,
                        warnings=warnings,
                    )
                    if not rows_to_insert:
                        continue

                    cur.execute(f"SAVEPOINT sp_table_{seq_idx};")
                    inserted_pks: list[list[Any]] = []
                    try:
                        for row_dict in rows_to_insert:
                            cols = list(row_dict.keys())
                            vals = [row_dict[c] for c in cols]
                            col_list_sql = ", ".join(f'"{c}"' for c in cols)
                            placeholders = ", ".join(["%s"] * len(cols))
                            ret_cols_sql = ", ".join(f'"{pk}"' for pk in t_meta.pk_cols)

                            stmt = (
                                f'INSERT INTO "{tbl_name}" ({col_list_sql}) '
                                f"VALUES ({placeholders}) RETURNING {ret_cols_sql};"
                            )
                            if len(generated_sql_preview) < 10:
                                generated_sql_preview.append(stmt)

                            cur.execute(stmt, vals)
                            ret_row = cur.fetchone()
                            if ret_row:
                                pk_tuple = [_normalize_json_val(ret_row[pk]) for pk in t_meta.pk_cols]
                                inserted_pks.append(pk_tuple)

                        cur.execute(f"RELEASE SAVEPOINT sp_table_{seq_idx};")
                    except Exception as tbl_exc:
                        cur.execute(f"ROLLBACK TO SAVEPOINT sp_table_{seq_idx};")
                        # 첫 번째 메인 테이블 자체가 실패하면 전체 중단
                        if seq_idx == 1:
                            raise ValueError(f"메인 테이블({tbl_name}) INSERT 실패: {tbl_exc}") from tbl_exc
                        continue

                    if inserted_pks:
                        if len(t_meta.pk_cols) == 1:
                            parent_inserted_pks[tbl_name] = [p[0] for p in inserted_pks]
                        operations.append(
                            {
                                "seq": seq_idx,
                                "table": tbl_name,
                                "pk_columns": t_meta.pk_cols,
                                "inserted_pks": inserted_pks,
                                "row_count": len(inserted_pks),
                            }
                        )

            if not operations:
                conn.rollback()
                return ToolResult(ok=False, error=f"화면 [{clean_screen}] 대상 테이블에 삽입된 행이 없습니다.")

            manifest: dict[str, Any] = {
                "tx_code": tx_code,
                "status": "DRY_RUN" if dry_run else "ACTIVE",
                "screen_no": clean_screen,
                "screen_name": screen_info.get("screen_name") or "",
                "menu_title": screen_info.get("menu_title") or "",
                "login": raw_login,
                "login_key": ctx.login_key,
                "company_cd": ctx.company_cd,
                "company_id": ctx.company_id,
                "emp_no": ctx.emp_no,
                "emp_id": ctx.emp_id,
                "org_id": ctx.org_id,
                "created_at": now.isoformat(timespec="seconds"),
                "rolled_back_at": None,
                "operations": operations,
                "warnings": warnings,
                "sql_preview": generated_sql_preview[:5],
            }

            if dry_run:
                conn.rollback()
            else:
                manifest_path = get_test_data_dir(work_dir) / f"{tx_code}.json"
                manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default)
                manifest_path.write_text(manifest_json, encoding="utf-8")
                manifest["manifest_path"] = str(manifest_path)
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            return ToolResult(ok=False, error=str(exc))

    # 4. 선택적 조회 API 검증
    if verify_api and not dry_run and screen_info.get("apis"):
        api_Verify_msg = _verify_screen_get_api(ctx, screen_info["apis"])
        if api_Verify_msg:
            manifest["api_verification"] = api_Verify_msg

    return ToolResult(ok=True, data=manifest)


def _verify_screen_get_api(ctx: LoginContext, apis: list[str]) -> str | None:
    """생성 직후 해당 화면의 GET API가 호출 가능하면 건수를 확인한다 (서버 미기동 시 조용히 생략)."""
    get_paths: list[str] = []
    for a in apis:
        m = re.match(r"^(?:GET\s+)?(/api/v1/[^\s{]+)$", a.strip(), re.IGNORECASE)
        if m and not a.strip().upper().startswith(("POST ", "PUT ", "DELETE ", "PATCH ")):
            get_paths.append(m.group(1))
    if not get_paths:
        return None

    try:
        from yunhee.tools.api_client import call_api

        res = call_api(
            method="GET",
            path=get_paths[0],
            as_user=ctx.emp_no,
            company_code=ctx.company_cd,
            password=ctx.password,
        )
        if res.ok and isinstance(res.data, dict):
            row_count = res.data.get("row_count")
            if row_count is not None:
                return f"GET {get_paths[0]} → {row_count}건 조회 확인"
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def list_test_transactions(
    work_dir: Path | None = None,
    status_filter: str | None = None,
    screen_no: str | None = None,
    login_spec: str | None = None,
) -> list[dict[str, Any]]:
    """저장된 테스트 데이터 트랜잭션 매니페스트 목록을 최신순으로 반환한다."""
    td_dir = get_test_data_dir(work_dir)
    items: list[dict[str, Any]] = []

    target_login_key: str | None = None
    if login_spec:
        company_cd, user, _ = parse_login_spec(login_spec)
        target_login_key = f"{company_cd.lower()}-{user.lower()}"

    clean_screen = screen_no.strip().lstrip("#") if screen_no else None

    for p in sorted(td_dir.glob("tx-*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if status_filter and data.get("status") != status_filter:
                continue
            if clean_screen and str(data.get("screen_no")) != clean_screen:
                continue
            if target_login_key and data.get("login_key") != target_login_key:
                continue
            data["manifest_path"] = str(p)
            items.append(data)
        except Exception:  # noqa: BLE001, S112
            continue

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def rollback_test_data(
    raw_login: str,
    tx_code: str | None = None,
    last: bool = False,
    screen_no: str | None = None,
    cascade_children: bool = True,
    dry_run: bool = False,
    force: bool = False,
    db_name: str | None = None,
    work_dir: Path | None = None,
) -> ToolResult:
    """`transaction-code`(또는 `--last` / `--screen`)에 해당하는 테스트 데이터를 역순으로 모두 삭제한다."""
    db_url = get_connection_string(db_name)
    if not db_url:
        return ToolResult(ok=False, error="DB 연결 정보를 찾을 수 없습니다 (LOCAL_DB / YUNHEE_DB 환경변수 확인).")

    try:
        ensure_local_db_write_safe(db_url)
        company_cd, user, _ = parse_login_spec(raw_login)
        req_login_key = f"{company_cd.lower()}-{user.lower()}"
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))

    td_dir = get_test_data_dir(work_dir)
    target_manifests: list[tuple[Path, dict[str, Any]]] = []

    if tx_code:
        clean_tx = tx_code.strip()
        p = td_dir / f"{clean_tx}.json"
        if not p.is_file():
            return ToolResult(ok=False, error=f"트랜잭션 코드를 찾을 수 없습니다: {clean_tx} ({p})")
        data = json.loads(p.read_text(encoding="utf-8"))
        target_manifests.append((p, data))
    elif last:
        active_list = list_test_transactions(work_dir=work_dir, status_filter="ACTIVE", login_spec=raw_login)
        if not active_list:
            return ToolResult(ok=False, error=f"계정({raw_login})으로 생성된 활성(ACTIVE) 테스트 트랜잭션이 없습니다.")
        latest = active_list[0]
        target_manifests.append((Path(latest["manifest_path"]), latest))
    elif screen_no:
        active_list = list_test_transactions(
            work_dir=work_dir,
            status_filter="ACTIVE",
            screen_no=screen_no,
            login_spec=raw_login,
        )
        if not active_list:
            return ToolResult(
                ok=False,
                error=f"화면 [{screen_no}] (계정: {raw_login})의 활성(ACTIVE) 테스트 트랜잭션이 없습니다.",
            )
        for item in active_list:
            target_manifests.append((Path(item["manifest_path"]), item))
    else:
        return ToolResult(ok=False, error="롤백할 <tx_code>를 지정하거나 --last 또는 --screen 옵션을 지정하세요.")

    # DB 연결 전 매니페스트 상태 및 소유자(계정) 일치 여부 사전 검증
    for m_path, manifest in target_manifests:
        m_tx = manifest.get("tx_code", m_path.stem)
        if manifest.get("status") == "ROLLED_BACK" and not force:
            return ToolResult(ok=False, error=f"이미 롤백된 트랜잭션입니다: {m_tx} ({manifest.get('rolled_back_at')})")

        m_login_key = manifest.get("login_key")
        if m_login_key and m_login_key != req_login_key and not force:
            return ToolResult(
                ok=False,
                error=(
                    f"트랜잭션 생성 계정({manifest.get('login')})과 요청 계정({raw_login})이 일치하지 않습니다. "
                    f"강제 롤백하려면 --force 옵션을 사용하세요."
                ),
            )

    rolled_back_results: list[dict[str, Any]] = []

    with psycopg.connect(db_url, autocommit=False) as conn:
        for m_path, manifest in target_manifests:
            m_tx = manifest.get("tx_code", m_path.stem)
            ops = list(manifest.get("operations") or [])
            # 역순(자식 → 부모)으로 정렬
            ops.sort(key=lambda x: x.get("seq", 0), reverse=True)

            deleted_details: list[dict[str, Any]] = []
            try:
                with conn.cursor() as cur:
                    # 1. cascade_children=True 이면 테스트 중 파생된 FK 자식 행 먼저 정리
                    if cascade_children:
                        cascade_deleted = _delete_cascade_children(conn, cur, ops)
                        deleted_details.extend(cascade_deleted)

                    # 2. 매니페스트에 기록된 테이블 행들을 자식 → 부모 역순으로 삭제
                    for op in ops:
                        tbl = op["table"]
                        pk_cols: list[str] = op["pk_columns"]
                        pks: list[list[Any]] = op["inserted_pks"]
                        if not pks:
                            continue

                        if len(pk_cols) == 1:
                            pk_col = pk_cols[0]
                            flat_vals = [row_pk[0] for row_pk in pks]
                            placeholders = ", ".join(["%s"] * len(flat_vals))
                            del_sql = f'DELETE FROM "{tbl}" WHERE "{pk_col}" IN ({placeholders});'
                            cur.execute(del_sql, flat_vals)
                        else:
                            col_tuple_sql = ", ".join(f'"{c}"' for c in pk_cols)
                            row_placeholders = ", ".join(
                                "(" + ", ".join(["%s"] * len(pk_cols)) + ")" for _ in pks
                            )
                            flat_vals = [v for row_pk in pks for v in row_pk]
                            del_sql = f'DELETE FROM "{tbl}" WHERE ({col_tuple_sql}) IN ({row_placeholders});'
                            cur.execute(del_sql, flat_vals)

                        deleted_details.append(
                            {
                                "table": tbl,
                                "pk_columns": pk_cols,
                                "deleted_count": max(cur.rowcount, 0),
                                "sql": del_sql,
                            }
                        )

                if dry_run:
                    conn.rollback()
                else:
                    conn.commit()
                    manifest["status"] = "ROLLED_BACK"
                    manifest["rolled_back_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
                    manifest["deleted_details"] = deleted_details
                    m_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
                        encoding="utf-8",
                    )

                rolled_back_results.append(
                    {
                        "tx_code": m_tx,
                        "screen_no": manifest.get("screen_no"),
                        "login": manifest.get("login"),
                        "status": "DRY_RUN" if dry_run else "ROLLED_BACK",
                        "deleted_details": deleted_details,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                return ToolResult(ok=False, error=f"롤백 실행 중 오류 발생 ({m_tx}): {exc}")

    return ToolResult(ok=True, data={"transactions": rolled_back_results})


def _delete_cascade_children(
    conn: psycopg.Connection,
    cur: psycopg.Cursor,
    ops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """삭제 대상 부모 테이블의 PK를 참조하는 외부 자식 테이블 행들을 탐지하여 선행 삭제한다."""
    deleted: list[dict[str, Any]] = []
    try:
        from yunhee.tools.biz.orphans import get_fk_relations

        rels = get_fk_relations(conn)
    except Exception:  # noqa: BLE001
        return deleted

    op_tables = {op["table"] for op in ops}
    for op in ops:
        parent_tbl = op["table"]
        pk_cols = op["pk_columns"]
        pks = op["inserted_pks"]
        if len(pk_cols) != 1 or not pks:
            continue
        parent_pk = pk_cols[0]
        parent_vals = [r[0] for r in pks]

        for rel in rels:
            if rel["parent_table"] == parent_tbl and rel["parent_pk"] == parent_pk:
                child_tbl = rel["child_table"]
                fk_col = rel["fk_col"]
                if child_tbl in op_tables or child_tbl in SYSTEM_MASTER_TABLES:
                    continue

                cur.execute("SAVEPOINT sp_cascade_child;")
                try:
                    placeholders = ", ".join(["%s"] * len(parent_vals))
                    del_sql = f'DELETE FROM "{child_tbl}" WHERE "{fk_col}" IN ({placeholders});'
                    cur.execute(del_sql, parent_vals)
                    cnt = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                    cur.execute("RELEASE SAVEPOINT sp_cascade_child;")
                    if cnt > 0:
                        deleted.append(
                            {
                                "table": child_tbl,
                                "pk_columns": [fk_col],
                                "deleted_count": cnt,
                                "cascade_from": parent_tbl,
                                "sql": del_sql,
                            }
                        )
                except Exception:  # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT sp_cascade_child;")

    return deleted
