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
TOKEN_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>|<!--.*?-->|<(/?)(\w+)([^>]*?)(/?)>|([^<]+)", re.DOTALL)
ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


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
                node = Node(tag, dict(ATTR_RE.findall(attrs)), [])
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
                    j = text.find(">", i)
                    j = n if j < 0 else j + 1
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


def eval_test_condition(test: str, params: dict[str, Any]) -> bool:
    """MyBatis <if test="..."> 또는 <when test="..."> 조건을 평가한다.

    지원:
    - isPostgreSql (True), isTibero / isOracle (False)
    - x == true / x == false (따옴표 없는 boolean 리터럴)
    - x != null / x == null
    - x != '' / x == ''
    - x == 'val' / x != 'val'
    - x.size() > 0 / x.size() == 0 등
    - and / or 복합식
    - 알 수 없는 식은 경고 출력 후 False
    """
    test = test.strip()
    if not test:
        return True

    if "isPostgreSql" in test or ("_databaseId" in test and "postgresql" in test.lower()):
        return True
    if "isTibero" in test or "isOracle" in test or ("_databaseId" in test and ("oracle" in test.lower() or "tibero" in test.lower())):
        return False

    # or 분리 (우선순위: or 단위 중 하나라도 True면 True)
    or_parts = re.split(r"\b(?:or|OR)\b", test)
    for or_part in or_parts:
        and_parts = re.split(r"\b(?:and|AND)\b", or_part)
        and_ok = True
        for and_part in and_parts:
            if not _eval_single_condition(and_part.strip(), params):
                and_ok = False
                break
        if and_ok:
            return True
    return False


def _eval_single_condition(expr: str, params: dict[str, Any]) -> bool:
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
            return val_str in ("true", "1", "y")
        return val_str in ("false", "0", "n") or val is None

    # x != true / x != false
    m_bool_ne = re.match(r"^(\w+)\s*!=\s*(true|false)$", expr, re.IGNORECASE)
    if m_bool_ne:
        var, target_val = m_bool_ne.group(1), m_bool_ne.group(2).lower()
        val = params.get(var)
        val_str = str(val).lower() if val is not None else ""
        if target_val == "true":
            return val_str not in ("true", "1", "y")
        return val_str not in ("false", "0", "n") and val is not None

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

    # x != 'val'
    m_ne = re.match(r"^(\w+)\s*!=\s*['\"]([^'\"]*)['\"]$", expr)
    if m_ne:
        var, val = m_ne.group(1), m_ne.group(2)
        return str(params.get(var, "")) != val

    # x.size() > 0 / x.size() == 0 등
    m_size = re.match(r"^(\w+)\.size\(\)\s*([><!=]=?)\s*(\d+)$", expr)
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

    # 판정하지 못한 식 경고 및 False 반환
    sys.stderr.write(f"⚠ 판정 못한 test: {expr}\n")
    return False


def eval_bind(name: str, value: str, params: dict[str, Any]) -> None:
    """<bind name="..." value="..."/> 태그를 평가하여 params 사전에 등록한다."""
    value = value.strip()
    # 단순 변수명
    if re.match(r"^\w+$", value):
        if value in params:
            params[name] = params[value]
        return

    # OGNL 문자열 연결: '%' + x + '%'
    if "+" in value:
        tokens = [t.strip() for t in re.split(r"\s*\+\s*", value)]
        res_parts = []
        for t in tokens:
            m_str = re.match(r"^['\"](.*)['\"]$", t)
            if m_str:
                res_parts.append(m_str.group(1))
            elif re.match(r"^\w+$", t):
                val = params.get(t, "")
                res_parts.append(str(val) if val is not None else "")
            else:
                sys.stderr.write(f"⚠ bind 식 건너뜀: {name}={value}\n")
                return
        params[name] = "".join(res_parts)
        return

    sys.stderr.write(f"⚠ bind 식 건너뜀: {name}={value}\n")


def render_node(
    node: Any,
    current_ns: str,
    statements: dict[str, Statement],
    params: dict[str, Any],
    mode: str = "params",
    seen: tuple[str, ...] = (),
    missing_params: list[str] | None = None,
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
            render_node(c, current_ns, statements, params, mode, seen, missing_params)
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
        attrs_str = "".join(f' {k}="{v}"' for k, v in node.attrs.items())
        body = "".join(
            render_node(c, current_ns, statements, params, mode, seen, missing_params)
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
            if pick:
                return render_node(pick, current_ns, statements, params, mode, seen, missing_params)
            return ""
        if tag == "if":
            test = node.attrs.get("test", "")
            if "isTibero" not in test:
                return "".join(
                    render_node(c, current_ns, statements, params, mode, seen, missing_params)
                    for c in node.children
                )
            return ""
        if tag == "foreach":
            return " NULL "
        if tag in ("where", "set", "trim"):
            body = "".join(
                render_node(c, current_ns, statements, params, mode, seen, missing_params)
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
            render_node(c, current_ns, statements, params, mode, seen, missing_params)
            for c in node.children
        )

    # mode == "params"
    if tag == "choose":
        whens = [w for w in node.children if isinstance(w, Node) and w.tag == "when"]
        other = next((w for w in node.children if isinstance(w, Node) and w.tag == "otherwise"), None)
        for w in whens:
            test = w.attrs.get("test", "")
            if eval_test_condition(test, params):
                return render_node(w, current_ns, statements, params, mode, seen, missing_params)
        if other:
            return render_node(other, current_ns, statements, params, mode, seen, missing_params)
        return ""

    if tag == "if":
        test = node.attrs.get("test", "")
        if eval_test_condition(test, params):
            return "".join(
                render_node(c, current_ns, statements, params, mode, seen, missing_params)
                for c in node.children
            )
        return ""

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
                    render_node(c, current_ns, statements, sub_params, mode, seen, missing_params)
                    for c in node.children
                )
                sub_sqls.append(sub_sql.strip())
            return f" {open_ch} {sep.join(sub_sqls)} {close_ch} "
        return f" {open_ch} NULL {close_ch} "

    if tag in ("where", "set", "trim"):
        body = "".join(
            render_node(c, current_ns, statements, params, mode, seen, missing_params)
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
        render_node(c, current_ns, statements, params, mode, seen, missing_params)
        for c in node.children
    )


def render(
    key: str,
    params: dict[str, Any] | None = None,
    mode: str = "params",
    src_root: Path | None = None,
    statements: dict[str, Statement] | None = None,
) -> tuple[str, list[str]]:
    """statement 또는 SQL 조각을 렌더링한다.

    반환: (완성된 SQL/텍스트, 누락된 파라미터 이름 목록)
    """
    if statements is None:
        statements = get_all_statements(src_root)
    if params is None:
        params = {}

    st = statements.get(key)
    if not st:
        # sid만 넘겼을 수도 있음
        st = next((s for s in statements.values() if s.sid == key), None)
    if not st:
        raise ValueError(f"statement를 찾을 수 없습니다: {key}")

    missing_params: list[str] = []
    local_params = dict(params)

    rendered = render_node(
        st.node,
        st.ns,
        statements,
        local_params,
        mode=mode,
        seen=(st.key,),
        missing_params=missing_params,
    )

    if mode == "structure":
        return rendered, []

    if mode == "explain":
        sql = rendered
        sql = re.sub(r"#\{[^}]*\}", "NULL", sql)
        sql = re.sub(r"(?i)\bin\s*\$\{[^}]*\}", "IN (1)", sql)
        sql = re.sub(r"(?i)\bin\s+NULL\b", "IN (NULL)", sql)
        sql = re.sub(r"\$\{[^}]*\}", "1", sql)
        return sql.strip().rstrip(";"), []

    # mode == "params" 파라미터 대입
    def replace_sharp(m: re.Match) -> str:
        var = m.group(1).strip()
        if var in local_params and local_params[var] is not None:
            val = local_params[var]
            val_escaped = str(val).replace("'", "''")
            return f"'{val_escaped}'"
        missing_params.append(var)
        return "NULL"

    def replace_dollar(m: re.Match) -> str:
        var = m.group(1).strip()
        if var in local_params and local_params[var] is not None:
            return str(local_params[var])
        return "1"

    sql = re.sub(r"#\{([^}]+)\}", replace_sharp, rendered)
    sql = re.sub(r"\$\{([^}]+)\}", replace_dollar, sql)

    # 정리: 중복 주석 제거 등
    sql = re.sub(r"<!--.*?-->", " ", sql, flags=re.DOTALL)
    sql = sql.strip().rstrip(";")

    # 고유한 누락 파라미터 목록
    unique_missing = sorted(set(missing_params))
    return sql, unique_missing


def render_from_xml(
    xml_text: str,
    sql_id: str,
    params: dict[str, Any] | None = None,
    mode: str = "params",
) -> tuple[str, list[str]]:
    """단일 XML 문자열에서 statement를 찾아 렌더링한다 (단위 테스트 및 fallback용)."""
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

    key = sql_id if "." in sql_id else f"{ns}.{sql_id}"
    if key not in statements and sql_id in statements:
        key = sql_id
    return render(key, params=params, mode=mode, statements=statements)

