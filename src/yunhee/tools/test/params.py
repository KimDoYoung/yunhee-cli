"""test-params: MyBatis 매퍼 statement 실행에 필요한 파라미터 값을 DB에서 자동 추론하는 도구."""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from yunhee import config
from yunhee.tools.as_is.mybatis_render import (
    STATEMENT_TAGS,
    Node,
    parse_xml,
    render_from_xml,
)
from yunhee.tools.base import ToolResult
from yunhee.tools.sql_runner import get_connection_string
from yunhee.tools.test.signature import (
    MethodSignature,
    get_method_signature,
)


@dataclass
class ResolvedParam:
    name: str
    java_type: str
    pg_type: str
    value: Any
    source: str
    reason: str


def _find_mapper_file(file_part: str) -> Path | None:
    mapper_path = Path(file_part)
    if mapper_path.is_file():
        return mapper_path.resolve()

    cand_roots = [
        config.WORK_DIR,
        getattr(config, "TOBE_SRC_DIR", None),
        getattr(config, "ASIS_SRC_DIR", None),
        Path.cwd(),
    ]
    for r in cand_roots:
        if not r:
            continue
        cand = r / file_part
        if cand.is_file():
            return cand.resolve()
        # glob 탐색
        cand_glob = list(r.rglob(mapper_path.name))
        if cand_glob:
            return cand_glob[0].resolve()

    return None


def _get_table_columns_from_db(conn: psycopg.Connection, table_names: list[str]) -> dict[str, set[str]]:
    """DB의 information_schema.columns로부터 테이블별 실제 열 목록 조회."""
    if not table_names:
        return {}
    res: dict[str, set[str]] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = ANY(%s)
            """,
            (table_names,),
        )
        for t_name, c_name in cur.fetchall():
            res.setdefault(t_name.lower(), set()).add(c_name.lower())
    return res


def _find_constants_in_service(java_file: Path | None, method_name: str, sig: MethodSignature | None) -> dict[str, tuple[str, str]]:
    """서비스 소스 파일에서 method_name 호출부의 상수 인자 (파라미터명 -> (값, 출처)) 추출."""
    if not java_file or not java_file.is_file():
        return {}
    service_dir = java_file.parent.parent / "service"
    if not service_dir.is_dir():
        return {}

    constants: dict[str, tuple[str, str]] = {}
    mapper_var_name = java_file.stem[0].lower() + java_file.stem[1:]  # EmpDeductMapper -> empDeductMapper

    for s_file in service_dir.glob("*.java"):
        try:
            content = s_file.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001, S112
            continue

        # static final 상수 정의 탐색 (접근제어자 무관)
        const_defs: dict[str, str] = {}
        for m in re.finditer(r'(?:private|protected|public)?\s*static\s+final\s+String\s+([A-Za-z0-9_]+)\s*=\s*["\']([^"\']+)["\']', content):
            const_defs[m.group(1)] = m.group(2)

        # mapper_var.methodName(...) 호출 탐색 (중첩 괄호 보호)
        patt = re.compile(rf"(?:{re.escape(mapper_var_name)}|mapper)\.{re.escape(method_name)}\s*\(")
        for m in patt.finditer(content):
            open_paren_idx = m.end() - 1
            depth = 0
            close_paren_idx = -1
            for i in range(open_paren_idx, len(content)):
                if content[i] == "(":
                    depth += 1
                elif content[i] == ")":
                    depth -= 1
                    if depth == 0:
                        close_paren_idx = i
                        break
            if close_paren_idx == -1:
                continue

            args_str = content[open_paren_idx + 1:close_paren_idx]
            from yunhee.tools.test.signature import split_args
            args = [a.strip() for a in split_args(args_str) if a.strip()]
            line_no = content[:m.start()].count("\n") + 1
            # 인자 순서와 시그니처 파라미터 매핑
            for idx, arg in enumerate(args):
                p_name_at_idx = sig.params[idx].name if sig and idx < len(sig.params) else None
                # 리터럴 문자열
                if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
                    val = arg[1:-1]
                    if p_name_at_idx:
                        constants[p_name_at_idx] = (val, f"{s_file.name}:{line_no} \"{val}\"")
                # 정의된 상수 변수
                elif arg in const_defs:
                    val = const_defs[arg]
                    if p_name_at_idx:
                        constants[p_name_at_idx] = (val, f"{s_file.name}:{line_no} {arg}")
                    constants[arg] = (val, f"{s_file.name}:{line_no} {arg}")
    return constants


def resolve_params_for_statement(
    target: str,
    company: str | None = None,
    n_tries: int = 3,
    user_params: dict[str, Any] | None = None,
    db_name: str | None = None,
) -> ToolResult:
    """매퍼 statement의 파라미터 값을 추론하여 ResolvedParam 목록 반환."""
    from yunhee import config

    db_name = db_name or config.DEFAULT_DB_NAME
    if "#" not in target:
        return ToolResult(ok=False, error=f"매퍼 파일과 statement id는 #으로 구분해야 합니다: {target}")

    file_part, sid = target.split("#", 1)
    file_part = file_part.strip()
    sid = sid.strip()

    mapper_path = _find_mapper_file(file_part)
    if not mapper_path or not mapper_path.is_file():
        return ToolResult(ok=False, error=f"매퍼 파일을 찾을 수 없습니다: {file_part}")

    raw_xml = mapper_path.read_text(encoding="utf-8", errors="replace")
    root = parse_xml(raw_xml)
    mapper_node = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), None)
    if not mapper_node:
        return ToolResult(ok=False, error=f"<mapper> 태그가 없습니다: {mapper_path}")

    target_node: Node | None = None
    for child in mapper_node.children:
        if isinstance(child, Node) and child.tag in STATEMENT_TAGS and child.attrs.get("id") == sid:
            target_node = child
            break

    if not target_node:
        return ToolResult(ok=False, error=f"statement '{sid}'를 찾을 수 없습니다: {mapper_path}")

    ns = mapper_node.attrs.get("namespace", mapper_path.stem)

    # 1. Java 시그니처 분석
    sig = get_method_signature(ns, sid, src_root=mapper_path)
    java_file = sig.java_file if sig else None

    # SQL 렌더링 (파라미터 추출용: structure 모드로 태그와 #{...} 보존)
    import html
    dummy_sql_raw, raw_missing = render_from_xml(raw_xml, sid, mode="structure")
    dummy_sql = html.unescape(dummy_sql_raw)

    # 파라미터 목록 수집 (Java 시그니처 우선, 없으면 raw_missing)
    param_names: list[str] = []
    if sig and sig.params:
        for p in sig.params:
            if p.name not in param_names:
                param_names.append(p.name)
    else:
        param_names = list(raw_missing)

    # 2. SQL 내 비교 열 및 테이블 매핑 추출
    # 예: WHERE emp35_person_id = #{personId}
    #     WHERE sys08_kind_cd = #{itemTypeCodeName}
    col_param_map: list[tuple[str, str, str]] = []  # (table_guess, col_name, param_name)
    for m in re.finditer(r"([a-zA-Z0-9_]+)\s*(?:=|!=|<>|<=|>=|<|>|like|in)\s*#\{\s*([a-zA-Z0-9_.]+)\s*\}", dummy_sql, re.IGNORECASE):
        c_name = m.group(1).lower()
        p_name = m.group(2)
        if "." in p_name:
            p_name = p_name.split(".")[-1]
        col_param_map.append(("", c_name, p_name))

    for m in re.finditer(r"#\{\s*([a-zA-Z0-9_.]+)\s*\}\s*(?:=|!=|<>|<=|>=|<|>)\s*([a-zA-Z0-9_]+)", dummy_sql, re.IGNORECASE):
        p_name = m.group(1)
        c_name = m.group(2).lower()
        if "." in p_name:
            p_name = p_name.split(".")[-1]
        col_param_map.append(("", c_name, p_name))

    # SQL에서 언급된 테이블 이름들 추출
    tables_in_sql = list(set(re.findall(r"\bfrom\s+([a-zA-Z0-9_]+)|\bjoin\s+([a-zA-Z0-9_]+)|\binto\s+([a-zA-Z0-9_]+)|\bupdate\s+([a-zA-Z0-9_]+)", dummy_sql, re.IGNORECASE)))
    found_tables = {t for tup in tables_in_sql for t in tup if t}

    # DB 연결
    conn_str = get_connection_string(db_name)
    if not conn_str:
        return ToolResult(ok=False, error=f"DB 접속 정보를 찾을 수 없습니다: {db_name}")

    resolved: dict[str, ResolvedParam] = {}
    user_given = dict(user_params or {})

    # Java 호출부 상수 탐색
    service_constants = _find_constants_in_service(java_file, sid, sig)

    # 서비스 상수 먼저 매핑 (코드/구분값 등 호출부 명시 상수)
    for p_nm in param_names:
        if p_nm in service_constants:
            c_val, c_src = service_constants[p_nm]
            jt = sig.param_map[p_nm].java_type if sig and p_nm in sig.param_map else "String"
            pt = sig.param_map[p_nm].pg_type if sig and p_nm in sig.param_map else "text"
            resolved[p_nm] = ResolvedParam(
                name=p_nm,
                java_type=jt,
                pg_type=pt,
                value=c_val,
                source=f"Java 호출부 상수 {c_src}",
                reason="서비스 호출부 상수",
            )

    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            # information_schema.columns 확인
            actual_table_cols = _get_table_columns_from_db(conn, list(found_tables))

            # 회사 ID 결정 (0번 슈퍼관리자 제외한 실제 운영 회사 우선)
            company_id = None
            if company:
                with conn.cursor() as cur:
                    if company.isdigit():
                        cur.execute("SELECT sys01_company_id FROM sys01_company WHERE sys01_company_id = %s", (int(company),))
                    else:
                        cur.execute("SELECT sys01_company_id FROM sys01_company WHERE sys01_company_cd = %s OR sys01_loc_nm = %s", (company, company))
                    row = cur.fetchone()
                    if row:
                        company_id = row[0]
            if not company_id:
                with conn.cursor() as cur:
                    cur.execute("SELECT sys01_company_id FROM sys01_company WHERE sys01_company_id >= 1000 ORDER BY sys01_company_id LIMIT 1")
                    row = cur.fetchone()
                    company_id = row[0] if row else 28000

            # 파라미터별 기본 타입 확인
            def get_types(p_nm: str) -> tuple[str, str]:
                if sig and p_nm in sig.param_map:
                    p_inf = sig.param_map[p_nm]
                    return p_inf.java_type, p_inf.pg_type
                if "id" in p_nm.lower() or "cnt" in p_nm.lower() or "no" in p_nm.lower():
                    return "Long", "numeric"
                if "date" in p_nm.lower():
                    return "LocalDate", "date"
                return "String", "text"

            # 1. 사용자가 명시한 값 먼저 등록
            for p_nm in param_names:
                if p_nm in user_given:
                    jt, pt = get_types(p_nm)
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value=user_given[p_nm],
                        source="사용자 지정 -p",
                        reason=f"사용자 인자 -p {p_nm}={user_given[p_nm]}",
                    )

            # 2. companyId
            for p_nm in param_names:
                if p_nm not in resolved and p_nm.lower() in ("companyid", "cid"):
                    jt, pt = get_types(p_nm)
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value=company_id,
                        source=f"sys01_company (회사 지정 {company or '-c 또는 기본 회사'})",
                        reason=f"sys01_company_id = {company_id}",
                    )

            # 3. SQL 비교 열 기반 동일 행 묶기 추론
            # 테이블별로 매핑된 컬럼-파라미터 수집
            table_col_params: dict[str, list[tuple[str, str]]] = {}
            for _, c_name, p_name in col_param_map:
                if p_name not in param_names:
                    continue
                # c_name이 어떤 테이블의 컬럼인지 DB 검증
                for t_name, cols in actual_table_cols.items():
                    if c_name in cols:
                        table_col_params.setdefault(t_name, []).append((c_name, p_name))
                        break

            for t_name, pairs in table_col_params.items():
                unresolved_pairs = [pair for pair in pairs if pair[1] not in resolved]
                if not unresolved_pairs:
                    continue
                cols_to_select = list(dict.fromkeys(p[0] for p in unresolved_pairs))
                # WHERE 절 구성 (이미 정해진 파라미터가 있다면 조건으로 활용)
                where_clauses: list[str] = []
                where_vals: list[Any] = []
                for p_col, p_name in pairs:
                    if p_name in resolved and resolved[p_name].value != "?":
                        where_clauses.append(f"{p_col} = %s")
                        where_vals.append(resolved[p_name].value)

                # 회사 ID 컬럼이 있으면 회사 조건 추가
                t_cols = actual_table_cols.get(t_name, set())
                comp_col = next((c for c in t_cols if "company_id" in c), None)
                if comp_col and company_id:
                    where_clauses.append(f"{comp_col} = %s")
                    where_vals.append(company_id)

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                sql_q = f"SELECT {', '.join(cols_to_select)} FROM {t_name} {where_sql} LIMIT 1"
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql_q, where_vals)
                        row = cur.fetchone()
                        if row:
                            for idx, c_nm in enumerate(cols_to_select):
                                val = row[idx]
                                matching_p = [p[1] for p in unresolved_pairs if p[0] == c_nm]
                                for p_name in matching_p:
                                    if p_name not in resolved:
                                        jt, pt = get_types(p_name)
                                        # 날짜 포맷
                                        if isinstance(val, (datetime.date, datetime.datetime)):
                                            val_str = val.strftime("%Y-%m-%d")
                                        else:
                                            val_str = str(val)
                                        resolved[p_name] = ResolvedParam(
                                            name=p_name,
                                            java_type=jt,
                                            pg_type=pt,
                                            value=val_str,
                                            source=f"{t_name}.{c_nm} ({t_name} 행 추출)",
                                            reason=f"동일 행 묶기 ({t_name})",
                                        )
                except Exception:  # noqa: BLE001, S110
                    pass

            # 4. 서비스 상수 매핑
            for p_nm in param_names:
                if p_nm not in resolved:
                    # 상수에 매칭되는 값 확인
                    for c_key, (c_val, c_src) in service_constants.items():
                        if c_key.lower() in p_nm.lower() or p_nm.lower() in c_key.lower() or c_val.lower() in p_nm.lower():
                            jt, pt = get_types(p_nm)
                            resolved[p_nm] = ResolvedParam(
                                name=p_nm,
                                java_type=jt,
                                pg_type=pt,
                                value=c_val,
                                source=f"Java 호출부 상수 {c_src}",
                                reason="서비스 상수 매칭",
                            )
                            break

            # 5. 이름 규칙 적용
            today_str = datetime.date.today().strftime("%Y-%m-%d")  # noqa: DTZ011
            year_str = str(datetime.date.today().year)  # noqa: DTZ011

            # 재직 사원 조회
            emp_row = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT emp01_person_id, emp01_emp_no, emp01_org_id
                          FROM emp01_person
                         WHERE emp01_company_id = %s
                           AND emp01_retire_date IS NULL
                         ORDER BY emp01_person_id
                         LIMIT 1
                        """,
                        (company_id,),
                    )
                    emp_row = cur.fetchone()
            except Exception:  # noqa: BLE001, S110
                pass

            for p_nm in param_names:
                if p_nm in resolved:
                    continue
                p_lower = p_nm.lower()
                jt, pt = get_types(p_nm)

                if p_lower in ("personid", "empid", "userid", "user_id", "emp_id"):
                    val = emp_row[0] if emp_row else 29029
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value=val,
                        source="emp01_person (재직 사원)",
                        reason=f"사원 ID {val}",
                    )
                elif p_lower in ("orgid", "orgcd", "org_id", "org_cd"):
                    val = emp_row[2] if emp_row and emp_row[2] else 0
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value=val,
                        source="emp01_person (사원 조직)",
                        reason=f"조직 ID {val}",
                    )
                elif p_lower in ("startdate", "start_date"):
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value="2000-01-01" if any("close" in x.lower() or "end" in x.lower() for x in param_names) else today_str,
                        source="이름 규칙 (시작일)",
                        reason="기간 시작일",
                    )
                elif p_lower in ("closedate", "close_date", "enddate", "end_date"):
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value="2099-12-31",
                        source="이름 규칙 (종료일)",
                        reason="기간 종료일",
                    )
                elif "date" in p_lower:
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value=today_str,
                        source="이름 규칙 (오늘)",
                        reason="기준일/선택일 오늘",
                    )
                elif "year" in p_lower:
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value=year_str,
                        source="이름 규칙 (올해)",
                        reason="연도",
                    )
                else:
                    # 미결정
                    resolved[p_nm] = ResolvedParam(
                        name=p_nm,
                        java_type=jt,
                        pg_type=pt,
                        value="?",
                        source="미결정",
                        reason="비교 열 없음 또는 적합한 값 부재",
                    )

    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"DB 조회 중 오류 발생: {exc}")

    res_list = [resolved[p] for p in param_names if p in resolved]
    return ToolResult(
        ok=True,
        data={
            "target": target,
            "mapper": mapper_path.stem,
            "statement_id": sid,
            "java_file": str(java_file.name) if java_file else None,
            "line_no": sig.line_no if sig else None,
            "params": res_list,
        },
    )


def format_params_output(data: dict[str, Any], fmt: str = "text") -> str:
    """test-params 결과를 text, json, args 형태로 포맷팅."""
    params: list[ResolvedParam] = data["params"]
    target = data["target"]

    if fmt == "json":
        items = [
            {
                "name": p.name,
                "javaType": p.java_type,
                "pgType": p.pg_type,
                "value": p.value,
                "source": p.source,
            }
            for p in params
        ]
        return json.dumps(items, ensure_ascii=False, indent=2)

    if fmt == "args":
        args = [f"-p {p.name}={p.value}" for p in params if p.value != "?"]
        return " ".join(args)

    # text 포맷
    header = f"{data['mapper']}.{data['statement_id']}"
    if data.get("java_file"):
        header += f"  (Java {data['java_file']}:{data.get('line_no', '')})"
    lines = [header]

    for p in params:
        lines.append(f"  {p.name:<15} {p.java_type:<10} {p.value!s:<16} ← {p.source}")

    args_str = " ".join(f"-p {p.name}={p.value}" for p in params if p.value != "?")
    lines.append(f"다시 돌리기: yunhee mapper-run \"{target}\" {args_str} --rollback")
    return "\n".join(lines)
