"""AS-IS 소스(GXT)에서 화면 → 서비스 → SQL → 테이블 호출 경로 및 UI 색인을 만드는 도구."""

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from yunhee.tools.base import ToolResult

JAVA_REL = Path("application/src/main/java")

COMMON_DOMAIN = "_common"  # client/vi 밖 (service, utils, grid ...)
VIEW_DOMAIN = "_view"  # DB 색인 views.md의 뷰 (테이블처럼 취급)
VI_ROOT_DOMAIN = "_frame"  # 프레임: client/vi 바로 아래, OMS는 client/app (MainFrame, LoginPage ...)

SEQ_SQL_ID = "dbConfig.getSeq"  # 채번 SQL (→ f_create_seq())
MAP_PUT_RE = re.compile(r'\bmap\s*\.\s*put\s*\(\s*"(\w+)"\s*,\s*(.+?)\s*\)\s*;')
SQL_CALL_RE = re.compile(
    r"\bsqlSession\s*\.\s*(selectList|selectOne|selectMap|selectCursor|insert|update|delete)\s*\("
)
UDM_CALL_RE = re.compile(
    r"(?:new\s+UpdateDataModel(?:\s*<[^>]*>)?\s*\(\s*\)\s*\.|\b\w+\s*\.)\s*(updateModel|deleteModel)\s*\([^,]+,[^,]+,\s*([^,]+),"
)
SERVICE_REQ_RE = re.compile(r"\bnew\s+ServiceRequest\s*\(")
SERVICE_KEY_LITERAL_RE = re.compile(r'"([a-z]\w*)\.([A-Z]\w*)\.(\w+)"')
METHOD_HEAD_RE = re.compile(r"\b(\w+)\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+?)?\s*\{")
NOT_METHOD = {
    "if", "for", "while", "switch", "catch", "synchronized",
    "return", "new", "else", "try", "do",
}
ASSIGN_RE = re.compile(r"(?<![\w.])(\w+)\s*=(?!=)\s*([^;]+);")
MENU_OPENER_RE = re.compile(
    r'"([^"]+)"\s*\.equals\(\s*className\s*\)\s*\)\s*\{\s*return[^;]*?(?:GWT\.create\(\s*([\w.]+)\.class|new\s+([\w.]+)\s*\()'
)
MENU_REGISTRY_RE = re.compile(
    r'\.put\(\s*"([^"]+)"\s*,\s*\(\s*\)\s*->[^;]*?(?:GWT\.create\(\s*([\w.]+)\.class|new\s+([\w.]+)\s*\()'
)
STATEMENT_RE = re.compile(
    r"<(select|insert|update|delete|sql)\b[^>]*?\bid\s*=\s*\"([^\"]+)\"[^>]*>", re.IGNORECASE
)
INCLUDE_RE = re.compile(r"<include\s+refid\s*=\s*\"([^\"]+)\"", re.IGNORECASE)
CTE_RE = re.compile(r"\b(\w+)\s+as\s*\(", re.IGNORECASE)  # WITH x AS (
TABLE_KEYWORD_RE = re.compile(r"\b(?:from|join|into|update)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)

UI_NEW_RE = re.compile(r"(?<![\w.])(\w+)\s*=\s*new\s+(\w+)\s*(?:<[^>]*>)?\s*\(")
UI_WIDGET_CLS_RE = re.compile(
    r"Button$|Field$|ComboBox|CheckBox$|TextArea$|Radio$|^Grid$|^TreeGrid$|^Grid<|Page_|Tab_|Lookup_|Edit_|Popup_|Tree_"
)
UI_HANDLER_RE = re.compile(r"(?<![\w.])((?:this\.)?[\w.()]+?)\.add(\w+)Handler\s*\(")
UI_REGION_RE = re.compile(r"\bset(West|Center|North|South|East)Widget\s*\(")
UI_PARAM_RE = re.compile(r"\.addParam\s*\(")
UI_MSG_RE = re.compile(
    r"(SimpleMessage\.\w+|new\s+ConfirmBox|Info\.display|Window\.alert|new\s+MessageBox|new\s+AlertMessageBox)\s*\("
)
UI_LOGIN_RE = re.compile(r"\bLoginUser\.(\w+)\s*\(")
UI_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
UI_BUILDER_CALL_RE = re.compile(
    r"(?<![\w.])(\w+)\.(add\w+|setChecked|getTreeGrid|getGrid|setRowNumHidden|setDoubleClickEdit)\s*\("
)


# ---------------------------------------------------------------- Java 전처리

def strip_java(text: str) -> tuple[str, str]:
    """(주석 제거본, 주석+문자열 제거본). 줄 번호가 유지되도록 지운 자리는 공백으로 채운다."""
    no_comment, bare = [], []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            no_comment.append(" " * (j - i))
            bare.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank = re.sub(r"[^\n]", " ", text[i:j])
            no_comment.append(blank)
            bare.append(blank)
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            no_comment.append(text[i:j])
            bare.append(c + " " * (j - i - 2) + c if j - i >= 2 else text[i:j])
            i = j
        else:
            no_comment.append(c)
            bare.append(c)
            i += 1
    return "".join(no_comment), "".join(bare)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def call_argument(text: str, open_paren: int) -> str:
    """'(' 다음부터 최상위 ',' 또는 ')' 전까지의 첫 번째 인자"""
    depth, i, in_str = 0, open_paren + 1, None
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'":
            in_str = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return text[open_paren + 1:i].strip()
            depth -= 1
        elif c == "," and depth == 0:
            return text[open_paren + 1:i].strip()
        i += 1
    return text[open_paren + 1:].strip()


def split_plus(expr: str) -> list[str]:
    parts, depth, cur, in_str = [], 0, [], None
    for idx, c in enumerate(expr):
        if in_str:
            cur.append(c)
            if c == in_str and expr[idx - 1] != "\\":
                in_str = None
            continue
        if c in "\"'":
            in_str = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        if c == "+" and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur).strip())
    return parts


_assign_cache: dict[int, tuple[str, dict[str, list[str]]]] = {}


def assignments(scope: str) -> dict[str, list[str]]:
    """코드 조각의 '변수 = 식;' 목록 (변수 → [식]). 같은 코드는 한 번만 스캔한다."""
    key = id(scope)
    cached = _assign_cache.get(key)
    if cached is None or cached[0] is not scope:
        found: dict[str, list[str]] = defaultdict(list)
        for m in ASSIGN_RE.finditer(scope):
            found[m.group(1)].append(m.group(2))
        cached = (scope, found)
        _assign_cache[key] = cached
    return cached[1]


def eval_string(expr: str, scopes: list[str], depth: int = 0) -> set[str] | None:
    """문자열 식을 정적으로 계산한다. 가능한 값 집합, 못 하면 None."""
    if depth > 4:
        return None
    values = {""}
    for part in split_plus(expr):
        part = part.strip().strip("()").strip()
        if re.fullmatch(r'"(?:[^"\\]|\\.)*"', part):
            vals: set[str] | None = {part[1:-1]}
        else:
            name = re.fullmatch(r"(?:this\.)?(\w+)", part)
            if not name:
                return None
            vals = None
            for scope in scopes:
                found = set()
                for rhs in assignments(scope).get(name.group(1), ()):
                    v = eval_string(rhs, scopes, depth + 1)
                    if v:
                        found |= v
                if len(found) > 1:
                    found.discard("")
                if found:
                    vals = found
                    break
            if not vals:
                return None
        values = {a + b for a in values for b in vals}
        if len(values) > 20:
            return None
    return values


def paren_end(text: str, open_paren: int) -> int:
    """'(' 위치에서 짝이 맞는 ')' 위치 (문자열 안의 괄호는 무시)"""
    depth, i, in_str = 0, open_paren, None
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'":
            in_str = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1


def split_args(args: str) -> list[str]:
    """최상위 ',' 기준으로 인자를 나눈다"""
    out, depth, cur, in_str, i = [], 0, [], None, 0
    while i < len(args):
        c = args[i]
        if in_str:
            if c == "\\":
                cur.append(args[i:i + 2])
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'":
            in_str = c
        elif c in "([{<":
            depth += 1
        elif c in ")]}>":
            depth -= 1
        elif c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _short(expr: str, n: int = 40) -> str:
    expr = re.sub(r"\s+", " ", expr).strip()
    return expr if len(expr) <= n else expr[:n - 1] + "…"


def _strings(expr: str) -> list[str]:
    return UI_STR_RE.findall(expr)


def ui_lines(cls: Any, with_events: bool = False) -> list[str]:
    """클래스 하나의 UI 요약 줄 (화면 파일 '## UI' 절).

    with_events면 '- 이벤트:'·'- 메서드:' 줄은 뒤따르는 events 절과 겹치므로 생략한다.
    """
    text = cls.path.read_text(encoding="utf-8", errors="replace")
    code, bare = strip_java(text)
    methods = find_methods(bare)
    meth_names = {m[0] for m in methods}
    total = text.count("\n") + 1

    widgets: dict[str, tuple[str, str]] = {}
    for m in UI_NEW_RE.finditer(code):
        var, klass = m.group(1), m.group(2)
        close = paren_end(code, m.end() - 1)
        args = code[m.end():close]
        widgets.setdefault(var, (klass, args))
    builders = {v for v, (k, _) in widgets.items() if k == "GridBuilder"}
    members = set(widgets) | set(
        re.findall(r"(?:private|protected|public)\s+(?:final\s+)?[\w<>,\s]+?\s+(\w+)\s*[=;]", code)
    )

    def label(var: str) -> str:
        var = var.replace("this.", "")
        w = widgets.get(var)
        if not w:
            return var
        s = _strings(w[1])
        if w[0].endswith("Button") and s:
            return f"{var}[{s[0]}]"
        return var

    out = [f"### {cls.name} (`{cls.rel}`, {total}줄)", ""]

    regions = []
    for m in UI_REGION_RE.finditer(code):
        arg = split_args(code[m.end():paren_end(code, m.end() - 1)])
        if arg:
            regions.append(f"{m.group(1).lower()}={arg[0].replace('this.', '')}")
    if regions:
        out.append("- 레이아웃: " + ", ".join(regions))

    for bar in [v for v, (k, _) in widgets.items() if k in ("ButtonBar", "ToolBar", "ColorButtonBar")]:
        items = []
        for m in re.finditer(rf"(?<![\w.]){bar}\.add\s*\(", code):
            arg = split_args(code[m.end():paren_end(code, m.end() - 1)])
            if not arg:
                continue
            a = arg[0].replace("this.", "")
            s = _strings(a)
            if a.startswith(("new LabelToolItem", "new FieldLabel")):
                if s and s[0].strip():
                    items.append(f"{s[0].strip()}:")
                inner = re.match(r"new FieldLabel\s*\(\s*(\w+)", a)
                if inner:
                    items.append(f"{{{inner.group(1)}}}")
            elif a in widgets and widgets[a][0].endswith("Button"):
                items.append(f"[{_strings(widgets[a][1])[0] if _strings(widgets[a][1]) else a}]")
            elif re.fullmatch(r"\w+", a):
                items.append(f"{{{a}}}")
        if items:
            out.append(f"- 툴바 `{bar}`: " + " ".join(items))

    fields = []
    for var, (klass, args) in widgets.items():
        if klass.endswith("Button") or klass in (
            "GridBuilder", "ButtonBar", "ToolBar", "ColorButtonBar", "ContentPanel",
            "VerticalLayoutContainer", "HorizontalLayoutContainer", "FieldLabel",
            "BorderLayoutData", "VerticalLayoutData", "HorizontalLayoutData", "Margins",
            "ServiceRequest", "ServiceCall", "ArrayList", "HashMap"
        ):
            continue
        if not UI_WIDGET_CLS_RE.search(klass) or klass.startswith("Grid"):
            continue
        desc = f"`{var}` {klass}"
        s = [x for x in _strings(args) if x.strip()]
        if s:
            desc += "(" + ", ".join(f'"{x}"' for x in s) + ")"
        empty = re.search(rf"(?<![\w.]){var}\.setEmptyText\s*\(\s*\"([^\"]*)\"", code)
        if empty:
            desc += f' 빈칸="{empty.group(1)}"'
        fields.append(desc)
    if fields:
        out.append("- 입력·하위 화면: " + ", ".join(fields))
    buttons = [label(v) for v, (k, _) in widgets.items() if k.endswith("Button") and k != "DialogButton"]
    if buttons:
        out.append("- 버튼: " + ", ".join(buttons))

    for name, decl, start, end, _pub, _params in methods:
        body = code[start:end]
        cols, flags = [], []
        for m in UI_BUILDER_CALL_RE.finditer(body):
            if m.group(1) not in builders:
                continue
            op = m.group(2)
            args = split_args(body[m.end():paren_end(body, m.end() - 1)])
            if op == "setChecked":
                flags.append("체크박스" + ("(다중)" if args and "MULTI" in args[0] else ""))
            elif op == "getTreeGrid":
                flags.append("트리")
            elif op == "setRowNumHidden":
                flags.append("행번호숨김")
            elif op == "setDoubleClickEdit":
                flags.append("더블클릭편집")
            elif op.startswith("add") and args:
                fld_m = re.search(r"\.(\w+)\s*\(\s*\)", args[0])
                fld = fld_m.group(1) if fld_m else _short(args[0], 20)
                width = args[1] if len(args) > 1 else ""
                head = _strings(args[2])[0] if len(args) > 2 and _strings(args[2]) else ""
                edit = ""
                if len(args) > 3:
                    em = re.match(r"new\s+(\w+)", args[3])
                    edit = f" 편집:{em.group(1) if em else _short(args[3], 20)}"
                kind = op[3:] or "Text"
                cols.append(f"{fld} {width} \"{head}\" {kind}{edit}")
        if cols:
            holder = re.search(rf"(\w+)\s*=\s*(?:this\.)?{name}\s*\(\s*\)", code)
            hdr = f"- 그리드 `{holder.group(1) if holder else name}` ({name}()"
            hdr += (", " + ", ".join(flags) if flags else "") + "):"
            out.append(hdr)
            out += [f"  - {c}" for c in cols]

    if with_events:
        out.append("")
        return out

    events, handler_spans = [], []
    for m in UI_HANDLER_RE.finditer(code):
        close = paren_end(code, m.end() - 1)
        handler_spans.append((m.end(), close))
        body = code[m.end():close]
        calls = []
        for c in re.finditer(r"(?<![\w])((?:\w+\.)?)(\w+)\s*\(", body):
            recv, fn = c.group(1), c.group(2)
            if recv in ("", "this.") and fn in meth_names:
                calls.append(f"{fn}()")
            elif recv and recv[:-1] in members and not fn.startswith(("get", "set", "is", "add")):
                calls.append(f"{recv}{fn}()")
        src = re.sub(r"\.getSelectionModel\(\)", "", m.group(1)).replace("this.", "")
        if calls:
            events.append(f"{label(src)}.{m.group(2)} → {', '.join(dict.fromkeys(calls))}")
    if events:
        out.append("- 이벤트: " + "; ".join(dict.fromkeys(events)))

    mlines = []
    for name, decl, start, end, _pub, params in methods:
        body = code[start:end]
        if name == cls.name and not body.strip("{} \n\t"):
            continue
        parts = []
        svcs = [s.group(0)[1:-1] for s in SERVICE_KEY_LITERAL_RE.finditer(body)]
        prms = []
        for p in UI_PARAM_RE.finditer(body):
            a = split_args(body[p.end():paren_end(body, p.end() - 1)])
            if len(a) >= 2:
                prms.append(f"{_strings(a[0])[0] if _strings(a[0]) else a[0]}={_short(a[1], 30)}")
        if svcs:
            parts.append(
                "서비스 " + ", ".join(f"`{s}`" for s in dict.fromkeys(svcs))
                + (f" ({', '.join(dict.fromkeys(prms))})" if prms else "")
            )
        own = list(bare[start:end])
        for hs, he in handler_spans:
            for i in range(max(hs, start), min(he, end)):
                own[i - start] = " "
        calls = [
            c.group(1) for c in re.finditer(r"(?<![\w.])(?:this\.)?(\w+)\s*\(", "".join(own))
            if c.group(1) in meth_names and c.group(1) != name
        ]
        if calls:
            parts.append("→ " + ", ".join(f"{c}()" for c in dict.fromkeys(calls)))
        msgs = []
        for mm in UI_MSG_RE.finditer(body):
            s = [x for x in _strings(body[mm.end():paren_end(body, mm.end() - 1)]) if x.strip()]
            if s:
                msgs.append(" / ".join(s))
        if msgs:
            parts.append("메시지 " + ", ".join(f'"{x}"' for x in dict.fromkeys(msgs)))
        login = sorted({l.group(1) for l in UI_LOGIN_RE.finditer(body)})
        if login:
            parts.append("세션 " + ", ".join(login))
        a, b = line_of(code, decl), line_of(code, end)
        mlines.append(f"  - `{name}({_short(params, 30)})` L{a}-{b}" + (": " + "; ".join(parts) if parts else ""))
    if mlines:
        out.append("- 메서드:")
        out += mlines
    out.append("")
    return out


class ClientClass:
    def __init__(self, name: str, rel: Path, domain: str, is_model: bool) -> None:
        self.name, self.rel, self.domain, self.is_model = name, rel, domain, is_model
        self.path: Path | None = None
        self.services: list[tuple[str, int]] = []
        self.unresolved: list[tuple[str, int]] = []
        self.refs: set[str] = set()
        self._bare: str = ""


class ServerMethod:
    def __init__(self, cls: Any, name: str, line: int, is_service: bool) -> None:
        self.cls, self.name, self.line, self.is_service = cls, name, line, is_service
        self.sql_ids: set[str] = set()
        self.unresolved: list[tuple[str, int]] = []
        self.calls: set[str] = set()
        self.cross: set[str] = set()
        self.udm_calls: list[tuple[str, str]] = []
        self._body_bare: str = ""
        self._tokens: set[str] = set()

    @property
    def key(self) -> str:
        return f"{self.cls.key}.{self.name}"


class ServerClass:
    def __init__(self, key: str, rel: Path, domain: str) -> None:
        self.key, self.rel, self.domain = key, rel, domain
        self.methods: dict[str, ServerMethod] = {}


class Statement:
    def __init__(self, ns: str, sid: str, kind: str, rel: Path, line: int, domain: str) -> None:
        self.ns, self.sid, self.kind, self.rel, self.line, self.domain = ns, sid, kind, rel, line, domain
        self.tables: set[str] = set()
        self.functions: set[str] = set()
        self.includes: list[str] = []
        self.ctes: set[str] = set()

    @property
    def key(self) -> str:
        return f"{self.ns}.{self.sid}"


def client_domain(rel: Path) -> str:
    parts = rel.parts
    if len(parts) >= 3 and parts[1] == "vi":
        return parts[2] if len(parts) >= 4 else VI_ROOT_DOMAIN
    if len(parts) == 3 and parts[1] == "app":
        return VI_ROOT_DOMAIN
    return COMMON_DOMAIN


def parse_client(app: Path) -> dict[str, list[ClientClass]]:
    classes: dict[str, list[ClientClass]] = {}
    server_dir = app / "server"
    server_domains = {d.name for d in server_dir.iterdir() if d.is_dir()} if server_dir.is_dir() else set()
    for path in sorted((app / "client").rglob("*.java")):
        rel = path.relative_to(app)
        no_comment, bare = strip_java(path.read_text(encoding="utf-8", errors="replace"))
        cls = ClientClass(path.stem, rel, client_domain(rel), "model" in rel.parts or path.stem.endswith("Properties"))
        cls.path = path
        for m in SERVICE_REQ_RE.finditer(no_comment):
            arg = call_argument(no_comment, m.end() - 1)
            line = line_of(no_comment, m.start())
            if not arg:
                continue
            vals = eval_string(arg, [no_comment])
            if vals:
                cls.services += [(v, line) for v in sorted(vals)]
            else:
                cls.unresolved.append((arg, line))
        for m in re.finditer(r"\.setServiceName\s*\(", no_comment):
            arg = call_argument(no_comment, m.end() - 1)
            vals = eval_string(arg, [no_comment])
            line = line_of(no_comment, m.start())
            if vals:
                cls.services += [(v, line) for v in sorted(vals)]
            else:
                cls.unresolved.append((arg, line))
        found = {v for v, _ in cls.services}
        for m in SERVICE_KEY_LITERAL_RE.finditer(no_comment):
            key = m.group(0)[1:-1]
            if m.group(1) in server_domains and key not in found:
                found.add(key)
                cls.services.append((key, line_of(no_comment, m.start())))
        cls._bare = bare
        classes.setdefault(cls.name, []).append(cls)

    vi_names = {
        name for name, items in classes.items()
        if any(c.domain != COMMON_DOMAIN and not c.is_model for c in items)
    }
    for items in classes.values():
        for cls in items:
            tokens = set(re.findall(r"\b[A-Z]\w+\b", cls._bare))
            cls.refs = (tokens & vi_names) - {cls.name}
            cls._bare = ""
    return classes


def find_methods(bare: str) -> list[tuple[str, int, int, int, bool, str]]:
    methods = []
    for m in METHOD_HEAD_RE.finditer(bare):
        name = m.group(1)
        if name in NOT_METHOD:
            continue
        prefix_start = max(bare.rfind(";", 0, m.start()), bare.rfind("{", 0, m.start()), bare.rfind("}", 0, m.start())) + 1
        prefix = bare[prefix_start:m.start()].split()
        if not prefix or prefix[-1] in NOT_METHOD or "=" in "".join(prefix) or prefix[-1].endswith((".", "(", ",")):
            continue
        modifiers = set(prefix)
        start = m.end() - 1
        depth, i = 0, start
        while i < len(bare):
            if bare[i] == "{":
                depth += 1
            elif bare[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        methods.append((name, m.start(1), start, i, "public" in modifiers, m.group(2)))
    methods.sort(key=lambda x: x[2])
    top, end = [], -1
    for meth in methods:
        if meth[2] > end:
            top.append(meth)
            end = meth[3]
    return top


def parse_server(app: Path) -> dict[str, ServerClass]:
    classes = {}
    server_dir = app / "server"
    if not server_dir.is_dir():
        return classes
    for path in sorted(server_dir.rglob("*.java")):
        rel = path.relative_to(app)
        pkg = path.relative_to(server_dir).with_suffix("")
        key = ".".join(pkg.parts)
        domain = pkg.parts[0] if len(pkg.parts) > 1 else COMMON_DOMAIN
        no_comment, bare = strip_java(path.read_text(encoding="utf-8", errors="replace"))
        cls = ServerClass(key, rel, domain)
        for name, name_pos, body_start, body_end, is_public, params in find_methods(bare):
            is_service = is_public and "SqlSession" in params and "ServiceRequest" in params and "ServiceResult" in params
            meth = ServerMethod(cls, name, line_of(bare, name_pos), is_service)
            body = no_comment[body_start:body_end + 1]
            body_bare = bare[body_start:body_end + 1]
            for m in SQL_CALL_RE.finditer(body):
                arg = call_argument(body, m.end() - 1)
                vals = eval_string(arg, [body, no_comment])
                if vals:
                    # namespace 없는 "getSeq"는 MyBatis가 dbConfig.getSeq로 찾는다.
                    meth.sql_ids |= {SEQ_SQL_ID if v == "getSeq" else v for v in vals}
                else:
                    meth.unresolved.append((arg, line_of(no_comment, body_start + m.start())))
            for m in UDM_CALL_RE.finditer(body):
                op = m.group(1)
                arg = m.group(2).strip()
                vals = eval_string(arg, [body, no_comment])
                if vals:
                    for v in sorted(vals):
                        meth.udm_calls.append((op, v))
            meth._body_bare = body_bare
            cls.methods.setdefault(name, meth)
        names = set(cls.methods)
        for meth in cls.methods.values():
            called = set(re.findall(r"(?<![\w.])(\w+)\s*\(", meth._body_bare)) & names
            meth.calls = called - {meth.name}
            meth._tokens = set(re.findall(r"\b[A-Z]\w+\b", meth._body_bare))
            meth._body_bare = ""
        classes[key] = cls
    simple = {c.key.split(".")[-1] for c in classes.values()}
    for cls in classes.values():
        for meth in cls.methods.values():
            meth.cross = (meth._tokens & simple) - {cls.key.split(".")[-1]}
            meth._tokens = set()
    return classes


def all_sql_ids(meth: ServerMethod, seen: set[str] | None = None) -> set[str]:
    seen = seen or set()
    if meth.name in seen:
        return set()
    seen.add(meth.name)
    ids = set(meth.sql_ids)
    for name in meth.calls:
        if name in meth.cls.methods:
            ids |= all_sql_ids(meth.cls.methods[name], seen)
    return ids


def all_udm_calls(meth: ServerMethod, seen: set[str] | None = None) -> list[tuple[str, str]]:
    seen = seen or set()
    if meth.name in seen:
        return []
    seen.add(meth.name)
    calls = list(meth.udm_calls)
    for name in meth.calls:
        if name in meth.cls.methods:
            calls += all_udm_calls(meth.cls.methods[name], seen)
    return calls


def java_literal(expr: str) -> str | None:
    """map.put 값이 리터럴이면 SQL 리터럴('true', 0, NULL)로, 변수·식이면 None."""
    expr = expr.strip()
    if re.fullmatch(r'"(?:[^"\\]|\\.)*"', expr):
        return "'" + expr[1:-1].replace("'", "''") + "'"
    if re.fullmatch(r"-?\d+(?:\.\d+)?[lLdDfF]?", expr):
        return expr.rstrip("lLdDfF")
    if expr == "null":
        return "NULL"
    if expr in ("true", "false"):
        return expr
    return None


def parse_update_data_model(app: Path) -> dict[str, dict[str, Any]]:
    """UpdateDataModel.java를 파싱하여 테이블별 저장 부수 효과(INSERT/UPDATE/PROC)를 수집한다."""
    udm_file = next(app.rglob("UpdateDataModel.java"), None)
    if not udm_file or not udm_file.is_file():
        return {}
    raw = udm_file.read_text(encoding="utf-8", errors="replace")
    no_comm, bare = strip_java(raw)

    side_effects: dict[str, dict[str, Any]] = {}
    for m in re.finditer(r'if\s*\(\s*"([^"]+)"\s*\.\s*equals\s*\(\s*tableName\s*\)\s*\)\s*\{', no_comm):
        tbl = m.group(1)
        start_pos = m.start()
        start_line = line_of(no_comm, start_pos)
        depth = 1
        i = m.end()
        while i < len(bare) and depth > 0:
            if bare[i] == "{":
                depth += 1
            elif bare[i] == "}":
                depth -= 1
            i += 1
        end_line = line_of(no_comm, i - 1)
        block = no_comm[m.end():i - 1]
        offset = m.end()

        found: list[tuple[int, tuple[str, str, str, int]]] = []
        for sm in re.finditer(r'sqlSession\s*\.\s*(insert|update|selectOne)\s*\(\s*"([^"]+)"', block):
            line = line_of(no_comm, offset + sm.start())
            # namespace 없는 "getSeq"도 dbConfig.getSeq(→ f_create_seq())로 푼다.
            sid = SEQ_SQL_ID if sm.group(2) == "getSeq" else sm.group(2)
            found.append((sm.start(), ("sql", sm.group(1), sid, line)))
        for pm in re.finditer(r'prepareStatement\s*\(\s*"(call\s+([a-zA-Z0-9_]+)\s*\([^)]*\))"', block):
            line = line_of(no_comm, offset + pm.start())
            found.append((pm.start(), ("proc", pm.group(1), pm.group(2), line)))
        found.sort(key=lambda x: x[0])

        items = []
        pending_seq = None
        seg_start = 0
        for pos, c in found:
            if c[0] == "sql" and c[2] == SEQ_SQL_ID:
                pending_seq = c
                continue
            # 이 호출에 넘기는 map.put 값: 직전 호출 이후, 마지막 map.clear() 이후 구간
            seg = block[seg_start:pos]
            clear = list(re.finditer(r"\bmap\s*\.\s*clear\s*\(\s*\)", seg))
            seg_off = seg_start + (clear[-1].end() if clear else 0)
            puts = []
            for mp in MAP_PUT_RE.finditer(block, seg_off, pos):
                puts.append((mp.group(1), java_literal(mp.group(2)), line_of(no_comm, offset + mp.start())))
            items.append({"seq": pending_seq, "call": c, "puts": puts})
            pending_seq = None
            seg_start = pos

        side_effects[tbl] = {
            "start_line": start_line,
            "end_line": end_line,
            "items": items,
        }
    return side_effects


def strip_sql(text: str) -> str:
    text = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", text)


def parse_mappers(
    app: Path,
    known_tables: dict[str, str],
    known_functions: set[str],
    known_columns: set[str] = frozenset(),
) -> tuple[dict[str, Statement], dict[str, list[Path]]]:
    statements: dict[str, Statement] = {}
    ns_files: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(app.rglob("*.xml")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        ns = re.search(r"<mapper\s+namespace\s*=\s*\"([^\"]+)\"", raw)
        if not ns:
            continue
        rel = path.relative_to(app)
        ns_str = ns.group(1)
        ns_files[ns_str].append(rel)
        domain = rel.parts[1] if len(rel.parts) > 2 and rel.parts[0] == "server" else COMMON_DOMAIN
        text = strip_sql(raw)
        for m in STATEMENT_RE.finditer(text):
            kind = m.group(1).lower()
            end = text.find(f"</{m.group(1)}>", m.end())
            body = text[m.end(): end if end > 0 else len(text)]
            st = Statement(ns_str, m.group(2), kind, rel, line_of(text, m.start()), domain)
            sql = re.sub(r"<[^>]+>", " ", body)
            st.ctes = {c.lower() for c in CTE_RE.findall(sql)}
            st.tables = {
                t.lower() for t in TABLE_KEYWORD_RE.findall(sql)
                if re.match(r"[a-z]+\d", t.lower()) and t.lower() not in (known_functions | known_columns)
            }
            if known_tables:
                st.tables |= {t for t in re.findall(r"\b[a-z_][a-z0-9_]*\b", sql.lower()) if t in known_tables}
            if known_functions:
                st.functions = {f for f in re.findall(r"\b([a-z_][a-z0-9_]*)\s*\(", sql.lower()) if f in known_functions}
            st.includes = INCLUDE_RE.findall(body)
            statements[st.key] = st

    def resolve(st: Statement, seen: set[str]) -> None:
        for ref in st.includes:
            target = statements.get(ref) or statements.get(f"{st.ns}.{ref}")
            if target and target.key not in seen:
                seen.add(target.key)
                resolve(target, seen)
                st.tables |= target.tables
                st.functions |= target.functions
                st.ctes |= target.ctes

    for st in statements.values():
        resolve(st, {st.key})
    for st in statements.values():
        st.tables -= st.ctes
    return statements, ns_files


def parse_menu_opener(app: Path) -> dict[str, str]:
    path = next(
        (p for p in (app / "client" / "vi" / "MenuOpener.java", app / "client" / "app" / "MenuOpener.java") if p.is_file()),
        None,
    )
    if not path:
        return {}
    no_comment, _ = strip_java(path.read_text(encoding="utf-8", errors="replace"))
    matches = [*MENU_OPENER_RE.finditer(no_comment), *MENU_REGISTRY_RE.finditer(no_comment)]
    return {m.group(1): (m.group(2) or m.group(3)).split(".")[-1] for m in matches}


def load_menus(path: Path | None) -> list[dict[str, str]]:
    menus = []
    if not path or not path.is_file():
        return menus
    for line in path.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 3 and cols[2]:
            menus.append({
                "no": cols[0],
                "path": cols[1],
                "key": cols[2],
                "use": cols[3] if len(cols) > 3 else "",
            })
    return menus


def load_db_index(db_dir: Path | None) -> tuple[dict[str, str], set[str], set[str]]:
    tables: dict[str, str] = {}
    functions: set[str] = set()
    columns: set[str] = set()
    if not db_dir or not db_dir.is_dir():
        return tables, functions, columns
    for f in (db_dir / "tables").glob("*.md"):
        text = f.read_text(encoding="utf-8")
        for name in re.findall(r"^\| `([^`]+)` \|", text, re.MULTILINE):
            tables[name] = f.stem
        columns |= set(re.findall(r'^\s+"(\w+)" "', text, re.MULTILINE))
    views = db_dir / "views.md"
    if views.is_file():
        for name in re.findall(r"^## \w+\.(\w+)", views.read_text(encoding="utf-8"), re.MULTILINE):
            tables[name] = VIEW_DOMAIN
    readme = db_dir / "functions" / "README.md"
    if readme.is_file():
        functions = set(re.findall(r"^\| \[`([^`]+)`\]", readme.read_text(encoding="utf-8"), re.MULTILINE))
    return tables, functions, columns


class Index:
    def __init__(
        self,
        app: Path,
        client: dict[str, list[ClientClass]],
        server: dict[str, ServerClass],
        statements: dict[str, Statement],
        opener: dict[str, str],
        menus: list[dict[str, str]],
        tables: dict[str, str],
        db_rel: str | None,
        ns_files: dict[str, list[Path]] | None = None,
    ) -> None:
        self.app, self.client, self.server, self.statements = app, client, server, statements
        self.opener, self.menus, self.tables, self.db_rel = opener, menus, tables, db_rel
        self.ns_files: dict[str, list[Path]] = ns_files or {}
        self.udm_side_effects: dict[str, dict[str, Any]] = parse_update_data_model(app)
        self.screen_names = set(opener.values())
        self.service_methods: dict[str, ServerMethod] = {}
        for cls in server.values():
            for meth in cls.methods.values():
                if meth.is_service:
                    self.service_methods[meth.key] = meth
        self.service_callers: dict[str, set[str]] = defaultdict(set)
        for items in client.values():
            for c in items:
                for key, _ in c.services:
                    self.service_callers[key].add(c.name)
        self.sql_users: dict[str, set[str]] = defaultdict(set)
        for meth in self.service_methods.values():
            for sid in all_sql_ids(meth):
                self.sql_users[sid].add(meth.key)
        self.ns_domain: dict[str, str] = {}
        for st in statements.values():
            self.ns_domain.setdefault(st.ns, st.domain)
        self.used_by_domains: dict[str, set[str]] = defaultdict(set)
        for items in client.values():
            for c in items:
                for ref in c.refs:
                    target = self.client_class(ref)
                    if (
                        target and self.is_vi(target) and target.domain != c.domain and self.is_vi(c)
                        and VI_ROOT_DOMAIN not in (c.domain, target.domain)
                    ):
                        self.used_by_domains[ref].add(c.domain)
        self.frame_names = {
            c.name for items in client.values() for c in items
            if c.domain == VI_ROOT_DOMAIN and not c.is_model
            and (c.services or any(self.is_vi(t) and t.domain != VI_ROOT_DOMAIN
                                   for t in map(self.client_class, c.refs) if t))
        }
        self.screen_names |= self.frame_names
        self.component_names = {n for n in self.used_by_domains if n not in self.screen_names}
        # events 절: index_src()가 켠다. 여러 화면이 같은 클래스를 공유하므로 경로별로 캐시한다.
        self.with_events = False
        self.button_types_path: Path | None = None
        self.events_cache: dict[Path, list[str]] = {}
        self.events_errors: list[tuple[str, str]] = []

    def client_class(self, name: str) -> ClientClass | None:
        items = self.client.get(name, [])
        return items[0] if items else None

    @staticmethod
    def is_vi(target_cls: ClientClass) -> bool:
        return target_cls.domain != COMMON_DOMAIN and not target_cls.is_model

    def is_unit(self, name: str) -> bool:
        return name in self.screen_names or name in self.component_names

    def closure(self, start: str) -> tuple[list[ClientClass], set[str]]:
        seen, stack, linked, visited = [], [start], set(), {start}
        in_frame = start in self.frame_names
        while stack:
            cls = self.client_class(stack.pop())
            if not cls:
                continue
            seen.append(cls)
            for ref in sorted(cls.refs):
                if ref in visited:
                    continue
                visited.add(ref)
                target = self.client_class(ref)
                if not target or not self.is_vi(target) or (target.domain == VI_ROOT_DOMAIN and not in_frame):
                    continue
                if self.is_unit(ref):
                    linked.add(ref)
                else:
                    stack.append(ref)
        return seen, linked

    def unit_path(self, name: str) -> str:
        cls = self.client_class(name)
        if not cls:
            return f"_unknown/screens/{name}.md"
        kind = "screens" if name in self.screen_names else "components"
        return f"{cls.domain}/{kind}/{name}.md"

    @staticmethod
    def service_path(server_cls: ServerClass) -> str:
        name = server_cls.key.split(".", 1)[1] if "." in server_cls.key else server_cls.key
        return f"{server_cls.domain}/services/{name}.md"

    def sql_path(self, ns: str) -> str:
        return f"{self.ns_domain.get(ns, COMMON_DOMAIN)}/sql/{ns}.md"

    def table_link(self, table: str, up: str) -> str:
        dom = self.tables.get(table)
        if self.tables and not dom:
            return f"`{table}` ⚠DB없음"
        if not dom or not self.db_rel:
            return f"`{table}`"
        doc = "views.md" if dom == VIEW_DOMAIN else f"tables/{dom}.md"
        return f"[`{table}`]({self.db_doc(doc, up)})"

    def db_doc(self, doc: str, up: str) -> str:
        """DB 색인 문서 링크 경로. db_rel이 절대 경로면(출력 폴더에서 멀리 떨어진 경우) up을 붙이지 않는다."""
        if self.db_rel and Path(self.db_rel).is_absolute():
            return f"{self.db_rel}/{doc}"
        return f"{up}{self.db_rel}/{doc}"

    def sql_link(self, sid: str, up: str) -> str:
        st = self.statements.get(sid)
        if not st:
            return f"`{sid}`(없음)"
        link = f"[`{sid}`]({up}{self.sql_path(st.ns)})"
        return link + " (→ `f_create_seq()`)" if sid == SEQ_SQL_ID else link


def md_cell(v: Any) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def write(out: Path, rel: str, lines: list[str]) -> None:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def events_lines(idx: Index, cls: ClientClass) -> list[str]:
    """클래스 하나의 `yunhee events` 결과 (화면 파일 '## UI' 절 안의 '#### 이벤트' 이하)."""
    if cls.path in idx.events_cache:
        return idx.events_cache[cls.path]
    # events.py가 이 모듈을 임포트하므로 순환 임포트를 피해 함수 안에서 가져온다.
    from yunhee.tools.as_is.events import (
        extract_buttons,
        extract_events_and_methods,
        extract_grid_spec,
        render_events_markdown,
    )

    try:
        text = cls.path.read_text(encoding="utf-8", errors="replace")
        ev_list, method_list = extract_events_and_methods(text, file_path=cls.path)
        grid_spec = extract_grid_spec(text, file_path=cls.path)
        buttons = extract_buttons(text, events=ev_list, file_path=cls.path, button_types_path=idx.button_types_path)
        md = render_events_markdown("", ev_list, method_list, grid_spec=grid_spec, buttons=buttons)
    except Exception as e:  # noqa: BLE001 — 한 파일 파싱 실패로 전체 색인을 멈추지 않는다
        idx.events_errors.append((cls.name, f"{type(e).__name__}: {e}"))
        out = [f"#### events 추출 실패: `{type(e).__name__}`", ""]
    else:
        # '원본:' 줄은 '### 클래스' 제목과 겹치므로 버리고, '## 절'은 '### 클래스' 아래로 내린다.
        out = [
            "#" * 2 + line if line.startswith("## ") else line
            for line in md.splitlines()
            if not line.startswith("원본:")
        ]
        while out and not out[0].strip():
            out.pop(0)
        out.append("")
    idx.events_cache[cls.path] = out
    return out


def write_unit(
    idx: Index,
    out: Path,
    name: str,
    menus_by_key: dict[str, list[dict[str, str]]],
    keys_by_class: dict[str, list[str]],
) -> tuple[int, int]:
    up = "../../"
    cls = idx.client_class(name)
    if not cls:
        return 0, 0
    classes, linked = idx.closure(name)
    is_screen = name in idx.screen_names
    kind = (
        "프레임 (로그인·메인 화면 등, 메뉴로 열지 않음)"
        if name in idx.frame_names
        else "화면"
        if is_screen
        else "컴포넌트 (다른 도메인에서도 쓰는 클래스)"
    )
    lines = [f"# {name}", "", f"- 종류: {kind}"]
    for key in keys_by_class.get(name, []):
        for m in menus_by_key.get(key, []):
            lines.append(f"- 메뉴: {m['path']} (#{m['no']}{'' if m['use'] == 'true' else ', 미사용'})")
        if key != name:
            lines.append(f"- 메뉴 키: `{key}`")
    if not is_screen:
        lines.append("- 사용 도메인: " + ", ".join(f"`{d}`" for d in sorted(idx.used_by_domains[name])))
    lines.append(f"- 파일: `{cls.rel}`")
    others = [c for c in classes if c is not cls]
    if others:
        lines.append(f"- 함께 쓰는 클래스 {len(others)}개:")
        lines += [f"  - `{c.name}` `{c.rel}`" for c in others]
    if linked:
        lines.append(
            "- 연결 화면·컴포넌트 (각 파일 참고): "
            + ", ".join(f"[`{n}`]({up}{idx.unit_path(n)})" for n in sorted(linked))
        )

    calls: dict[str, set[str]] = defaultdict(set)
    for c in classes:
        for skey, line in c.services:
            calls[skey].add(f"{c.name}:{line}")
    tables, functions = set(), set()
    if calls:
        lines += ["", "## 서비스", "", "| 서비스 | 호출 위치 | 서버 | SQL ID |", "|:---|:---|:---|:---|"]
        for skey in sorted(calls):
            meth = idx.service_methods.get(skey)
            if meth:
                ids = sorted(all_sql_ids(meth))
                udm_calls = all_udm_calls(meth)
                for sid in ids:
                    st = idx.statements.get(sid)
                    if st:
                        tables |= st.tables
                        functions |= st.functions
                sql_parts = [idx.sql_link(i, up) for i in ids]
                for op, tbl in udm_calls:
                    tables.add(tbl)
                    has_side_effect = tbl in idx.udm_side_effects
                    if op == "updateModel":
                        part = f"`UpdateDataModel({tbl})` 동적 INSERT/UPDATE → {idx.sql_link(f'{tbl}.selectById', up)}"
                        if has_side_effect:
                            part += ' ; 부수 효과: 아래 "저장 시 부수 효과"'
                            for it in idx.udm_side_effects[tbl]["items"]:
                                if it.get("seq"):
                                    st_seq = idx.statements.get(it["seq"][2])
                                    if st_seq:
                                        tables |= st_seq.tables
                                        functions |= st_seq.functions
                                call_item = it["call"]
                                if call_item[0] == "sql":
                                    st_call = idx.statements.get(call_item[2])
                                    if st_call:
                                        tables |= st_call.tables
                                        functions |= st_call.functions
                                elif call_item[0] == "proc":
                                    functions.add(call_item[2])
                        sql_parts.append(part)
                    elif op == "deleteModel":
                        sql_parts.append(f"`UpdateDataModel({tbl})` 동적 DELETE")
                server = f"[`{meth.cls.rel.name}:{meth.line}`]({up}{idx.service_path(meth.cls)})"
                sql = ", ".join(sql_parts) or "-"
            elif skey == "getSeq":
                server = "(공통) 채번"
                sql = idx.sql_link(SEQ_SQL_ID, up)
                st = idx.statements.get(SEQ_SQL_ID)
                if st:
                    tables |= st.tables
                    functions |= st.functions
                functions.add("f_create_seq")
            else:
                server, sql = "**(없음)**", "-"
            lines.append(f"| `{skey}` | {', '.join(sorted(calls[skey]))} | {server} | {md_cell(sql)} |")
    if tables:
        lines += ["", "## 테이블", "", ", ".join(idx.table_link(t, up) for t in sorted(tables))]
    if functions:
        lines += ["", "## DB 함수", "", ", ".join(f"`{f}`" for f in sorted(functions))]
    side_effect_tables = {
        tbl for c in classes for skey, _ in c.services
        if (meth := idx.service_methods.get(skey))
        for op, tbl in all_udm_calls(meth)
        if op == "updateModel" and tbl in idx.udm_side_effects
    }
    if side_effect_tables:
        for tbl in sorted(side_effect_tables):
            se = idx.udm_side_effects[tbl]
            lines += [
                "",
                "## 저장 시 부수 효과 (UpdateDataModel)",
                "",
                f"`{tbl}`를 새로 INSERT하면 (UpdateDataModel.java L{se['start_line']}-{se['end_line']}) 이어서:",
                "",
            ]
            for idx_num, it in enumerate(se["items"], 1):
                seq = it.get("seq")
                call = it["call"]
                parts = []
                if seq:
                    parts.append(idx.sql_link(seq[2], up))
                    parts.append("→")
                if call[0] == "sql":
                    sql_id = call[2]
                    st = idx.statements.get(sql_id)
                    tbl_info = f", {', '.join(idx.table_link(t, up) for t in sorted(st.tables))}" if st and st.tables else ""
                    parts.append(f"{idx.sql_link(sql_id, up)} (L{call[3]}{tbl_info})")
                elif call[0] == "proc":
                    proc_name = call[2]
                    proc_call = call[1]
                    proc_link = f" → [{proc_name}]({idx.db_doc(f'functions/{proc_name}.md', up)})" if idx.db_rel else ""
                    parts.append(f"`{proc_call}` (L{call[3]}, DB 프로시저{proc_link})")
                lines.append(f"{idx_num}. {' '.join(parts)}")
    unresolved = [(c.name, e, l) for c in classes for e, l in c.unresolved]
    if unresolved:
        lines += ["", "## 해석 못 한 서비스 호출", ""] + [f"- `{n}:{l}` `{md_cell(e)}`" for n, e, l in unresolved]
    ui = [c for c in classes if idx.is_vi(c) and c.path]
    if ui:
        lines += ["", "## UI", "", "GXT 소스에서 정적으로 뽑은 화면 구성 (LLM 없음). 처리 로직은 메서드 줄 범위만 원본에서 읽는다.", ""]
        for c in ui:
            lines += ui_lines(c, with_events=idx.with_events)
            if idx.with_events:
                lines += events_lines(idx, c)
    write(out, idx.unit_path(name), lines)
    return len(others), len(calls)


def write_services(idx: Index, out: Path, cls: ServerClass) -> int:
    up = "../../"
    services = sorted((m for m in cls.methods.values() if m.is_service), key=lambda m: m.line)
    lines = [
        f"# {cls.key}", "", f"`{cls.rel}`", "",
        "서비스 키 `" + cls.key + ".{메서드}`. SQL ID는 같은 클래스 안에서 호출하는 메서드의 것까지 포함한다.", "",
        "| 메서드 | 줄 | SQL ID | 호출 클래스 | 다른 서버 클래스 |",
        "|:---|---:|:---|:---|:---|",
    ]
    for m in services:
        udm_parts = []
        for op, tbl in all_udm_calls(m):
            if op == "updateModel":
                udm_parts.append(f"`UpdateDataModel({tbl})` 동적 INSERT/UPDATE")
            elif op == "deleteModel":
                udm_parts.append(f"`UpdateDataModel({tbl})` 동적 DELETE")
        all_parts = [idx.sql_link(i, up) for i in sorted(all_sql_ids(m))] + udm_parts
        ids = ", ".join(all_parts) or "-"
        callers = ", ".join(f"`{c}`" for c in sorted(idx.service_callers.get(m.key, []))) or "-"
        cross = ", ".join(f"`{c}`" for c in sorted(m.cross))
        lines.append(f"| `{m.name}` | {m.line} | {ids} | {callers} | {cross} |")
    write(out, idx.service_path(cls), lines)
    return len(services)


def write_sql(idx: Index, out: Path, ns: str, items: list[Statement]) -> None:
    up = "../../"
    lines = [
        f"# {ns}", "", f"`{items[0].rel}`", "",
    ]
    ns_files = idx.ns_files.get(ns, [])
    if len(ns_files) > 1:
        lines += [
            f"> ⚠ 같은 namespace 매퍼 {len(ns_files)}개: " + ", ".join(f"`{p.name}`" for p in ns_files),
            "",
        ]
    lines += [
        "테이블·DB 함수는 `<include>`한 SQL 조각의 것까지 포함한다.", "",
        "| SQL ID | 종류 | 줄 | 테이블 | DB 함수 | 사용 서버 메서드 |",
        "|:---|:---|---:|:---|:---|:---|",
    ]
    for s in sorted(items, key=lambda s: s.line):
        tables = ", ".join(idx.table_link(t, up) for t in sorted(s.tables)) or "-"
        funcs = ", ".join(f"`{f}`" for f in sorted(s.functions))
        users = ", ".join(f"`{u}`" for u in sorted(idx.sql_users.get(s.key, []))) or ("" if s.kind == "sql" else "-")
        lines.append(f"| `{s.sid}` | {s.kind} | {s.line} | {tables} | {funcs} | {users} |")
    write(out, idx.sql_path(ns), lines)


def write_domains(idx: Index, out: Path) -> dict[str, dict[str, int]]:
    menus_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for m in idx.menus:
        menus_by_key[m["key"]].append(m)
    keys_by_class: dict[str, list[str]] = defaultdict(list)
    for key, name in idx.opener.items():
        keys_by_class[name].append(key)

    dom_units: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for name in sorted(idx.screen_names | idx.component_names):
        cls = idx.client_class(name)
        if cls and idx.is_vi(cls):
            n_classes, n_services = write_unit(idx, out, name, menus_by_key, keys_by_class)
            dom_units[cls.domain].append((name, n_classes, n_services))
    dom_services: dict[str, list[tuple[ServerClass, int]]] = defaultdict(list)
    for cls in sorted(idx.server.values(), key=lambda c: c.key):
        if any(m.is_service for m in cls.methods.values()):
            dom_services[cls.domain].append((cls, write_services(idx, out, cls)))
    dom_sql: dict[str, list[tuple[str, list[Statement]]]] = defaultdict(list)
    by_ns: dict[str, list[Statement]] = defaultdict(list)
    for st in idx.statements.values():
        by_ns[st.ns].append(st)
    for ns, items in sorted(by_ns.items()):
        write_sql(idx, out, ns, items)
        dom_sql[idx.ns_domain[ns]].append((ns, items))

    stats = {}
    for dom in sorted(set(dom_units) | set(dom_services) | set(dom_sql)):
        units = dom_units.get(dom, [])
        screens = [u for u in units if u[0] in idx.screen_names]
        comps = [u for u in units if u[0] not in idx.screen_names]
        lines = [
            f"# 도메인: {dom}", "",
            f"화면 {len(screens)}개, 컴포넌트 {len(comps)}개, 서버 클래스 {len(dom_services.get(dom, []))}개, 매퍼 {len(dom_sql.get(dom, []))}개.", "",
        ]
        if screens:
            lines += ["## 화면", "", "| 화면 | 메뉴 | 클래스 | 서비스 |", "|:---|:---|---:|---:|"]
            for name, n_cls, n_svc in screens:
                menu = "; ".join(m["path"] for k in keys_by_class.get(name, []) for m in menus_by_key.get(k, [])) or "-"
                lines.append(f"| [`{name}`](screens/{name}.md) | {md_cell(menu)} | {n_cls + 1} | {n_svc} |")
            lines.append("")
        if comps:
            lines += [
                "## 컴포넌트", "", "다른 도메인 화면에서도 쓰는 클래스. 화면 파일은 여기까지만 적고 링크한다.", "",
                "| 컴포넌트 | 사용 도메인 | 클래스 | 서비스 |", "|:---|:---|---:|---:|",
            ]
            for name, n_cls, n_svc in comps:
                lines.append(f"| [`{name}`](components/{name}.md) | {', '.join(sorted(idx.used_by_domains[name]))} | {n_cls + 1} | {n_svc} |")
            lines.append("")
        if dom_services.get(dom):
            lines += ["## 서버 클래스", "", "| 클래스 | 서비스 메서드 |", "|:---|---:|"]
            for s_cls, n in dom_services[dom]:
                lines.append(f"| [`{s_cls.key}`](../{idx.service_path(s_cls)}) | {n} |")
            lines.append("")
        if dom_sql.get(dom):
            lines += ["## 매퍼", "", "| namespace | SQL 수 |", "|:---|---:|"]
            for ns, items in dom_sql[dom]:
                lines.append(f"| [`{ns}`](sql/{ns}.md) | {len(items)} |")
            lines.append("")
        orphans = []
        reached = set()
        for name, _, _ in units:
            reached |= {c.name for c in idx.closure(name)[0]}
        for items in idx.client.values():
            for c in items:
                if c.domain == dom and idx.is_vi(c) and c.name not in reached and c.services:
                    orphans.append(c)
        if orphans:
            lines += [
                "## 화면·컴포넌트에서 도달하지 않는 클래스", "",
                "메뉴에 없거나 다른 방식으로 열리는 클래스 중 서비스를 호출하는 것.", "",
                "| 클래스 | 파일 | 서비스 |", "|:---|:---|:---|",
            ]
            for c in sorted(orphans, key=lambda c: c.name):
                lines.append(f"| `{c.name}` | `{c.rel}` | {', '.join(sorted({f'`{s}`' for s, _ in c.services}))} |")
        write(out, f"{dom}/README.md", lines)
        stats[dom] = {
            "screens": len(screens),
            "components": len(comps),
            "server_classes": len(dom_services.get(dom, [])),
            "mappers": len(dom_sql.get(dom, [])),
            "sql": sum(len(i) for _, i in dom_sql.get(dom, [])),
        }
    return stats


def write_menus(idx: Index, out: Path) -> None:
    lines = ["# 메뉴 → 화면", ""]
    if idx.menus:
        lines += [
            "`sys06_menu` 기준. 클래스가 MenuOpener에 없으면 '(MenuOpener 없음)'.", "",
            "| 메뉴 | # | 사용 | 화면 |", "|:---|:---|:---|:---|",
        ]
        for m in idx.menus:
            name = idx.opener.get(m["key"], "")
            cls = idx.client_class(name)
            target = f"[`{name}`]({idx.unit_path(name)})" if cls and idx.is_vi(cls) else f"`{m['key']}` (MenuOpener 없음)"
            lines.append(f"| {md_cell(m['path'])} | {m['no']} | {m['use']} | {target} |")
    else:
        lines += ["메뉴 TSV 없이 만들어 MenuOpener 기준으로만 적는다.", "", "| 메뉴 키 | 화면 |", "|:---|:---|"]
        for key, name in sorted(idx.opener.items()):
            cls = idx.client_class(name)
            lines.append(f"| `{key}` | " + (f"[`{name}`]({idx.unit_path(name)})" if cls and idx.is_vi(cls) else f"`{name}` (파일 없음)") + " |")
    write(out, "menus.md", lines)


def write_unresolved(idx: Index, out: Path) -> tuple[int, int]:
    lines = [
        "# 정적으로 해석하지 못한 호출", "",
        "문자열을 실행 시점에 조합하는 경우. 필요하면 해당 위치를 직접 읽는다.", "",
        "## 클라이언트 서비스 호출", "", "| 클래스 | 줄 | 식 |", "|:---|---:|:---|",
    ]
    for items in sorted(idx.client.values(), key=lambda x: x[0].name):
        for c in items:
            for expr, line in c.unresolved:
                lines.append(f"| `{c.rel}` | {line} | `{md_cell(expr)}` |")
    lines += ["", "## 서버 SQL 호출", "", "| 메서드 | 줄 | 식 |", "|:---|---:|:---|"]
    for s_cls in sorted(idx.server.values(), key=lambda c: c.key):
        for m in s_cls.methods.values():
            for expr, line in m.unresolved:
                lines.append(f"| `{m.key}` | {line} | `{md_cell(expr)}` |")
    missing_service = sorted({s for s in idx.service_callers if s not in idx.service_methods and s != "getSeq"})
    lines += ["", "## 서버 메서드가 없는 서비스 키", "", "클래스·메서드 이름이 바뀌었거나 삭제된 경우.", ""]
    lines += [f"- `{s}` ← " + ", ".join(f"`{c}`" for c in sorted(idx.service_callers[s])) for s in missing_service] or ["- 없음"]
    missing_sql = sorted({sid for m in idx.service_methods.values() for sid in all_sql_ids(m) if sid not in idx.statements})
    lines += ["", "## 매퍼에 없는 SQL ID", ""]
    lines += [f"- `{s}` ← " + ", ".join(f"`{u}`" for u in sorted(idx.sql_users[s])) for s in missing_sql] or ["- 없음"]
    write(out, "unresolved.md", lines)
    return len(missing_service), len(missing_sql)


def write_readme(
    idx: Index,
    out: Path,
    src_root: Path,
    stats: dict[str, dict[str, int]],
    menus_path: Path | None,
    missing: tuple[int, int],
) -> None:
    n_client = sum(len(v) for v in idx.client.values())
    n_unres_client = sum(len(c.unresolved) for v in idx.client.values() for c in v)
    n_unres_server = sum(len(m.unresolved) for c in idx.server.values() for m in c.methods.values())
    lines = [
        "# AS-IS 소스 호출 경로 색인", "",
        "`yunhee index-src`가 생성했다. 직접 수정하지 말고 명령어를 다시 실행한다.", "",
        "## 원본", "",
        f"- 소스: `{src_root}` (파일 경로는 `{idx.app.relative_to(src_root).as_posix()}/` 기준)",
        f"- 메뉴: `{menus_path or '(없음 - MenuOpener 기준)'}`",
        f"- DB 색인: `{idx.db_rel or '(없음)'}`", "",
        "## 읽는 방법 (화면 하나 변환할 때)", "",
        "1. [menus.md](menus.md)에서 메뉴로 화면 파일(`{도메인}/screens/{화면}.md`)을 찾는다.",
        "2. 화면 파일에서 함께 쓰는 클래스, 서비스 → 서버 메서드 → SQL ID, 테이블을 본다.",
        "   다른 화면·컴포넌트(예: 전자결재 문서 편집)는 링크만 있으니 필요할 때만 연다.",
        "   UI 절의 클래스별 `#### 이벤트`·`#### 메서드`·`#### Grid Spec`·`#### 사용된 버튼들`은 `yunhee events <클래스>` 결과와 같다 (`--no-events`로 생성했으면 없음).",
        "3. 링크를 따라 필요한 것만 연다: 서버 `{도메인}/services/{클래스}.md`, SQL `{도메인}/sql/{namespace}.md`(파일·줄), 테이블은 DB 색인.",
        "4. 실제 코드는 소스 경로의 해당 파일·줄만 연다.", "",
        "## 통계", "",
        (
            f"- 클라이언트 클래스 {n_client}개, 메뉴 화면 {len(idx.screen_names) - len(idx.frame_names)}개, 프레임 {len(idx.frame_names)}개([_frame](_frame/README.md)), 컴포넌트 {len(idx.component_names)}개, "
            f"서버 서비스 메서드 {len(idx.service_methods)}개, 매퍼 SQL {len(idx.statements)}개"
        ),
        (
            f"- 해석 못 한 호출: 클라이언트 {n_unres_client}건, 서버 {n_unres_server}건, 서버 메서드 없는 서비스 키 {missing[0]}개, "
            f"매퍼에 없는 SQL ID {missing[1]}개 → [unresolved.md](unresolved.md)"
        ),
        "",
        "| 도메인 | 화면 | 컴포넌트 | 서버 클래스 | 매퍼 | SQL |",
        "|:---|---:|---:|---:|---:|---:|",
    ]
    for dom, s in sorted(stats.items()):
        lines.append(
            f"| [`{dom}`]({dom}/README.md) | {s['screens']} | {s['components']} | {s['server_classes']} | {s['mappers']} | {s['sql']} |"
        )
    lines += [
        "", "## 메뉴 TSV 만들기", "",
        "```bash",
        "psql -h localhost -U kdy987 -d asseterpdb -AtF $'\\t' -c \"",
        "WITH RECURSIVE t AS (",
        "  SELECT sys06_menu_id id, sys06_menu_nm::text path, sys06_seq::text sort FROM sys06_menu WHERE sys06_parent_id = 0",
        "  UNION ALL",
        "  SELECT m.sys06_menu_id, t.path || ' > ' || m.sys06_menu_nm, t.sort || '.' || coalesce(m.sys06_seq,'')",
        "  FROM sys06_menu m JOIN t ON m.sys06_parent_id = t.id)",
        "SELECT coalesce(m.sys06_menu_no,''), t.path, m.sys06_class_nm, coalesce(m.sys06_use_yn,'')",
        "FROM t JOIN sys06_menu m ON m.sys06_menu_id = t.id",
        "WHERE coalesce(m.sys06_class_nm,'') <> '' ORDER BY t.sort\" > docs/as-is/menus.tsv",
        "```",
    ]
    write(out, "README.md", lines)


def clean_generated(out: Path) -> tuple[bool, str]:
    """이전 출력 삭제: 안전 표식(README.md)을 확인한 후 .md와 빈 폴더만 지운다."""
    if not out.is_dir():
        return True, ""
    readme = out / "README.md"
    existing_md = list(out.glob("*.md")) + list(out.glob("*/*.md"))
    if existing_md and not readme.is_file():
        return False, f"안전 가드: '{out}' 폴더에 기존 마크다운 파일이 있으나 README.md가 없습니다. 엉뚱한 폴더 삭제 방지를 위해 중단합니다."
    if readme.is_file():
        content = readme.read_text(encoding="utf-8", errors="replace")
        if "index-src" not in content and "src-index.py" not in content and "AS-IS 소스 호출 경로 색인" not in content:
            return False, f"안전 가드: '{out}/README.md'에 AS-IS 소스 색인 생성기 표식이 없습니다. 엉뚱한 폴더 삭제 방지를 위해 중단합니다."

    for f in out.rglob("*.md"):
        f.unlink()
    for d in sorted((p for p in out.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    return True, ""


def find_app(src_root: Path) -> Path | None:
    """앱 패키지 폴더(client/와 server/를 가진 폴더): AssetERP는 myApp, OMS는 myOms"""
    def is_app(d: Path) -> bool:
        return (d / "client").is_dir() and (d / "server").is_dir()

    if is_app(src_root):
        return src_root
    java = src_root / JAVA_REL
    if java.is_dir():
        found = [d for d in sorted(java.iterdir()) if d.is_dir() and is_app(d)]
        if len(found) == 1:
            return found[0]
    # 전체 하위 2단계 탐색
    found_any = [d for d in src_root.glob("**/client") if d.is_dir() and (d.parent / "server").is_dir()]
    if len(found_any) == 1:
        return found_any[0].parent
    return None


def index_src(
    src_root: Path,
    target_dir: Path,
    menus_path: Path | None = None,
    db_index_dir: Path | None = None,
    with_events: bool = True,
    button_types_path: Path | None = None,
) -> ToolResult:
    """AS-IS 소스의 화면 → 서비스 → SQL → 테이블 호출 경로 색인을 target_dir에 생성한다.

    with_events면 화면·컴포넌트 파일의 UI 절에 클래스별 `yunhee events` 결과(이벤트·메서드·Grid Spec·버튼)를 함께 넣는다.
    """
    if not src_root.is_dir():
        return ToolResult(ok=False, error=f"AS-IS 소스 디렉터리를 찾을 수 없습니다: {src_root}")

    app = find_app(src_root)
    if not app:
        return ToolResult(
            ok=False,
            error=f"{src_root} 아래에서 client/와 server/를 모두 가진 앱 패키지를 찾을 수 없습니다.",
        )

    if menus_path and not menus_path.is_file():
        return ToolResult(ok=False, error=f"메뉴 TSV 파일이 없습니다: {menus_path}")

    target_dir.mkdir(parents=True, exist_ok=True)

    tables, functions, columns = load_db_index(db_index_dir)
    db_rel = None
    if tables and db_index_dir:
        try:
            db_rel = Path(os.path.relpath(db_index_dir.resolve(), target_dir.resolve())).as_posix()
        except ValueError:
            db_rel = None
        # 출력 폴더가 색인 폴더 밖(예: /tmp)이면 ../가 끝없이 붙으므로 절대 경로로 쓴다.
        # (화면 파일은 출력 폴더 아래 2단계라 링크에 ../../가 더 붙는다)
        if db_rel is None or db_rel.split("/").count("..") > 4:
            db_rel = db_index_dir.resolve().as_posix()

    client = parse_client(app)
    server = parse_server(app)
    statements, ns_files = parse_mappers(app, tables, functions, columns)
    idx = Index(
        app,
        client,
        server,
        statements,
        parse_menu_opener(app),
        load_menus(menus_path),
        tables,
        db_rel,
        ns_files=ns_files,
    )
    idx.with_events = with_events
    idx.button_types_path = button_types_path

    clean_ok, clean_err = clean_generated(target_dir)
    if not clean_ok:
        return ToolResult(ok=False, error=clean_err)
    stats = write_domains(idx, target_dir)
    write_menus(idx, target_dir)
    missing = write_unresolved(idx, target_dir)
    write_readme(idx, target_dir, src_root, stats, menus_path, missing)

    n_screens = len(idx.screen_names) - len(idx.frame_names)
    return ToolResult(
        ok=True,
        data={
            "target_dir": str(target_dir),
            "app_package": str(app.relative_to(src_root)),
            "client_classes_count": sum(len(v) for v in client.values()),
            "screens_count": n_screens,
            "frame_screens_count": len(idx.frame_names),
            "components_count": len(idx.component_names),
            "service_methods_count": len(idx.service_methods),
            "statements_count": len(statements),
            "domains_count": len(stats),
            "missing_service_keys_count": missing[0],
            "missing_sql_ids_count": missing[1],
            "events_classes_count": len(idx.events_cache),
            "events_errors": idx.events_errors,
        },
    )
