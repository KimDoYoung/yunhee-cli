"""TOBE 소스(React + Spring Boot/MyBatis)의 호출 체인과 `AS-IS` 주석 색인.

TSX → `api/*.ts`의 함수 → 컨트롤러 엔드포인트 → 서비스 메서드 → mapper 인터페이스 메서드 → XML 문장.
TOBE 소스에는 대응하는 ASIS 항목이 주석(`AS-IS emp.Emp00_TransInfo.selectByText`, `AS-IS selectByText L339`)으로 적혀 있어
trace-pair/diff/gap은 이 주석을 **근거**로 짝을 짓는다. 이름이 비슷하다는 이유만으로 짝짓지 않는다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from yunhee import config

SERVICE_KEY = re.compile(r"\b([a-z][a-z0-9]{1,5}\.[A-Z][A-Za-z0-9_]*\.[a-zA-Z_][A-Za-z0-9_]*)\b", re.ASCII)  # ASCII만: `selectByText의`처럼 한글 조사가 붙지 않게
HTTP_ANNOTATION = re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping(?:\(\s*(?:value\s*=\s*)?(?:\{?\s*\"([^\"]*)\"\s*\}?)?[^)]*\))?")


@dataclass
class TobeLayout:
    root: Path
    frontend: Path  # frontend/src
    api_dir: Path
    pages_dir: Path
    java_dir: Path  # backend/src/main/java
    mapper_dir: Path  # backend/src/main/resources/mapper

    @property
    def usable(self) -> bool:
        return self.pages_dir.is_dir() or self.java_dir.is_dir()


def find_layout(path: Path | None = None) -> TobeLayout:
    """`--tobe`(프로젝트 루트 또는 frontend/src)나 설정(TOBE_SRC_DIR)/작업 폴더에서 TOBE 레이아웃을 찾는다."""
    if path:
        base = Path(path)
        if not base.exists() and not base.is_absolute() and getattr(config, "TOBE_SRC_DIR", None) != config.WORK_DIR:
            cand = config.TOBE_SRC_DIR / base
            if cand.exists():
                base = cand
    else:
        base = getattr(config, "TOBE_SRC_DIR", config.WORK_DIR)
    if base.name == "src" and base.parent.name == "frontend":
        base = base.parent.parent
    elif (base / "frontend" / "src").is_dir() is False and (base / "src" / "pages").is_dir():
        base = base.parent  # frontend 폴더 자체를 준 경우
    front = base / "frontend" / "src"
    return TobeLayout(
        root=base,
        frontend=front,
        api_dir=front / "api",
        pages_dir=front / "pages",
        java_dir=base / "backend" / "src" / "main" / "java",
        mapper_dir=base / "backend" / "src" / "main" / "resources" / "mapper",
    )


def _keys(text: str) -> list[str]:
    return list(dict.fromkeys(SERVICE_KEY.findall(text)))


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _doc_above(lines: list[str], idx: int) -> str:
    """lines[idx] 바로 위의 Javadoc·주석 블록(어노테이션 줄은 건너뜀)."""
    j = idx - 1
    while j >= 0 and lines[j].strip().startswith("@"):
        j -= 1
    if j < 0:
        return ""
    if lines[j].strip().endswith("*/"):
        k = j
        while k >= 0 and "/*" not in lines[k]:
            k -= 1
        return " ".join(lines[max(k, 0) : j + 1])
    out = []
    while j >= 0 and lines[j].strip().startswith("//"):
        out.append(lines[j])
        j -= 1
    return " ".join(reversed(out))


# --- api/*.ts ----------------------------------------------------------------


@dataclass
class ApiFn:
    obj: str  # empApi
    name: str  # searchTransInfos
    verb: str  # GET
    url: str  # /api/v1/emp/trans-infos (경로 변수는 {})
    file: str
    line: int
    keys: list[str] = field(default_factory=list)  # 주석의 AS-IS 서비스 키


_API_OBJ = re.compile(r"^export const (\w+)\s*=\s*\{", re.MULTILINE)
_API_FN = re.compile(r"^\s{1,4}(\w+)\s*:\s*(?:async\s*)?\(")
_API_CALL = re.compile(r"apiClient\.(get|post|put|delete|patch)\s*(?:<[^()]*>)?\s*\(\s*([`'\"])(.*?)\2", re.DOTALL)


def normalize_url(url: str) -> str:
    url = re.sub(r"\$\{[^}]*\}", "{}", url.split("?")[0])
    url = re.sub(r"\{[^}/]*\}", "{}", url)
    url = "/" + url.strip("/")
    return url if url.startswith("/api/") else "/api" + url


def parse_api_ts(text: str, file: str) -> list[ApiFn]:
    lines = text.splitlines()
    fns: list[ApiFn] = []
    obj = ""
    for i, line in enumerate(lines):
        if m := _API_OBJ.match(line):
            obj = m.group(1)
            continue
        if not obj or not (m := _API_FN.match(line)):
            continue
        # 이 함수 본문(다음 함수 시작 전)에서 apiClient 호출들을 모두 찾는다
        end = i + 1
        while end < len(lines) and not _API_FN.match(lines[end]) and not _API_OBJ.match(lines[end]):
            end += 1
        body = "\n".join(lines[i:end])
        calls = list(_API_CALL.finditer(body))
        keys = _keys(_doc_above(lines, i))
        for call in calls:
            fns.append(ApiFn(obj, m.group(1), call.group(1).upper(), normalize_url(call.group(3)), file, i + 1, keys))
    return fns


# --- 컨트롤러 / 서비스 / mapper 인터페이스 -----------------------------------------


@dataclass
class Endpoint:
    verb: str
    path: str
    controller: str
    method: str
    file: str
    line: int
    keys: list[str] = field(default_factory=list)
    service_calls: list[tuple[str, str]] = field(default_factory=list)  # (서비스 필드명, 메서드)


def _calls(body: str, typed_fields: set[str], name_hint: str) -> list[tuple[str, str]]:
    """본문의 `필드.메서드(` 호출. 필드는 타입이 …Service/…Mapper인 것이거나 이름에 service/mapper가 들어간 것."""
    found = re.findall(r"\b([A-Za-z_]\w*)\s*\.\s*(\w+)\s*\(", body)
    return list(dict.fromkeys((f, m) for f, m in found if f in typed_fields or name_hint.lower() in f.lower()))


def _body(text: str, brace_pos: int) -> str:
    depth = 0
    for i in range(brace_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_pos : i + 1]
    return text[brace_pos:]


def parse_controller(text: str, file: str) -> list[Endpoint]:
    cls = re.search(r"\bclass\s+(\w+)", text)
    svc_fields = {n for n, t in field_types(text).items() if t.endswith("Service")}  # 타입이 …Service인 필드 (이름이 svc 같아도 잡는다)
    base = re.search(r"@RequestMapping\(\s*(?:value\s*=\s*)?\"([^\"]*)\"", text)
    prefix = base.group(1) if base else ""
    lines = text.splitlines()
    out: list[Endpoint] = []
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln) + 1)
    for i, line in enumerate(lines):
        m = HTTP_ANNOTATION.search(line)
        if not m:
            continue
        sig = re.search(r"\b(\w+)\s*\(", "\n".join(lines[i + 1 : i + 6]))
        name = None
        for j in range(i + 1, min(i + 8, len(lines))):
            mm = re.search(r"public\s+[\w<>\[\], ?.]+?\s+(\w+)\s*\(", lines[j])
            if mm:
                name = mm.group(1)
                body_from = offsets[j]
                break
        if name is None and sig:
            name, body_from = sig.group(1), offsets[i]
        if name is None:
            continue
        brace = text.find("{", body_from)
        body = _body(text, brace) if brace >= 0 else ""
        path = (prefix.rstrip("/") + "/" + (m.group(2) or "").strip("/")).rstrip("/") if (m.group(2) or prefix) else "/"
        out.append(
            Endpoint(
                m.group(1).upper(), re.sub(r"\{[^}/]*\}", "{}", path or "/"), cls.group(1) if cls else Path(file).stem,
                name, file, i + 1, _keys(_doc_above(lines, i)),
                _calls(body, svc_fields, "ervice"),
            )
        )
    return out


@dataclass
class ServiceMethod:
    service: str
    name: str
    file: str
    line: int
    mapper_calls: list[tuple[str, str]] = field(default_factory=list)  # (mapper 필드명, 메서드)
    keys: list[str] = field(default_factory=list)


def parse_service(text: str, file: str) -> list[ServiceMethod]:
    cls = re.search(r"\bclass\s+(\w+)", text)
    mapper_fields = {n for n, t in field_types(text).items() if t.endswith("Mapper")}
    lines = text.splitlines()
    out: list[ServiceMethod] = []
    for m in re.finditer(r"^[ \t]{2,8}(?:public|protected)\s+(?!class)[\w<>\[\], ?.]+?\s+(\w+)\s*\([^)]*\)[^{;]*\{", text, re.MULTILINE):
        line = _line_of(text, m.start())
        body = _body(text, m.end() - 1)
        out.append(
            ServiceMethod(
                cls.group(1) if cls else Path(file).stem, m.group(1), file, line,
                _calls(body, mapper_fields, "apper"),
                _keys(_doc_above(lines, line - 1)),
            )
        )
    return out


def field_types(text: str) -> dict[str, str]:
    """`private final EmpTransInfoMapper empTransInfoMapper;` → {empTransInfoMapper: EmpTransInfoMapper}"""
    return {name: typ for typ, name in re.findall(r"\b(?:private|protected)?\s*(?:final\s+)?(\w+(?:Mapper|Service))\s+(\w+)\s*;", text)}


# --- mapper XML 문장의 AS-IS 주석 ----------------------------------------------------

_ASIS_SQL_ID = re.compile(r"\b([a-z]{2,6}\d{2}_[a-z0-9_]+|dbConfig)\.([A-Za-z]\w*)\b", re.ASCII)  # emp00_trans_info.selectByText
_STMT = re.compile(r"<(select|insert|update|delete)\b[^>]*\bid=\"([^\"]+)\"", re.IGNORECASE)
_TABLE_NAME_RE = re.compile(r"\b(?:from|join|update|into)\s+([a-z]{2,5}\d{2}_[a-z0-9_]+)\b")


@dataclass
class MapperStatement:
    namespace: str
    id: str
    file: str
    line: int
    kind: str
    as_is_ids: list[str] = field(default_factory=list)  # ASIS statement id (`ns.sid`) 또는 sid
    comment: str = ""
    tables: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.id}"


def parse_mapper_xml(text: str, file: str) -> tuple[list[MapperStatement], str, list[str]]:
    """(문장들, 헤더 주석의 ASIS mapper 이름, 헤더가 말하는 ASIS statement id들)."""
    ns = (re.search(r"<mapper\s+namespace=\"([^\"]+)\"", text) or [None, ""])[1]
    header = ""
    hm = re.search(r"<!--(.*?)-->\s*<mapper", text, re.DOTALL) or re.search(r"<!--(.*?AS-IS.*?)-->", text, re.DOTALL)
    if hm:
        header = hm.group(1)
    asis_ns = (re.search(r"AS-IS(?:\([^)]*\))?\s+(?:[\w/]+/)?(\w+)\.xml", header) or [None, ""])[1]
    header_ids = list(dict.fromkeys(re.findall(r"\b([A-Za-z]\w*)\s*\(L\d+\)", header)))
    stmts: list[MapperStatement] = []
    for m in _STMT.finditer(text):
        before = text[: m.start()].rstrip()
        comment = ""
        if before.endswith("-->"):
            start = before.rfind("<!--")
            comment = before[start:] if start >= 0 else ""
        ids: list[str] = []
        if "AS-IS" in comment:  # AS-IS를 말하지 않는 주석(컬럼 설명 등)의 `t.col` 같은 표기는 SQL id가 아니다
            for full in _ASIS_SQL_ID.findall(comment):
                ids.append(f"{full[0]}.{full[1]}")
            for bare in re.findall(r"AS-IS\s+(?:[\w/]*/)?([a-z][A-Za-z0-9_]*)\s+L\d+", comment):
                if asis_ns and "." not in bare:
                    ids.append(f"{asis_ns}.{bare}")
        kind = m.group(1).lower()
        end_tag = f"</{kind}>"
        pos = text.lower().find(end_tag, m.end())
        body = text[m.start() : pos + len(end_tag)] if pos != -1 else text[m.start() : m.start() + 2000]
        stmt_tables = list(dict.fromkeys(_TABLE_NAME_RE.findall(body.lower())))
        stmts.append(
            MapperStatement(
                ns,
                m.group(2),
                file,
                _line_of(text, m.start()),
                kind,
                list(dict.fromkeys(ids)),
                re.sub(r"\s+", " ", comment)[:200],
                tables=stmt_tables,
            )
        )
    return stmts, asis_ns, header_ids


# --- TSX -------------------------------------------------------------------------


from typing import Self


class GridCol(tuple):
    """(field, label) 2-튜플 하위 호환 + col_type, field, label, width 속성 보존."""

    col_type: str
    field: str
    label: str
    width: int

    def __new__(cls, field: str, label: str, col_type: str = "text", width: int = 0) -> Self:
        obj = super().__new__(cls, (field, label))
        obj.col_type = col_type
        obj.field = field
        obj.label = label
        obj.width = width
        return obj


@dataclass
class TsxInfo:
    name: str
    file: str
    header_menu_nos: list[str]
    as_is_file: str  # 헤더의 `AS-IS: myApp/client/vi/emp/X.java`
    api_calls: list[tuple[str, str]]  # (xxxApi, fn)
    grid_cols: list[GridCol]  # (field, label) 튜플 호환 + .col_type, .width
    buttons: list[str]
    impl_events: set[str]
    skipped_events: set[str]
    api_call_lines: dict[tuple[str, str], list[int]] = field(default_factory=dict)


_GB = re.compile(r"\b\w*gb\w*\.(\w+)\(\s*(['\"])(.*?)\2\s*,\s*([^,]+?)\s*,\s*(['\"])(.*?)\5")


def _extract_grid_cols(text: str) -> list[GridCol]:
    cols: list[GridCol] = []
    seen: set[tuple[str, str]] = set()
    for m in _GB.finditer(text):
        col_type = m.group(1)
        field_name = m.group(3)
        w_str = m.group(4).strip()
        width = int(w_str) if w_str.isdigit() else 0
        label = m.group(6)
        key = (field_name, label)
        if key not in seen:
            seen.add(key)
            cols.append(GridCol(field_name, label, col_type=col_type, width=width))
    # ColDef 직접 객체 리터럴: { field: '...', headerName: '...' }
    if not cols:
        for m_col in re.finditer(r"\{\s*(?:[^{}]*?\bfield\s*:\s*['\"]([^'\"]+)['\"][^{}]*?\bheaderName\s*:\s*['\"]([^'\"]+)['\"]|[^{}]*?\bheaderName\s*:\s*['\"]([^'\"]+)['\"][^{}]*?\bfield\s*:\s*['\"]([^'\"]+)['\"])", text):
            fld = m_col.group(1) or m_col.group(4)
            lbl = m_col.group(2) or m_col.group(3)
            key = (fld, lbl)
            if key not in seen:
                seen.add(key)
                cols.append(GridCol(fld, lbl, col_type="text", width=0))
    return cols


def _extract_buttons_from_tsx(text: str) -> list[str]:
    btns: list[str] = []

    # 1. JSX <Button ...>...</Button> 태그 파싱
    for m in re.finditer(r"<Button\b", text):
        start = m.start()
        i = m.end()
        n = len(text)
        brace = 0
        quote = None
        tag_open_end = -1
        while i < n:
            ch = text[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            else:
                if ch in ('"', "'", "`"):
                    quote = ch
                elif ch == "{":
                    brace += 1
                elif ch == "}":
                    brace = max(0, brace - 1)
                elif brace == 0 and ch == ">":
                    tag_open_end = i + 1
                    break
            i += 1
        if tag_open_end != -1:
            close_idx = text.find("</Button>", tag_open_end)
            if close_idx != -1 and close_idx - tag_open_end < 500:
                inner = text[tag_open_end:close_idx]
                clean = re.sub(r"<[^>]+>", "", inner).strip()
                clean = re.sub(r"\{[^}]*\}", "", clean).strip()
                if clean:
                    btns.append(clean)
                else:
                    attrs = text[start:tag_open_end]
                    t_m = re.search(r"\b(?:title|label)\s*=\s*['\"]([^'\"]+)['\"]", attrs)
                    if t_m:
                        btns.append(t_m.group(1).strip())

    # 2. SearchBar onSearch -> 조회
    if re.search(r"<SearchBar\b[^>]*?\bonSearch\b", text) and "조회" not in btns:
        btns.insert(0, "조회")

    # 3. ModalEditGrid editButton -> 수정
    m_edit = re.search(r"<ModalEditGrid\b[^>]*?\beditButton(?:=\{?['\"]?([^'\"}>]+)['\"]?\}?)?", text)
    if m_edit:
        eb_val = m_edit.group(1)
        lbl = "수정" if (not eb_val or eb_val in ("true", "")) else eb_val.strip()
        if lbl not in btns:
            btns.append(lbl)

    # 4. 이벤트 주석의 버튼 대괄호 라벨 보조 ([E4] retrieveButton[조회].Select 또는 [E3] createRoot[루트매뉴 등록].Select)
    for b in re.findall(r"\[E\d+\]\s*[A-Za-z0-9_]*\[([^\]]+)\]", text):
        clean_b = b.strip()
        if (
            clean_b
            and not clean_b.startswith(("http", "L", "선택", "Enter", "data", "arg"))
            and len(clean_b) <= 20
            and clean_b not in btns
        ):
            btns.append(clean_b)

    return list(dict.fromkeys(btns))


def event_ids(text: str) -> tuple[set[str], set[str]]:
    """TSX의 `[E5]`, `[E5]~[E9]`, `[E1 생략]`, `[E1]~[E3 생략]` 표기에서 (구현, 생략) 이벤트 집합 (수정사항 021 A-1과 같은 규칙)."""
    impl: set[str] = set()
    skip: set[str] = set()
    for m in re.finditer(r"\[E(\d+)\]\s*[~∼-]\s*\[E(\d+)( 생략)?\]|\[E(\d+)( 생략)?\]", text):
        if m.group(1):
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                (skip if m.group(3) else impl).update(f"E{n}" for n in range(a, b + 1))
        else:
            (skip if m.group(5) else impl).add(f"E{m.group(4)}")
    return impl, skip - impl


def parse_tsx(text: str, file: str) -> TsxInfo:
    head = text[:3000]
    menu = re.findall(r"\[(\d{3,4})\]", head.split("*/")[0] if "*/" in head else head)
    as_is = (re.search(r"AS-IS[^:\n]*:\s*(\S+\.java)", head) or [None, ""])[1]
    impl, skip = event_ids(text)

    api_calls: list[tuple[str, str]] = []
    api_call_lines: dict[tuple[str, str], list[int]] = defaultdict(list)
    for line_no, line in enumerate(text.splitlines(), start=1):
        code_part = line.split("//")[0]
        for m in re.finditer(r"\b(\w+Api)\s*\.\s*(\w+)\b", code_part):
            key = (m.group(1), m.group(2))
            if key not in api_calls:
                api_calls.append(key)
            api_call_lines[key].append(line_no)

    return TsxInfo(
        name=Path(file).stem,
        file=file,
        header_menu_nos=menu,
        as_is_file=as_is,
        api_calls=api_calls,
        grid_cols=_extract_grid_cols(text),
        buttons=_extract_buttons_from_tsx(text),
        impl_events=impl,
        skipped_events=skip,
        api_call_lines=dict(api_call_lines),
    )


# --- 전체 색인 -------------------------------------------------------------------


@dataclass
class TobeIndex:
    layout: TobeLayout
    tsx: dict[str, TsxInfo] = field(default_factory=dict)  # 클래스명 → TSX
    api_fns: dict[tuple[str, str], ApiFn] = field(default_factory=dict)
    api_fns_multi: dict[tuple[str, str], list[ApiFn]] = field(default_factory=dict)
    endpoints: list[Endpoint] = field(default_factory=list)
    services: dict[tuple[str, str], ServiceMethod] = field(default_factory=dict)  # (서비스 클래스, 메서드)
    service_fields: dict[str, dict[str, str]] = field(default_factory=dict)  # 컨트롤러 클래스 → {필드: 타입}
    mapper_fields: dict[str, dict[str, str]] = field(default_factory=dict)  # 서비스 클래스 → {필드: 타입}
    statements: dict[str, MapperStatement] = field(default_factory=dict)  # key → 문장
    mapper_files: dict[str, str] = field(default_factory=dict)  # namespace → xml 파일
    mapper_asis_ns: dict[str, str] = field(default_factory=dict)  # TOBE namespace → ASIS mapper 이름

    def endpoints_for_key(self, key: str) -> list[Endpoint]:
        return [e for e in self.endpoints if key in e.keys]

    def endpoint_of(self, fn: ApiFn) -> list[Endpoint]:
        fns = self.api_fns_multi.get((fn.obj, fn.name), [fn])
        matched: list[Endpoint] = []
        for f in fns:
            for e in self.endpoints:
                if e.verb == f.verb and e.path == f.url and e not in matched:
                    matched.append(e)
        return matched

    def endpoints_of_fn(self, target: ApiFn | tuple[str, str]) -> list[Endpoint]:
        if isinstance(target, ApiFn):
            fns = self.api_fns_multi.get((target.obj, target.name), [target])
        else:
            fns = self.api_fns_multi.get(target, [])
            if not fns and target in self.api_fns:
                fns = [self.api_fns[target]]
        eps: list[Endpoint] = []
        for fn in fns:
            for ep in self.endpoints:
                if ep.verb == fn.verb and ep.path == fn.url and ep not in eps:
                    eps.append(ep)
        return eps

    def statements_of(self, ep: Endpoint) -> list[MapperStatement]:
        """엔드포인트 → 서비스 → mapper 호출을 따라간 XML 문장들."""
        found: list[MapperStatement] = []
        ctrl_fields = self.service_fields.get(ep.controller, {})
        for field_name, method in ep.service_calls:
            svc_type = ctrl_fields.get(field_name)
            svc = self.services.get((svc_type, method)) if svc_type else None
            if svc is None:
                continue
            map_fields = self.mapper_fields.get(svc.service, {})
            for mfield, mmethod in svc.mapper_calls:
                mtype = map_fields.get(mfield)
                for st in self.statements.values():
                    if st.id == mmethod and st.namespace.endswith("." + (mtype or "\0")):
                        found.append(st)
        return list({st.key: st for st in found}.values())

    def rel(self, path: str | Path) -> str:
        try:
            return str(Path(path).relative_to(self.layout.root))
        except ValueError:
            return str(path)


@lru_cache(maxsize=2)
def build_index(root: str) -> TobeIndex:
    layout = find_layout(Path(root))
    idx = TobeIndex(layout)
    if layout.pages_dir.is_dir():
        for p in sorted(layout.pages_dir.rglob("*.tsx")):
            info = parse_tsx(p.read_text(encoding="utf-8", errors="replace"), str(p))
            idx.tsx.setdefault(info.name, info)
    if layout.api_dir.is_dir():
        for p in sorted(layout.api_dir.glob("*.ts")):
            for fn in parse_api_ts(p.read_text(encoding="utf-8", errors="replace"), str(p)):
                idx.api_fns_multi.setdefault((fn.obj, fn.name), []).append(fn)
                if (fn.obj, fn.name) not in idx.api_fns:
                    idx.api_fns[(fn.obj, fn.name)] = fn
    if layout.java_dir.is_dir():
        for p in sorted(layout.java_dir.rglob("*.java")):
            text = p.read_text(encoding="utf-8", errors="replace")
            if p.name.endswith("Controller.java"):
                idx.endpoints += parse_controller(text, str(p))
                idx.service_fields[p.stem] = field_types(text)
            elif p.name.endswith("Service.java"):
                for sm in parse_service(text, str(p)):
                    idx.services[(sm.service, sm.name)] = sm
                idx.mapper_fields[p.stem] = field_types(text)
    if layout.mapper_dir.is_dir():
        for p in sorted(layout.mapper_dir.glob("*.xml")):
            stmts, asis_ns, _ = parse_mapper_xml(p.read_text(encoding="utf-8", errors="replace"), str(p))
            for st in stmts:
                idx.statements[st.key] = st
                idx.mapper_files[st.namespace] = str(p)
                idx.mapper_asis_ns[st.namespace] = asis_ns
    return idx
