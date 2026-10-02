"""AS-IS GXT 소스에서 위젯/화면 이벤트 및 메서드를 결정적(정규식/파서)으로 정밀 추출하는 모듈."""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from yunhee.config import ASIS_SRC_DIR, WORK_DIR
from yunhee.tools.as_is import find_as_is_dir
from yunhee.tools.as_is.button_type_map import BUTTON_TYPE_MAP, load_button_types
from yunhee.tools.as_is.src_indexer import (
    UI_NEW_RE,
    UI_STR_RE,
    UI_WIDGET_CLS_RE,
    find_methods,
    line_of,
    paren_end,
    split_args,
    strip_java,
)

# 명시적 핸들러 등록 패턴: widget.addXxxHandler(...) 또는 widget.addXxxListener(...)
HANDLER_CALL_RE = re.compile(
    r"(?<![\w.])((?:this\.)?[\w.()]+?)\.add(\w+?)(?:Handler|Listener)\s*\("
)

# SearchBarBuilder 암묵적 이벤트 패턴
SEARCHBAR_RETRIEVE_RE = re.compile(r"(?<![\w.])(\w+)\.addRetrieveButton\s*\(")
SEARCHBAR_UPDATE_RE = re.compile(r"(?<![\w.])(\w+)\.addUpdateButton\s*\(([^)]*)\)")
SEARCHBAR_INSERT_RE = re.compile(r"(?<![\w.])(\w+)\.addInsertButton\s*\(([^)]*)\)")
SEARCHBAR_DELETE_RE = re.compile(r"(?<![\w.])(\w+)\.addDeleteButton\s*\(")
SEARCHBAR_ENTER_RE = re.compile(
    r"(?<![\w.])(\w+)\.add(?:TextField|DateField)\s*\(([^)]+)\)"
)

# GridBuilder 암묵적 이벤트 패턴
GRID_DBLCLICK_RE = re.compile(r"(?<![\w.])(\w+)\.setDoubleClickEdit\s*\(")


@dataclass
class EventInfo:
    id: str  # E0, E1, E2, ...
    source: str  # 화면 열림 (생성자 L63-107), retrieveButton[조회], messageBox 등
    event_type: str  # Open, Select, SelectionChanged, DialogHide 등
    line: int  # 시작 줄 번호
    end_line: int  # 끝 줄 번호
    action: str  # retrieve() 또는 인라인 L56-60
    kind: str  # lifecycle | explicit | implicit
    target_class: str  # 소속 클래스명
    condition: str = ""  # [Enter], [선택>0], [YES], [arg0 != null] 등
    parent_id: str | None = None  # 중첩 종속 이벤트의 부모 E-id
    sub_events: list["EventInfo"] = field(default_factory=list)
    raw_snippet: str = ""  # 본문 요약 발췌

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sub_events"] = [e.to_dict() for e in self.sub_events]
        return d


@dataclass
class MethodInfo:
    name: str  # public retrieve() 또는 private deleteCompany()
    line_start: int  # 시작 줄 번호
    line_end: int  # 끝 줄 번호
    visibility: str  # public | private | protected | package
    callers: list[str]  # ["생성자", "E1", "E2"]
    work_desc: str  # 서비스, 팝업, 다이얼로그, 초기값 등 상세 동작
    category: str  # 업무 | UI구성 (이벤트 절로 대체) | UI구성 (그리드 절로 대체) | 유틸 (변환 불필요)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ButtonInfo:
    label: str  # 버튼 제목 문자열 (예: "조회", "등록", "삭제")
    button_type: str  # search, register, delete, save, etc. (미정의 시 unknown)
    handler: str  # onClick 핸들러 식별자 (예: retrieve, insert, () => edit(null))
    line: int = 0  # 소스 코드 내 줄 번호

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "type": self.button_type,
            "onClick": self.handler,
            "jsx": self.jsx,
            "line": self.line,
        }

    @property
    def jsx(self) -> str:
        return f'<Button type="{self.button_type}" onClick={{{self.handler}}}>{self.label}</Button>'


def get_source_label(file_path: Path, total_lines: int) -> str:
    """출력용 원본 경로 문자열 (예: 'Asset-ERP myApp/client/vi/sys/Sys01_Tab_Company.java (316줄)')"""
    parts = file_path.parts
    proj = ""
    for known in ("Asset-ERP", "Asset-OMS", "AssetERP", "AssetOMS"):
        if known in parts:
            proj = known
            break

    rel_str = ""
    for idx, part in enumerate(parts):
        if part in ("myApp", "myOms") or (part == "client" and idx + 1 < len(parts) and parts[idx + 1] == "vi"):
            rel_str = "/".join(parts[idx:])
            break
    if not rel_str:
        rel_str = file_path.name

    if proj and not rel_str.startswith(proj):
        return f"{proj} {rel_str} ({total_lines}줄)"
    return f"{rel_str} ({total_lines}줄)"


def _clean_recv(recv: str) -> str:
    """수신자 표현식 정리: this. 및 getSelectionModel() 제거"""
    recv = recv.strip().removeprefix("this.")
    recv = re.sub(r"\.getSelectionModel\(\)", "", recv)
    return recv.strip()


def extract_if_condition(body: str) -> str:
    """if (...) 조건식을 괄호 깊이를 고려하여 온전히 추출"""
    m = re.search(r"\bif\s*\(", body)
    if not m:
        return ""
    open_paren = m.end() - 1
    close_paren = paren_end(body, open_paren)
    return body[open_paren + 1:close_paren].strip()


def detect_condition(event_name: str, body: str) -> str:
    """핸들러 본문에서 실행 조건 추출 ([Enter], [선택>0], [YES], [arg0 != null] 등)"""
    # 1. 다이얼로그 버튼 조건
    if re.search(r'(?:case\s+YES|PredefinedButton\.YES|"YES"\.equals)', body):
        return "[YES]"
    if re.search(r'(?:case\s+NO|PredefinedButton\.NO|"NO"\.equals)', body):
        return "[NO]"
    if re.search(r'(?:case\s+OK|PredefinedButton\.OK|"OK"\.equals)', body):
        return "[OK]"

    # 2. 키보드 이벤트 조건
    ev_lower = event_name.lower()
    if "key" in ev_lower:
        if re.search(r"\b(?:13|KEY_ENTER|KeyCodes\.KEY_ENTER)\b", body):
            return "[Enter]"
        if re.search(r"\b(?:27|KEY_ESCAPE|KeyCodes\.KEY_ESCAPE)\b", body):
            return "[Esc]"

    # 3. if 조건문 원문 보존 추출
    cond_raw = extract_if_condition(body)
    if cond_raw:
        if re.search(r"\.size\(\)\s*>\s*0|\.isEmpty\(\)\s*==\s*false|!\s*[\w.()]+\.isEmpty\(\)", cond_raw):
            return "[선택>0]"
        cond_clean = re.sub(r"\s+", " ", cond_raw).strip()
        if len(cond_clean) <= 25:
            return f"[{cond_clean}]"

    return ""


def _summarize_inline_body(body: str, line_start: int, line_end: int) -> str:
    """메서드 호출이 없는 인라인 핸들러 본문 요약"""
    cases = re.findall(r"case\s+([A-Za-z0-9_]+)\s*:\s*([^;]+;)", body)
    if cases:
        case_strs = [f"{c[0]}: {c[1].strip()}" for c in cases[:2]]
        return f"인라인 L{line_start}-{line_end} ({', '.join(case_strs)})"

    msg_m = re.search(r"(?:SimpleMessage|ConfirmBox|Window|AlertMessageBox)\.\w+\s*\(([^)]*)\)", body)
    if msg_m:
        arg = msg_m.group(1).split(",")[0].strip()
        return f"인라인 L{line_start}-{line_end} (메시지: {arg[:30]})"

    stmts = [
        s.strip() for s in body.split(";")
        if s.strip() and not s.strip().startswith(("@Override", "public void", "{", "}"))
    ]
    if stmts:
        first = re.sub(r"\s+", " ", stmts[0])
        if len(first) > 40:
            first = first[:37] + "…"
        return f"인라인 L{line_start}-{line_end} ({first})"

    return f"인라인 L{line_start}-{line_end}"


def extract_events_and_methods(
    text: str,
    file_path: Path | str = "",
) -> tuple[list[EventInfo], list[MethodInfo]]:
    """단일 Java 소스 텍스트에서 이벤트 목록과 메서드 분석 목록을 추출한다."""
    p = Path(file_path) if file_path else Path("Unknown.java")
    class_match = re.search(r"\bpublic\s+(?:final\s+)?class\s+(\w+)", text)
    class_name = class_match.group(1) if class_match else (p.stem or "Unknown")

    code, bare = strip_java(text)
    raw_methods = find_methods(bare)
    meth_names = {m[0] for m in raw_methods} | {"hide", "close", "show"}

    # 1. 탭페이지 등록 수집: tabPanel.add(new Sys01_TabPage_Info01(), "관리정보")
    tab_pages: list[str] = []
    for tm in re.finditer(r"tabPanel\.add\s*\(\s*new\s+(\w+)\s*\([^)]*\)\s*,\s*([^)]+)\)", code):
        cls_name = tm.group(1)
        lbls = UI_STR_RE.findall(tm.group(2))
        lbl_str = f"[{lbls[0]}]" if lbls else ""
        tab_pages.append(f"{cls_name}{lbl_str}")

    # 2. 위젯 생성 분석 및 라벨 수집
    widgets: dict[str, tuple[str, str]] = {}
    for m in UI_NEW_RE.finditer(code):
        var, klass = m.group(1), m.group(2)
        close = paren_end(code, m.end() - 1)
        args = code[m.end():close]
        widgets.setdefault(var, (klass, args))

    widget_labels: dict[str, str] = {}
    for var, (klass, args) in widgets.items():
        clean_var = var.removeprefix("this.").strip()
        s = UI_STR_RE.findall(args)
        if s and s[0].strip() and (
            klass.endswith("Button")
            or "ButtonBar" in klass
            or "Button" in klass
            or UI_WIDGET_CLS_RE.search(klass)
        ):
            widget_labels[clean_var] = s[0].strip()

    # FieldLabel 연결: new FieldLabel(field, "권한명")
    for m in re.finditer(r"new\s+FieldLabel\s*\(\s*([^,]+),\s*([^)]+)\)", code):
        fld_expr = m.group(1).replace("this.", "").strip()
        s = UI_STR_RE.findall(m.group(2))
        if s:
            widget_labels[fld_expr] = s[0].strip()

    # useYnBox.setBoxLabel(...) 등
    for m in re.finditer(r"(\w+)\.set(?:BoxLabel|Text|HTML)\s*\(([^)]+)\)", code):
        var_name = m.group(1).replace("this.", "").strip()
        s = UI_STR_RE.findall(m.group(2))
        if s and var_name not in widget_labels:
            widget_labels[var_name] = s[0].strip()

    def label(var: str) -> str:
        clean = _clean_recv(var)
        if clean in widget_labels:
            return f"{clean}[{widget_labels[clean]}]"
        return clean

    events_raw: list[dict[str, Any]] = []
    handler_spans: list[tuple[int, int]] = []
    ctor = next((m for m in raw_methods if m[0] == class_name), None)

    # 3. 명시적 핸들러 탐지 (widget.addXxxHandler(...))
    for m in HANDLER_CALL_RE.finditer(code):
        recv_raw = m.group(1)
        event_name = m.group(2)
        open_paren = m.end() - 1
        close_paren = paren_end(code, open_paren)
        body = code[m.end():close_paren]
        body_bare = bare[m.end():close_paren]

        start_line = line_of(code, m.start())
        end_line = line_of(code, close_paren)
        handler_spans.append((m.start(), close_paren))

        cond = detect_condition(event_name, body)

        # 본문에서 호출하는 내부 메서드 추출
        calls: list[str] = []
        for c in re.finditer(r"(?<![\w])((?:\w+\.)?)(\w+)\s*\(", body_bare):
            recv_call, fn = c.group(1), c.group(2)
            if recv_call in ("", "this.") and fn in meth_names:
                calls.append(f"{fn}()")

        if calls:
            action_desc = ", ".join(dict.fromkeys(calls))
        else:
            svcs = [s.group(1) for s in re.finditer(r'"([a-z]\w*\.[A-Z]\w*\.\w+)"', body)]
            # 파라미터: companyId=선택행 등
            prms = []
            for pm in re.finditer(r'\.addParam\s*\(\s*"([^"]+)"\s*,\s*([^)]+)\)', body):
                p_key = pm.group(1)
                p_val = pm.group(2)
                if "getSelectedItem" in p_val or "getSelected" in p_val:
                    prms.append(f"{p_key}=선택행")
                else:
                    prms.append(p_key)
            prm_str = f"({', '.join(prms)})" if prms else ""

            msgs = []
            for mm in re.finditer(r'new\s+(?:SimpleMessage|HtmlMessageBox|ConfirmBox|MessageBox)\s*\(([^)]+)\)', body):
                for a in split_args(mm.group(1)):
                    s = UI_STR_RE.findall(a)
                    if s and not s[0].startswith(("sys.", "dcr.", "ast.", "emp.", "com.")):
                        msgs.append(s[0].strip())
            act_parts = []
            if svcs:
                act_parts.append(f"서비스 {', '.join(dict.fromkeys(svcs))}{prm_str}")
            if msgs:
                m_str = " / ".join(dict.fromkeys(msgs))
                if len(m_str) > 30:
                    m_str = m_str[:27] + "…"
                act_parts.append(f'메시지 "{m_str}"')
            if act_parts:
                action_desc = ", ".join(act_parts)
            else:
                action_desc = _summarize_inline_body(body, start_line, end_line)

        snippet = re.sub(r"\s+", " ", body[:60]).strip()
        events_raw.append({
            "source": label(recv_raw),
            "event_type": event_name,
            "condition": cond,
            "line": start_line,
            "end_line": end_line,
            "action": action_desc,
            "kind": "explicit",
            "target_class": class_name,
            "raw_snippet": snippet,
        })

    # 4. 암묵적 이벤트 탐지 (SearchBarBuilder)
    for m in SEARCHBAR_RETRIEVE_RE.finditer(code):
        line = line_of(code, m.start())
        events_raw.append({
            "source": f"{m.group(1)}[조회]",
            "event_type": "Retrieve",
            "condition": "",
            "line": line,
            "end_line": line,
            "action": "retrieve()",
            "kind": "implicit",
            "target_class": class_name,
            "raw_snippet": m.group(0),
        })

    for m in SEARCHBAR_UPDATE_RE.finditer(code):
        line = line_of(code, m.start())
        args = split_args(m.group(2))
        lbl = UI_STR_RE.findall(args[0])[0] if args and UI_STR_RE.findall(args[0]) else "저장"
        events_raw.append({
            "source": f"{m.group(1)}[{lbl}]",
            "event_type": "Update",
            "condition": "",
            "line": line,
            "end_line": line,
            "action": "update()",
            "kind": "implicit",
            "target_class": class_name,
            "raw_snippet": m.group(0),
        })

    for m in SEARCHBAR_INSERT_RE.finditer(code):
        line = line_of(code, m.start())
        args = split_args(m.group(2))
        lbl = UI_STR_RE.findall(args[0])[0] if args and UI_STR_RE.findall(args[0]) else "등록"
        events_raw.append({
            "source": f"{m.group(1)}[{lbl}]",
            "event_type": "Insert",
            "condition": "",
            "line": line,
            "end_line": line,
            "action": "insertRow()",
            "kind": "implicit",
            "target_class": class_name,
            "raw_snippet": m.group(0),
        })

    for m in SEARCHBAR_DELETE_RE.finditer(code):
        line = line_of(code, m.start())
        events_raw.append({
            "source": f"{m.group(1)}[삭제]",
            "event_type": "Delete",
            "condition": "",
            "line": line,
            "end_line": line,
            "action": "deleteRow()",
            "kind": "implicit",
            "target_class": class_name,
            "raw_snippet": m.group(0),
        })

    for m in SEARCHBAR_ENTER_RE.finditer(code):
        args = split_args(m.group(2))
        if args and any("true" in a.lower() or "useenterkey" in a.lower() for a in args):
            line = line_of(code, m.start())
            fld = args[0].replace("this.", "").strip()
            lbl = UI_STR_RE.findall(args[1])[0] if len(args) > 1 and UI_STR_RE.findall(args[1]) else fld
            events_raw.append({
                "source": f"{fld}[{lbl}]",
                "event_type": "EnterKey",
                "condition": "[Enter]",
                "line": line,
                "end_line": line,
                "action": "retrieve()",
                "kind": "implicit",
                "target_class": class_name,
                "raw_snippet": m.group(0),
            })

    # 5. 암묵적 이벤트 탐지 (GridBuilder)
    for m in GRID_DBLCLICK_RE.finditer(code):
        line = line_of(code, m.start())
        events_raw.append({
            "source": label(m.group(1)),
            "event_type": "DoubleClickEdit",
            "condition": "",
            "line": line,
            "end_line": line,
            "action": "더블클릭 편집 활성화",
            "kind": "implicit",
            "target_class": class_name,
            "raw_snippet": m.group(0),
        })

    # 6. [E0] 생성자 분석 (화면 열림, 핸들러 등록 스팬 제외)
    ev_list: list[EventInfo] = []
    ctor_bare = ""
    if ctor:
        _, c_decl, c_start, c_end, _, _ = ctor
        c_start_line = line_of(code, c_decl)
        c_end_line = line_of(code, c_end)

        c_chars = list(bare[c_start:c_end])
        for hs, he in handler_spans:
            s_rel = max(0, hs - c_start)
            e_rel = min(len(c_chars), he - c_start)
            if s_rel < e_rel:
                for idx in range(s_rel, e_rel):
                    c_chars[idx] = " "
        ctor_bare = "".join(c_chars)

        ctor_calls = []
        for c in re.finditer(r"(?<![\w.])(?:this\.)?(\w+)\s*\(", ctor_bare):
            fn = c.group(1)
            if fn in meth_names and fn != class_name and not fn.startswith("setHtml"):
                ctor_calls.append(f"{fn}()")
        action = ", ".join(dict.fromkeys(ctor_calls)) if ctor_calls else "초기화"
        ev_list.append(EventInfo(
            id="E0",
            source=f"화면 열림 (생성자 L{c_start_line}-{c_end_line})",
            event_type="Open",
            condition="",
            line=c_start_line,
            end_line=c_end_line,
            action=action,
            kind="lifecycle",
            target_class=class_name,
            raw_snippet="",
        ))

    # 7. ID 부여: E1..En
    events_raw.sort(key=lambda x: (x["line"], x["source"]))
    for idx, e in enumerate(events_raw, start=1):
        ev_list.append(EventInfo(
            id=f"E{idx}",
            source=e["source"],
            event_type=e["event_type"],
            condition=e["condition"],
            line=e["line"],
            end_line=e["end_line"],
            action=e["action"],
            kind=e["kind"],
            target_class=class_name,
            raw_snippet=e["raw_snippet"],
        ))

    # 8. 중첩 트리 구조 (종속 이벤트 연결: DialogHide, 확인창 등)
    NESTABLE_EVENTS = {"DialogHide", "Hide", "Close", "Callback"}
    meth_spans = {
        m[0]: (line_of(code, m[1]), line_of(code, m[3]))
        for m in raw_methods if m[0] != class_name
    }
    meth_callers: dict[str, list[EventInfo]] = {m: [] for m in meth_spans}
    for ev in ev_list:
        for m_name in meth_spans:
            if f"{m_name}()" in ev.action:
                meth_callers[m_name].append(ev)

    for ev in ev_list:
        if ev.id == "E0" or ev.event_type not in NESTABLE_EVENTS:
            continue
        for m_name, (m_s, m_e) in meth_spans.items():
            if any(k in m_name.lower() for k in ("setting", "init", "layout", "build", "make", "create")):
                continue
            if m_s <= ev.line <= m_e:
                callers = [c for c in meth_callers.get(m_name, []) if c.id != "E0"]
                if callers:
                    parent = callers[0]
                    if parent.id != ev.id:
                        ev.parent_id = parent.id
                        parent.sub_events.append(ev)
                break

    # 9. 메서드 분석
    method_infos: list[MethodInfo] = []
    first_meth_pos = min(m[1] for m in raw_methods) if raw_methods else len(code)
    field_code = code[:first_meth_pos]

    for m in raw_methods:
        name, decl, start, end, is_pub, _ = m
        if name == class_name:
            continue
        m_start_line = line_of(code, decl)
        m_end_line = line_of(code, end)
        m_body = code[start:end]

        # 1) 호출처 (callers)
        callers = []
        # 생성자 자체에서 호출하는지 확인 -> "생성자"
        if ctor_bare and re.search(rf"(?<![\w.])(?:this\.)?{name}\s*\(", ctor_bare):
            callers.append("생성자")

        # 각 이벤트 핸들러에서 직접 호출하는지 확인 (E0 제외)
        for ev in ev_list:
            if ev.id != "E0" and f"{name}()" in ev.action:
                callers.append(ev.id)

        # 다른 일반 메서드(핸들러 제외 본문)에서 호출하는지 확인
        for other_m in raw_methods:
            if other_m[0] in (name, class_name):
                continue
            o_start, o_end = other_m[2], other_m[3]
            o_chars = list(bare[o_start:o_end])
            for hs, he in handler_spans:
                s_rel = max(0, hs - o_start)
                e_rel = min(len(o_chars), he - o_start)
                if s_rel < e_rel:
                    for idx in range(s_rel, e_rel):
                        o_chars[idx] = " "
            o_bare = "".join(o_chars)
            if re.search(rf"(?<![\w.])(?:this\.)?{name}\s*\(", o_bare):
                callers.append(other_m[0])

        if re.search(rf"(?<![\w.])(?:this\.)?{name}\s*\(", field_code):
            callers.append("필드 초기화")

        callers = list(dict.fromkeys(callers))
        if not callers:
            callers = ["공개 메서드"] if is_pub else ["미사용 후보"]

        # 2) 구분 (category)
        if name in ("settings", "initUI", "initLayout") or re.search(r"^(?:make|init|setup)Layout$", name):
            category = "UI구성 (이벤트 절로 대체)"
        elif name in ("buildGrid", "initGrid", "createGrid") or re.search(r"^(?:build|init|create)Grid$", name):
            category = "UI구성 (그리드 절로 대체)"
        elif name.startswith("setHtml") or "SafeHtml" in code[decl:start]:
            category = "유틸 (변환 불필요)"
        else:
            category = "업무"

        # 3) 하는 일 (work_desc)
        work_parts = []
        svcs = [s.group(1) for s in re.finditer(r'"([a-z]\w*\.[A-Z]\w*\.\w+)"', m_body)]
        prms = [p.group(1) for p in re.finditer(r'\.addParam\s*\(\s*"([^"]+)"', m_body)]

        # 팝업 / 조회창
        popups = re.findall(r'new\s+([A-Za-z0-9_]+(?:Edit|Lookup|Popup|Window)[A-Za-z0-9_]*)\s*\(', m_body)
        for pop in popups:
            if "Lookup" in pop:
                cb_desc = ""
                if "unmask" in m_body:
                    cb_desc = " → 콜백: unmask"
                work_parts.append(f"조회창 {pop} 열기{cb_desc}")
            else:
                work_parts.append(f"팝업 {pop} 열기")

        sub_evs = [
            ev for ev in ev_list
            if ev.parent_id and any(f"{name}()" in p_ev.action for p_ev in ev_list if p_ev.id == ev.parent_id)
        ]

        # 미선택 alert 메시지 추출
        has_alert = "SimpleMessage" in m_body and ("getSelectedItem" in m_body and "null" in m_body)
        alert_msg = ""
        if has_alert:
            sm_m = re.search(r'new\s+SimpleMessage\s*\(\s*"([^"]+)"\s*\)', m_body)
            if sm_m:
                alert_msg = f' "{sm_m.group(1)}"'

        has_confirm = "ConfirmBox" in m_body or "HtmlMessageBox" in m_body or "messageBox" in m_body

        if has_alert and has_confirm and sub_evs:
            work_parts.append(f"미선택 시 alert{alert_msg} → 확인창 {sub_evs[0].id}")
        elif has_confirm and sub_evs:
            work_parts.append(f"ConfirmBox → {sub_evs[0].id}")
        elif has_confirm:
            work_parts.append("확인창 표시")
        elif has_alert:
            work_parts.append(f"미선택 시 alert{alert_msg}")

        # 서비스 호출
        if svcs and not (has_confirm and sub_evs):
            prm_str = f"({', '.join(prms)})" if prms else ""
            if "GridDeleteData" in m_body:
                tgt = "(체크된 행 목록)" if ("getSelectedItems" in m_body or "checkedList" in m_body) else ""
                work_parts.append(f"GridDeleteData {', '.join(svcs)}{tgt}")
            elif "GridRetrieveData" in m_body:
                # 실제 코드에 건수 표시 로직(txtTotalRow, setTotal, totalRow)이 있을 때만 표시
                has_count = any(k in m_body for k in ("txtTotalRow", "setTotal", "totalRow", "count"))
                cnt_desc = ", 건수 표시" if has_count else ""
                work_parts.append(f"서비스 {', '.join(svcs)}{prm_str}{cnt_desc}")
            else:
                work_parts.append(f"서비스 {', '.join(svcs)}{prm_str}")

        # 탭페이지 retrieve
        if "InterfaceTabPage" in m_body or "selectedPage.retrieve" in m_body:
            prm_desc = f"({', '.join(prms)})" if prms else ""
            tab_desc = f" (탭: {', '.join(tab_pages)})" if tab_pages else ""
            work_parts.append(f"선택 회사로 탭페이지 retrieve{prm_desc}{tab_desc}")

        # 초기값 설정 (settings 등)
        inits = []
        for set_m in re.finditer(r"(\w+)\.setValue\s*\(([^)]+)\)", m_body):
            var = set_m.group(1).removeprefix("this.").strip()
            val = set_m.group(2).strip()
            lbl = widget_labels.get(var, "")
            lbl_str = f'("{lbl}")' if lbl else ""
            inits.append(f"{var}={val}{lbl_str}")
        if inits and category.startswith("UI구성"):
            work_parts.append(f"이벤트 연결, 초기값: {', '.join(inits)}")
        elif category == "UI구성 (그리드 절로 대체)":
            work_parts.append("그리드 컬럼")
        elif category == "UI구성 (이벤트 절로 대체)":
            work_parts.append("이벤트 연결")

        if "LabelHtml" in m_body or "ColorLabelToolItem.setHtml" in m_body or name.startswith("setHtml"):
            work_parts.append("LabelHtml 래퍼")

        desc = ", ".join(dict.fromkeys(work_parts)) if work_parts else "상태 처리"

        # 가시성(public, private, protected, package) 판별
        decl_tokens = bare[max(0, decl - 40):decl].split()
        vis = "package"
        for tok in reversed(decl_tokens):
            if tok in ("public", "private", "protected"):
                vis = tok
                break
        if vis == "package" and is_pub:
            vis = "public"

        disp_name = f"{vis} {name}()"
        method_infos.append(MethodInfo(
            name=disp_name,
            line_start=m_start_line,
            line_end=m_end_line,
            visibility=vis,
            callers=callers,
            work_desc=desc,
            category=category,
        ))

    # 정렬: 업무 -> UI구성 -> 유틸
    cat_order = {
        "업무": 1,
        "UI구성 (이벤트 절로 대체)": 2,
        "UI구성 (그리드 절로 대체)": 3,
        "UI구성": 4,
        "유틸 (변환 불필요)": 5,
        "유틸": 6,
    }
    method_infos.sort(key=lambda m: (cat_order.get(m.category, 99), m.line_start))

    return ev_list, method_infos


KNOWN_GB_OPS = {
    "addText": "gb.text",
    "addTextCenter": "gb.textCenter",
    "addTextRight": "gb.textRight",
    "addTextArea": "gb.textArea",
    "addTextStatus": "gb.textStatus",
    "addLong": "gb.long",
    "addLongCenter": "gb.longCenter",
    "addLongColor": "gb.longColor",
    "addDouble": "gb.double",
    "addDoubleCenter": "gb.doubleCenter",
    "addDoubleColor": "gb.doubleColor",
    "addDate": "gb.date",
    "addDateMonth": "gb.dateMonth",
    "addDateTime": "gb.dateTime",
    "addBoolean": "gb.boolean",
    "addBooleanYn": "gb.booleanYn",
    "addBooleanYn2": "gb.booleanYn2",
    "addHeaderGroupMap": "gb.group",
}


def to_camel_case(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def col_to_tobe_prop(col: str, table_prefix: str = "") -> str:
    if table_prefix and col.startswith(table_prefix):
        col = col[len(table_prefix):]
    else:
        col = re.sub(r"^[a-z]+\d*_", "", col)
    return to_camel_case(col)


_MAPPER_CACHE: dict[str, tuple[dict[str, str], str, str]] = {}


def find_mapper_for_model(model_name: str, roots: list[Path]) -> tuple[dict[str, str], str, str]:
    """AS-IS MyBatis 매퍼 XML을 찾아 model의 resultMap 속성→컬럼 매핑을 반환한다."""
    if not model_name:
        return {}, "", ""
    if model_name in _MAPPER_CACHE:
        return _MAPPER_CACHE[model_name]

    for root in roots:
        if not root or not root.is_dir():
            continue
        for xml_file in root.glob("**/mapper/*.xml"):
            try:
                xml_text = xml_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if model_name not in xml_text:
                continue
            rm = re.search(
                rf'<resultMap\s+[^>]*type="[^"]*{re.escape(model_name)}"[^>]*>(.*?)</resultMap>',
                xml_text,
                re.DOTALL,
            )
            if not rm:
                continue
            body = rm.group(1)
            prop_to_col: dict[str, str] = {}
            for c, p in re.findall(r'<(?:id|result)\s+[^>]*column="([^"]+)"[^>]*property="([^"]+)"', body):
                prop_to_col[p] = c
            for p, c in re.findall(r'<(?:id|result)\s+[^>]*property="([^"]+)"[^>]*column="([^"]+)"', body):
                prop_to_col[p] = c

            ns_m = re.search(r'<mapper\s+namespace="([^"]+)"', xml_text)
            ns = ns_m.group(1) if ns_m else ""
            tbl_m = re.search(r"\bfrom\s+([a-z0-9_]+)", xml_text, re.IGNORECASE)
            tbl = tbl_m.group(1).lower() if tbl_m else ns
            res = (prop_to_col, ns, tbl)
            _MAPPER_CACHE[model_name] = res
            return res

    _MAPPER_CACHE[model_name] = ({}, "", "")
    return {}, "", ""


_TABLE_COLS_CACHE: dict[str, set[str] | None] = {}


def find_table_columns(table_name: str) -> set[str] | None:
    """DBML 색인에서 대상 테이블의 컬럼 집합을 조회한다."""
    if not table_name:
        return None
    if table_name in _TABLE_COLS_CACHE:
        return _TABLE_COLS_CACHE[table_name]

    # 1. docs/as-is/db/tables/*.md 탐색
    cand_dirs = [
        find_as_is_dir("db") / "tables",
        WORK_DIR / "docs" / "as-is" / "db" / "tables",
        Path("/home/kdy987/work/framework-sprt/docs/as-is/db/tables"),
    ]
    for c_dir in cand_dirs:
        if not c_dir.is_dir():
            continue
        dom = table_name[:3] if len(table_name) >= 3 else ""
        dom_file = c_dir / f"{dom}.md"
        files_to_check = [dom_file] if dom_file.is_file() else list(c_dir.glob("*.md"))
        for f in files_to_check:
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(rf'Table\s+(?:"[^"]+"\.)?"{re.escape(table_name)}"\s*\{{([^}}]+)\}}', text, re.IGNORECASE)
            if not m:
                m = re.search(rf"Table\s+(?:[^\s.]+\.)?{re.escape(table_name)}\s*\{{([^}}]+)\}}", text, re.IGNORECASE)
            if m:
                cols = set(re.findall(r'^\s*"([a-z0-9_]+)"', m.group(1), re.MULTILINE))
                if cols:
                    _TABLE_COLS_CACHE[table_name] = cols
                    return cols

    # 2. dbml 마크다운 파일 탐색
    cand_dbmls = [
        *list(find_as_is_dir().glob("*-dbml.md")),
        *list(WORK_DIR.glob(".yunhee/*-dbml.md")),
        Path("/home/kdy987/work/framework-sprt/.yunhee/asseterp-dbml.md"),
    ]
    for dbml in cand_dbmls:
        if not dbml.is_file():
            continue
        try:
            text = dbml.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(rf'Table\s+(?:"[^"]+"\.)?"{re.escape(table_name)}"\s*\{{([^}}]+)\}}', text, re.IGNORECASE)
        if not m:
            m = re.search(rf"Table\s+(?:[^\s.]+\.)?{re.escape(table_name)}\s*\{{([^}}]+)\}}", text, re.IGNORECASE)
        if m:
            cols = set(re.findall(r'^\s*"([a-z0-9_]+)"', m.group(1), re.MULTILINE))
            if cols:
                _TABLE_COLS_CACHE[table_name] = cols
                return cols

    _TABLE_COLS_CACHE[table_name] = None
    return None


def extract_grid_spec(text: str, file_path: Path | None = None) -> str | None:
    """AS-IS GXT 소스에서 GridBuilder 컬럼 명세를 TOBE React 스타일의 buildGrid 함수로 정밀 추출한다."""
    no_comm, bare = strip_java(text)
    methods = find_methods(bare)

    roots: list[Path] = []
    if file_path:
        for parent in file_path.parents:
            cand = parent / "src" / "main" / "java"
            if cand.is_dir():
                roots.append(cand)
            cand_srv = parent / "server"
            if cand_srv.is_dir():
                roots.append(cand_srv)
            if (parent / "application").is_dir():
                roots.append(parent / "application" / "src" / "main" / "java")
    if ASIS_SRC_DIR and ASIS_SRC_DIR.is_dir():
        cand = ASIS_SRC_DIR / "application" / "src" / "main" / "java"
        roots.append(cand if cand.is_dir() else ASIS_SRC_DIR)
    roots.append(WORK_DIR)
    dedup_roots: list[Path] = []
    for r in roots:
        if r.is_dir() and r not in dedup_roots:
            dedup_roots.append(r)

    cls_model = ""
    cls_mod_m = re.search(r"GridBuilder<(\w+)>", text) or re.search(r"(\w+?)Properties\b", text)
    if cls_mod_m:
        cand_cls = cls_mod_m.group(1)
        cls_model = cand_cls if cand_cls.endswith("Model") else f"{cand_cls}Model"

    grid_specs: list[str] = []

    for name, decl, start, end, is_pub, params in methods:
        body_bare = bare[start:end]
        has_gb = "GridBuilder" in body_bare or "gridBuilder" in body_bare or "builder.add" in body_bare or "gb.add" in body_bare
        has_grid_name = "buildgrid" in name.lower() or "grid" in name.lower()
        if not (has_gb or has_grid_name):
            continue

        builder_vars = set(re.findall(r"GridBuilder(?:<[^>]*>)?\s+(\w+)\s*=", body_bare))
        if not builder_vars:
            builder_vars = {"gridBuilder", "builder", "gb"}

        builder_alt = "|".join(re.escape(v) for v in builder_vars)
        add_calls_re = re.compile(rf"(?<![\w.])(?:{builder_alt})\.(add\w+)\s*\(")
        matches = list(add_calls_re.finditer(body_bare))
        if not matches:
            continue

        meth_mod_m = re.search(r"GridBuilder<(\w+)>", text[start:end]) or re.search(r"(\w+?)Properties\b", text[start:end])
        if meth_mod_m:
            cand_m = meth_mod_m.group(1)
            model_name = cand_m if cand_m.endswith("Model") else f"{cand_m}Model"
        else:
            model_name = cls_model

        prop_to_col, _ns, table_name = find_mapper_for_model(model_name, dedup_roots)
        table_cols = find_table_columns(table_name) if table_name else None

        tbl_pfx_m = re.match(r"^([a-z]+\d*)", table_name)
        tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""

        grid_lines: list[str] = [f"const {name} = () => ["]

        for m in matches:
            op = m.group(1)
            call_start = start + m.start()

            if no_comm[call_start:call_start + 10].strip() == "":
                continue

            line_num = line_of(text, call_start)
            p_close = paren_end(body_bare, m.end() - 1)
            raw_args = body_bare[m.end():p_close]
            args = split_args(raw_args)
            if not args:
                continue

            if op not in KNOWN_GB_OPS:
                grid_lines.append(f"  // ⚠ 대응 없음 (GridBuilder L{line_num}) {op}")
                continue

            prop_m = re.search(r"\.(\w+)\s*\(\s*\)", args[0])
            prop_name = prop_m.group(1) if prop_m else re.sub(r"[^\w]", "", args[0])

            width = args[1].strip() if len(args) > 1 else "100"

            arg_text = text[start + m.end():start + p_close]
            lbl_m = re.search(r'"([^"]*)"', arg_text)
            label = lbl_m.group(1) if lbl_m else (args[2].strip().strip('"').strip("'") if len(args) > 2 else "")
            clean_label = label.replace("'", "\\'")

            editor_opt = ""
            for arg in args[3:]:
                if "TextField" in arg:
                    editor_opt = ", { editor: 'text' }"
                    break
                elif any(k in arg for k in ("NumberField", "LongField", "DoubleField")):
                    editor_opt = ", { editor: 'number' }"
                    break
                elif any(k in arg for k in ("DateField", "MyDateField")):
                    editor_opt = ", { editor: 'date' }"
                    break
                elif "TextArea" in arg:
                    editor_opt = ", { editor: 'largeText' }"
                    break
                elif "ComboBox" in arg:
                    editor_opt = ", { editor: 'select' }"
                    break

            col = prop_to_col.get(prop_name, "")
            tobe_prop = col_to_tobe_prop(col, tbl_prefix) if col else prop_name

            if table_cols is not None:
                chk_col = col
                if not chk_col:
                    snake_prop = re.sub(r"(?<!^)(?=[A-Z])", "_", prop_name).lower()
                    chk_col = f"{tbl_prefix}{snake_prop}"
                if chk_col and chk_col not in table_cols:
                    grid_lines.append(f'  // ⚠DB없음 L{line_num} {prop_name} {width} "{label}" ({chk_col} 컬럼 없음)')
                    continue

            gb_func = KNOWN_GB_OPS[op]
            grid_lines.append(f"  {gb_func}('{tobe_prop}', {width}, '{clean_label}'{editor_opt}),  // L{line_num}")

        grid_lines.append("];")
        if len(grid_lines) > 2:
            grid_specs.append("\n".join(grid_lines))

    if not grid_specs:
        return None
    return "\n\n".join(grid_specs)


def extract_events(text: str, file_name: str = "") -> list[EventInfo]:
    """기존 호환용: 이벤트 목록만 반환"""
    ev_list, _ = extract_events_and_methods(text, file_name)
    return ev_list


def extract_buttons(
    text: str,
    events: list[EventInfo] | None = None,
    file_path: Path | str = "",
    button_types_path: Path | str | None = None,
) -> list[ButtonInfo]:
    """AS-IS GXT 소스에서 사용된 버튼들을 추출하고 TOBE Button 규격(type, onClick, label)으로 매핑한다."""
    p = Path(file_path) if file_path else Path("Unknown.java")
    code, bare = strip_java(text)
    btn_map = load_button_types(button_types_path) if button_types_path else BUTTON_TYPE_MAP

    if events is None:
        events, _ = extract_events_and_methods(text, file_path=p)

    # 1. 컨테이너에 add된 순서 수집 (화면 UI 배치 순서)
    container_order: list[str] = []
    for m in re.finditer(r"(?:buttonBar|getButtonBar\(\)|searchBar)\.add\s*\(\s*([\w.]+)\s*\)", code):
        v = m.group(1).replace("this.", "").strip()
        if v not in container_order:
            container_order.append(v)

    # 2. 버튼 위젯 변수 수집
    btn_vars: dict[str, dict[str, Any]] = {}
    for m in UI_NEW_RE.finditer(code):
        var, klass = m.group(1).replace("this.", "").strip(), m.group(2)
        if (
            klass in ("ColorButtonBar", "ColorButtonBottom", "OmsButton", "TextButton", "Button")
            or klass.endswith("Button")
        ) and klass not in ("ButtonBar", "HeaderButtonBar"):
            close = bare.find(")", m.end() - 1)
            args_str = code[m.end():close] if close != -1 else ""
            lbls = UI_STR_RE.findall(args_str)
            label = lbls[0].strip() if lbls else ""
            line = line_of(code, m.start())
            btn_vars[var] = {
                "var": var,
                "label": label,
                "klass": klass,
                "line": line,
                "handler": "",
            }

    # 3. setText / setHTML 등으로 라벨이 지정된 경우 보완
    for m in re.finditer(r"(\w+)\.set(?:Text|HTML)\s*\(([^)]+)\)", code):
        v = m.group(1).replace("this.", "").strip()
        if v in btn_vars and not btn_vars[v]["label"]:
            lbls = UI_STR_RE.findall(m.group(2))
            if lbls:
                btn_vars[v]["label"] = lbls[0].strip()

    # 4. SearchBarBuilder 암묵적 버튼 수집
    sbb_buttons: list[dict[str, Any]] = []
    for m in re.finditer(r"(?<![\w.])(\w+)\.addRetrieveButton\s*\(", code):
        sbb_buttons.append({
            "var": f"sbb_retrieve_{m.start()}",
            "label": "조회",
            "handler": "retrieve",
            "line": line_of(code, m.start()),
        })
    for m in re.finditer(r"(?<![\w.])(\w+)\.addUpdateButton\s*\(([^)]*)\)", code):
        args = split_args(m.group(2))
        lbl = UI_STR_RE.findall(args[0])[0] if args and UI_STR_RE.findall(args[0]) else "저장"
        sbb_buttons.append({
            "var": f"sbb_update_{m.start()}",
            "label": lbl,
            "handler": "update",
            "line": line_of(code, m.start()),
        })
    for m in re.finditer(r"(?<![\w.])(\w+)\.addInsertButton\s*\(([^)]*)\)", code):
        args = split_args(m.group(2))
        lbl = UI_STR_RE.findall(args[0])[0] if args and UI_STR_RE.findall(args[0]) else "등록"
        sbb_buttons.append({
            "var": f"sbb_insert_{m.start()}",
            "label": lbl,
            "handler": "insertRow",
            "line": line_of(code, m.start()),
        })
    for m in re.finditer(r"(?<![\w.])(\w+)\.addDeleteButton\s*\(", code):
        sbb_buttons.append({
            "var": f"sbb_delete_{m.start()}",
            "label": "삭제",
            "handler": "deleteRow",
            "line": line_of(code, m.start()),
        })

    # 5. 인라인 생성 버튼 (변수 없이 buttonBar.add(new ...))
    for m in re.finditer(
        r"(?:buttonBar|getButtonBar\(\)|searchBar)\.add\s*\(\s*new\s+([\w.]+)\s*\(([^)]*)\)\s*\)",
        code,
    ):
        klass, args_str = m.group(1), m.group(2)
        if (
            klass in ("ColorButtonBar", "ColorButtonBottom", "OmsButton", "TextButton", "Button")
            or klass.endswith("Button")
        ) and klass not in ("ButtonBar", "HeaderButtonBar"):
            lbls = UI_STR_RE.findall(args_str)
            label = lbls[0].strip() if lbls else ""
            line = line_of(code, m.start())
            anon_var = f"anon_btn_{m.start()}"
            container_order.append(anon_var)
            btn_vars[anon_var] = {
                "var": anon_var,
                "label": label,
                "klass": klass,
                "line": line,
                "handler": "",
            }

    # 6. 이벤트 목록에서 핸들러 매핑
    def format_handler(action: str) -> str:
        act = action.strip()
        if not act:
            return "undefined"
        m = re.match(r"^(?:this\.)?([a-zA-Z_]\w*)\(\)$", act)
        if m:
            return m.group(1)
        m2 = re.match(r"^(?:this\.)?([a-zA-Z_]\w*\([^)]*\))$", act)
        if m2:
            return f"() => {m2.group(1)}"
        return f"() => /* {act} */"

    for e in events:
        src_m = re.match(r"^(\w+)(?:\[.*\])?", e.source)
        if src_m:
            ev_var = src_m.group(1)
            if ev_var in btn_vars:
                btn_vars[ev_var]["handler"] = format_handler(e.action)
                if not btn_vars[ev_var]["label"]:
                    lbl_m = re.search(r"\[(.*)\]", e.source)
                    if lbl_m:
                        btn_vars[ev_var]["label"] = lbl_m.group(1)

    all_raw = list(btn_vars.values()) + sbb_buttons

    def sort_key(b: dict[str, Any]) -> tuple[int, int, int]:
        var = b["var"]
        if var in container_order:
            return (0, container_order.index(var), b["line"])
        return (1, b["line"], 0)

    all_raw.sort(key=sort_key)

    result: list[ButtonInfo] = []
    seen: set[str] = set()
    for b in all_raw:
        var = b["var"]
        if var in seen:
            continue
        seen.add(var)

        lbl = b["label"]
        handler = b["handler"] or "undefined"
        b_type = btn_map.get(lbl, "unknown")
        result.append(
            ButtonInfo(
                label=lbl,
                button_type=b_type,
                handler=handler,
                line=b["line"],
            )
        )

    return result


def render_events_markdown(
    file_label: str,
    events: list[EventInfo],
    methods: list[MethodInfo],
    grid_spec: str | None = None,
    buttons: list[ButtonInfo] | None = None,
) -> str:
    """마크다운 형태로 이벤트 및 메서드 분석 결과를 렌더링한다."""
    lines = [f"원본: {file_label}", "", "## 이벤트"]

    # E0 (생성자/열림)
    e0 = next((e for e in events if e.id == "E0"), None)
    if e0:
        cond_str = f" {e0.condition}" if e0.condition else ""
        lines.append(f"[{e0.id}] {e0.source}{cond_str} → {e0.action}")

    # E1..En 최상위 이벤트들 (parent_id가 없는 이벤트)
    for e in events:
        if e.id == "E0" or e.parent_id:
            continue
        cond_str = f" {e.condition}" if e.condition else ""
        lines.append(f"[{e.id}] {e.source}.{e.event_type}{cond_str} (L{e.line}) → {e.action}")
        for sub in e.sub_events:
            s_cond = f" {sub.condition}" if sub.condition else ""
            lines.append(f"       └ [{sub.id}] {sub.source}.{sub.event_type}{s_cond} (L{sub.line}) → {sub.action}")

    lines.append("")
    lines.append("## 메서드")
    lines.append("| 메서드 | 줄 | 호출처 | 하는 일 | 구분 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for m in methods:
        callers_str = ",".join(m.callers) if m.callers else "-"
        lines.append(f"| {m.name} | L{m.line_start}-{m.line_end} | {callers_str} | {m.work_desc} | {m.category} |")

    lines.append("")
    lines.append("## Grid Spec")
    if grid_spec and grid_spec.strip():
        lines.append("```javascript")
        lines.append(grid_spec.strip())
        lines.append("```")
    else:
        lines.append("Grid 사용하지 않음")

    lines.append("")
    lines.append("## 사용된 버튼들")
    if buttons:
        for idx, b in enumerate(buttons, 1):
            lines.append(f"{idx}. {b.jsx}")
    else:
        lines.append("버튼 사용하지 않음")

    return "\n".join(lines)

