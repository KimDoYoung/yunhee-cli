"""AS-IS 메서드 본문 분석 도구 (클라이언트·서버)."""

import difflib
import re
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import AmbiguousTargetError, resolve_as_is_paths
from yunhee.tools.as_is.src_indexer import (
    find_app,
    find_methods,
    paren_end,
    split_args,
    strip_java,
)

NAME = "method"
DESCRIPTION = "AS-IS 메서드 본문 및 호출 흐름 분석 (클라이언트·서버)"
TARGET_HELP = "<클래스>.<메서드>[#n]"
FORMATS = ("md", "code")
EXAMPLES = [
    "yunhee analysis method Emp03_TabPage_Trans.insertRow",
    "yunhee analysis method Emp00_TransInfo.update --server -o code",
    "yunhee analysis method Org00_Lookup_SelectSingle.open#3",
]


class MethodNotFoundError(AmbiguousTargetError):
    """메서드를 찾지 못했을 때 후보 목록을 제공 (Exit 2)."""

    def __init__(self, target_method: str, candidates: list[str]) -> None:
        cands_str = ", ".join(candidates)
        self.target_method = target_method
        self.candidates = candidates
        self._msg = f"찾는 메서드: {target_method} — 후보: {cands_str}"
        super(AmbiguousTargetError, self).__init__(self._msg)

    def __str__(self) -> str:
        return self._msg


def _find_class_method_candidates(full_text: str, cls_name: str, target_method: str) -> list[str]:
    """클래스 소스에서 target_method와 유사한 메서드 이름 후보를 최대 3개 추출한다."""
    _, bare = strip_java(full_text)
    raw_methods = find_methods(bare)

    declared_methods: list[tuple[str, bool]] = []
    for m in raw_methods:
        name = m[0]
        is_pub = m[4]
        if not any(dm[0] == name for dm in declared_methods):
            declared_methods.append((name, is_pub))

    all_names = [dm[0] for dm in declared_methods]

    # 1. difflib 기반 유사 이름
    matches = difflib.get_close_matches(target_method, all_names, n=3, cutoff=0.35)
    if matches:
        return [f"{name} (생성자)" if name == cls_name else name for name in matches]

    # 2. 유사 이름이 없는 경우 일반 메서드 우선 (공개, retrieve 우선)
    non_ctors = [dm for dm in declared_methods if dm[0] != cls_name]
    non_ctors.sort(key=lambda x: (0 if x[0] == "retrieve" else 1, 0 if x[1] else 1))
    ordered = [name for name, _ in non_ctors]
    if cls_name in all_names:
        ordered.append(f"{cls_name} (생성자)")

    return ordered[:3]


def _detect_delegation(body: str) -> tuple[str, str] | None:
    """메서드 본문에서 타 클래스로의 단순 위임 호출(new X().y(...) 또는 X x = new X(); x.y(...))을 탐지한다."""
    # 1. new Target().method(
    m = re.search(r"new\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\.\s*([A-Za-z0-9_]+)\s*\(", body)
    if m:
        return m.group(1), m.group(2)
    # 2. Target var = new Target(); var.method(
    m2 = re.search(r"([A-Za-z0-9_]+)\s+(\w+)\s*=\s*new\s+\1\s*\([^)]*\)\s*;", body)
    if m2:
        cls_name = m2.group(1)
        var_name = m2.group(2)
        m3 = re.search(rf"\b{re.escape(var_name)}\s*\.\s*([A-Za-z0-9_]+)\s*\(", body)
        if m3:
            return cls_name, m3.group(1)
    return None


def _find_method_blocks(full_text: str, target_method: str) -> list[tuple[str, int, int, str]]:
    """자바 소스에서 target_method 이름의 메서드(생성자 포함)들을 찾아 (시그니처, 시작줄, 끝줄, 본문) 목록을 반환한다."""
    is_ctor_name = bool(target_method and target_method[0].isupper())
    if is_ctor_name:
        pattern = re.compile(
            r"(?<!new\s)(?:(?:public|protected|private)\s+)\b("
            + re.escape(target_method)
            + r")\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+?)?\s*\{"
        )
    else:
        pattern = re.compile(
            r"(?:(?:public|protected|private|static|final|synchronized|abstract|default)\s+)*(?:<[\w,\s?]+>\s+)?(?:[\w<>\[\], ?]+)\s+\b("
            + re.escape(target_method)
            + r")\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+?)?\s*\{"
        )

    results = []
    for m in pattern.finditer(full_text):
        m_name = m.group(1)
        params_str = m.group(2).strip()
        sig = f"{m_name}({params_str})"

        # 시작 줄: 메서드 선언의 첫 토큰 위치 (public/protected/.../반환형)
        matched_text = m.group(0)
        first_tok = re.search(r"[a-zA-Z_<]", matched_text)
        offset = first_tok.start() if first_tok else 0
        start_pos = m.start() + offset
        start_line = full_text.count("\n", 0, start_pos) + 1

        # 중괄호 깊이 추적하여 끝 줄 탐색
        open_brace = m.end() - 1
        depth = 0
        end_pos = open_brace
        in_str = None
        in_char = False
        k = open_brace
        n = len(full_text)
        while k < n:
            c = full_text[k]
            if in_str:
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == in_str:
                    in_str = None
            elif in_char:
                if c == "\\" and k + 1 < n:
                    k += 2
                    continue
                if c == "'":
                    in_char = False
            elif c == '"':
                in_str = '"'
            elif c == "'":
                in_char = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end_pos = k
                    break
            k += 1

        end_line = full_text.count("\n", 0, end_pos) + 1
        body = full_text[start_pos : end_pos + 1]
        results.append((sig, start_line, end_line, body))

    return results


def _find_caller_event(src_index: Path | None, cls_name: str, meth_name: str) -> str | None:
    """색인 디렉터리에서 해당 클래스·메서드의 이벤트 ID(E1, E2, E3 등)를 찾는다."""
    if not src_index or not src_index.is_dir():
        return None

    # screens/*.md 파일 탐색
    for md_file in src_index.rglob("*.md"):
        if "screens" not in md_file.parts and md_file.name != f"{cls_name}.md":
            continue
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if cls_name not in content:
            continue

        # ### {cls_name} 섹션 찾기
        cls_pattern = rf"###\s+{re.escape(cls_name)}\b.*?(?=\n###\s|\Z)"
        cls_m = re.search(cls_pattern, content, re.DOTALL)
        if not cls_m:
            continue
        cls_section = cls_m.group(0)

        # 이벤트 목록: [E3] ... → meth_name
        ev_m = re.search(rf"\[(E\d+)\][^\n]*→\s*{re.escape(meth_name)}\b", cls_section)
        if ev_m:
            return ev_m.group(1)

        # 메서드 표: | public ... meth_name(...) | ... | E3 |
        table_m = re.search(
            rf"\|\s*(?:public|protected|private)\s+{re.escape(meth_name)}\([^)]*\)\s*\|\s*L\d+-\d+\s*\|\s*([^|]*\b(E\d+)\b[^|]*)\|",
            cls_section,
        )
        if table_m:
            return table_m.group(2)

    return None


def _extract_combo_options(file_text: str) -> dict[str, list[str]]:
    """클래스 전체 소스에서 콤보박스 변수별 .add(...) 선택지 및 CodeComboBox 코드 키를 수집한다 (#17)."""
    combo_opts: dict[str, list[str]] = {}
    if not file_text:
        return combo_opts

    # 1. comboVar = new CodeComboBox / CommonComboBoxField / SimpleComboBox
    for m_decl in re.finditer(
        r"(\w+)\s*=\s*new\s+(?:CodeComboBox|CommonComboBoxField|ComboBoxField|SimpleComboBox)\w*(?:<[^>]*>)?\s*\(([^;]*)\)",
        file_text,
    ):
        var_name = m_decl.group(1)
        args_raw = m_decl.group(2)
        str_lits = re.findall(r'"([^"]+)"', args_raw)
        if str_lits:
            combo_opts.setdefault(var_name, []).extend(
                [f"코드:{s}" if idx == 0 and len(str_lits) >= 1 and s.isupper() else s for idx, s in enumerate(str_lits)]
            )

    # 2. comboVar.add("...") 호출 수집
    for m_add in re.finditer(r"(?:this\.)?(\w+)\.add\s*\(\s*\"([^\"]+)\"\s*\)", file_text):
        var_name, opt_val = m_add.group(1), m_add.group(2)
        if var_name in ("list", "result", "params", "sql", "sb", "buffer"):
            continue
        opts_list = combo_opts.setdefault(var_name, [])
        if opt_val not in opts_list:
            opts_list.append(opt_val)

    return combo_opts


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """대상 메서드를 찾아 해석한다 (다중 메서드 지정 지원)."""
    target_clean = target.strip()
    extra_targets: list[str] = list(opts.get("extra_targets") or [])

    # 1) "ClassName m1 m2" 또는 "ClassName.m1 m2" 또는 "ClassName.m1,m2" 처리
    if "." not in target_clean and extra_targets:
        cls_prefix = target_clean
        meth_list = []
        for et in extra_targets:
            meth_list.extend([x.strip() for x in et.split(",") if x.strip()])
        if len(meth_list) == 1:
            target_clean = f"{cls_prefix}.{meth_list[0]}"
            extra_targets = []
        elif len(meth_list) > 1:
            sub_opts = {**opts, "extra_targets": []}
            resolved_items = [resolve(f"{cls_prefix}.{m}", sub_opts) for m in meth_list]
            return {
                **resolved_items[0],
                "multi_methods": resolved_items,
            }
    elif "." in target_clean and ("," in target_clean.split(".")[-1] or extra_targets):
        prefix_part, last_part = target_clean.rsplit(".", 1)
        meth_list = [x.strip() for x in last_part.split(",") if x.strip()]
        for et in extra_targets:
            meth_list.extend([x.strip() for x in et.split(",") if x.strip()])
        if len(meth_list) > 1:
            sub_opts = {**opts, "extra_targets": []}
            resolved_items = [
                resolve(m if "." in m else f"{prefix_part}.{m}", sub_opts)
                for m in meth_list
            ]
            return {
                **resolved_items[0],
                "multi_methods": resolved_items,
            }

    idx_choice = None
    if "#" in target_clean:
        target_clean, num_str = target_clean.split("#", 1)
        try:
            idx_choice = int(num_str)
        except ValueError:
            pass

    if "." not in target_clean:
        raise ValueError(f"올바른 형식(<클래스>.<메서드>)으로 입력해 주세요: {target}")

    tokens = target_clean.split(".")
    if len(tokens) >= 3:
        cls_name = tokens[-2]
        meth_name = tokens[-1]
        pkg_parts = tokens[:-2]
    else:
        cls_name = tokens[0]
        meth_name = tokens[1]
        pkg_parts = []

    src_root, src_index = resolve_as_is_paths(
        src=opts.get("src"),
        src_index=opts.get("src_index"),
    )
    if not src_root or not src_root.is_dir():
        raise ValueError("AS-IS 소스 디렉터리를 찾을 수 없습니다. --src 옵션을 지정하세요.")

    app = find_app(src_root) or src_root

    is_server_opt = opts.get("server", False)
    is_client_opt = opts.get("client", False)

    # 검색 대상 Java 파일 탐색
    search_dirs: list[Path] = []
    if is_server_opt:
        search_dirs = [d for d in [app / "server", app] if d.is_dir()]
    elif is_client_opt:
        search_dirs = [d for d in [app / "client", app] if d.is_dir()]
    else:
        search_dirs = [app]

    cand_files: list[Path] = []
    if pkg_parts:
        pkg_path = Path(*pkg_parts)
        for sdir in search_dirs:
            cand = sdir / pkg_path / f"{cls_name}.java"
            if cand.is_file() and cand not in cand_files:
                cand_files.append(cand)
        if not cand_files and is_server_opt:
            cand = app / "server" / pkg_path / f"{cls_name}.java"
            if cand.is_file() and cand not in cand_files:
                cand_files.append(cand)

    if not cand_files:
        for sdir in search_dirs:
            for f in sdir.rglob(f"{cls_name}.java"):
                if "target" not in f.parts and f not in cand_files:
                    cand_files.append(f)

    if not cand_files:
        raise ValueError(f"클래스 소스 파일을 찾을 수 없습니다: {cls_name}.java")

    caller_event = _find_caller_event(src_index, cls_name, meth_name)

    # 후보 메서드 수집
    candidates: list[dict[str, Any]] = []
    for f in cand_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = f.relative_to(app) if f.is_relative_to(app) else f.relative_to(src_root)
        blocks = _find_method_blocks(text, meth_name)
        for sig, s_line, e_line, body in blocks:
            candidates.append({
                "file": f,
                "file_text": text,
                "rel": str(rel),
                "cls": cls_name,
                "method": meth_name,
                "sig": sig,
                "start": s_line,
                "end": e_line,
                "body": body,
                "is_server": "server" in f.parts,
                "caller_event": caller_event,
                "src_root": src_root,
                "follow": bool(opts.get("follow", False)),
            })

    if not candidates:
        if cand_files:
            try:
                first_text = cand_files[0].read_text(encoding="utf-8", errors="replace")
                alt_cands = _find_class_method_candidates(first_text, cls_name, meth_name)
                if alt_cands:
                    raise MethodNotFoundError(meth_name, alt_cands)
            except MethodNotFoundError:
                raise
            except Exception:  # noqa: BLE001, S110
                pass
        raise ValueError(f"{cls_name} 에서 메서드 '{meth_name}'을 찾을 수 없습니다.")

    if called_from := opts.get("called_from"):
        selected = _resolve_overload_by_caller(candidates, called_from, app, src_root)
        if selected:
            return selected

    if len(candidates) > 1 and idx_choice is None:
        is_short_or_delegated = _annotate_overloads(candidates)
        cand_descs = [
            f"{c['rel']}:{c['start']} {c['sig']}"
            + (f"  → #{c['delegates_to']} 위임" if c.get("delegates_to") else "")
            for c in candidates
        ]
        if opts.get("output") == "code" and is_short_or_delegated:
            return {
                **candidates[0],
                "multi_candidates": candidates,
                "cand_descs": cand_descs,
            }
        if is_short_or_delegated and any(c.get("delegates_to") for c in candidates):
            return {
                **candidates[0],
                "multi_methods": candidates,
                "cand_descs": cand_descs,
            }
        raise AmbiguousTargetError(cand_descs, target)

    if idx_choice is not None:
        if idx_choice < 1 or idx_choice > len(candidates):
            raise ValueError(f"선택한 번호 #{idx_choice}가 범위를 벗어났습니다 (1~{len(candidates)})")
        return candidates[idx_choice - 1]

    return candidates[0]


def _annotate_overloads(candidates: list[dict[str, Any]]) -> bool:
    """오버로드 후보들의 실질 코드 줄 수와 위임 관계(→ #N 위임)를 분석하고 인라인 출력 대상인지 반환한다."""
    if not candidates:
        return False
    meth_name = candidates[0]["method"]

    # 각 후보의 파라미터 개수 계산
    param_counts: list[int] = []
    for c in candidates:
        sig = c["sig"]
        m_p = re.search(r"\((.*)\)", sig, re.DOTALL)
        if not m_p or not m_p.group(1).strip():
            param_counts.append(0)
        else:
            p_str = re.sub(r"<[^<>]*>", "", m_p.group(1))
            param_counts.append(p_str.count(",") + 1)

    for idx, c in enumerate(candidates):
        body = c["body"]
        b_start = body.find("{")
        b_end = body.rfind("}")
        inner = body[b_start + 1:b_end] if (b_start != -1 and b_end > b_start) else body
        no_comm, _ = strip_java(inner)
        code_lines = [ln.strip() for ln in no_comm.splitlines() if ln.strip() and ln.strip() not in ("{", "}")]
        c["code_lines_count"] = len(code_lines)

        # 같은 이름의 오버로드 호출(this.meth(...) 또는 meth(...)) 탐색
        for m_call in re.finditer(rf"(?:\bthis\s*\.\s*|\b){re.escape(meth_name)}\s*\(([^()]*)\)", no_comm):
            args_str = m_call.group(1).strip()
            call_cnt = 0 if not args_str else (args_str.count(",") + 1)
            for other_idx, p_cnt in enumerate(param_counts):
                if other_idx != idx and p_cnt == call_cnt:
                    c["delegates_to"] = other_idx + 1
                    break

    all_short = all(c.get("code_lines_count", 99) <= 5 or c.get("delegates_to") for c in candidates)
    return all_short



def _resolve_overload_by_caller(
    candidates: list[dict[str, Any]],
    called_from: str,
    app: Path,
    src_root: Path,
) -> dict[str, Any] | None:
    caller_clean = called_from.strip().removesuffix(".java")
    caller_files = list(app.rglob(f"{caller_clean}.java"))
    if not caller_files:
        caller_files = [f for f in src_root.rglob(f"{caller_clean}.java") if "target" not in f.parts]
    if not caller_files:
        return None

    caller_text = caller_files[0].read_text(encoding="utf-8", errors="replace")
    meth_name = candidates[0]["method"]

    call_m = re.search(rf"\b\w+\.{re.escape(meth_name)}\s*\(", caller_text)
    if not call_m:
        call_m = re.search(rf"\b{re.escape(meth_name)}\s*\(", caller_text)
    if not call_m:
        return None

    open_p = caller_text.find("(", call_m.start())
    close_p = paren_end(caller_text, open_p)
    raw_args = caller_text[open_p + 1 : close_p]
    args = split_args(raw_args)

    def infer_type(arg: str) -> str:
        a = arg.strip()
        if "Callback" in a or "callback" in a:
            return "cb"
        if "new Date" in a or "Date" in a or "date" in a:
            return "Date"
        if a in ("true", "false") or "Boolean" in a:
            return "Boolean"
        if "Long." in a or re.match(r"^\d+L$", a) or (a.endswith("Id") and not a.startswith("new")):
            return "Long"
        if a.startswith('"') or "Text" in a or "String" in a or "jobName" in a:
            return "String"
        if "Integer." in a or re.match(r"^\d+$", a):
            return "Integer"
        return "Object"

    inferred_types = [infer_type(a) for a in args]

    def get_cand_types(cand: dict[str, Any]) -> list[str]:
        sig = cand["sig"]
        inside = sig.split("(", 1)[1].rstrip(")").strip()
        if not inside:
            return []
        parts = [p.strip() for p in inside.split(",") if p.strip()]
        types = []
        for p in parts:
            t = p.split()[0]
            if "Callback" in t:
                types.append("cb")
            else:
                types.append(t)
        return types

    matched_cand = None
    for cand in candidates:
        cand_types = get_cand_types(cand)
        if len(cand_types) != len(inferred_types):
            continue
        score = sum(1 for it, ct in zip(inferred_types, cand_types) if it == ct or (it == "cb" and ct == "cb"))
        if score == len(cand_types):
            matched_cand = cand
            break

    if not matched_cand:
        matched_by_len = [c for c in candidates if len(get_cand_types(c)) == len(inferred_types)]
        if len(matched_by_len) == 1:
            matched_cand = matched_by_len[0]

    if not matched_cand:
        return None

    # 위임 체인 탐색
    chain = [matched_cand]
    curr = matched_cand
    for _ in range(5):
        body = curr["body"]
        brace_idx = body.find("{")
        if brace_idx == -1:
            break
        body_after = body[brace_idx + 1 :]
        m_deleg = re.search(rf"\b{re.escape(meth_name)}\s*\(", body_after)
        if not m_deleg:
            break
        d_open = body_after.find("(", m_deleg.start())
        d_close = paren_end(body_after, d_open)
        d_raw_args = body_after[d_open + 1 : d_close]
        d_args = split_args(d_raw_args)
        d_arg_count = len(d_args)
        next_cands = [c for c in candidates if c != curr and len(get_cand_types(c)) == d_arg_count]
        if next_cands:
            curr = next_cands[0]
            chain.append(curr)
        else:
            break

    file_text = matched_cand.get("file_text", "")
    btn_defs = dict(re.findall(r'(\w+Button)\s*=\s*new\s+\w+\s*\(\s*["\']([^"\']+)["\']', file_text))

    buttons_found = []
    preferred_order = ["확인", "전체", "공통", "취소"]
    raw_buttons = []
    for c in chain:
        for m_btn in re.finditer(r'(?:this\.)?addButton\s*\(\s*(\w+)\s*\)', c["body"]):
            b_var = m_btn.group(1)
            b_lbl = btn_defs.get(b_var, b_var.replace("Button", ""))
            if b_lbl not in raw_buttons:
                raw_buttons.append(b_lbl)

    # 정렬: preferred_order 우선, 나머지 뒤로
    buttons_found = [b for b in preferred_order if b in raw_buttons] + [b for b in raw_buttons if b not in preferred_order]

    grid_mode = "SINGLE" if "SelectionMode.SINGLE" in file_text else ""
    if "SelectionMode.MULTI" in file_text:
        grid_mode = "MULTI"

    chain_parts = []
    for c in chain:
        c_types = get_cand_types(c)
        short_types = ", ".join(c_types)
        chain_parts.append(f"{meth_name}({short_types}) L{c['start']}")

    chain_str = " → ".join(chain_parts)
    extra_info = []
    if buttons_found:
        extra_info.append(f"단추 {'·'.join(buttons_found)}")
    if grid_mode:
        extra_info.append(f"그리드 {grid_mode}")

    extra_str = f" : {', '.join(extra_info)}" if extra_info else ""
    matched_cand["chain_summary"] = f"{chain_str}{extra_str}"
    return matched_cand


def _summarize_body(
    body: str,
    start_line: int,
    is_server: bool,
    file_text: str = "",
    src_root: Path | None = None,
    follow: bool = False,
) -> list[str]:
    """메서드 본문을 파싱하여 중요 작업 흐름을 요약한다."""
    items = []
    lines = body.splitlines()
    method_len = len(lines)

    class_constants = dict(
        re.findall(r'(?:private|protected|public)?\s*String\s+(\w+)\s*=\s*"([^"]+)"', file_text)
    )
    combo_options_map = _extract_combo_options(file_text) if not is_server else {}
    reported_combos: set[str] = set()

    in_callback = False
    callback_depth = 0
    seen_callback_brace = False

    def add_item(it: str) -> None:
        if not is_server and in_callback and not it.startswith("callback: "):
            items.append(f"callback: {it}")
        else:
            items.append(it)

    for idx, line in enumerate(lines):
        line_num = start_line + idx
        s = line.strip()

        # 콜백 블록 추적
        if not is_server:
            if not in_callback:
                if "getServiceResult(" in s:
                    in_callback = True
                    callback_depth = s.count("{") - s.count("}")
                    seen_callback_brace = (s.count("{") > 0)
            else:
                callback_depth += s.count("{") - s.count("}")
                if s.count("{") > 0:
                    seen_callback_brace = True

        # 0. 콤보박스 선택지 (.add("...")) 및 참조된 콤보 필드 선택지 (#17)
        if not is_server:
            m_combo_add = re.search(r'(?:this\.)?(\w+)\.add\s*\(\s*"([^"]+)"\s*\)', s)
            if m_combo_add:
                c_var = m_combo_add.group(1)
                if c_var not in ("list", "result", "params", "sql", "sb", "buffer") and c_var not in reported_combos:
                    reported_combos.add(c_var)
                    opts_vals = combo_options_map.get(c_var) or re.findall(
                        rf'(?:this\.)?{re.escape(c_var)}\.add\s*\(\s*"([^"]+)"\s*\)', body
                    )
                    if opts_vals:
                        add_item(f"콤보 선택지 {c_var}: [{', '.join(repr(v) for v in opts_vals)}] (L{line_num})")
                continue

            for c_var, opts_vals in combo_options_map.items():
                if c_var not in reported_combos and re.search(rf"\b{re.escape(c_var)}\b", s):
                    reported_combos.add(c_var)
                    add_item(f"콤보 선택지 {c_var}: [{', '.join(repr(v) for v in opts_vals)}]")

        # 1. editDriver.flush()
        if not is_server and "editDriver.flush()" in s:
            add_item(f"editDriver.flush() (L{line_num})")
            continue

        # 2. 메시지 / alert
        m_msg = re.search(r'new\s+(?:SimpleMessage|AlertMessageBox)\s*\(\s*"([^"]+)"', s)
        if m_msg:
            add_item(f'SimpleMessage "{m_msg.group(1)}" (L{line_num})')
            continue
        m_alert = re.search(r'alert\s*\(\s*"([^"]+)"', s)
        if m_alert:
            add_item(f'alert "{m_alert.group(1)}" (L{line_num})')
            continue
        if '"사원을 먼저 선택해주세요"' in s:
            add_item(f'경고: "사원을 먼저 선택해주세요" (L{line_num})')
            continue
        m_html = re.search(r'new\s+HtmlMessageBox\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', s)
        if m_html:
            add_item(f'HtmlMessageBox "{m_html.group(1)}", "{m_html.group(2)}" (L{line_num})')
            continue
        if "setEmptyText(" in s:
            m_empty = re.search(r'setEmptyText\s*\(\s*"([^"]+)"', s)
            if m_empty:
                add_item(f'setEmptyText "{m_empty.group(1)}" (L{line_num})')
                continue

        # 3. 분기 처리 (if / else if / else)
        is_else_only = bool(re.search(r'^(?:\}\s*)?else\s*\{?\s*$', s))
        m_if = re.search(r'(?:^|\})\s*(?:else\s+)?if\s*\(', s)

        if not is_server and is_else_only and method_len <= 120:
            add_item(f"분기: else (L{line_num})")
            continue

        if m_if:
            p_open = s.find("(", m_if.start())
            p_close = paren_end(s, p_open)
            cond = s[p_open + 1 : p_close] if p_close > p_open else s[p_open + 1 :].rstrip("{").strip()
            show_branch = False
            if "result.getStatus() < 0" in cond or not is_server and method_len <= 120 or "selected" in cond.lower() or "null" in cond.lower() or "size()" in cond.lower():
                show_branch = True

            if show_branch:
                cond_clean = cond.strip()
                if len(cond_clean) > 80:
                    cond_clean = cond_clean[:77] + "…"
                add_item(f"분기: if ({cond_clean}) (L{line_num})")
                continue

        # 4. 클라이언트 콜백 / 폼 / 스토어 / 이벤트 발화 / 팝업 관련
        if not is_server:
            # fireEvent(new XxxEvent(...))
            m_fire = re.search(r'fireEvent\s*\(\s*new\s+(\w+Event)\s*\(([^)]*)\)', s)
            if m_fire:
                add_item(f"fireEvent: new {m_fire.group(1)}({m_fire.group(2).strip()}) (L{line_num})")
                continue

            # 팝업/모달 open/show
            m_open = re.search(r'(?:this\.)?(\w+)\.(open|show)\s*\(([^)]*)\)', s)
            if m_open and m_open.group(1) not in ("this", "super", "window", "Window"):
                add_item(f"{m_open.group(1)}.{m_open.group(2)}({m_open.group(3).strip()}) (L{line_num})")
                continue

            # executeService / callService 래퍼 호출
            m_exec = re.search(r'\b(executeService|callService)\s*\(([^;]+)\)', s)
            if m_exec:
                add_item(f"{m_exec.group(1)}({m_exec.group(2).strip()}) (L{line_num})")
                continue

            # result.getResult(\d+) / result.getResult()
            m_get_res = re.search(r'result\.getResult\s*\(\s*(\d*)\s*\)', s)
            if m_get_res:
                arg_val = m_get_res.group(1)
                add_item(f"result.getResult({arg_val}) (L{line_num})")
                continue

            # editDriver.edit(X)
            m_ed_edit = re.search(r'editDriver\.edit\s*\(', s)
            if m_ed_edit:
                p_open = s.find("(", m_ed_edit.start())
                p_close = paren_end(s, p_open)
                arg_x = s[p_open + 1 : p_close].strip() if p_close > p_open else s[m_ed_edit.end():].rstrip(";").rstrip(")")
                add_item(f"editDriver.edit({arg_x}) (L{line_num})")
                continue

            # \w+\.getStore\(\)\.(update|add|remove|replaceAll|clear)\(
            m_store = re.search(r'(\w+)\.getStore\(\)\.(update|add|remove|replaceAll|clear)\s*\(', s)
            if m_store:
                p_open = s.find("(", m_store.start() + len(m_store.group(1)) + len(".getStore()." + m_store.group(2)))
                p_close = paren_end(s, p_open)
                full_call = s[m_store.start(): p_close + 1] if p_close > p_open else s[m_store.start():].rstrip(";")
                add_item(f"{full_call} (L{line_num})")
                continue

            # (\w+)\.setValue\(\s*([^)]+)\s*\) (this. 제거)
            m_set_v = re.search(r'(?:this\.)?(\w+)\.setValue\s*\(\s*([^)]+)\s*\)', s)
            if m_set_v:
                add_item(f'{m_set_v.group(1)}.setValue({m_set_v.group(2).strip()}) (L{line_num})')
                continue

            # 위젯 값 읽기: var = widget.getValue()
            m_get_v = re.search(r'(\w+)\s*=\s*(?:this\.)?(\w+)\.getValue\s*\(\s*\)', s)
            if m_get_v:
                add_item(f"{m_get_v.group(1)} ← {m_get_v.group(2)}.getValue() (L{line_num})")
                continue

            # ^(\w+)\s*=\s*"([^"]*)"\s*; (지역 변수에 문자열 리터럴 대입)
            m_var_assign = re.search(r'^\s*(\w+)\s*=\s*"([^"]*)"\s*;', s)
            if m_var_assign:
                add_item(f'{m_var_assign.group(1)} = "{m_var_assign.group(2)}" (L{line_num})')
                continue

        # 5. 클라이언트 서비스 호출 (ServiceRequest("...") + addParam)
        m_srv = re.search(r'new\s+ServiceRequest\s*\(\s*"([a-z]\w*\.[A-Z]\w*\.\w+)"\s*\)', s)
        if m_srv:
            srv_name = m_srv.group(1)
            params = []
            for j in range(idx + 1, min(idx + 12, len(lines))):
                sub_line = lines[j].strip()
                m_param = re.search(r'addParam\s*\(\s*"([^"]+)"\s*,\s*', sub_line)
                if m_param:
                    p_k = m_param.group(1)
                    arg_start = m_param.end()
                    open_paren = sub_line.find("(", m_param.start())
                    close_paren = paren_end(sub_line, open_paren)
                    if close_paren > arg_start:
                        p_v = sub_line[arg_start:close_paren].strip()
                    else:
                        p_v = sub_line[arg_start:].rstrip(";").rstrip(")")
                    params.append(f"{p_k}={p_v}")
                if "execute(" in sub_line or "new ServiceCall" in sub_line:
                    break
            param_str = f"({', '.join(params)})" if params else ""
            add_item(f"서비스 {srv_name}{param_str} (L{line_num})")
            continue

        # 기타 서비스 호출 문자열 (ex: "org.Org00_OrgInfo.selectByOrgCodeId")
        m_srv_raw = re.search(r'"([a-z]\w*\.[A-Z]\w*\.\w+)"', s)
        if m_srv_raw and not is_server:
            add_item(f"서비스 {m_srv_raw.group(1)} (L{line_num})")
            continue

        # GridInsertRow / insertRow / deselectAll
        if "deselectAll()" in s:
            add_item(f"grid.getSelectionModel().deselectAll() (L{line_num})")
            continue
        if "insertRow" in s and ("GridInsertRow" in s or ".insertRow" in s):
            add_item(f"GridInsertRow.insertRow (L{line_num})")
            continue

        # addChange
        m_chg = re.search(r'addChange\s*\(', s)
        if m_chg:
            p_open = s.find("(", m_chg.start())
            p_close = paren_end(s, p_open)
            raw_args = s[m_chg.end():p_close] if p_close > m_chg.end() else s[m_chg.end():].rstrip(";").rstrip(")")
            args = split_args(raw_args)
            if len(args) >= 2:
                prop_arg = args[0].strip()
                val_arg = args[1].strip()
                prop_m = re.search(r"\.(\w+)\s*(?:\(\s*\))?", prop_arg)
                prop_name = prop_m.group(1) if prop_m else prop_arg
                add_item(f"addChange {prop_name} ← {val_arg} (L{line_num})")
            elif len(args) == 1:
                add_item(f"addChange {args[0]} (L{line_num})")
            continue

        # 서버 전용: getSeq, UpdateDataModel, setXxx("리터럴"), sqlSession, commit
        if is_server:
            if "getSeq" in s:
                m_seq = re.search(r'(\w+)\s*=\s*(?:.*getSeq|.*dbConfig\.getSeq)', s)
                var = m_seq.group(1) if m_seq else "seq"
                add_item(f"getSeq ({var}) (L{line_num})")
                continue

            m_udm = re.search(r'new\s+UpdateDataModel[^\n]*\(\s*["\']?(\w+)["\']?\s*\)', s)
            if m_udm:
                add_item(f"UpdateDataModel({m_udm.group(1)}) (L{line_num})")
                continue
            m_updm = re.search(r'\.updateModel\s*\([^,]+,[^,]+,\s*["\'](\w+)["\']', s)
            if m_updm:
                add_item(f"UpdateDataModel({m_updm.group(1)}) (L{line_num})")
                continue

            m_set_val = re.search(r'\.set([A-Z]\w*)\s*\(\s*"([^"]+)"\s*\)', s)
            if m_set_val:
                prop = m_set_val.group(1)
                prop_name = prop[0].lower() + prop[1:]
                add_item(f'{prop_name}="{m_set_val.group(2)}" (L{line_num})')
                continue

            m_sql_expr = re.search(
                r'sqlSession\.\w+\s*\(\s*(?:([a-zA-Z0-9_]+)\s*\+\s*)?["\']([^"\']+)["\']',
                s,
            )
            if m_sql_expr:
                prefix_var = m_sql_expr.group(1)
                sql_id = m_sql_expr.group(2)
                target_sql_key = ""
                if prefix_var:
                    if prefix_var in class_constants:
                        full_sql = f"{class_constants[prefix_var]}.{sql_id.lstrip('.')}"
                        target_sql_key = full_sql
                        item_desc = f"sqlSession: {full_sql} (L{line_num})"
                    else:
                        target_sql_key = sql_id.lstrip(".")
                        item_desc = f"sqlSession: {prefix_var} + '{sql_id}' (L{line_num})"
                else:
                    target_sql_key = sql_id
                    item_desc = f"sqlSession: {sql_id} (L{line_num})"

                warn_missing = ""
                if src_root:
                    try:
                        from yunhee.tools.as_is.mybatis_render import get_all_statements

                        stmts = get_all_statements(src_root)
                        if target_sql_key and target_sql_key not in stmts and not any(k.endswith(f".{target_sql_key}") for k in stmts):
                            warn_missing = " ⚠ 매퍼에 SQL 없음 — 원본에서도 실패"
                    except Exception:  # noqa: BLE001, S110
                        pass

                add_item(f"{item_desc}{warn_missing}")
                continue

            if "commit()" in s:
                add_item(f"commit() (L{line_num})")
                continue

        # 콜백 닫힘 체크
        if not is_server and in_callback and seen_callback_brace and callback_depth <= 0:
            in_callback = False

    # 서버 전용 결과 반환 여부 검증 (A-4)
    if is_server:
        has_result = any(fn in body for fn in (
            "result.setResult(",
            "result.setRetrieveResult(",
            "result.addResult(",
            "result.setList(",
        ))
        brace_pos = body.find("{")
        body_content = body[brace_pos:] if brace_pos != -1 else body
        has_delegate = bool(re.search(r'(?:,\s*result\s*\)|\(\s*result\s*\))', body_content))

        sig_header = body[:brace_pos] if brace_pos != -1 else ""
        is_void = bool(re.search(r"\bvoid\b", sig_header))
        delegation = _detect_delegation(body)
        has_set_status = "result.setStatus" in body

        if not has_result and not has_delegate:
            if is_void and not has_set_status and delegation:
                items.append("ℹ 위임 전용")
            else:
                items.append("⚠ 결과 없음: result.setResult/setRetrieveResult 호출이 없다 — 클라이언트가 result.getResult(…)를 읽으면 실패한다")

        if follow and delegation and src_root:
            d_cls, d_meth = delegation
            app = find_app(src_root) or src_root
            d_files = list(app.rglob(f"{d_cls}.java"))
            if not d_files:
                d_files = [f for f in src_root.rglob(f"{d_cls}.java") if "target" not in f.parts]
            if d_files:
                try:
                    d_text = d_files[0].read_text(encoding="utf-8", errors="replace")
                    d_blocks = _find_method_blocks(d_text, d_meth)
                    if d_blocks:
                        _, db_start, db_end, db_body = d_blocks[0]
                        db_sqls = []
                        for sm in re.finditer(r'sqlSession\.\w+\s*\(\s*(?:([a-zA-Z0-9_]+)\s*\+\s*)?["\']([^"\']+)["\']', db_body):
                            ln = db_start + db_body.count("\n", 0, sm.start())
                            db_sqls.append((sm.group(2), ln))
                        items.append(f"→ {d_cls}.{d_meth} (L{db_start}-{db_end})")
                        for sql_id, ln in db_sqls:
                            items.append(f"  - sqlSession: {sql_id} (L{ln})")

                        # d_body에서 내부 서브메서드 호출 탐색 (2단계)
                        _, d_bare = strip_java(d_text)
                        d_methods = find_methods(d_bare)
                        class_sub_methods = {m[0]: m for m in d_methods if m[0] not in (d_cls, d_meth)}
                        sub_called = []
                        for m_name in class_sub_methods:
                            if re.search(rf"\b{re.escape(m_name)}\s*\(", db_body):
                                sub_called.append(m_name)

                        for sm_name in sub_called:
                            sm_blocks = _find_method_blocks(d_text, sm_name)
                            if sm_blocks:
                                _, smb_start, smb_end, smb_body = sm_blocks[0]
                                sm_sqls = []
                                for sm in re.finditer(r'sqlSession\.\w+\s*\(\s*(?:([a-zA-Z0-9_]+)\s*\+\s*)?["\']([^"\']+)["\']', smb_body):
                                    ln = smb_start + smb_body.count("\n", 0, sm.start())
                                    sm_sqls.append((sm.group(2), ln))
                                if sm_sqls:
                                    items.append(f"  하위 {sm_name} (L{smb_start}-{smb_end}):")
                                    for sql_id, ln in sm_sqls:
                                        items.append(f"    - sqlSession: {sql_id} (L{ln})")
                except Exception:  # noqa: BLE001, S110
                    pass

    return items


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if opts is None:
        opts = {}

    if obj.get("multi_methods"):
        blocks = [
            render({k: v for k, v in item.items() if k != "multi_methods"}, fmt=fmt, opts=opts)
            for item in obj["multi_methods"]
        ]
        return "\n\n".join(blocks)

    rel_file = obj["rel"]
    start_line = obj["start"]
    end_line = obj["end"]
    body = obj["body"]

    if fmt == "code":
        if obj.get("multi_candidates"):
            header_lines = [f"#{i}: {desc}" for i, desc in enumerate(obj["cand_descs"], 1)]
            body_blocks = [
                f"// #{i} (L{c['start']}-{c['end']})\n{c['body']}"
                for i, c in enumerate(obj["multi_candidates"], 1)
            ]
            return "\n".join(header_lines) + "\n\n" + "\n".join(body_blocks)
        return f"{rel_file}:{start_line}-{end_line}\n{body}"

    # 기본 md 요약: caller_event가 있으면 기본으로 붙임
    header_event = ""
    if obj.get("caller_event"):
        header_event = f"  ← [{obj['caller_event']}]"
    cls_name = obj["cls"]
    meth_name = obj["method"]
    is_server = obj["is_server"]
    follow = bool(opts.get("follow") or obj.get("follow", False))

    summary_items = _summarize_body(
        body,
        start_line,
        is_server,
        file_text=obj.get("file_text", ""),
        src_root=obj.get("src_root"),
        follow=follow,
    )

    out = [f"{cls_name}.{meth_name}()  {rel_file}:{start_line}-{end_line}{header_event}"]
    if obj.get("chain_summary"):
        out.insert(0, f"→ {obj['chain_summary']}\n")

    if summary_items:
        for it in summary_items:
            out.append(f"- {it}")
    else:
        first_lines = [line.strip() for line in body.splitlines()[1:4] if line.strip()]
        for l in first_lines:
            out.append(f"- {l}")

    if opts.get("raw"):
        out.append(f"\n#### 원문 코드 (`{rel_file}:{start_line}-{end_line}`)\n```java\n{body}\n```")

    return "\n".join(out)
