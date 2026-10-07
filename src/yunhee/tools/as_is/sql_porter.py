"""AS-IS MyBatis 매퍼 SQL을 TOBE 매퍼 조각 및 레코드 DTO로 변환하고 명시 저장 SQL을 생성하는 도구."""

import re
from pathlib import Path
from typing import Any

from yunhee.config import ASIS_SRC_DIR, SCHEMA_ENV, WORK_DIR
from yunhee.tools.as_is.events import (
    col_to_tobe_prop,
    find_table_columns,
    strip_java,
    to_camel_case,
)
from yunhee.tools.as_is.src_indexer import find_app, parse_update_data_model
from yunhee.tools.base import ToolResult


def to_plural(s: str) -> str:
    """단어의 복수형을 생성한다 (예: Role -> Roles, Company -> Companies, Box -> Boxes)."""
    if s.endswith("y") and not any(s.endswith(v + "y") for v in "aeiou"):
        return s[:-1] + "ies"
    if s.endswith(("s", "sh", "ch", "x", "z")):
        return s + "es"
    return s + "s"


def _strip_sql_noise(body: str) -> str:
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", body)


def statement_tag(body: str, original: str) -> str:
    """본문 첫 키워드로 MyBatis 태그를 정한다. INSERT/UPDATE/DELETE/CALL(→ update), 그 밖은 원본 태그."""
    text = re.sub(r"<[^>]+>", " ", _strip_sql_noise(body))
    m = re.match(r"\s*\(*\s*(\w+)", text)
    kw = m.group(1).upper() if m else ""
    if kw == "WITH":
        dml = re.search(r"\)\s*(INSERT|UPDATE|DELETE)\b", text, re.IGNORECASE)
        kw = dml.group(1).upper() if dml else kw
    return {"INSERT": "insert", "UPDATE": "update", "DELETE": "delete", "CALL": "update"}.get(kw, original)


def inline_fixed_params(body: str, puts: list[tuple[str, str | None, int]]) -> tuple[str, list[str]]:
    """map.put 리터럴 값을 #{키}·${키} 자리에 넣는다. 반환: (새 본문, ["useYn = 'true' (L161)", ...])

    map에 put하지 않은 키는 AS-IS에서도 null이었으므로 NULL로 넣는다 (puts가 있을 때만 — map 사용이 확인된 호출).
    """
    fixed = []
    entries: list[tuple[str, str | None, str]] = [(k, lit, f"L{line}") for k, lit, line in puts]
    if puts:
        put_keys = {k for k, _, _ in puts}
        text = _strip_sql_noise(body)
        items = set(re.findall(r'<foreach\b[^>]*\bitem="(\w+)"', text))
        for key in dict.fromkeys(re.findall(r"[#$]\{\s*(\w+)", text)):
            if key not in put_keys and key not in items:
                entries.append((key, "NULL", "map에 없음"))
    for key, literal, where in entries:
        if literal is None:
            continue
        raw = literal[1:-1].replace("''", "'") if literal.startswith("'") else literal
        new_body = re.sub(rf"#\{{\s*{re.escape(key)}\s*(?:,[^}}]*)?\}}", lambda _m, v=literal: v, body)
        new_body = re.sub(rf"\$\{{\s*{re.escape(key)}\s*\}}", lambda _m, v=raw: v, new_body)
        if new_body != body:
            fixed.append(f"{key} = {literal} ({where})")
            body = new_body
    return body, fixed


def java_params(body: str) -> str:
    """SQL 본문의 #{}/${} 파라미터로 Mapper 메서드 파라미터 선언을 만든다."""
    text = _strip_sql_noise(body)
    items = {m.group(1) for m in re.finditer(r'<foreach\b[^>]*\bitem="(\w+)"', text)}
    names: list[tuple[str, str]] = []
    for m in re.finditer(r'<foreach\b[^>]*\bcollection="(\w+)"', text):
        if m.group(1) not in [n for n, _ in names]:
            names.append((m.group(1), "List<Long>"))
    for m in re.finditer(r"[#$]\{\s*(\w+)", text):
        name = m.group(1)
        if name in items or name in [n for n, _ in names]:
            continue
        jtype = "Long" if name.endswith(("Id", "Seq")) else "String"
        names.append((name, jtype))
    if len(names) == 1:
        return f"{names[0][1]} {names[0][0]}"
    return ", ".join(f'@Param("{n}") {t} {n}' for n, t in names)


def find_mapper_file(ns: str, src_root: Path | None = None) -> Path | None:
    """AS-IS 소스 트리에서 지정한 namespace/파일명의 매퍼 XML을 찾는다."""
    roots: list[Path] = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if ASIS_SRC_DIR and ASIS_SRC_DIR.is_dir():
        roots.append(ASIS_SRC_DIR)
    roots.append(WORK_DIR)

    dedup: list[Path] = []
    for r in roots:
        if r.is_dir() and r not in dedup:
            dedup.append(r)

    # 1. 파일명 정확 일치 (예: sys04_role.xml)
    xml_name = f"{ns}.xml" if not ns.endswith(".xml") else ns
    for r in dedup:
        for p in r.rglob(xml_name):
            if "target" not in p.parts:
                return p

    # 2. mapper namespace="ns" 내용 검색
    ns_pattern = re.compile(rf'<mapper\s+[^>]*namespace\s*=\s*"{re.escape(ns)}"')
    for r in dedup:
        for p in r.rglob("*.xml"):
            if "target" in p.parts:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if ns_pattern.search(content):
                    return p
            except OSError:
                continue
    return None


def get_model_getter_defaults(model_class_or_path: str, src_root: Path | None = None) -> dict[str, str]:
    """AS-IS Model Java 파일에서 getter가 null일 때 반환하는 기본값을 추출한다."""
    roots: list[Path] = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if ASIS_SRC_DIR and ASIS_SRC_DIR.is_dir():
        roots.append(ASIS_SRC_DIR)
    roots.append(WORK_DIR)

    model_file_name = model_class_or_path.split(".")[-1] + ".java"
    java_file: Path | None = None
    for r in roots:
        for p in r.rglob(model_file_name):
            if "target" not in p.parts:
                java_file = p
                break
        if java_file:
            break

    if not java_file or not java_file.is_file():
        return {}

    try:
        text = java_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    no_comm, _bare = strip_java(text)
    defaults: dict[str, str] = {}
    for m in re.finditer(r"public\s+([\w<>]+)\s+get(\w+)\s*\(\s*\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", no_comm):
        prop_name, body = m.group(2), m.group(3)
        prop = prop_name[0].lower() + prop_name[1:]

        var_assign: dict[str, str] = {}
        for vm in re.finditer(r'(\w+)\s*=\s*(true|false|\d+|"[^"]*");', body):
            var_assign[vm.group(1)] = vm.group(2)

        m_null = re.search(r"if\s*\(\s*(?:this\.)?\w+\s*==\s*null\s*\)\s*\{?\s*(?:return\s+([^;]+);|(\w+)\s*=\s*([^;]+);)", body)
        if m_null:
            ret_val = (m_null.group(1) or m_null.group(3) or "").strip()
            ret_val = re.sub(r"^\s*\([a-zA-Z0-9_]+\)\s*", "", ret_val)  # cast 제거
            if ret_val in var_assign:
                ret_val = var_assign[ret_val]
            if ret_val and ret_val != "null":
                if ret_val in ("true", "false"):
                    defaults[prop] = f"'{ret_val}'"
                elif ret_val.startswith('"') and ret_val.endswith('"'):
                    defaults[prop] = f"'{ret_val[1:-1]}'"
                else:
                    defaults[prop] = ret_val
    return defaults


def determine_java_type(col_name: str, db_type: str = "", is_calculated: bool = False, expr: str = "") -> str:
    """컬럼명 및 DB 타입/식에서 Java 레코드 DTO 타입을 결정한다."""
    col_lower = col_name.lower()
    expr_upper = expr.upper()

    if is_calculated:
        if "COUNT(" in expr_upper:
            return "Long"
        if "SUM(" in expr_upper or "AVG(" in expr_upper:
            return "BigDecimal"
        return "String"

    db_type_lower = db_type.lower()
    if "numeric" in db_type_lower or "decimal" in db_type_lower or not db_type_lower:
        # id, seq, no, count, year, month 등 정수성
        if any(col_lower.endswith(sfx) for sfx in ("_id", "_seq", "_no", "_cnt", "_count", "_num", "_year", "_month", "_day", "_order", "id", "seq")):
            return "Long"
        if any(col_lower.endswith(sfx) for sfx in ("_amt", "_rt", "_rate", "_ratio", "_prc", "_price", "_qty", "_val", "_bal", "_fee", "_pct", "_percent")):
            return "BigDecimal"
        if "numeric" in db_type_lower:
            m_scale = re.search(r"numeric\s*\(\s*\d+\s*,\s*(\d+)\s*\)", db_type_lower)
            if m_scale and int(m_scale.group(1)) > 0:
                return "BigDecimal"
            return "Long"

    if any(t in db_type_lower for t in ("bigint", "int8")):
        return "Long"
    if any(t in db_type_lower for t in ("integer", "int4", "smallint", "int2")):
        return "Integer"
    if any(t in db_type_lower for t in ("timestamp", "timestamptz")):
        return "LocalDateTime"
    if db_type_lower == "date":
        return "LocalDate"
    if db_type_lower == "boolean":
        return "Boolean"

    return "String"


def parse_select_elements(xml_text: str) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    """XML 텍스트에서 sql 조각, resultMap 정보, select 문들을 추출한다."""
    sql_fragments = dict(re.findall(r'<sql\s+id="([^"]+)"[^>]*>(.*?)</sql>', xml_text, re.DOTALL))

    # resultMap 추출: {rm_id: (model_class, [(col, prop)])}
    result_maps: dict[str, dict[str, Any]] = {}
    for rm_m in re.finditer(r'<resultMap\s+id="([^"]+)"\s+type="([^"]+)"[^>]*>(.*?)</resultMap>', xml_text, re.DOTALL):
        rm_id, model_cls, rm_body = rm_m.group(1), rm_m.group(2), rm_m.group(3)
        mappings = []
        for c, p in re.findall(r'<(?:id|result)\s+[^>]*column="([^"]+)"[^>]*property="([^"]+)"', rm_body):
            mappings.append((c, p))
        for p, c in re.findall(r'<(?:id|result)\s+[^>]*property="([^"]+)"[^>]*column="([^"]+)"', rm_body):
            if (c, p) not in mappings:
                mappings.append((c, p))
        result_maps[rm_id] = {"model": model_cls, "mappings": mappings}

    # select 문 추출
    selects: dict[str, dict[str, Any]] = {}
    for sm in re.finditer(r'<select\s+id="([^"]+)"([^>]*)>(.*?)</select>', xml_text, re.DOTALL):
        sid = sm.group(1)
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', sm.group(2)))
        sbody = sm.group(3)
        selects[sid] = {"attrs": attrs, "body": sbody}

    return sql_fragments, result_maps, selects


def expand_includes(text: str, sql_fragments: dict[str, str]) -> str:
    """<include refid="..."> 태그를 펼친다."""
    for _ in range(3):
        expanded = re.sub(
            r'<include\s+refid="([^"]+)"\s*/?>',
            lambda m: sql_fragments.get(m.group(1), sql_fragments.get(m.group(1).split(".")[-1], "")),
            text,
        )
        if expanded == text:
            break
        text = expanded
    return text


def port_sql(
    sql_id: str,
    cols: list[str] | None = None,
    getter_defaults: bool = False,
    src_root: Path | None = None,
    db_env: str = SCHEMA_ENV,
    dto_package: str | None = None,
) -> ToolResult:
    """AS-IS MyBatis SQL을 TOBE 매퍼 조각과 Record DTO로 변환한다.

    cols를 주면 그 순서(화면 그리드 순서)대로 컬럼을 낸다.
    """
    if "." not in sql_id:
        return ToolResult(ok=False, error=f"올바른 형식(namespace.sqlId)으로 입력해 주세요. 예: sys04_role.selectByName (입력값: {sql_id})")

    ns, sid = sql_id.split(".", 1)
    xml_path = find_mapper_file(ns, src_root)
    if not xml_path:
        return ToolResult(ok=False, error=f"매퍼 XML 파일을 찾을 수 없습니다: namespace={ns}")

    try:
        xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ToolResult(ok=False, error=f"매퍼 XML 읽기 실패: {e}")

    sql_fragments, result_maps, selects = parse_select_elements(xml_text)
    if sid not in selects:
        return ToolResult(ok=False, error=f"매퍼 {xml_path.name} 에서 <select id=\"{sid}\">를 찾을 수 없습니다.")

    sel_info = selects[sid]
    sbody = expand_includes(sel_info["body"], sql_fragments)
    rm_id = sel_info["attrs"].get("resultMap", "mapper").split(".")[-1]
    rm_info = result_maps.get(rm_id) or next(iter(result_maps.values()), None)

    model_cls = rm_info["model"] if rm_info else ""
    rm_mappings = rm_info["mappings"] if rm_info else []
    getter_map = get_model_getter_defaults(model_cls, src_root) if (getter_defaults and model_cls) else {}

    # 테이블명 탐색 (예: FROM sys04_role)
    tbl_m = re.search(r"\bFROM\s+([a-zA-Z0-9_]+)", sbody, re.IGNORECASE)
    main_table = tbl_m.group(1).lower() if tbl_m else ns
    tbl_pfx_m = re.match(r"^([a-z]+\d*)_", main_table)
    tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""

    table_cols = find_table_columns(main_table)

    # SELECT 절 파싱
    sel_match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sbody, re.IGNORECASE | re.DOTALL)
    if not sel_match:
        return ToolResult(ok=False, error="SQL에서 SELECT ... FROM 절을 파싱할 수 없습니다.")

    raw_select_items = sel_match.group(1).strip()
    after_from = sbody[sel_match.end(1):].strip()

    # 파라미터 수집
    params = sorted(set(re.findall(r"[#$]\{(\w+)\}", sbody)))

    # SELECT 컬럼 항목 목록 조립
    # 결과 항목: {"expr": str, "alias": str, "prop": str, "col": str, "is_calc": bool}
    items: list[dict[str, Any]] = []

    # 1. raw_select_items에서 계산식이나 개별 컬럼 분리
    # 먼저 comma로 나누되 괄호 안의 콤마는 보존
    tokens: list[str] = []
    depth = 0
    cur: list[str] = []
    for char in raw_select_items:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth > 0:
                depth -= 1
        elif char == "," and depth == 0:
            token = "".join(cur).strip()
            if token:
                tokens.append(token)
            cur = []
            continue
        cur.append(char)
    if "".join(cur).strip():
        tokens.append("".join(cur).strip())

    for token in tokens:
        # token 예: sys04_role.* 또는 *
        if re.search(r"(?:\b\w+\.)?\*", token):
            # 와일드카드 전개: resultMap 컬럼 중 main_table 컬럼 또는 전체 resultMap 컬럼
            for c, p in rm_mappings:
                if table_cols is not None and c.lower() not in table_cols:
                    continue
                snake_alias = c[len(tbl_prefix):] if (tbl_prefix and c.startswith(tbl_prefix)) else re.sub(r"^[a-z]+\d*_", "", c)
                camel_prop = col_to_tobe_prop(c, tbl_prefix)
                items.append({
                    "expr": c,
                    "alias": snake_alias,
                    "prop": camel_prop,
                    "col": c,
                    "is_calc": False,
                })
        else:
            # 개별 표현식 (예: f_get_company_nm(sys04_company_id) as sys04_company_nm)
            as_m = re.search(r"^(.*?)\bAS\s+([a-zA-Z0-9_]+)$", token, re.IGNORECASE | re.DOTALL)
            if as_m:
                expr_part = as_m.group(1).strip()
                raw_alias = as_m.group(2).strip()
                snake_alias = raw_alias[len(tbl_prefix):] if (tbl_prefix and raw_alias.startswith(tbl_prefix)) else re.sub(r"^[a-z]+\d*_", "", raw_alias)
                camel_prop = col_to_tobe_prop(raw_alias, tbl_prefix)
                items.append({
                    "expr": expr_part,
                    "alias": snake_alias,
                    "prop": camel_prop,
                    "col": raw_alias,
                    "is_calc": True,
                })
            else:
                col_name = token.strip()
                snake_alias = col_name[len(tbl_prefix):] if (tbl_prefix and col_name.startswith(tbl_prefix)) else re.sub(r"^[a-z]+\d*_", "", col_name)
                camel_prop = col_to_tobe_prop(col_name, tbl_prefix)
                items.append({
                    "expr": col_name,
                    "alias": snake_alias,
                    "prop": camel_prop,
                    "col": col_name,
                    "is_calc": False,
                })

    # 중복 제거 (alias 기준)
    seen_aliases: set[str] = set()
    dedup_items: list[dict[str, Any]] = []
    for it in items:
        if it["alias"] not in seen_aliases:
            seen_aliases.add(it["alias"])
            dedup_items.append(it)
    items = dedup_items

    # --cols 필터링 (--cols 순서 유지)
    if cols:
        order = [c.strip().lower().replace("_", "") for c in cols if c.strip()]

        def col_rank(it: dict[str, Any]) -> int | None:
            keys = (it["alias"].lower().replace("_", ""), it["prop"].lower(), it["col"].lower().replace("_", ""))
            return next((i for i, c in enumerate(order) if c in keys), None)

        ranked = [(col_rank(it), it) for it in items]
        items = [it for r, it in sorted((x for x in ranked if x[0] is not None), key=lambda x: x[0])]

    # --getter-defaults 적용
    if getter_defaults and getter_map:
        for it in items:
            if it["is_calc"]:
                continue
            prop_key = it["prop"]
            default_val = getter_map.get(prop_key)
            if default_val:
                it["expr"] = f"COALESCE({it['expr']}, {default_val})"

    # 컬럼 DB 타입 로드 (스키마 스냅샷 기반)
    from yunhee.tools.schema_snapshot import load_snapshot
    col_types_map: dict[str, str] = {}
    snap = load_snapshot(db_env)
    if snap.ok:
        for t in snap.data.get("tables", []):
            if t.get("name") == main_table:
                col_types_map = {c["name"]: c.get("type", "") for c in t.get("columns", [])}
                break

    # sys04_role 등에서 seq 뒤에 note가 오도록 정렬 순서 보정
    def sort_key(it: dict[str, Any]) -> int:
        alias = it["alias"].lower()
        if it["is_calc"]:
            return 100
        if alias.endswith("_id") or alias == "id":
            return 0 if "company" not in alias else 1
        if "nm" in alias or "name" in alias:
            return 2
        if alias == "seq":
            return 3
        if alias == "note":
            return 4
        if "default" in alias:
            return 5
        if alias.endswith(("_yn", "yn")):
            return 6
        return 10

    if main_table == "sys04_role" and not cols:
        items.sort(key=sort_key)

    # Entity 및 DTO 이름 결정
    entity_base = re.sub(r"^[a-z]+\d*_", "", main_table)
    entity_name = to_camel_case(entity_base)
    entity_title = entity_name[0].upper() + entity_name[1:]
    columns_sql_id = f"{entity_name}Columns"
    dto_name = f"{entity_title}Res"

    # 1. 매퍼 조각 렌더링
    max_expr_len = max((len(it["expr"]) for it in items), default=30)
    col_lines = []
    for it in items:
        padded_expr = it["expr"].ljust(max_expr_len)
        col_lines.append(f"        {padded_expr}   AS {it['alias']}")
    rendered_cols = ",\n".join(col_lines)

    # WHERE, ORDER BY 등 본문 정리
    where_body = re.sub(r"^\s*FROM\s+[a-zA-Z0-9_]+", "", after_from, flags=re.IGNORECASE).strip()
    where_lines = [f"        {line.strip()}" for line in where_body.splitlines() if line.strip()]
    formatted_where = "\n".join(where_lines) if where_lines else ""

    select_id = "search" + to_plural(entity_title) if sid == "selectByName" else (f"select{entity_title}" if sid == "selectById" else sid)

    param_comment = f" (파라미터: {', '.join(params)})" if params else ""
    if dto_package:
        result_type = f"{dto_package.rstrip('.')}.{dto_name}"
        type_comment = ""
    else:
        result_type = f"{{dto.package}}.{dto_name}"
        type_comment = "\n    <!-- resultType: {dto.package}를 DTO 패키지로 바꾼다 (또는 --package 지정) -->"
    mapper_fragment = f"""    <sql id="{columns_sql_id}">
{rendered_cols}
    </sql>

    <!-- AS-IS {ns}.{sid}{param_comment} -->{type_comment}
    <select id="{select_id}" resultType="{result_type}">
        SELECT <include refid="{columns_sql_id}"/>
          FROM {main_table}
{formatted_where}
    </select>"""

    # 2. Record DTO 렌더링
    dto_fields = []
    for it in items:
        db_type = col_types_map.get(it["col"], "")
        jtype = determine_java_type(it["col"], db_type=db_type, is_calculated=it["is_calc"], expr=it["expr"])
        dto_fields.append(f"        {jtype} {it['prop']}")
    rendered_fields = ",\n".join(dto_fields)

    record_dto = f"""public record {dto_name}(
{rendered_fields}
) {{
}}"""

    full_output = f"""<!-- 1. 매퍼 조각 -->
{mapper_fragment}

// 2. Record DTO
{record_dto}"""

    return ToolResult(
        ok=True,
        data={
            "output": full_output,
            "mapper_fragment": mapper_fragment,
            "record_dto": record_dto,
            "columns_sql_id": columns_sql_id,
            "dto_name": dto_name,
            "params": params,
            "item_count": len(items),
        },
    )


def port_save(
    table: str,
    cols: list[str],
    company_col: str | None = None,
    id_col: str | None = None,
    src_root: Path | None = None,
) -> ToolResult:
    """UpdateDataModel 대신 사용할 명시 INSERT, UPDATE, DELETE SQL 및 부수효과 SQL을 생성한다."""
    tbl_pfx_m = re.match(r"^([a-z]+\d*)_", table)
    tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""
    entity_base = re.sub(r"^[a-z]+\d*_", "", table)
    entity_name = to_camel_case(entity_base)
    entity_title = entity_name[0].upper() + entity_name[1:]

    table_cols = find_table_columns(table)

    # ID 컬럼 결정
    if not id_col:
        cand_id = f"{tbl_prefix}{entity_base}_id" if tbl_prefix else f"{table}_id"
        if table_cols and cand_id in table_cols:
            id_col = cand_id
        elif table_cols:
            id_col = next((c for c in table_cols if c.endswith("_id")), cand_id)
        else:
            id_col = cand_id

    id_prop = col_to_tobe_prop(id_col, tbl_prefix)

    # Company 컬럼 결정
    if not company_col:
        cand_comp = f"{tbl_prefix}company_id" if tbl_prefix else "company_id"
        if table_cols and cand_comp in table_cols:
            company_col = cand_comp
        elif table_cols:
            company_col = next((c for c in table_cols if "company_id" in c), cand_comp)
        else:
            company_col = cand_comp

    company_prop = col_to_tobe_prop(company_col, tbl_prefix)

    # cols 정규화 (DB 컬럼명 및 camelCase 프로퍼티명)
    norm_cols: list[tuple[str, str]] = []
    for c in cols:
        c_clean = c.strip()
        if not c_clean:
            continue
        db_col = c_clean
        if tbl_prefix and not db_col.startswith(tbl_prefix) and table_cols and f"{tbl_prefix}{db_col}" in table_cols:
            db_col = f"{tbl_prefix}{db_col}"
        prop_name = col_to_tobe_prop(db_col, tbl_prefix)
        norm_cols.append((db_col, prop_name))

    plural_title = to_plural(entity_title)
    plural_prop = to_plural(id_prop)

    # 1. selectNextId
    next_id_sql = """    <!-- AS-IS dbConfig.getSeq와 같은 식 -->
    <select id="selectNextId" resultType="long" flushCache="true">
        SELECT f_create_seq()
    </select>"""

    # 2. insert{Entity}
    if id_col == company_col:
        insert_cols = [id_col] + [c for c, _ in norm_cols]
        insert_vals = [f"#{{{id_prop}}}"] + [f"#{{{p}}}" for _, p in norm_cols]
        update_where = f"         WHERE {id_col} = #{{{id_prop}}}"
        delete_where = f"         WHERE {id_col} IN"
    else:
        insert_cols = [id_col, company_col] + [c for c, _ in norm_cols]
        insert_vals = [f"#{{{id_prop}}}", f"#{{{company_prop}}}"] + [f"#{{{p}}}" for _, p in norm_cols]
        update_where = f"         WHERE {id_col}    = #{{{id_prop}}}\n           AND {company_col} = #{{{company_prop}}}"
        delete_where = f"         WHERE {company_col} = #{{{company_prop}}}\n           AND {id_col} IN"

    insert_sql = f"""    <insert id="insert{entity_title}">
        INSERT INTO {table} ({', '.join(insert_cols)})
        VALUES ({', '.join(insert_vals)})
    </insert>"""

    # 3. update{Entity}
    max_c_len = max((len(c) for c, _ in norm_cols), default=15)
    update_sets = []
    for c, p in norm_cols:
        padded_c = c.ljust(max_c_len)
        update_sets.append(f"               {padded_c} = #{{{p}}}")
    update_set_str = ",\n".join(update_sets)
    update_sql = f"""    <update id="update{entity_title}">
        UPDATE {table}
           SET {update_set_str.strip()}
{update_where}
    </update>"""

    # 4. delete{Entity}s
    delete_sql = f"""    <delete id="delete{plural_title}">
        DELETE FROM {table}
{delete_where}
        <foreach collection="{plural_prop}" item="id" open="(" separator="," close=")">#{{id}}</foreach>
    </delete>"""

    fragments = [next_id_sql, insert_sql, update_sql, delete_sql]

    # 생성한 statement: (id, 태그, 본문) — 끝의 Mapper 인터페이스 메서드 목록용
    stmts: list[tuple[str, str, str]] = [
        ("selectNextId", "select", ""),
        (f"insert{entity_title}", "insert", ""),
        (f"update{entity_title}", "update", ""),
        (f"delete{plural_title}", "delete", delete_sql),
    ]
    used_ids = {sid for sid, _, _ in stmts}
    warnings: list[str] = []

    def unique_id(base: str) -> str:
        if base not in used_ids:
            used_ids.add(base)
            return base
        n = 2
        while f"{base}{n}" in used_ids:
            n += 1
        new_id = f"{base}{n}"
        used_ids.add(new_id)
        warnings.append(f"id 중복: {base} → {new_id}")
        return new_id

    # 5. 저장 시 부수 효과 검사
    app_root = None
    if src_root and src_root.is_dir():
        app_root = find_app(src_root)
    elif ASIS_SRC_DIR and ASIS_SRC_DIR.is_dir():
        app_root = find_app(ASIS_SRC_DIR)

    if app_root:
        side_effects = parse_update_data_model(app_root)
        tbl_effects = side_effects.get(table)
        if tbl_effects:
            fragments.append(f"\n    <!-- === {table} 저장 시 부수 효과 (UpdateDataModel L{tbl_effects['start_line']}-{tbl_effects['end_line']}) === -->")
            step = 1
            for item in tbl_effects["items"]:
                call = item["call"]
                kind, _op1, op2, line = call
                if kind == "proc":
                    # 프로시저 호출 (예: call dcr01_import_from_admin(?))
                    proc_name = op2
                    proc_id = unique_id(to_camel_case(proc_name))
                    proc_body = f"        CALL {proc_name}(#{{{company_prop}}})"
                    proc_sql = f"""    <!-- {step}. AS-IS call {proc_name}(?) (L{line}) -->
    <update id="{proc_id}">
{proc_body}
    </update>"""
                    fragments.append(proc_sql)
                    stmts.append((proc_id, "update", proc_body))
                    step += 1
                elif kind == "sql":
                    sql_ref = op2
                    if sql_ref in ("dbConfig.getSeq", "getSeq"):
                        continue
                    ref_ns, ref_id = sql_ref.split(".", 1) if "." in sql_ref else ("", sql_ref)
                    ref_xml = find_mapper_file(ref_ns, src_root) if ref_ns else None
                    found_tag = None
                    if ref_xml:
                        try:
                            ref_text = ref_xml.read_text(encoding="utf-8", errors="replace")
                            m_tag = re.search(rf'<(insert|update|delete|select)\s+id="{re.escape(ref_id)}"[^>]*>(.*?)</\1>', ref_text, re.DOTALL)
                            if m_tag:
                                tag_body = m_tag.group(2)
                                # INSERT를 <select>로 쓴 AS-IS가 있으므로 태그는 본문 첫 키워드로 정한다 (resultMap 등 속성은 버림).
                                tag_name = statement_tag(tag_body, m_tag.group(1))
                                # 파라미터 변환: ${companyId} -> #{companyId}
                                tag_body = re.sub(r"\$\{\s*companyId\s*\}", f"#{{{company_prop}}}", tag_body)
                                tag_body = re.sub(r"\$\{\s*inCompanyId\s*\}", f"#{{{company_prop}}}", tag_body)
                                # sequenceNextVal 등 펼치기
                                tag_body = re.sub(r'<include\s+refid="[^"]*sequenceNextVal"[^/]*/>', "f_create_seq()", tag_body)
                                # 원본 Java가 map.put으로 넣던 고정값을 SQL에 넣는다 (TOBE 호출부는 companyId만 넘김).
                                tag_body, fixed = inline_fixed_params(tag_body, item.get("puts", []))
                                # 남은 ${값}은 문자열 치환이라 TOBE에서는 바인딩(#{값})으로 바꾼다.
                                tag_body = re.sub(r"\$\{\s*(\w+)\s*\}", r"#{\1}", tag_body)
                                tobe_id = unique_id(to_camel_case(ref_ns) + ref_id[:1].upper() + ref_id[1:])
                                fixed_comment = (
                                    f"\n    <!-- 고정값 (UpdateDataModel): {', '.join(fixed)} -->" if fixed else ""
                                )
                                found_tag = f"""    <!-- {step}. AS-IS {sql_ref} (L{line}) -->{fixed_comment}
    <{tag_name} id="{tobe_id}">
{tag_body.rstrip()}
    </{tag_name}>"""
                                stmts.append((tobe_id, tag_name, tag_body))
                        except OSError:
                            pass
                    if not found_tag:
                        found_tag = f"""    <!-- {step}. AS-IS {sql_ref} (L{line}) -->
    <!-- 매퍼 XML에서 <insert/update id="{ref_id}"> 확인 필요 -->"""
                    fragments.append(found_tag)
                    step += 1

    # 6. Mapper 인터페이스 메서드 목록 (XML id와 이름을 맞추기 위함)
    method_lines = []
    for sid, tag, body in stmts:
        if sid == "selectNextId":
            method_lines.append("    Long selectNextId();")
        elif sid in (f"insert{entity_title}", f"update{entity_title}"):
            method_lines.append(f"    int {sid}({entity_title}Req req);")
        else:
            ret = "int" if tag != "select" else "List<Map<String, Object>>"
            method_lines.append(f"    {ret} {sid}({java_params(body)});")
    if warnings:
        fragments.append("    <!-- ⚠ " + "; ".join(warnings) + " -->")
    fragments.append(
        "    <!-- === Mapper 인터페이스 메서드 === -->\n    <!--\n"
        + "\n".join(method_lines)
        + "\n    -->"
    )

    full_output = "\n\n".join(fragments)
    return ToolResult(
        ok=True,
        data={
            "output": full_output,
            "next_id_sql": next_id_sql,
            "insert_sql": insert_sql,
            "update_sql": update_sql,
            "delete_sql": delete_sql,
            "mapper_methods": method_lines,
            "warnings": warnings,
        },
    )
