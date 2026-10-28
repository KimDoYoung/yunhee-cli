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
    text = re.sub(r"</?[a-zA-Z0-9_]+(?:'[^']*'|\"[^\"]*\"|[^>'])*>", " ", _strip_sql_noise(body))
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


def split_depth0_commas(s: str) -> list[str]:
    """괄호·따옴표·주석·CASE/END 깊이 0에 있는 쉼표로만 분리한다."""
    tokens: list[str] = []
    depth = 0
    case_depth = 0
    cur: list[str] = []
    in_q = None
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if in_q:
            if ch == in_q:
                if in_q == "'" and i + 1 < n and s[i + 1] == "'":
                    cur.append(ch)
                    cur.append(s[i + 1])
                    i += 2
                    continue
                in_q = None
            cur.append(ch)
            i += 1
            continue
        # 블록 주석 /* ... */ 및 XML 주석 <!-- ... --> 건너뛰기
        if s.startswith("/*", i):
            end_c = s.find("*/", i + 2)
            end_c = n if end_c < 0 else end_c + 2
            cur.append(s[i:end_c])
            i = end_c
            continue
        if s.startswith("<!--", i):
            end_c = s.find("-->", i + 4)
            end_c = n if end_c < 0 else end_c + 3
            cur.append(s[i:end_c])
            i = end_c
            continue
        if s.startswith("--", i):
            end_c = s.find("\n", i + 2)
            end_c = n if end_c < 0 else end_c
            cur.append(s[i:end_c])
            i = end_c
            continue
        if ch in ("'", '"'):
            in_q = ch
            cur.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth > 0:
                depth -= 1
        elif s[i : i + 4].upper() == "CASE" and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")) and (i + 4 == n or not (s[i + 4].isalnum() or s[i + 4] == "_")):
            case_depth += 1
        elif s[i : i + 3].upper() == "END" and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")) and (i + 3 == n or not (s[i + 3].isalnum() or s[i + 3] == "_")):
            if case_depth > 0:
                case_depth -= 1
        elif ch == "," and depth == 0 and case_depth == 0:
            token = "".join(cur).strip()
            if token:
                tokens.append(token)
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if "".join(cur).strip():
        tokens.append("".join(cur).strip())
    return tokens


def camel_to_snake(name: str) -> str:
    """camelCase 문자열을 snake_case로 변환한다."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return re.sub(r"_+", "_", s)


def _normalize_col_name(name: str) -> str:
    """컬럼명 또는 프로퍼티명을 비교용 표준 형태로 정규화한다."""
    s = re.sub(r"^[a-z]+\d*_", "", name.strip()).lower().replace("_", "")
    s = re.sub(r"name$", "nm", s)
    s = re.sub(r"address$", "addr", s)
    s = re.sub(r"telno$", "tel", s)
    s = re.sub(r"count$", "cnt", s)
    s = re.sub(r"number$", "no", s)
    return s


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


def _java_cond_to_sql_candidate(
    cond: str,
    prop_to_col: dict[str, str],
    alias: str,
) -> str | None:
    """단순 Java 비교식을 SQL 표현식 후보로 변환한다."""
    tokens = re.split(r"\s*(\|\||&&)\s*", cond.strip())
    sql_parts: list[str] = []
    for tok in tokens:
        t = tok.strip()
        if t == "||":
            sql_parts.append("OR")
            continue
        if t == "&&":
            sql_parts.append("AND")
            continue
        m_cmp = re.match(r"^(?:this\.)?(\w+)\s*(==|!=|<=|>=|<|>)\s*(.+)$", t)
        if not m_cmp:
            return None
        prop, op, val = m_cmp.group(1), m_cmp.group(2), m_cmp.group(3).strip()
        col = prop_to_col.get(prop)
        if not col:
            return None
        sql_op = "=" if op == "==" else ("<>" if op == "!=" else op)
        if val.startswith('"') and val.endswith('"'):
            sql_val = f"'{val[1:-1]}'"
        else:
            sql_val = val
        if sql_op == "<>" and sql_val == "0":
            sql_parts.append(f"COALESCE({col},0) <> 0")
        else:
            sql_parts.append(f"{col} {sql_op} {sql_val}")
    if not sql_parts:
        return None
    joined = " ".join(sql_parts)
    if " OR " in joined or " AND " in joined:
        return f"({joined}) AS {alias}"
    return f"{joined} AS {alias}"


def get_model_calculated_getters(
    model_class_or_path: str,
    src_root: Path | None = None,
    rm_mappings: list[tuple[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Model.java에서 필드가 없는 계산 getter(메서드명, 줄범위, 반환타입, 본문 식, SQL 후보)를 추출한다."""
    if not model_class_or_path:
        return {}
    roots = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if ASIS_SRC_DIR and Path(ASIS_SRC_DIR).is_dir():
        roots.append(Path(ASIS_SRC_DIR))
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

    lines = text.splitlines()
    fields: set[str] = set()
    for line in lines:
        m_field = re.search(r"(?:private|protected)\s+([\w<>\[\], ?]+)\s+(\w+)\s*;", line)
        if m_field:
            fields.add(m_field.group(2))

    prop_to_col: dict[str, str] = {}
    if rm_mappings:
        for c, p in rm_mappings:
            prop_to_col[p] = c

    calc_getters: dict[str, dict[str, Any]] = {}
    for i, line in enumerate(lines):
        m_get = re.search(r"public\s+([\w<>\[\], ?]+)\s+(get([A-Z]\w*))\s*\(\s*\)", line)
        if not m_get:
            continue
        ret_type = m_get.group(1).strip()
        meth_name = m_get.group(2).strip()
        raw_name = m_get.group(3)
        prop_name = raw_name[0].lower() + raw_name[1:]
        if prop_name in ("keyId",) or prop_name in fields:
            continue

        start_l = i + 1
        end_l = start_l
        for j in range(i, min(len(lines), i + 30)):
            if "}" in lines[j]:
                end_l = j + 1
                break

        # 전체 메서드 본문 추출 (중괄호 깊이 기준)
        depth = 0
        body_lines: list[str] = []
        started = False
        for j in range(i, min(len(lines), i + 40)):
            ln = lines[j]
            for ch in ln:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
            body_lines.append(ln)
            if started and depth <= 0:
                break

        raw_body = "\n".join(body_lines)
        brace_idx = raw_body.find("{")
        rbrace_idx = raw_body.rfind("}")
        inner_body = raw_body[brace_idx + 1:rbrace_idx].strip() if (brace_idx != -1 and rbrace_idx > brace_idx) else raw_body.strip()

        expr_str = ""
        m_if_bool = re.search(
            r"if\s*\((.+?)\)\s*\{\s*return\s+true\s*;\s*\}\s*else\s*\{\s*return\s+false\s*;\s*\}",
            inner_body,
            re.DOTALL,
        )
        if m_if_bool:
            expr_str = re.sub(r"\s+", " ", m_if_bool.group(1).strip())
        else:
            m_ret = re.match(r"^return\s+(.+?)\s*;$", inner_body.strip(), re.DOTALL)
            if m_ret:
                expr_str = re.sub(r"\s+", " ", m_ret.group(1).strip())
            else:
                expr_str = re.sub(r"\s+", " ", inner_body)

        snake_alias = camel_to_snake(prop_name)
        sql_cand = _java_cond_to_sql_candidate(expr_str, prop_to_col, snake_alias) if prop_to_col else None
        calc_getters[prop_name] = {
            "method": meth_name,
            "start": start_l,
            "end": end_l,
            "ret_type": ret_type,
            "expr": expr_str,
            "sql_candidate": sql_cand,
        }
    return calc_getters



def get_model_field_types(
    model_class_or_path: str,
    src_root: Path | None = None,
) -> dict[str, str]:
    """Model.java에서 선언된 필드명 -> Java 타입 맵을 추출한다."""
    if not model_class_or_path:
        return {}
    roots = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if ASIS_SRC_DIR and Path(ASIS_SRC_DIR).is_dir():
        roots.append(Path(ASIS_SRC_DIR))
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

    no_comm, _ = strip_java(text)
    field_types: dict[str, str] = {}
    for line in no_comm.splitlines():
        m_field = re.search(r"(?:private|protected)\s+([\w<>\[\], ?]+)\s+(\w+)\s*;", line)
        if m_field:
            field_types[m_field.group(2)] = m_field.group(1).strip()
    return field_types


def determine_java_type(
    col_name: str,
    db_type: str = "",
    is_calculated: bool = False,
    expr: str = "",
    model_type: str = "",
) -> str:
    """컬럼명 및 DB 타입/식/모델 필드 타입에서 Java 레코드 DTO 타입을 결정한다."""
    col_lower = col_name.lower()
    expr_upper = expr.upper()

    if is_calculated:
        if model_type in ("Long", "Integer", "Double", "BigDecimal", "Boolean"):
            return model_type
        if "COUNT(" in expr_upper or "ROW_NUMBER(" in expr_upper:
            return "Long"
        if any(col_lower.endswith(sfx) for sfx in ("_id", "_seq", "_no", "_cnt", "_count", "_num", "id", "seq")):
            return "Long"
        if any(col_lower.endswith(sfx) for sfx in ("_rt", "_rate", "_ratio", "_pct", "_percent")):
            return "Double" if "100.0" in expr_upper else "BigDecimal"
        if "SUM(" in expr_upper or "AVG(" in expr_upper:
            return "BigDecimal"
        return "String"

    if not db_type and model_type in ("Long", "Integer", "Double", "BigDecimal", "Boolean"):
        return model_type

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


_SQL_KEYWORDS = {
    "END", "NULL", "TRUE", "FALSE", "ASC", "DESC", "FROM", "WHERE", "AND", "OR", "ELSE", "THEN", "WHEN",
}


def _extract_subquery_body(after_from: str) -> str | None:
    """FROM 절이 '( SELECT ... ) alias' 인라인 뷰로 시작하면 괄호 안 본문을 반환한다."""
    from yunhee.tools.as_is.mybatis_render import mask_sql_preserve

    masked_af = mask_sql_preserve(after_from)
    m_open = re.match(r"^\s*\(", masked_af)
    if not m_open:
        return None
    open_pos = m_open.end() - 1
    depth = 0
    for i in range(open_pos, len(masked_af)):
        if masked_af[i] == "(":
            depth += 1
        elif masked_af[i] == ")":
            depth -= 1
            if depth == 0:
                return after_from[open_pos + 1 : i]
    return None


def _parse_subquery_items(
    sub_body: str,
    wc_prefix: str,
    tbl_prefix: str,
    rm_mappings: list[tuple[str, str]],
    table_cols: set[str] | None,
    cols: list[str] | None,
) -> list[dict[str, Any]]:
    """인라인 뷰(서브쿼리)의 최상위 SELECT 열을 파싱하여 바깥 쿼리의 와일드카드(t.*) 확장 항목을 만든다."""
    from yunhee.tools.as_is.mybatis_render import mask_sql_preserve
    from yunhee.tools.as_is.sql_checker import _depth0_matches

    masked_sub = mask_sql_preserve(sub_body)
    sel_matches = _depth0_matches(masked_sub, r"\bSELECT\b")
    if not sel_matches:
        return []
    main_sel = sel_matches[0]
    from_matches = [m for m in _depth0_matches(masked_sub, r"\bFROM\b") if m.start() > main_sel.end()]
    if not from_matches:
        return []

    sub_select_raw = sub_body[main_sel.end() : from_matches[0].start()].strip()
    sub_after_from = sub_body[from_matches[0].end() :].strip()

    sub_tokens = split_depth0_commas(sub_select_raw)
    result_items: list[dict[str, Any]] = []

    for sub_tok in sub_tokens:
        clean_sub = _strip_sql_noise(sub_tok).strip()
        if not clean_sub:
            continue
        m_wc = re.match(r"^(?:(\w+)\.)?\*$", clean_sub)
        if m_wc:
            inner_sub_body = _extract_subquery_body(sub_after_from)
            if inner_sub_body is not None:
                result_items.extend(
                    _parse_subquery_items(inner_sub_body, wc_prefix, tbl_prefix, rm_mappings, table_cols, cols)
                )
            else:
                # 서브쿼리 안의 테이블 와일드카드 (예: SELECT tdm51_chck_org.*, ... FROM tdm51_chck_org)
                for c, p in rm_mappings:
                    if table_cols is not None and c.lower() not in table_cols:
                        continue
                    snake_alias = c[len(tbl_prefix) :] if (tbl_prefix and c.startswith(tbl_prefix)) else re.sub(r"^[a-z]+\d*_", "", c)
                    camel_prop = p or col_to_tobe_prop(c, tbl_prefix)
                    result_items.append({
                        "expr": f"{wc_prefix}{c}",
                        "alias": snake_alias,
                        "prop": camel_prop,
                        "col": c,
                        "is_calc": False,
                        "calc_expr": "",
                    })
            continue

        as_m = re.search(r"^(.*?)\bAS\s+([a-zA-Z0-9_]+)\s*$", clean_sub, re.IGNORECASE | re.DOTALL)
        if not as_m:
            as_m = re.search(r"^(.*?[\w\)])\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$", clean_sub, re.DOTALL)
            if as_m and as_m.group(2).upper() in _SQL_KEYWORDS:
                as_m = None

        if as_m:
            inner_expr = as_m.group(1).strip()
            inner_alias = as_m.group(2).strip()
            is_calc = True
        else:
            inner_expr = clean_sub
            inner_alias = clean_sub.split(".")[-1].strip()
            is_calc = False

        snake_alias = (
            inner_alias[len(tbl_prefix) :]
            if (tbl_prefix and inner_alias.startswith(tbl_prefix))
            else re.sub(r"^[a-z]+\d*_", "", inner_alias)
        )
        camel_prop = col_to_tobe_prop(inner_alias, tbl_prefix)
        result_items.append({
            "expr": f"{wc_prefix}{inner_alias}",
            "alias": snake_alias,
            "prop": camel_prop,
            "col": inner_alias,
            "is_calc": is_calc,
            "calc_expr": inner_expr,
        })

    return result_items


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


def _convert_colon_to_sharp(sql: str) -> str:
    """SQL 본문의 :param을 #{param}으로 치환한다. 단 ::cast, 문자열 리터럴, 주석은 보존한다."""
    pattern = re.compile(
        r"('(?:''|[^'])*')|"           # 'string literal'
        r"(/\*.*?\*/)|"                # /* comment */
        r"(--[^\n]*)|"                 # -- comment
        r"(?<!:):([a-zA-Z_]\w*)"       # :param (not preceded by :)
        , re.DOTALL,
    )

    def repl(m: re.Match) -> str:
        if m.group(1):
            return m.group(1)
        if m.group(2):
            return m.group(2)
        if m.group(3):
            return m.group(3)
        return f"#{{{m.group(4)}}}"

    return pattern.sub(repl, sql)


def port_sql(
    sql_id: str,
    cols: list[str] | None = None,
    getter_defaults: bool = False,
    src_root: Path | None = None,
    db_env: str = SCHEMA_ENV,
    dto_package: str | None = None,
    raw: bool = False,
    insert_into: str | None = None,
    insert_cols: str | None = None,
) -> ToolResult:
    """AS-IS MyBatis SQL을 TOBE 매퍼 조각과 Record DTO로 변환한다.

    cols를 주면 그 순서(화면 그리드 순서)대로 컬럼을 낸다.
    raw=True이면 컬럼 파싱 및 DTO 생성을 생략하고 원본 SQL을 verbatim CDATA로 낸다.
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
    # mybatis_render를 통해 structure 모드로 include 완전 펼치기
    from yunhee.tools.as_is.mybatis_render import get_all_statements, mask_sql_preserve
    from yunhee.tools.as_is.mybatis_render import render as mr_render
    from yunhee.tools.as_is.sql_checker import _depth0_matches

    stmts = get_all_statements(src_root)
    if sql_id in stmts or any(s.sid == sid for s in stmts.values()):
        sbody, _ = mr_render(sql_id, mode="structure", statements=stmts)
        m_tag = re.match(r"^\s*<(?:select|insert|update|delete|sql)\b[^>]*>(.*?)</(?:select|insert|update|delete|sql)>\s*$", sbody, re.DOTALL | re.IGNORECASE)
        if m_tag:
            sbody = m_tag.group(1)
    else:
        sbody = expand_includes(sel_info["body"], sql_fragments)

    if raw:
        converted_sql = _convert_colon_to_sharp(sbody.strip())
        # 중첩 CDATA 방지: 이미 CDATA 태그가 있다면 내용만 추출
        clean_cdata_sql = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", converted_sql, flags=re.DOTALL)

        warnings: list[str] = []
        # 원본 첫 줄이 SELECT *이고 조인이 있으면 모호 열 경고
        m_first_sel = re.search(r"^\s*SELECT\s+.*?\bFROM\b", clean_cdata_sql, re.IGNORECASE | re.DOTALL)
        if m_first_sel and re.search(r"\*", m_first_sel.group(0)) and re.search(r"\bJOIN\b", clean_cdata_sql, re.IGNORECASE):
            warnings.append("SELECT *와 JOIN이 함께 사용되어 서브쿼리로 감싸 쓸 때 컬럼명이 중복될 수 있습니다")

        warn_comment = ("    <!-- ⚠ " + "; ".join(warnings) + " -->\n") if warnings else ""

        # <sql id="{sid}">
        sql_fragment = f"""    <sql id="{sid}">
<![CDATA[
{clean_cdata_sql}
]]>
    </sql>"""

        insert_fragment = ""
        if insert_into:
            insert_lines_target = []
            insert_lines_select = []
            if insert_cols:
                col_pairs = [c.strip() for c in insert_cols.split(",") if c.strip()]
                for cp in col_pairs:
                    if "=" in cp:
                        t_col, s_expr = cp.split("=", 1)
                        insert_lines_target.append(t_col.strip())
                        insert_lines_select.append(s_expr.strip())
                    else:
                        insert_lines_target.append(cp)
                        insert_lines_select.append(f"y.{cp}")
            target_cols_str = ",\n               ".join(insert_lines_target) if insert_lines_target else "..."
            select_exprs_str = ",\n             ".join(insert_lines_select) if insert_lines_select else "..."
            entity_base = re.sub(r"^[a-z]+\d*_", "", insert_into)
            entity_name = to_camel_case(entity_base)
            entity_title = entity_name[0].upper() + entity_name[1:]
            insert_fragment = f"""

    <insert id="insert{entity_title}">
        INSERT INTO {insert_into}
               ( {target_cols_str} )
        SELECT {select_exprs_str}
          FROM (<include refid="{sid}"/>) y
    </insert>"""

        full_output = f"<!-- AS-IS {ns}.{sid} verbatim query -->\n{warn_comment}{sql_fragment}{insert_fragment}"
        return ToolResult(
            ok=True,
            data={
                "output": full_output,
                "mapper_fragment": sql_fragment,
                "insert_fragment": insert_fragment,
                "record_dto": "",
                "columns_sql_id": sid,
                "dto_name": "",
                "params": [],
                "item_count": 0,
                "warnings": warnings,
            },
        )

    rm_id = sel_info["attrs"].get("resultMap", "mapper").split(".")[-1]
    rm_info = result_maps.get(rm_id) or next(iter(result_maps.values()), None)

    model_cls = rm_info["model"] if rm_info else ""
    rm_mappings = rm_info["mappings"] if rm_info else []
    rm_col_to_prop = {c.lower(): p for c, p in rm_mappings}
    model_field_types = get_model_field_types(model_cls, src_root) if model_cls else {}
    getter_map = get_model_getter_defaults(model_cls, src_root) if (getter_defaults and model_cls) else {}
    calc_getters = get_model_calculated_getters(model_cls, src_root, rm_mappings) if model_cls else {}

    # 최상위 깊이 SELECT 절 파싱
    masked = mask_sql_preserve(sbody)
    sel_matches = _depth0_matches(masked, r"\bSELECT\b")
    if not sel_matches:
        return ToolResult(
            ok=False,
            error=f"SELECT ... FROM 절을 파싱할 수 없습니다. include·CTE를 펼친 원문은 'yunhee analysis sql {sql_id} -o sql'로 확인하세요.",
        )
    main_sel = sel_matches[-1] if len(sel_matches) > 1 else sel_matches[0]
    start = main_sel.end()

    from_matches = [m for m in _depth0_matches(masked, r"\bFROM\b") if m.start() > start]
    if not from_matches:
        return ToolResult(
            ok=False,
            error=f"SELECT ... FROM 절을 파싱할 수 없습니다. include·CTE를 펼친 원문은 'yunhee analysis sql {sql_id} -o sql'로 확인하세요.",
        )
    stop = from_matches[0].start()
    raw_select_items = sbody[start:stop].strip()
    after_from = sbody[from_matches[0].end():].strip()

    # CTE (WITH ...) 확인
    cte_block = ""
    prefix_text = sbody[:main_sel.start()].strip()
    if prefix_text.upper().startswith("WITH") or "WITH " in prefix_text.upper():
        cte_block = f"    {prefix_text}\n"

    # 테이블명 탐색 (예: FROM sys04_role)
    tbl_m = re.match(r"\s*([a-zA-Z0-9_]+)", after_from)
    main_table = tbl_m.group(1).lower() if tbl_m else ns
    tbl_pfx_m = re.match(r"^([a-z]+\d*)_", main_table)
    tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""

    table_cols = find_table_columns(main_table)

    # 파라미터 수집
    params = sorted(set(re.findall(r"[#$]\{(\w+)\}", sbody)))

    # SELECT 컬럼 항목 목록 조립
    # 결과 항목: {"expr": str, "alias": str, "prop": str, "col": str, "is_calc": bool}
    items: list[dict[str, Any]] = []
    subquery_expand_failed = False

    # 1. raw_select_items에서 계산식이나 개별 컬럼 분리
    tokens = split_depth0_commas(raw_select_items)

    for token in tokens:
        clean_token = _strip_sql_noise(token).strip()
        if not clean_token:
            continue
        # token 예: sys04_role.* 또는 t.* 또는 *
        m_wc = re.match(r"^(?:(\w+)\.)?\*$", clean_token)
        if m_wc:
            wc_alias = m_wc.group(1)
            wc_prefix = f"{wc_alias}." if wc_alias else ""
            sub_body = _extract_subquery_body(after_from)
            if sub_body is not None:
                sub_items = _parse_subquery_items(
                    sub_body, wc_prefix, tbl_prefix, rm_mappings, table_cols, cols
                )
                if not sub_items:
                    subquery_expand_failed = True
                else:
                    items.extend(sub_items)
                continue

            # 일반 테이블 와일드카드 전개: cols가 주어지면 cols에 매핑되는 컬럼만 전개
            if cols:
                cols_norm_map: dict[str, str] = {}
                for u in cols:
                    u_c = u.strip()
                    if u_c:
                        cols_norm_map[_normalize_col_name(u_c)] = u_c

                col_by_norm: dict[str, tuple[str, str]] = {}
                for c, p in rm_mappings:
                    if table_cols is not None and c.lower() not in table_cols:
                        continue
                    snake_alias = c[len(tbl_prefix):] if (tbl_prefix and c.startswith(tbl_prefix)) else re.sub(r"^[a-z]+\d*_", "", c)
                    camel_prop = col_to_tobe_prop(c, tbl_prefix)
                    for k in (_normalize_col_name(camel_prop), _normalize_col_name(snake_alias), _normalize_col_name(c)):
                        if k not in col_by_norm:
                            col_by_norm[k] = (c, p)

                for u_norm, u_clean in cols_norm_map.items():
                    if u_norm in col_by_norm:
                        c, p = col_by_norm[u_norm]
                        snake_alias = camel_to_snake(u_clean)
                        items.append({
                            "expr": c,
                            "alias": snake_alias,
                            "prop": u_clean,
                            "col": c,
                            "is_calc": False,
                        })
            else:
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
            as_m = re.search(r"^(.*?)\bAS\s+([a-zA-Z0-9_]+)\s*$", clean_token, re.IGNORECASE | re.DOTALL)
            if not as_m:
                as_m = re.search(r"^(.*?[\w\)])\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$", clean_token, re.DOTALL)
                if as_m and as_m.group(2).upper() in _SQL_KEYWORDS:
                    as_m = None
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
                col_name = clean_token
                snake_alias = col_name[len(tbl_prefix):] if (tbl_prefix and col_name.startswith(tbl_prefix)) else re.sub(r"^[a-z]+\d*_", "", col_name)
                camel_prop = col_to_tobe_prop(col_name, tbl_prefix)
                items.append({
                    "expr": col_name,
                    "alias": snake_alias,
                    "prop": camel_prop,
                    "col": col_name,
                    "is_calc": False,
                })

    if subquery_expand_failed:
        return ToolResult(
            ok=False,
            error="⚠ 서브쿼리 t.* 확장 실패 — 수동 작성 필요",
        )

    # 중복 제거 (alias 기준)
    seen_aliases: set[str] = set()
    dedup_items: list[dict[str, Any]] = []
    for it in items:
        if it["alias"] not in seen_aliases:
            seen_aliases.add(it["alias"])
            dedup_items.append(it)
    items = dedup_items

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

    # --cols 매핑 및 Record DTO 필드 생성
    warnings: list[str] = []
    dto_fields: list[str] = []
    sql_candidate_comments: list[str] = []

    if cols:
        matched_items: list[dict[str, Any]] = []
        matched_indices: set[int] = set()
        for user_col in cols:
            u_clean = user_col.strip()
            if not u_clean:
                continue
            u_norm = _normalize_col_name(u_clean)
            match_idx = None
            for idx, it in enumerate(items):
                if idx in matched_indices:
                    continue
                keys = (
                    _normalize_col_name(it["prop"]),
                    _normalize_col_name(it["alias"]),
                    _normalize_col_name(it["col"]),
                )
                if u_norm in keys:
                    match_idx = idx
                    break
            if match_idx is not None:
                matched_indices.add(match_idx)
                it = items[match_idx]
                snake_alias = camel_to_snake(u_clean)
                it["alias"] = snake_alias
                it["prop"] = u_clean
                db_type = col_types_map.get(it["col"], "")
                m_prop = rm_col_to_prop.get(it["col"].lower()) or u_clean
                m_type = model_field_types.get(m_prop) or model_field_types.get(u_clean, "")
                calc_expr = it.get("calc_expr") or it["expr"]
                jtype = determine_java_type(
                    it["col"], db_type=db_type, is_calculated=it["is_calc"], expr=calc_expr, model_type=m_type
                )
                dto_fields.append(f"        {jtype} {u_clean}")
                matched_items.append(it)
            elif u_clean in calc_getters:
                cg = calc_getters[u_clean]
                dto_fields.append(
                    f"        // {cg['method']} L{cg['start']}-{cg['end']}: {cg['expr']}\n        {cg['ret_type']} {u_clean}"
                )
                if cg.get("sql_candidate"):
                    sql_candidate_comments.append(
                        f"        -- {cg['method']} L{cg['start']}-{cg['end']}: {cg['sql_candidate']}"
                    )
            else:
                warnings.append(f"SQL 열 없음: {u_clean}")
                dto_fields.append(f"        // ⚠ SQL 열 없음: {u_clean}\n        String {u_clean}")

        remaining_items = [it for idx, it in enumerate(items) if idx not in matched_indices]
        items = matched_items + remaining_items
    else:
        for it in items:
            db_type = col_types_map.get(it["col"], "")
            m_prop = rm_col_to_prop.get(it["col"].lower()) or it["prop"]
            m_type = model_field_types.get(m_prop, "")
            calc_expr = it.get("calc_expr") or it["expr"]
            jtype = determine_java_type(
                it["col"], db_type=db_type, is_calculated=it["is_calc"], expr=calc_expr, model_type=m_type
            )
            dto_fields.append(f"        {jtype} {it['prop']}")

    # 1. 매퍼 조각 렌더링 (SELECT 열 전체 보존)
    max_expr_len = max((len(it["expr"]) for it in items), default=30)
    col_lines = []
    for it in items:
        padded_expr = it["expr"].ljust(max_expr_len)
        col_lines.append(f"        {padded_expr}   AS {it['alias']}")
    rendered_cols = ",\n".join(col_lines)
    if sql_candidate_comments:
        rendered_cols = "\n".join(sql_candidate_comments) + "\n" + rendered_cols


    # FROM 절 및 본문 포맷팅 (최상위 FROM부터 원문 그대로 복사)
    from_raw = sbody[from_matches[0].start():].strip()
    from_lines = from_raw.splitlines()
    formatted_from_lines = []
    for idx, line in enumerate(from_lines):
        st_line = line.strip()
        if not st_line:
            continue
        if idx == 0 and re.match(r"^FROM\b", st_line, re.IGNORECASE):
            rest_first = re.sub(r"^FROM\s*", "", st_line, flags=re.IGNORECASE)
            formatted_from_lines.append(f"          FROM {rest_first}")
        else:
            formatted_from_lines.append(f"        {st_line}")
    formatted_from = "\n".join(formatted_from_lines)

    select_id = "search" + to_plural(entity_title) if sid == "selectByName" else (f"select{entity_title}" if sid == "selectById" else sid)

    param_comment = f" (파라미터: {', '.join(params)})" if params else ""
    warn_comment = ("\n    <!-- ⚠ " + "; ".join(warnings) + " -->") if warnings else ""
    if dto_package:
        result_type = f"{dto_package.rstrip('.')}.{dto_name}"
        type_comment = ""
    else:
        result_type = f"{{dto.package}}.{dto_name}"
        type_comment = "\n    <!-- resultType: {dto.package}를 DTO 패키지로 바꾼다 (또는 --package 지정) -->"
    mapper_fragment = f"""    <sql id="{columns_sql_id}">
{rendered_cols}
    </sql>

    <!-- AS-IS {ns}.{sid}{param_comment} -->{type_comment}{warn_comment}
    <select id="{select_id}" resultType="{result_type}">
{cte_block}        SELECT <include refid="{columns_sql_id}"/>
{formatted_from}
    </select>"""

    # 2. Record DTO 렌더링
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
            "warnings": warnings,
        },
    )


def port_save(
    table: str,
    cols: list[str],
    company_col: str | None = None,
    id_col: str | None = None,
    company_via: str | None = None,
    src_root: Path | None = None,
    insert_only_cols: list[str] | None = None,
) -> ToolResult:
    """UpdateDataModel 대신 사용할 명시 INSERT, UPDATE, DELETE SQL 및 부수효과 SQL을 생성한다."""
    tbl_pfx_m = re.match(r"^([a-z]+\d*)_", table)
    tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""
    entity_base = re.sub(r"^[a-z]+\d*_", "", table)
    entity_name = to_camel_case(entity_base)
    entity_title = entity_name[0].upper() + entity_name[1:]

    table_cols = find_table_columns(table)
    warnings: list[str] = []

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

    # Company 컬럼 결정 및 company_via 처리
    has_company = True
    subquery_condition = ""
    company_prop = "companyId"

    if company_via:
        has_company = False
        company_col = None
        if "=" in company_via:
            target_part, current_fk = company_via.split("=", 1)
            target_part, current_fk = target_part.strip(), current_fk.strip()
            if "." in target_part:
                target_tbl, target_pk = target_part.split(".", 1)
            else:
                target_tbl, target_pk = target_part, f"{target_part}_id"
            target_cols = find_table_columns(target_tbl)
            t_pfx_m = re.match(r"^([a-z]+\d*)_", target_tbl)
            t_pfx = (t_pfx_m.group(1) + "_") if t_pfx_m else ""
            t_comp = f"{t_pfx}company_id"
            if target_cols and t_comp not in target_cols:
                t_comp_match = next((c for c in target_cols if "company_id" in c), t_comp)
                t_comp = t_comp_match
            subquery_condition = f"AND {current_fk} IN (SELECT {target_pk} FROM {target_tbl} WHERE {t_comp} = #{{{company_prop}}})"
    elif not company_col:
        cand_comp = f"{tbl_prefix}company_id" if tbl_prefix else "company_id"
        if table_cols is not None:
            if cand_comp in table_cols:
                company_col = cand_comp
                company_prop = "companyId"
            else:
                comp_match = next((c for c in table_cols if "company_id" in c), None)
                if comp_match:
                    company_col = comp_match
                    company_prop = "companyId"
                else:
                    has_company = False
                    company_col = None
                    warnings.append("회사 컬럼 없음")
        else:
            company_col = cand_comp
            company_prop = "companyId"
    else:
        # company_col이 명시적으로 주어진 경우
        if table_cols is not None:
            if company_col in table_cols:
                pass
            elif tbl_prefix and f"{tbl_prefix}{company_col}" in table_cols:
                company_col = f"{tbl_prefix}{company_col}"
            else:
                candidates = [c for c in table_cols if "company" in c.lower()]
                warnings.append(
                    f"컬럼 없음: {company_col}"
                    + (f" (후보: {', '.join(candidates)})" if candidates else "")
                )
        company_prop = "companyId" if "company" in company_col.lower() else col_to_tobe_prop(company_col, tbl_prefix)

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

    # insert_only_cols 정규화 (--insert-cols: INSERT에만 들어가고 UPDATE SET에는 제외)
    norm_insert_only: list[tuple[str, str]] = []
    for c in insert_only_cols or []:
        c_clean = c.strip()
        if not c_clean:
            continue
        db_col = c_clean
        if tbl_prefix and not db_col.startswith(tbl_prefix) and table_cols and f"{tbl_prefix}{db_col}" in table_cols:
            db_col = f"{tbl_prefix}{db_col}"
        prop_name = col_to_tobe_prop(db_col, tbl_prefix)
        if db_col not in {col for col, _ in norm_cols} and db_col not in {id_col, company_col}:
            norm_insert_only.append((db_col, prop_name))

    # 화면 insertRow()의 setter 후보 탐색 (선택)
    insert_candidates: list[str] = []
    if table_cols:
        norm_col_names = {c for c, _ in norm_cols} | {c for c, _ in norm_insert_only} | {id_col, company_col}
        common_cols = {"reg_date", "reg_dt", "mod_date", "mod_dt", "created_at", "updated_at"}
        for tc in table_cols:
            if (
                tc not in norm_col_names
                and not any(tc.endswith(f"_{cc}") for cc in common_cols)
                and any(kw in tc.lower() for kw in ("person_id", "start_date", "user_id"))
            ):
                base_c = tc[len(tbl_prefix):] if (tbl_prefix and tc.startswith(tbl_prefix)) else tc
                insert_candidates.append(base_c)
    if insert_candidates:
        cand_str = ", ".join(insert_candidates)
        warnings.append(f"INSERT 후보 열: {cand_str} — 화면이 채움, 서버가 넣을 값인지 확인 (--insert-cols {cand_str})")

    plural_title = to_plural(entity_title)
    plural_prop = to_plural(id_prop)

    # 1. selectNextId
    next_id_sql = """    <!-- AS-IS dbConfig.getSeq와 같은 식 -->
    <select id="selectNextId" resultType="long" flushCache="true">
        SELECT f_create_seq()
    </select>"""

    # 2. insert{Entity}
    all_insert_Pairs = norm_insert_only + norm_cols
    if has_company and company_col:
        if id_col == company_col:
            insert_cols = [id_col] + [c for c, _ in all_insert_Pairs]
            insert_vals = [f"#{{{id_prop}}}"] + [f"#{{{p}}}" for _, p in all_insert_Pairs]
            update_where = f"         WHERE {id_col} = #{{{id_prop}}}"
            delete_where = f"         WHERE {id_col} IN"
        else:
            insert_cols = [id_col, company_col] + [c for c, _ in all_insert_Pairs]
            insert_vals = [f"#{{{id_prop}}}", f"#{{{company_prop}}}"] + [f"#{{{p}}}" for _, p in all_insert_Pairs]
            update_where = f"         WHERE {id_col}    = #{{{id_prop}}}\n           AND {company_col} = #{{{company_prop}}}"
            delete_where = f"         WHERE {company_col} = #{{{company_prop}}}\n           AND {id_col} IN"
    else:
        insert_cols = [id_col] + [c for c, _ in all_insert_Pairs]
        insert_vals = [f"#{{{id_prop}}}"] + [f"#{{{p}}}" for _, p in all_insert_Pairs]
        if subquery_condition:
            update_where = f"         WHERE {id_col} = #{{{id_prop}}}\n           {subquery_condition}"
            where_first = subquery_condition.strip()
            where_first = where_first.removeprefix("AND ")
            delete_where = f"         WHERE {where_first}\n           AND {id_col} IN"
        else:
            update_where = f"         WHERE {id_col} = #{{{id_prop}}}"
            delete_where = f"         WHERE {id_col} IN"

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
    delete_item_var = id_prop if id_prop != company_prop else "item"
    delete_sql = f"""    <delete id="delete{plural_title}">
        DELETE FROM {table}
{delete_where}
        <foreach collection="{plural_prop}" item="{delete_item_var}" open="(" separator="," close=")">#{{{delete_item_var}}}</foreach>
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

    # 5. 저장 시 부수 효과 검사 및 UpdateDataModel 자동 채움 열 확인
    auto_fill_parts: list[str] = []
    if table_cols:
        upd_nm_col = f"{tbl_prefix}upd_nm" if tbl_prefix else "upd_nm"
        upd_date_col = f"{tbl_prefix}upd_date" if tbl_prefix else "upd_date"
        if upd_nm_col in table_cols:
            auto_fill_parts.append(f"{upd_nm_col} = 로그인 사용자 이름")
        if upd_date_col in table_cols:
            auto_fill_parts.append(f"{upd_date_col} = 현재 시각")

    app_root = None
    if src_root and src_root.is_dir():
        app_root = find_app(src_root)
    elif ASIS_SRC_DIR and ASIS_SRC_DIR.is_dir():
        app_root = find_app(ASIS_SRC_DIR)

    tbl_effects = None
    if app_root:
        side_effects = parse_update_data_model(app_root)
        tbl_effects = side_effects.get(table)

    if tbl_effects or auto_fill_parts:
        if tbl_effects:
            header = f"\n    <!-- === {table} 저장 시 부수 효과 (UpdateDataModel L{tbl_effects['start_line']}-{tbl_effects['end_line']}) === -->"
        else:
            header = f"\n    <!-- === {table} 저장 시 부수 효과 (UpdateDataModel) === -->"
        if auto_fill_parts:
            header += f"\n    <!-- 자동 채움: {', '.join(auto_fill_parts)} -->"
        fragments.append(header)

    if tbl_effects:
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
