"""MyBatis 매퍼 SQL 파싱 및 펼치기 통합 렌더러.

port-sql, compare, sql-check, analysis sql에서 공통으로 사용한다.
- 다른 namespace의 <include> 완전 펼치기 (Common.xml 등)
- <bind> 변수 바인딩 및 OGNL 문자열 연결 ('%' + x + '%')
- <choose> / <if> 조건 판정 (boolean 리터럴, and/or, size() 등)
- mode="params" (파라미터 대입 실행 SQL), mode="explain" (EXPLAIN용), mode="structure" (include만 펼친 XML)
"""

import re
import sys
from pathlib import Path
from typing import Any

from yunhee import config

STATEMENT_TAGS = ("select", "insert", "update", "delete", "sql")
TOKEN_RE = re.compile(
    r"""<!\[CDATA\[(.*?)\]\]>"""
    r"""|<!--.*?-->"""
    r"""|<(/?)(\w+)((?:\s*|'[^']*'|"[^"]*"|[^>'"])*?)(/?)>"""
    r"""|([^<]+)""",
    re.DOTALL,
)
ATTR_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')


def _parse_attrs(attrs_str: str) -> dict[str, str]:
    res = {}
    for m in ATTR_RE.finditer(attrs_str):
        name = m.group(1)
        val = m.group(2) if m.group(2) is not None else (m.group(3) or "")
        res[name] = unescape(val)
    return res


class Node:
    """아주 작은 XML 트리 (MyBatis 매퍼는 SQL 텍스트와 태그가 섞여 있어 ElementTree보다 이쪽이 단순하다)."""

    def __init__(self, tag: str, attrs: dict[str, str], children: list[Any]) -> None:
        self.tag, self.attrs, self.children = tag, attrs, children


def unescape(s: str) -> str:
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#160;", " ")
    )


def parse_xml(text: str) -> Node:
    root = Node("root", {}, [])
    stack = [root]
    for m in TOKEN_RE.finditer(text):
        cdata, closing, tag, attrs, selfclose, chars = m.groups()
        if cdata is not None:
            stack[-1].children.append(cdata)
        elif chars is not None:
            stack[-1].children.append(chars)
        elif tag:
            if closing:
                while len(stack) > 1 and stack[-1].tag != tag:
                    stack.pop()
                if len(stack) > 1:
                    stack.pop()
            else:
                node = Node(tag, _parse_attrs(attrs), [])
                stack[-1].children.append(node)
                if not selfclose:
                    stack.append(node)
    return root


def mask_sql_preserve(text: str) -> str:
    """줄 번호와 문자 위치(오프셋)를 보존하면서 주석과 문자열 리터럴, XML 태그를 공백으로 채운다."""
    chars = list(text)
    n = len(text)
    i = 0
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if chars[k] != "\n":
                    chars[k] = " "
            i = j
        elif text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                chars[k] = " "
            i = j
        elif chars[i] in ("'", '"'):
            quote = chars[i]
            j = i + 1
            while j < n and chars[j] != quote:
                if chars[j] == "\\":
                    j += 2
                else:
                    j += 1
            j = min(n, j + 1)
            for k in range(i, j):
                if chars[k] != "\n":
                    chars[k] = " "
            i = j
        elif chars[i] == "<":
            if i + 1 < n and (text[i + 1].isalpha() or text[i + 1] in ("/", "?", "!")):
                if text.startswith("<!--", i):
                    j = text.find("-->", i + 4)
                    j = n if j < 0 else j + 3
                elif text.startswith("<![CDATA[", i):
                    for k in range(i, min(n, i + 9)):
                        chars[k] = " "
                    j_cdata = text.find("]]>", i + 9)
                    if j_cdata >= 0:
                        chars[j_cdata] = " "
                        chars[j_cdata + 1] = " "
                        chars[j_cdata + 2] = " "
                    i = i + 9
                    continue
                else:
                    j = i + 1
                    in_q = None
                    while j < n:
                        c = text[j]
                        if in_q:
                            if c == in_q:
                                in_q = None
                        elif c in ("'", '"'):
                            in_q = c
                        elif c == ">":
                            j += 1
                            break
                        j += 1
                for k in range(i, j):
                    if chars[k] != "\n":
                        chars[k] = " "
                i = j
            else:
                i += 1
        else:
            i += 1
    return "".join(chars)


class Statement:
    """단일 매퍼 statement 또는 <sql> 조각."""

    def __init__(self, ns: str, sid: str, kind: str, node: Node, rel: Path, line: int, raw: str = "") -> None:
        self.ns, self.sid, self.kind, self.node, self.rel, self.line, self.raw = ns, sid, kind, node, rel, line, raw

    @property
    def key(self) -> str:
        return f"{self.ns}.{self.sid}"


# 캐시
_CACHED_STATEMENTS: dict[str, dict[str, Statement]] = {}


def load_statements(app_or_root: Path) -> dict[str, Statement]:
    """지정된 디렉터리 내 모든 매퍼 XML을 파싱하여 statements와 <sql> 조각을 사전으로 반환한다."""
    cache_key = str(app_or_root.resolve())
    if cache_key in _CACHED_STATEMENTS:
        return _CACHED_STATEMENTS[cache_key]

    statements: dict[str, Statement] = {}
    for path in sorted(app_or_root.rglob("*.xml")):
        if "target" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ns_m = re.search(r"<mapper\s+namespace\s*=\s*\"([^\"]+)\"", raw)
        if not ns_m:
            continue
        ns = ns_m.group(1)
        root = parse_xml(raw)
        mapper = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), None)
        if not mapper:
            continue
        rel = path.relative_to(app_or_root)
        for child in mapper.children:
            if isinstance(child, Node) and child.tag in STATEMENT_TAGS and "id" in child.attrs:
                sid = child.attrs["id"]
                pos = re.search(rf'<{child.tag}\b[^>]*\bid\s*=\s*"{re.escape(sid)}"', raw)
                line = raw.count("\n", 0, pos.start()) + 1 if pos else 0
                st = Statement(ns, sid, child.tag, child, rel, line, raw)
                statements[st.key] = st

    _CACHED_STATEMENTS[cache_key] = statements
    return statements


def get_all_statements(src_root: Path | None = None) -> dict[str, Statement]:
    """기본 AS-IS 소스 루트 또는 지정 경로에서 모든 statements를 로드한다."""
    roots_to_try: list[Path] = []
    if src_root and src_root.is_dir():
        roots_to_try.append(src_root)
    if config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        roots_to_try.append(config.ASIS_SRC_DIR)
    roots_to_try.append(config.WORK_DIR)

    for r in roots_to_try:
        from yunhee.tools.as_is.src_indexer import find_app
        app = find_app(r) or r
        stmts = load_statements(app)
        if stmts:
            return stmts
    return {}


def find_target_statement(ref: str, current_ns: str, statements: dict[str, Statement]) -> Statement | None:
    """refid 또는 statement key로 Statement를 찾는다."""
    if ref in statements:
        return statements[ref]
    if f"{current_ns}.{ref}" in statements:
        return statements[f"{current_ns}.{ref}"]
    # sid로 찾기
    for st in statements.values():
        if st.sid == ref:
            return st
    return None


def eval_test_condition_status(
    test: str,
    params: dict[str, Any],
    branch_overrides: dict[str, bool] | None = None,
) -> tuple[bool | None, str]:
    """MyBatis <if test="..."> 또는 <when test="..."> 조건을 평가하고 상태와 관련 변수명을 반환한다.

    반환: (True|False|None, var_name)
    - True: 조건 일치
    - False: 조건 불일치
    - None: 식을 판정하지 못함
    """
    test = unescape(test).strip()
    if not test:
        return True, ""

    # 변수명 추정 (test 내 첫 식별자)
    v_match = re.search(r"\b([a-zA-Z_]\w*)\b", test)
    var_name = v_match.group(1) if v_match else ""

    # branch_overrides 확인 (test 전체 식 또는 변수명 일치)
    if branch_overrides:
        test_norm = test.strip()
        if test_norm in branch_overrides:
            return branch_overrides[test_norm], var_name
        if var_name and var_name in branch_overrides:
            return branch_overrides[var_name], var_name
        for k, v in branch_overrides.items():
            if k == test_norm or (var_name and k == var_name):
                return v, var_name

    if "isPostgreSql" in test or ("_databaseId" in test and "postgresql" in test.lower()):
        return True, ""
    if "isTibero" in test or "isOracle" in test or ("_databaseId" in test and ("oracle" in test.lower() or "tibero" in test.lower())):
        return False, ""

    # or 분리 (우선순위: or/|| 단위 중 하나라도 True면 True)
    or_parts = re.split(r"\b(?:or|OR)\b|\|\|", test)
    any_none = False
    for or_part in or_parts:
        and_parts = re.split(r"\b(?:and|AND)\b|&&", or_part)
        and_ok = True
        for and_part in and_parts:
            res = _eval_single_condition_status(and_part.strip(), params)
            if res is None:
                any_none = True
                and_ok = False
                break
            if not res:
                and_ok = False
                break
        if and_ok:
            return True, var_name

    if any_none:
        return None, var_name
    return False, var_name


def _strip_type_prefix(val: Any) -> tuple[str | None, Any]:
    """파라미터 값에서 명시적 타입 접두사(s:, n:, b:, null:)를 분리한다."""
    if isinstance(val, str):
        if val.startswith("s:"):
            return "s", val[2:]
        if val.startswith("n:"):
            return "n", val[2:]
        if val.startswith("b:"):
            b_val = val[2:].strip().lower()
            return "b", (b_val in ("true", "1", "t", "y"))
        if val == "null:" or val.startswith("null:"):
            return "null", None
    return None, val


def _clean_params_for_eval(params: dict[str, Any]) -> dict[str, Any]:
    """조건식 평가를 위해 s:/n: 접두사를 제거한 파라미터 사전을 반환한다."""
    return {k: _strip_type_prefix(v)[1] for k, v in params.items()}


_STRING_LIKE_VAR_RE = re.compile(
    r"(?:Type|Cd|Code|Ym|Year|Month|Date|Dt|Yn|Text|Txt|Nm|Name|Status|Stat|Div|Gb|Kind|Cls|Class|Flag|Mode|Tel|Phone|Zip|Addr|Address|Email|Url|Path|Key|Msg|Note|Rmk|Desc|Content|Title|Step|Grade)$",
    re.IGNORECASE,
)
_NUMERIC_LIKE_VAR_RE = re.compile(
    r"(?:Id|Seq|Cnt|Count|Limit|Offset|Size|Page|Row|Idx|Amt|Price|Rate|Num|Order)$",
    re.IGNORECASE,
)
_STRING_LIKE_COL_RE = re.compile(
    r"\b\w+_(?:type|cd|code|ym|date|dt|yn|nm|name|text|note|status|div|gb|kind|cls|flag|mode|tel|phone|zip)\s*(?:=|!=|<>|LIKE|IN\s*\([^)]*)\s*$",
    re.IGNORECASE,
)


def _is_string_like_param(var: str, sql_before: str = "") -> bool:
    """변수명 접미사 또는 직전 SQL 컬럼 문맥을 통해 문자열 바인딩 대상인지 판별한다."""
    if _NUMERIC_LIKE_VAR_RE.search(var):
        return False
    if _STRING_LIKE_VAR_RE.search(var):
        return True
    return bool(sql_before and _STRING_LIKE_COL_RE.search(sql_before))


def _eval_single_condition_status(expr: str, params: dict[str, Any]) -> bool | None:
    params = _clean_params_for_eval(params)
    expr = expr.strip()
    if not expr:
        return True
    if expr.startswith("(") and expr.endswith(")"):
        expr = expr[1:-1].strip()

    if "isPostgreSql" in expr or ("_databaseId" in expr and "postgresql" in expr.lower()):
        return True
    if "isTibero" in expr or "isOracle" in expr or ("_databaseId" in expr and ("oracle" in expr.lower() or "tibero" in expr.lower())):
        return False

    # x == true / x == false
    m_bool_eq = re.match(r"^(\w+)\s*==\s*(true|false)$", expr, re.IGNORECASE)
    if m_bool_eq:
        var, target_val = m_bool_eq.group(1), m_bool_eq.group(2).lower()
        val = params.get(var)
        val_str = str(val).lower() if val is not None else ""
        if target_val == "true":
            return val is True or val_str in ("true", "1", "y", "t")
        return val is False or val_str in ("false", "0", "n", "f") or val is None

    # x != true / x != false
    m_bool_ne = re.match(r"^(\w+)\s*!=\s*(true|false)$", expr, re.IGNORECASE)
    if m_bool_ne:
        var, target_val = m_bool_ne.group(1), m_bool_ne.group(2).lower()
        val = params.get(var)
        val_str = str(val).lower() if val is not None else ""
        if target_val == "true":
            return not (val is True or val_str in ("true", "1", "y", "t"))
        return not (val is False or val_str in ("false", "0", "n", "f") or val is None)

    # x != null
    m_not_null = re.match(r"^(\w+)\s*!=\s*null$", expr, re.IGNORECASE)
    if m_not_null:
        var = m_not_null.group(1)
        return var in params and params[var] is not None and params[var] != ""

    # x == null
    m_null = re.match(r"^(\w+)\s*==\s*null$", expr, re.IGNORECASE)
    if m_null:
        var = m_null.group(1)
        return var not in params or params[var] is None or params[var] == ""

    # x != ''
    m_not_empty = re.match(r"^(\w+)\s*!=\s*['\"]['\"]$", expr)
    if m_not_empty:
        var = m_not_empty.group(1)
        return bool(params.get(var))

    # x == ''
    m_empty = re.match(r"^(\w+)\s*==\s*['\"]['\"]$", expr)
    if m_empty:
        var = m_empty.group(1)
        return not bool(params.get(var))

    # x == 'val'
    m_eq = re.match(r"^(\w+)\s*==\s*['\"]([^'\"]*)['\"]$", expr)
    if m_eq:
        var, val = m_eq.group(1), m_eq.group(2)
        return str(params.get(var, "")) == val

    # 'val' == x
    m_eq_rev = re.match(r"^['\"]([^'\"]*)['\"]\s*==\s*(\w+)$", expr)
    if m_eq_rev:
        val, var = m_eq_rev.group(1), m_eq_rev.group(2)
        return str(params.get(var, "")) == val

    # x != 'val'
    m_ne = re.match(r"^(\w+)\s*!=\s*['\"]([^'\"]*)['\"]$", expr)
    if m_ne:
        var, val = m_ne.group(1), m_ne.group(2)
        return str(params.get(var, "")) != val

    # 'val' != x
    m_ne_rev = re.match(r"^['\"]([^'\"]*)['\"]\s*!=\s*(\w+)$", expr)
    if m_ne_rev:
        val, var = m_ne_rev.group(1), m_ne_rev.group(2)
        return str(params.get(var, "")) != val

    # x.equals('val') / !x.equals('val')
    m_equals = re.match(r"^(!?)\s*(\w+)\.equals\(\s*['\"]([^'\"]*)['\"]\s*\)$", expr)
    if m_equals:
        neg, var, lit = m_equals.group(1), m_equals.group(2), m_equals.group(3)
        val = str(params.get(var, "")) if var in params and params[var] is not None else ""
        return (val != lit) if neg else (val == lit)

    # 'val'.equals(x) / !'val'.equals(x)
    m_equals_rev = re.match(r"^(!?)\s*['\"]([^'\"]*)['\"]\s*\.equals\(\s*(\w+)\s*\)$", expr)
    if m_equals_rev:
        neg, lit, var = m_equals_rev.group(1), m_equals_rev.group(2), m_equals_rev.group(3)
        val = str(params.get(var, "")) if var in params and params[var] is not None else ""
        return (val != lit) if neg else (val == lit)

    # x.equalsIgnoreCase('val') / !x.equalsIgnoreCase('val')
    m_eq_ignore = re.match(r"^(!?)\s*(\w+)\.equalsIgnoreCase\(\s*['\"]([^'\"]*)['\"]\s*\)$", expr)
    if m_eq_ignore:
        neg, var, lit = m_eq_ignore.group(1), m_eq_ignore.group(2), m_eq_ignore.group(3)
        val = str(params.get(var, "")) if var in params and params[var] is not None else ""
        return (val.lower() != lit.lower()) if neg else (val.lower() == lit.lower())

    # x.isEmpty() / !x.isEmpty()
    m_empty_call = re.match(r"^(!?)\s*(\w+)\.isEmpty\(\)$", expr)
    if m_empty_call:
        neg, var = m_empty_call.group(1), m_empty_call.group(2)
        val = params.get(var)
        is_emp = (val is None or val == "" or (isinstance(val, (list, tuple, dict, set)) and len(val) == 0))
        return (not is_emp) if neg else is_emp

    # x.length() op number
    m_len = re.match(r"^(\w+)\.length\(\)\s*([><!=]=?)\s*(\d+)$", expr)
    if m_len:
        var, op, limit_str = m_len.group(1), m_len.group(2), m_len.group(3)
        limit = int(limit_str)
        val = params.get(var)
        length = len(str(val)) if val is not None else 0
        if op == ">": return length > limit
        if op == ">=": return length >= limit
        if op == "<": return length < limit
        if op == "<=": return length <= limit
        if op in ("==", "="): return length == limit
        if op == "!=": return length != limit

    # x.size() > 0 / x.size() == 0 / x.size != 0 등 (.size와 .size() 둘 다 지원)
    m_size = re.match(r"^(\w+)\.size(?:\(\))?\s*([><!=]=?)\s*(\d+)$", expr)
    if m_size:
        var, op, limit_str = m_size.group(1), m_size.group(2), m_size.group(3)
        limit = int(limit_str)
        val = params.get(var)
        if isinstance(val, (list, tuple, set, dict)):
            length = len(val)
        elif isinstance(val, str) and val.strip():
            length = len([s for s in val.split(",") if s.strip()])
        else:
            length = 0
        if op == ">":
            return length > limit
        if op == ">=":
            return length >= limit
        if op == "<":
            return length < limit
        if op == "<=":
            return length <= limit
        if op in ("==", "="):
            return length == limit
        if op == "!=":
            return length != limit

    # x op number: personId > 1, count >= 0, status == 1, personId != 0l 등
    m_num = re.match(r"^(\w+)\s*([><!=]=?)\s*(-?\d+(?:\.\d+)?)[lL]?$", expr)
    if m_num:
        var, op, limit_str = m_num.group(1), m_num.group(2), m_num.group(3)
        if var not in params or params[var] is None or params[var] == "":
            return False
        try:
            val_num = float(params[var])
            limit = float(limit_str)
            if op == ">":
                return val_num > limit
            if op == ">=":
                return val_num >= limit
            if op == "<":
                return val_num < limit
            if op == "<=":
                return val_num <= limit
            if op in ("==", "="):
                return val_num == limit
            if op == "!=":
                return val_num != limit
        except (ValueError, TypeError):
            return False

    # number op x: 0 < personId, 0L != personId 등
    m_num_rev = re.match(r"^(-?\d+(?:\.\d+)?)[lL]?\s*([><!=]=?)\s*(\w+)$", expr)
    if m_num_rev:
        limit_str, op, var = m_num_rev.group(1), m_num_rev.group(2), m_num_rev.group(3)
        if var not in params or params[var] is None or params[var] == "":
            return False
        try:
            val_num = float(params[var])
            limit = float(limit_str)
            if op == ">":
                return limit > val_num
            if op == ">=":
                return limit >= val_num
            if op == "<":
                return limit < val_num
            if op == "<=":
                return limit <= val_num
            if op in ("==", "="):
                return limit == val_num
            if op == "!=":
                return limit != val_num
        except (ValueError, TypeError):
            return False

    # 단일 변수: isSeparateAddTitle 등
    m_single = re.match(r"^(\w+)$", expr)
    if m_single:
        var = m_single.group(1)
        val = params.get(var)
        if val is True:
            return True
        if isinstance(val, str) and val.lower() in ("true", "1"):
            return True
        if val is False or val is None or val == "":
            return False
        return bool(val)

    # 판정하지 못한 식은 None
    return None


def eval_test_condition(
    test: str,
    params: dict[str, Any],
    branch_overrides: dict[str, bool] | None = None,
) -> bool:
    """MyBatis <if test="..."> 또는 <when test="..."> 조건을 평가한다."""
    res, _ = eval_test_condition_status(test, params, branch_overrides=branch_overrides)
    return bool(res)


def eval_bind(name: str, value: str, params: dict[str, Any]) -> None:
    """<bind name="..." value="..."/> 태그를 평가하여 params 사전에 등록한다."""
    value = value.strip()
    # 1. 단순 리터럴 문자열: 'regDate' 또는 "regDate" (내부에 따옴표가 없는 단일 리터럴)
    m_lit = re.match(r"^'([^']*)'$|^\"([^\"]*)\"$", value)
    if m_lit:
        params[name] = m_lit.group(1) if m_lit.group(1) is not None else m_lit.group(2)
        return

    # 2. 숫자/불리언 리터럴: 10, 3.14, true, false
    if re.match(r"^\d+$", value):
        params[name] = int(value)
        return
    if re.match(r"^\d+\.\d+$", value):
        params[name] = float(value)
        return
    if value.lower() in ("true", "false"):
        params[name] = value.lower() == "true"
        return

    # 3. 단순 변수명
    if re.match(r"^\w+$", value):
        if value in params:
            params[name] = params[value]
        return

    # 4. OGNL 문자열 연결: '%' + x + '%'
    if "+" in value:
        tokens = [t.strip() for t in re.split(r"\s*\+\s*", value)]
        res_parts = []
        for t in tokens:
            m_str = re.match(r"^['\"](.*)['\"]$", t)
            if m_str:
                res_parts.append(m_str.group(1))
            elif re.match(r"^\w+$", t):
                _, val = _strip_type_prefix(params.get(t, ""))
                res_parts.append(str(val) if val is not None else "")
            else:
                sys.stderr.write(f"⚠ bind 식 건너뜀: {name}={value}\n")
                return
        params[name] = "".join(res_parts)
        return

    sys.stderr.write(f"⚠ bind 식 건너뜀: {name}={value}\n")


def extract_branch_condition_vars(
    node: Any,
    current_ns: str,
    statements: dict[str, Statement],
    seen: tuple[str, ...] = (),
) -> set[str]:
    """문장(include 포함) 내 <when>/<if> 조건식에서 검사하는 변수명 집합을 추출한다."""
    if isinstance(node, str):
        return set()
    vars_found: set[str] = set()
    tag = node.tag
    if tag == "include":
        ref = node.attrs.get("refid", "")
        target = find_target_statement(ref, current_ns, statements)
        if target and target.key not in seen:
            vars_found.update(
                extract_branch_condition_vars(target.node, target.ns, statements, seen + (target.key,))
            )
        return vars_found

    if tag in ("when", "if"):
        test = node.attrs.get("test", "")
        for m in re.finditer(r"\b([a-zA-Z_]\w*)\b", test):
            w = m.group(1)
            if w.lower() not in (
                "null",
                "true",
                "false",
                "and",
                "or",
                "not",
                "size",
                "ispostgresql",
                "istibero",
                "isoracle",
                "_databaseid",
            ):
                vars_found.add(w)

    for c in node.children:
        vars_found.update(extract_branch_condition_vars(c, current_ns, statements, seen))
    return vars_found


def render_node(
    node: Any,
    current_ns: str,
    statements: dict[str, Statement],
    params: dict[str, Any],
    mode: str = "params",
    seen: tuple[str, ...] = (),
    missing_params: list[str] | None = None,
    branch_log: list[str] | None = None,
    branch_overrides: dict[str, bool] | None = None,
) -> str:
    """MyBatis 노드를 렌더링한다.

    mode:
    - "params": 파라미터를 판정/대입한 실행 SQL
    - "explain": 첫 when 선택, 파라미터는 NULL/1로 채운 EXPLAIN용 SQL
    - "structure": include만 펼치고 choose/if/bind 태그를 보존한 XML
    """
    if missing_params is None:
        missing_params = []

    if isinstance(node, str):
        return unescape(node) if mode != "structure" else node

    tag = node.tag
    if tag == "root":
        return "".join(
            render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
            for c in node.children
        )

    if tag == "include":
        ref = node.attrs.get("refid", "")
        target = find_target_statement(ref, current_ns, statements)
        if target and target.key not in seen:
            return render_node(
                target.node,
                target.ns,
                statements,
                params,
                mode,
                seen + (target.key,),
                missing_params,
                branch_log,
                branch_overrides=branch_overrides,
            )
        if mode == "structure":
            return f'<!-- include {ref} 없음 -->'
        return f" /* include {ref} 없음 */ "

    if tag == "bind":
        name = node.attrs.get("name", "")
        value = node.attrs.get("value", "")
        if name and value:
            eval_bind(name, value, params)
        if mode == "structure":
            return f'<bind name="{name}" value="{value}"/>\n'
        return ""

    if mode == "structure":
        # 태그 구조 보존 모드 (port-sql 용): include만 펼치고 나머지는 태그 그대로 출력
        if tag == "sql":
            return "".join(
                render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
                for c in node.children
            )
        attrs_str = "".join(f' {k}="{v}"' for k, v in node.attrs.items())
        body = "".join(
            render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
            for c in node.children
        )
        return f"<{tag}{attrs_str}>{body}</{tag}>"

    # mode == "explain"
    if mode == "explain":
        if tag in ("bind", "selectKey"):
            return ""
        if tag == "choose":
            whens = [w for w in node.children if isinstance(w, Node) and w.tag == "when"]
            other = next((w for w in node.children if isinstance(w, Node) and w.tag == "otherwise"), None)
            pick = (
                next((w for w in whens if "isPostgreSql" in w.attrs.get("test", "")), None)
                or next((w for w in whens if "isTibero" not in w.attrs.get("test", "")), None)
                or other
            )
            variant = params.get("__pick__", 0)  # 0이면 위 기본 선택. 1 이상이면 다른 분기를 차례로 고른다 (분기 전수 조사용)
            if variant and pick:
                rest = [w for w in [*whens, other] if w is not None and w is not pick and "isTibero" not in w.attrs.get("test", "")]
                pick = [pick, *rest][min(variant, len(rest))]
            if pick:
                return render_node(pick, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
            return ""
        if tag == "if":
            test = node.attrs.get("test", "")
            if "isTibero" not in test:
                return "".join(
                    render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
                    for c in node.children
                )
            return ""
        if tag == "foreach":
            return " NULL "
        if tag in ("where", "set", "trim"):
            body = "".join(
                render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
                for c in node.children
            )
            if tag == "where":
                return " WHERE 1=1 " + re.sub(r"^\s*(AND|OR)\b", " AND ", body, flags=re.IGNORECASE) if body.strip() else ""
            if tag == "set":
                return " SET " + body.strip().rstrip(",")
            prefix = node.attrs.get("prefix", "")
            overrides = [o.strip() for o in node.attrs.get("suffixOverrides", "").split("|") if o.strip()]
            body = body.strip()
            for o in overrides:
                if body.upper().endswith(o.upper()):
                    body = body[:-len(o)]
            return f" {prefix} {body} {node.attrs.get('suffix', '')} "
        return "".join(
            render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
            for c in node.children
        )

    # mode == "params"
    if tag == "choose":
        whens = [w for w in node.children if isinstance(w, Node) and w.tag == "when"]
        other = next((w for w in node.children if isinstance(w, Node) and w.tag == "otherwise"), None)
        selected_when = None
        selected_var = None
        excluded_vars = []
        uneval_tests = []
        for w in whens:
            test = w.attrs.get("test", "")
            eval_res, var_name = eval_test_condition_status(test, params, branch_overrides=branch_overrides)
            if eval_res is True and selected_when is None:
                selected_when = w
                if var_name and var_name not in ("isPostgreSql", "isTibero", "isOracle"):
                    selected_var = var_name
            elif eval_res is False:
                if var_name and var_name not in ("isPostgreSql", "isTibero", "isOracle"):
                    excluded_vars.append(var_name)
            else:
                uneval_tests.append(test)
                sys.stderr.write(f"⚠ 분기 평가 불가: {test} — 양쪽(켬/끔) 모두 보려면 --branch '{test}'=on|off\n")
                if branch_log is not None:
                    branch_log.append(f"⚠ {test} 평가 불가")
        if branch_log is not None:
            if selected_var:
                entry = f"{selected_var} ON"
                if entry not in branch_log:
                    branch_log.append(entry)
            for ev in excluded_vars:
                entry = f"{ev} OFF"
                if entry not in branch_log:
                    branch_log.append(entry)
        if selected_when:
            return render_node(selected_when, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
        if other:
            return render_node(other, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
        if excluded_vars:
            return f"\n-- 분기 제외: {', '.join(excluded_vars)}\n"
        if uneval_tests:
            return f"\n/* ⚠ 분기 평가 불가(기본 OFF): {', '.join(uneval_tests)} */\n"
        return ""

    if tag == "if":
        test = node.attrs.get("test", "")
        eval_res, var_name = eval_test_condition_status(test, params, branch_overrides=branch_overrides)
        if eval_res is True:
            if branch_log is not None and var_name and var_name not in ("isPostgreSql", "isTibero", "isOracle"):
                entry = f"{var_name} ON"
                if entry not in branch_log:
                    branch_log.append(entry)
            return "".join(
                render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
                for c in node.children
            )
        elif eval_res is False:
            if var_name and var_name not in ("isPostgreSql", "isTibero", "isOracle"):
                if branch_log is not None:
                    entry = f"{var_name} OFF"
                    if entry not in branch_log:
                        branch_log.append(entry)
                return f"\n-- 분기 제외: {var_name}\n"
            return ""
        else:
            sys.stderr.write(f"⚠ 분기 평가 불가: {test} — 양쪽(켬/끔) 모두 보려면 --branch '{test}'=on|off\n")
            if branch_log is not None:
                branch_log.append(f"⚠ {test} 평가 불가")
            body = "".join(
                render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
                for c in node.children
            )
            return f"\n/* ⚠ 분기 평가 불가(기본 OFF): {test}\n{body}\n*/\n"

    if tag == "foreach":
        collection = node.attrs.get("collection", "")
        item_var = node.attrs.get("item", "item")
        open_ch = node.attrs.get("open", "(")
        close_ch = node.attrs.get("close", ")")
        sep = node.attrs.get("separator", ",")
        items = params.get(collection)
        if isinstance(items, str) and items:
            items = [s.strip() for s in items.split(",") if s.strip()]
        if items and isinstance(items, (list, tuple, set)):
            sub_sqls = []
            for it in items:
                sub_params = dict(params)
                sub_params[item_var] = it
                sub_sql = "".join(
                    render_node(c, current_ns, statements, sub_params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
                    for c in node.children
                )
                sub_sqls.append(sub_sql.strip())
            return f" {open_ch} {sep.join(sub_sqls)} {close_ch} "
        return f" {open_ch} NULL {close_ch} "

    if tag in ("where", "set", "trim"):
        body = "".join(
            render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
            for c in node.children
        ).strip()
        if tag == "where":
            if body:
                body = re.sub(r"^(AND|OR)\b", "", body, flags=re.IGNORECASE).strip()
                return f" WHERE {body} "
            return ""
        if tag == "set":
            body = body.rstrip(",")
            return f" SET {body} " if body else ""
        # trim
        prefix = node.attrs.get("prefix", "")
        suffix = node.attrs.get("suffix", "")
        overrides = [o.strip() for o in node.attrs.get("suffixOverrides", "").split("|") if o.strip()]
        for o in overrides:
            if body.upper().endswith(o.upper()):
                body = body[:-len(o)]
        return f" {prefix} {body} {suffix} " if body else ""

    return "".join(
        render_node(c, current_ns, statements, params, mode, seen, missing_params, branch_log, branch_overrides=branch_overrides)
        for c in node.children
    )


def render_with_meta(
    key: str,
    params: dict[str, Any] | None = None,
    mode: str = "params",
    src_root: Path | None = None,
    statements: dict[str, Statement] | None = None,
    branch_overrides: dict[str, bool] | None = None,
) -> tuple[str, list[str], list[str]]:
    """statement를 렌더링하고 (SQL, 누락 파라미터 목록, 분기 판정 로그)를 반환한다."""
    if statements is None:
        statements = get_all_statements(src_root)
    if params is None:
        params = {}

    st = statements.get(key)
    if not st:
        st = next((s for s in statements.values() if s.sid == key), None)
    if not st:
        raise ValueError(f"statement를 찾을 수 없습니다: {key}")

    missing_params: list[str] = []
    branch_log: list[str] = []
    local_params = dict(params)

    rendered = render_node(
        st.node,
        st.ns,
        statements,
        local_params,
        mode=mode,
        seen=(st.key,),
        missing_params=missing_params,
        branch_log=branch_log,
        branch_overrides=branch_overrides,
    )

    if mode == "structure":
        return rendered, [], branch_log

    if mode == "explain":
        sql = rendered
        if local_params.get("__keep_params__"):  # 파라미터 이름을 남긴다 (상태값 추적용): #{statCd} → "__p_statCd" (따옴표로 대소문자 유지)
            sql = re.sub(r"#\{\s*([^},\s]+)[^}]*\}", lambda m: '"__p_' + re.sub(r"\W", "_", m.group(1)) + '"', sql)
        sql = re.sub(r"#\{[^}]*\}", "NULL", sql)
        sql = re.sub(r"(?i)\bin\s*\$\{[^}]*\}", "IN (1)", sql)
        sql = re.sub(r"(?i)\bin\s+NULL\b", "IN (NULL)", sql)
        sql = re.sub(r"\$\{[^}]*\}", "1", sql)
        return sql.strip().rstrip(";"), [], branch_log

    # mode == "params" 파라미터 대입
    def replace_sharp(m: re.Match) -> str:
        var = m.group(1).strip()
        if "," in var:
            var = var.split(",")[0].strip()
        if var in local_params and local_params[var] is not None:
            raw_val = local_params[var]
            type_pfx, val = _strip_type_prefix(raw_val)
            if type_pfx == "null" or val is None:
                return "NULL"
            val_str = str(val)
            if type_pfx == "s":
                val_escaped = val_str.replace("'", "''")
                return f"'{val_escaped}'"
            if type_pfx == "n":
                return val_str
            if type_pfx == "b":
                return "TRUE" if bool(val) else "FALSE"
            sql_before = rendered[max(0, m.start() - 80):m.start()]
            if (
                val_str.lstrip("-").isdigit()
                and not (val_str.startswith("0") and len(val_str) > 1)
                and not _is_string_like_param(var, sql_before)
            ):
                return val_str
            val_escaped = val_str.replace("'", "''")
            return f"'{val_escaped}'"
        missing_params.append(var)
        return f":{var}"

    def replace_dollar(m: re.Match) -> str:
        var = m.group(1).strip()
        if "," in var:
            var = var.split(",")[0].strip()
        if var in local_params and local_params[var] is not None:
            type_pfx, val = _strip_type_prefix(local_params[var])
            if type_pfx == "null" or val is None:
                return "NULL"
            if type_pfx == "b":
                return "TRUE" if bool(val) else "FALSE"
            return str(val)
        return "1"

    sql = re.sub(r"#\{([^}]+)\}", replace_sharp, rendered)
    sql = re.sub(r"\$\{([^}]+)\}", replace_dollar, sql)

    # 정리: 중복 주석 제거 등
    sql = re.sub(r"<!--.*?-->", " ", sql, flags=re.DOTALL)
    sql = sql.strip().rstrip(";")

    # 고유한 누락 파라미터 목록
    unique_missing = sorted(set(missing_params))
    if unique_missing:
        sql += "\n" + "\n".join(f"-- 필요: {p}" for p in unique_missing)
    return sql, unique_missing, branch_log


def render(
    key: str,
    params: dict[str, Any] | None = None,
    mode: str = "params",
    src_root: Path | None = None,
    statements: dict[str, Statement] | None = None,
    branch_overrides: dict[str, bool] | None = None,
) -> tuple[str, list[str]]:
    """statement 또는 SQL 조각을 렌더링한다.

    반환: (완성된 SQL/텍스트, 누락된 파라미터 이름 목록)
    """
    sql, unique_missing, _ = render_with_meta(
        key,
        params=params,
        mode=mode,
        src_root=src_root,
        statements=statements,
        branch_overrides=branch_overrides,
    )
    return sql, unique_missing


def parse_xml_statements(xml_text: str) -> tuple[str, dict[str, Statement]]:
    """단일 XML 문자열에서 namespace와 statement 사전을 파싱한다."""
    ns_m = re.search(r"<mapper\s+namespace\s*=\s*\"([^\"]+)\"", xml_text)
    ns = ns_m.group(1) if ns_m else "default"
    root = parse_xml(xml_text)
    mapper = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), root)
    statements: dict[str, Statement] = {}
    for child in mapper.children:
        if isinstance(child, Node) and child.tag in STATEMENT_TAGS and "id" in child.attrs:
            sid = child.attrs["id"]
            st = Statement(ns, sid, child.tag, child, Path("inline.xml"), 1, xml_text)
            statements[st.key] = st
            statements[sid] = st
    return ns, statements


def render_from_xml_with_meta(
    xml_text: str,
    sql_id: str,
    params: dict[str, Any] | None = None,
    mode: str = "params",
    branch_overrides: dict[str, bool] | None = None,
) -> tuple[str, list[str], list[str]]:
    """단일 XML 문자열에서 statement를 찾아 (SQL, 누락 파라미터, 분기 로그)를 반환한다."""
    ns, statements = parse_xml_statements(xml_text)
    key = sql_id if "." in sql_id else f"{ns}.{sql_id}"
    if key not in statements and sql_id in statements:
        key = sql_id
    return render_with_meta(
        key,
        params=params,
        mode=mode,
        statements=statements,
        branch_overrides=branch_overrides,
    )


def render_from_xml(
    xml_text: str,
    sql_id: str,
    params: dict[str, Any] | None = None,
    mode: str = "params",
    branch_overrides: dict[str, bool] | None = None,
) -> tuple[str, list[str]]:
    """단일 XML 문자열에서 statement를 찾아 렌더링한다 (단위 테스트 및 fallback용)."""
    sql, missing, _ = render_from_xml_with_meta(
        xml_text,
        sql_id,
        params=params,
        mode=mode,
        branch_overrides=branch_overrides,
    )
    return sql, missing

