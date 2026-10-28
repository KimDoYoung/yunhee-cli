"""trace-branch: 조건 지점 전체 목록.

- mapper id: `<if test>`, `<when test>`, `<otherwise>`, `<foreach>`, `<where>/<trim>`(`<include>` 조각 안까지), SQL의 `CASE WHEN`
- 화면·클래스: 이벤트 조건(`[Enter]`, `[선택>0]`), Java의 if / else if / switch / throw, 버튼·필드 활성·표시 조건, 도달 불가 이벤트
- TOBE(TSX): `disabled`·`readOnly`·`hidden`, `&&`·삼항 조건부 렌더링, if 문

조건식은 소스에 적힌 그대로 보여 주고 해석(참/거짓 판정)은 하지 않는다. 이름 모를 동적 값은 판단하지 않고 원문을 낸다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    TraceContext,
    find_class_doc,
    resolve_screen,
    wants_asis,
    wants_tobe,
)
from yunhee.tools.trace.screen import ScreenDoc, parse_screen_doc

MAX_COND_CHARS = 140
DIALECT = re.compile(r"isTibero|isPostgreSql")
_UI_STATE = re.compile(r"(?P<w>[\w.()]+?)\s*\.\s*set(?P<kind>Enabled|Visible|ReadOnly|Editable|Hidden)\s*\((?P<arg>[^;]*)\)\s*;")


@dataclass
class Cond:
    line: int
    kind: str  # if / else if / switch / throw / when / otherwise / foreach / case-when ...
    text: str
    scope: str = ""  # 메서드 이름·include 출처
    file: str = ""  # 근거 파일 (mapper는 <include> 조각이 있는 파일일 수 있다)


def _short(text: str, limit: int = MAX_COND_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# mapper
# ---------------------------------------------------------------------------

_BRANCH_TAGS = {"if", "when", "otherwise", "foreach", "where", "trim", "set"}  # <choose>는 <when>/<otherwise>로 충분하다


def _offset_of_line(raw: str, line: int) -> int:
    pos = 0
    for _ in range(max(line - 1, 0)):
        nl = raw.find("\n", pos)
        if nl < 0:
            break
        pos = nl + 1
    return pos


def _mapper_conditions(st: Any, statements: dict[str, Any], seen: set[str], out: list[Cond], depth: int = 0) -> None:
    """statement(와 `<include>` 조각)의 분기 태그를 문서 순서로 모은다."""
    from yunhee.tools.as_is.mybatis_render import Node, find_target_statement

    if st.key in seen:
        return
    seen = seen | {st.key}
    cursor = [_offset_of_line(st.raw, st.line)]
    origin = "" if depth == 0 else f"include {st.key} → {st.rel}"

    def line_of(snippet: str) -> int:
        pos = st.raw.find(snippet, cursor[0])
        if pos < 0:
            return st.line
        cursor[0] = pos
        return st.raw.count("\n", 0, pos) + 1

    def walk(node: Any) -> None:
        if isinstance(node, str):
            return
        tag = node.tag
        if tag == "include":
            target = find_target_statement(node.attrs.get("refid", ""), st.ns, statements)
            if target is not None:
                _mapper_conditions(target, statements, seen, out, depth + 1)
            else:
                out.append(Cond(st.line, "include", f"refid={node.attrs.get('refid', '?')} (조각을 찾지 못함)", origin, str(st.rel)))
        elif tag in _BRANCH_TAGS and not (tag in ("where", "trim", "set") and not node.attrs):
            # <where>/<trim>/<set>은 속성이 없으면 구문 정리용이라 조건으로 보지 않는다
            test = node.attrs.get("test")
            if test is not None:
                ln, text = line_of(f'test="{test}"'), test
            else:
                ln, text = line_of(f"<{tag}"), " ".join(f'{k}="{v}"' for k, v in node.attrs.items())
            out.append(Cond(ln, tag, _short(text), origin, str(st.rel)))
        for child in getattr(node, "children", []):
            if isinstance(child, Node):
                walk(child)

    walk(st.node)


def _mapper_result(key: str, st: Any, statements: dict[str, Any], res: TraceResult) -> None:
    from yunhee.tools.sql_parse import parse_statement

    conds: list[Cond] = []
    _mapper_conditions(st, statements, set(), conds)
    where = f"{st.rel}:{st.line}"
    res.facts.append(f"statement {key} ({where}, {st.kind})")
    dialect = [c for c in conds if DIALECT.search(c.text)]
    plain = [c for c in conds if c not in dialect]
    if plain:
        lines = [f"  - L{c.line} <{c.kind}{' test' if c.kind in ('if', 'when') else ''}> {c.text}" + (f"  ({c.scope})" if c.scope else "") for c in plain]
        res.facts.append(f"동적 SQL 분기({len(plain)}):\n" + "\n".join(lines))
    else:
        res.facts.append("동적 SQL 분기: 없음 (<if>/<choose> 없이 고정된 SQL)")
    if dialect:
        res.facts.append(
            f"DB 방언 분기({len(dialect)}) — PostgreSQL/Tibero 선택:\n"
            + "\n".join(f"  - L{c.line} <{c.kind}> {c.text}" for c in dialect)
        )
    parsed = parse_statement(key, statements)
    if parsed.ok:
        cases = parsed.data.cases
        if cases:
            res.facts.append(f"CASE WHEN({len(cases)}):\n" + "\n".join(f"  - {_short(c)}" for c in cases))
        for u in parsed.data.unresolved:
            res.unresolved.append(u)
    else:
        res.unresolved.append(f"SQL 해석 실패: {parsed.error}")
    for c in conds:
        res.evidence.append(f"{c.file or st.rel}:{c.line} <{c.kind}>")


# ---------------------------------------------------------------------------
# Java (ASIS 클라이언트·서버)
# ---------------------------------------------------------------------------


def _blank_comments(text: str) -> str:
    """주석을 공백으로 지운다 (줄 수와 문자열 리터럴은 보존)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _mask_strings(text: str) -> str:
    """문자열·문자 리터럴의 내용을 공백으로 가린다 (길이와 줄 수 보존). 키워드 검색이 리터럴 안을 보지 않게 한다."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(c + re.sub(r"[^\n]", " ", text[i + 1 : j]) + (text[j] if j < n else ""))
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _balanced(text: str, open_pos: int) -> tuple[str, int]:
    """open_pos의 `(`와 짝이 맞는 `)`까지의 안쪽 문자열과 끝 위치. 닫히지 않으면 ("", -1)."""
    depth, i, n = 0, open_pos, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_pos + 1 : i], i
        i += 1
    return "", -1


_JAVA_KEYWORD = re.compile(r"(?P<else>\belse\s+)?\b(?P<kw>if|switch)\s*\(|\bthrow\s+new\s+(?P<exc>\w+)\s*\(")


def scan_java_conditions(text: str) -> list[Cond]:
    """if / else if / switch / throw 지점을 줄 번호와 함께 모은다. 여러 줄에 걸친 조건도 괄호 짝으로 읽는다."""
    clean = _blank_comments(text)
    masked = _mask_strings(clean)  # 키워드 검색용. 표시할 조건식은 원문(clean)에서 자른다
    conds: list[Cond] = []
    for m in _JAVA_KEYWORD.finditer(masked):
        line = clean.count("\n", 0, m.start()) + 1
        open_pos = masked.find("(", m.start())
        _, end = _balanced(masked, open_pos)
        if end < 0:
            conds.append(Cond(line, "?", "(괄호가 닫히지 않음)"))
            continue
        inner = clean[open_pos + 1 : end]
        if m.group("exc"):
            conds.append(Cond(line, "throw", f"{m.group('exc')}({_short(inner)})"))
        else:
            kind = "else if" if m.group("else") else m.group("kw")
            conds.append(Cond(line, kind, _short(inner)))
    return conds


def scan_ui_state(text: str) -> list[Cond]:
    """setEnabled / setVisible / setReadOnly 호출. 인자가 리터럴(true/false)이면 고정 상태, 식이면 조건이다."""
    clean = _blank_comments(text)
    out: list[Cond] = []
    for m in _UI_STATE.finditer(clean):
        arg = _short(m.group("arg"))
        line = clean.count("\n", 0, m.start()) + 1
        kind = m.group("kind")
        literal = arg in ("true", "false")
        out.append(Cond(line, f"set{kind}", f"{m.group('w').strip()} ← {arg}" + ("" if not literal else "  (고정값)")))
    return out


def _class_source(ctx: TraceContext, cls: str, doc: ScreenDoc | None) -> Path | None:
    from yunhee.tools.as_is.src_indexer import find_app

    rel = None
    if ctx.index_data:
        rel = ctx.index_data.get("client_classes", {}).get(cls, {}).get("file")
    if rel is None and doc is not None:
        ui = doc.ui.get(cls)
        rel = (ui.java if ui and ui.java else None) or (doc.file if cls == doc.name else None)
    if not rel or not ctx.src_root:
        return None
    app = find_app(Path(ctx.src_root))
    for base in ([app] if app else []) + [Path(ctx.src_root)]:
        cand = base / rel
        if cand.is_file():
            return cand
    return None


def _method_at(ui: Any, line: int) -> str:
    if ui is None:
        return ""
    for m in ui.methods:
        if m.start <= line <= m.end:
            return f"{m.name}()"
    for e in ui.event_rows:  # 생성자는 메서드 표가 아니라 화면 열림 이벤트(E0)의 줄 범위로 알 수 있다
        if "생성자" in e.desc and any(a <= line <= b for a, b in e.ranges):
            return "생성자"
    return ""


def _class_result(target: str, ctx: TraceContext, res: TraceResult) -> str | None:
    name = resolve_screen(target, ctx)
    res.params["resolved"] = name
    doc_path = find_class_doc(ctx, name)
    doc = parse_screen_doc(name, doc_path.read_text(encoding="utf-8", errors="replace")) if doc_path else None
    ui = doc.ui.get(name) if doc else None
    if doc is None:
        res.unresolved.append(f"색인 문서가 없어 이벤트 조건은 건너뜀 ({name}은 화면이 아니라 하위 클래스일 수 있음)")

    if ui is not None:
        guards = [e for e in ui.event_rows if e.guard]
        if guards:
            res.facts.append(
                f"이벤트 조건({len(guards)}) — 이 조건일 때만 핸들러가 실행됨:\n"
                + "\n".join(f"  - [{e.id}] {e.desc} → 조건 [{e.guard}]" for e in guards)
            )
        dead = [e for e in ui.event_rows if e.unreachable]
        if dead:
            res.facts.append(
                f"도달 불가 이벤트({len(dead)}):\n" + "\n".join(f"  - [{e.id}] {e.desc} {e.handlers.split('⚠')[-1].strip()}" for e in dead)
            )

    src = _class_source(ctx, name, doc)
    if src is None:
        res.unresolved.append(f"{name}의 Java 소스를 찾지 못해 if/switch/throw를 건너뜀 (YUNHEE_ASIS_SRC_DIR)")
        return name
    text = src.read_text(encoding="utf-8", errors="replace")
    rel = src.name
    conds = scan_java_conditions(text)
    by_method: dict[str, list[Cond]] = {}
    for c in conds:
        by_method.setdefault(_method_at(ui, c.line) or "(메서드 구분 없음)", []).append(c)
    if conds:
        body = []
        for method, items in by_method.items():
            body.append(f"  {method}:")
            body += [f"    - L{c.line} {c.kind} ({c.text})" if c.kind != "throw" else f"    - L{c.line} throw {c.text}" for c in items]
        res.facts.append(f"소스 분기({len(conds)}) — if / else if / switch / throw:\n" + "\n".join(body))
    else:
        res.facts.append("소스 분기: 없음 (if/switch/throw가 없음)")
    for c in conds:
        res.evidence.append(f"{rel}:{c.line} {c.kind}")
        if c.kind == "?":
            res.unresolved.append(f"{rel}:{c.line} 조건을 끝까지 읽지 못함")
    ui_state = scan_ui_state(text)
    if ui_state:
        dynamic = [c for c in ui_state if "고정값" not in c.text]
        res.facts.append(
            f"활성·표시 조건({len(ui_state)}, 식으로 정해지는 것 {len(dynamic)}):\n"
            + "\n".join(f"  - L{c.line} {c.kind}: {c.text}" for c in ui_state)
        )
        res.evidence += [f"{rel}:{c.line} {c.kind}" for c in ui_state]
    return name


# ---------------------------------------------------------------------------
# TOBE (TSX)
# ---------------------------------------------------------------------------

_TSX_PATTERNS = [
    ("disabled", re.compile(r"\bdisabled=\{([^}]+)\}")),
    ("readOnly", re.compile(r"\breadOnly=\{([^}]+)\}")),
    ("hidden", re.compile(r"\b(?:hidden|visible)=\{([^}]+)\}")),
    ("조건부 렌더링 &&", re.compile(r"\{\s*([^{}?]+?)\s*&&\s*[(<]")),
    ("조건부 렌더링 ?:", re.compile(r"\{\s*([^{}?]+?)\s*\?\s*[(<]")),
]


def scan_tsx_conditions(text: str) -> list[Cond]:
    conds: list[Cond] = []
    for ln, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("import ", "//", "*", "/*")):
            continue
        for kind, rx in _TSX_PATTERNS:
            for m in rx.finditer(line):
                conds.append(Cond(ln, kind, _short(m.group(1))))
        if m_if := re.match(r"\s*(?:\}\s*else\s+)?if\s*\(", line):
            inner, end = _balanced(line, m_if.end() - 1)
            if end >= 0:
                conds.append(Cond(ln, "if", _short(inner)))
    return conds


def _tobe_result(name: str, tobe_dir: Path | None, res: TraceResult) -> None:
    from yunhee.tools.trace.screen import _find_tobe

    path = _find_tobe(name, tobe_dir)
    if path is None:
        res.unresolved.append(f"TOBE 화면 {name}.tsx를 찾지 못함 (--tobe로 frontend/src 경로 지정)")
        return
    conds = scan_tsx_conditions(path.read_text(encoding="utf-8", errors="replace"))
    if conds:
        res.facts.append(
            f"TOBE 조건({len(conds)}) — {path.name}:\n" + "\n".join(f"  - L{c.line} {c.kind}: {c.text}" for c in conds)
        )
    else:
        res.facts.append(f"TOBE 조건: 없음 ({path.name})")
    res.evidence += [f"TOBE {path.name}:{c.line} {c.kind}" for c in conds]


# ---------------------------------------------------------------------------


def _find_statement(target: str, ctx: TraceContext) -> tuple[str, Any, dict[str, Any]] | None:
    """target이 mapper statement(`ns.id`)면 (key, statement, 전체 statements)."""
    if "." not in target or not ctx.src_root or not Path(ctx.src_root).is_dir():
        return None
    from yunhee.tools.as_is.mybatis_render import get_all_statements

    statements = get_all_statements(Path(ctx.src_root))
    st = statements.get(target)
    return (st.key, st, statements) if st is not None and st.kind != "sql" else None


def trace_branch(target: str, ctx: TraceContext, tobe_dir: Path | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-branch",
        description="조건 지점 전체: 이벤트 조건, if/switch/throw, 활성·표시 조건, <if test>, CASE WHEN, TSX 조건부 렌더링",
        side=ctx.side,
        params={"target": target},
    )
    res.unresolved += ctx.unresolved
    name = target
    if wants_asis(ctx.side):
        found = _find_statement(target, ctx)
        if found is not None:
            key, st, statements = found
            res.params["kind"] = "mapper"
            _mapper_result(key, st, statements, res)
        elif ctx.has_index:
            res.params["kind"] = "class"
            try:
                name = _class_result(target, ctx, res) or target
            except TargetNotFoundError:
                if wants_tobe(ctx.side):
                    res.unresolved.append(f"ASIS 색인에서 '{target}'를 찾지 못함 — TOBE 쪽만 조회")
                else:
                    raise
        elif "." not in target:
            pass  # 색인 없음은 ctx.unresolved에 이미 있다
        else:
            res.unresolved.append(f"mapper statement '{target}'를 찾지 못함 (ASIS 소스 또는 id 확인)")
    if wants_tobe(ctx.side) and "." not in target:
        _tobe_result(name if name != target else target, tobe_dir, res)
    elif wants_tobe(ctx.side) and res.params.get("kind") != "mapper":
        res.unresolved.append("TOBE mapper의 분기는 아직 지원하지 않음 (trace-diff --branch 단계)")
    return res
