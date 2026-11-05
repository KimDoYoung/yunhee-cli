"""AS-IS 팝업/컴포넌트 호출부(new + open/view/edit 인자) 역추적 및 TOBE 대조 분석 도구."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.src_indexer import (
    find_app,
    find_methods,
    line_of,
    paren_end,
    split_args,
    strip_java,
)

NAME = "callers"
DESCRIPTION = "클래스(조회·편집 팝업 등)를 여는 호출부·메서드·리터럴 인자·메뉴 역추적 및 TOBE 대조"
TARGET_HELP = "<클래스명>"
FORMATS = ("md", "json")
EXAMPLES = [
    "yunhee analysis callers Crm09_Lookup_SelectSingle",
    "yunhee analysis callers Tdm00_Lookup_RelateAppr",
    "yunhee analysis callers Crm09_Lookup_SelectSingle --tobe frontend/src",
]

ACTION_METHODS = {
    "open",
    "view",
    "edit",
    "show",
    "retrieve",
    "gridInsert",
    "insertRow",
    "editRegEmpMsg",
    "editConfirmMsg",
    "viewMsg",
    "openLookup",
}


def _extract_literals(args_list: list[str]) -> list[str]:
    """인자 목록에서 문자열·숫자·불리언 리터럴을 추출한다 (콜백 익명 클래스는 제외)."""
    lits: list[str] = []
    for arg in args_list:
        a = arg.strip()
        if not a or "new Interface" in a or "new AsyncCallback" in a or "function(" in a:
            continue
        str_matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', a)
        if str_matches:
            for s in str_matches:
                lits.append(f'"{s}"')
        elif re.fullmatch(r"(?:true|false|-?\d+(?:\.\d+)?[LDFldf]?)", a):
            lits.append(a)
    return lits


def _load_menu_map(src_index: Path | None) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    """(화면클래스 -> ['#번호 메뉴명'], 하위클래스 -> {상위화면클래스}) 매핑을 로드한다."""
    screen_menus: dict[str, list[str]] = {}
    class_to_screens: dict[str, set[str]] = {}
    if not src_index or not src_index.is_dir():
        tobe_dir = getattr(config, "TOBE_SRC_DIR", None)
        if tobe_dir and (Path(tobe_dir) / "docs" / "as-is" / "src").is_dir():
            src_index = Path(tobe_dir) / "docs" / "as-is" / "src"
        else:
            return screen_menus, class_to_screens

    menus_md = src_index / "menus.md"
    if menus_md.is_file():
        menu_row_re = re.compile(r"^\|\s*(?P<path>[^|]+?)\s*\|\s*(?P<no>\d+)\s*\|\s*(?P<use>[^|]*?)\s*\|\s*(?P<screen>[^|]*?)\s*\|\s*$")
        link_re = re.compile(r"\[`([^`]+)`\]")
        try:
            for line in menus_md.read_text(encoding="utf-8", errors="replace").splitlines():
                m = menu_row_re.match(line)
                if not m:
                    continue
                link = link_re.search(m["screen"])
                if not link:
                    continue
                scr_cls = link.group(1)
                leaf_name = m["path"].split(">")[-1].strip()
                label = f"#{m['no']} {leaf_name}".strip()
                if label not in screen_menus.setdefault(scr_cls, []):
                    screen_menus[scr_cls].append(label)
        except OSError:
            pass

    for md_path in src_index.glob("*/screens/*.md"):
        scr_name = md_path.stem
        try:
            txt = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m_hdr in re.finditer(r"^###\s+(\w+)\s+\(", txt, re.MULTILINE):
            sub_cls = m_hdr.group(1)
            if sub_cls != scr_name:
                class_to_screens.setdefault(sub_cls, set()).add(scr_name)
        for m_link in re.finditer(r"-\s*연결 화면·컴포넌트[^\n]*:\s*([^\n]+)", txt):
            for l_cls in re.findall(r"\[`(\w+)`\]", m_link.group(1)):
                if l_cls != scr_name:
                    class_to_screens.setdefault(l_cls, set()).add(scr_name)

    return screen_menus, class_to_screens


def _format_menu_for_class(
    cls_name: str,
    screen_menus: dict[str, list[str]],
    class_to_screens: dict[str, set[str]],
) -> str:
    if cls_name in screen_menus:
        return ", ".join(screen_menus[cls_name][:2])
    parent_screens = sorted(class_to_screens.get(cls_name, ()))
    out: list[str] = []
    for scr in parent_screens[:2]:
        menus = screen_menus.get(scr, [])
        if menus:
            out.append(f"{menus[0]} ({scr})")
        else:
            out.append(scr)
    return ", ".join(out) if out else "-"


def _scan_tobe_callers(target_cls: str, tobe_arg: str | None) -> dict[str, list[dict[str, Any]]]:
    """TOBE 디렉터리에서 target_cls 컴포넌트를 렌더링하는 곳을 찾는다.

    반환: {호출_파일_stem: [{"file": rel_path, "line": int, "props": str, "raw": str}]}
    """
    if not tobe_arg:
        return {}

    roots: list[Path] = []
    for part in str(tobe_arg).split(","):
        p_str = part.strip()
        if not p_str:
            continue
        p = Path(p_str)
        if not p.exists():
            cand = config.WORK_DIR / p
            if cand.exists():
                p = cand
            elif getattr(config, "TOBE_SRC_DIR", None) and (config.TOBE_SRC_DIR / p).exists():
                p = config.TOBE_SRC_DIR / p
        if p.exists():
            roots.append(p)

    if not roots:
        return {}

    by_caller: dict[str, list[dict[str, Any]]] = {}
    jsx_re = re.compile(rf"<{re.escape(target_cls)}\b([^>]*?)/?>", re.DOTALL)

    for root in roots:
        tsx_files = [root] if root.is_file() else sorted(root.rglob("*.tsx"))
        for tf in tsx_files:
            if tf.stem == target_cls or "node_modules" in tf.parts:
                continue
            try:
                text = tf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if target_cls not in text:
                continue
            try:
                rel = tf.relative_to(root).as_posix() if root.is_dir() else tf.name
            except ValueError:
                rel = tf.name

            for m in jsx_re.finditer(text):
                ln = line_of(text, m.start())
                attrs_raw = m.group(1)
                props_extracted: list[str] = []
                for pm in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|\{([^{}]+)\})', attrs_raw):
                    pname = pm.group(1)
                    if pname in ("open", "onClose", "onResult", "onSelect", "onOk", "onCancel", "ref"):
                        continue
                    pval = pm.group(2) if pm.group(2) is not None else (pm.group(3) if pm.group(3) is not None else pm.group(4))
                    if pval is not None:
                        q = '"' if (pm.group(2) is not None or pm.group(3) is not None) else ""
                        props_extracted.append(f"{pname}={q}{pval.strip()}{q}")
                by_caller.setdefault(tf.stem, []).append({
                    "file": rel,
                    "stem": tf.stem,
                    "line": ln,
                    "props": ", ".join(props_extracted),
                })

    return by_caller


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """AS-IS에서 target 클래스를 생성·호출하는 모든 지점을 수집한다."""
    target_cls = target.strip().removesuffix(".java").removesuffix(".tsx")
    if not target_cls:
        raise ValueError("대상 클래스명을 입력해 주세요. 예: yunhee analysis callers Crm09_Lookup_SelectSingle")

    src_root, src_index = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_root or not src_root.is_dir():
        raise ValueError("AS-IS 소스 디렉터리를 찾을 수 없습니다. --src 옵션을 지정하세요.")

    app = find_app(src_root) or src_root
    client_dir = app / "client"
    search_dir = client_dir if client_dir.is_dir() else app

    screen_menus, class_to_screens = _load_menu_map(src_index)
    tobe_map = _scan_tobe_callers(target_cls, opts.get("tobe"))

    new_re = re.compile(
        rf"(?:(?:final[ \t]+)?(?:[\w<>?,]+[ \t]+)?(\w+)[ \t]*=[ \t]*)?new[ \t]+{re.escape(target_cls)}\s*(?:<[^>]*>)?\s*\("
    )

    rows: list[dict[str, Any]] = []
    for java_file in sorted(search_dir.rglob("*.java")):
        if java_file.stem == target_cls or "target" in java_file.parts:
            continue
        try:
            raw = java_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if target_cls not in raw:
            continue

        no_comment, bare = strip_java(raw)
        methods = find_methods(bare)
        rel_path = java_file.relative_to(app) if java_file.is_relative_to(app) else java_file.name

        for m_new in new_re.finditer(no_comment):
            var_name = m_new.group(1)
            new_pos = m_new.start()
            new_line = line_of(no_comment, new_pos)
            close_paren = paren_end(no_comment, m_new.end() - 1)
            ctor_args_raw = no_comment[m_new.end() : close_paren]
            ctor_lits = _extract_literals(split_args(ctor_args_raw))

            # 감싼 메서드 찾기
            enclosing_meth = "<field>"
            scope_end = len(no_comment)
            for m_name, _npos, b_start, b_end, _is_pub, _params in methods:
                if b_start <= new_pos <= b_end:
                    enclosing_meth = m_name
                    scope_end = b_end
                    break

            called_methods: list[str] = []
            call_lines: list[int] = []
            literals: list[str] = list(ctor_lits)

            # 1) 체이닝 호출 확인: new TargetCls(...).open(...)
            after_ctor = no_comment[close_paren + 1 : min(len(no_comment), close_paren + 80)]
            m_chain = re.match(r"\s*\.\s*(\w+)\s*\(", after_ctor)
            if m_chain:
                cm_name = m_chain.group(1)
                c_open = close_paren + 1 + m_chain.end() - 1
                c_close = paren_end(no_comment, c_open)
                c_args = split_args(no_comment[c_open + 1 : c_close])
                called_methods.append(cm_name)
                call_lines.append(line_of(no_comment, c_open))
                for lit in _extract_literals(c_args):
                    if lit not in literals:
                        literals.append(lit)
            elif var_name:
                # 2) 변수 호출 추적: 메서드 범위(또는 필드면 클래스 전체)에서 var_name.xxx(...) 탐색
                search_start = close_paren + 1 if enclosing_meth != "<field>" else 0
                search_end = scope_end if enclosing_meth != "<field>" else len(no_comment)
                scope_slice = no_comment[search_start:search_end]
                var_call_re = re.compile(rf"\b{re.escape(var_name)}\s*\.\s*(\w+)\s*\(")
                raw_calls: list[tuple[str, int, list[str]]] = []
                for mc in var_call_re.finditer(scope_slice):
                    cm_name = mc.group(1)
                    abs_open = search_start + mc.end() - 1
                    abs_close = paren_end(no_comment, abs_open)
                    c_args = split_args(no_comment[abs_open + 1 : abs_close])
                    c_line = line_of(no_comment, search_start + mc.start())
                    raw_calls.append((cm_name, c_line, _extract_literals(c_args)))

                # 주요 액션 메서드가 있으면 그것들을 우선, 없으면 전체 호출 메서드
                action_calls = [rc for rc in raw_calls if rc[0] in ACTION_METHODS]
                chosen_calls = action_calls if action_calls else raw_calls
                for cm_name, c_line, c_lits in chosen_calls:
                    if cm_name not in called_methods:
                        called_methods.append(cm_name)
                    call_lines.append(c_line)
                    for lit in c_lits:
                        if lit not in literals:
                            literals.append(lit)

            # 표시할 줄 번호 결정: new 바로 다음 줄에서 단일 호출이 일어나면 호출 줄(예: 209), 멀거나 복수면 new_line
            display_line = new_line
            if len(call_lines) == 1 and 0 <= (call_lines[0] - new_line) <= 1:
                display_line = call_lines[0]

            meth_str = "/".join(called_methods) if called_methods else "<init>"
            lit_str = ", ".join(literals) if literals else "-"
            menu_str = _format_menu_for_class(java_file.stem, screen_menus, class_to_screens)

            tobe_entries = tobe_map.get(java_file.stem, [])
            tobe_str = ""
            if opts.get("tobe"):
                if tobe_entries:
                    parts_t = []
                    for te in tobe_entries:
                        p_info = f" ({te['props']})" if te.get("props") else ""
                        parts_t.append(f"`{te['stem']}.tsx:{te['line']}`{p_info}")
                    tobe_str = ", ".join(parts_t)
                else:
                    tobe_str = "❌ 미연결"

            rows.append({
                "caller_class": java_file.stem,
                "file": f"{java_file.name}:{display_line}",
                "rel_file": f"{rel_path}:{display_line}",
                "new_line": new_line,
                "call_lines": call_lines,
                "called_method": meth_str,
                "literals": lit_str,
                "enclosing_method": enclosing_meth,
                "menu": menu_str,
                "tobe": tobe_str,
            })

    return {
        "target": target_cls,
        "rows": rows,
        "has_tobe": bool(opts.get("tobe")),
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """호출부 분석 결과를 표 또는 JSON으로 렌더링한다."""
    target_cls = obj["target"]
    rows = obj["rows"]
    has_tobe = obj.get("has_tobe", False)

    if fmt == "json":
        return json.dumps(obj, ensure_ascii=False, indent=2)

    if not rows:
        return f"`{target_cls}` 클래스를 생성(`new {target_cls}`)하는 호출부를 찾지 못했습니다."

    lines = [f"### `{target_cls}` 호출부 ({len(rows)}곳)", ""]
    if has_tobe:
        lines.append("| 파일:줄 | 부른 메서드 | 리터럴 인자 | 감싼 메서드 | 메뉴 | TOBE |")
        lines.append("|:---|:---|:---|:---|:---|:---|")
        for r in rows:
            lines.append(
                f"| `{r['file']}` | `{r['called_method']}` | `{r['literals']}` | `{r['enclosing_method']}` | {r['menu']} | {r['tobe']} |"
            )
    else:
        lines.append("| 파일:줄 | 부른 메서드 | 리터럴 인자 | 감싼 메서드 | 메뉴 |")
        lines.append("|:---|:---|:---|:---|:---|")
        for r in rows:
            lines.append(
                f"| `{r['file']}` | `{r['called_method']}` | `{r['literals']}` | `{r['enclosing_method']}` | {r['menu']} |"
            )

    return "\n".join(lines)
