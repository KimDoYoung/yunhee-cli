"""AS-IS 메서드 본문 분석 도구 (클라이언트·서버)."""

import re
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import AmbiguousTargetError, resolve_as_is_paths
from yunhee.tools.as_is.src_indexer import find_app

NAME = "method"
DESCRIPTION = "AS-IS 메서드 본문 및 호출 흐름 분석 (클라이언트·서버)"
TARGET_HELP = "<클래스>.<메서드>[#n]"
FORMATS = ("md", "code")
EXAMPLES = [
    "yunhee analysis method Emp03_TabPage_Trans.insertRow",
    "yunhee analysis method Emp00_TransInfo.update --server -o code",
    "yunhee analysis method Org00_Lookup_SelectSingle.open#3",
]


def _find_method_blocks(full_text: str, target_method: str) -> list[tuple[str, int, int, str]]:
    """자바 소스에서 target_method 이름의 메서드들을 찾아 (시그니처, 시작줄, 끝줄, 본문) 목록을 반환한다."""
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


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """대상 메서드를 찾아 해석한다."""
    target_clean = target.strip()
    idx_choice = None
    if "#" in target_clean:
        target_clean, num_str = target_clean.split("#", 1)
        try:
            idx_choice = int(num_str)
        except ValueError:
            pass

    if "." not in target_clean:
        raise ValueError(f"올바른 형식(<클래스>.<메서드>)으로 입력해 주세요: {target}")

    cls_name, meth_name = target_clean.rsplit(".", 1)

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
                "rel": str(rel),
                "cls": cls_name,
                "method": meth_name,
                "sig": sig,
                "start": s_line,
                "end": e_line,
                "body": body,
                "is_server": "server" in f.parts,
                "caller_event": caller_event,
            })

    if not candidates:
        raise ValueError(f"{cls_name} 에서 메서드 '{meth_name}'을 찾을 수 없습니다.")

    if len(candidates) > 1 and idx_choice is None:
        cand_descs = [f"{c['rel']}:{c['start']} {c['sig']}" for c in candidates]
        raise AmbiguousTargetError(cand_descs, target)

    if idx_choice is not None:
        if idx_choice < 1 or idx_choice > len(candidates):
            raise ValueError(f"선택한 번호 #{idx_choice}가 범위를 벗어났습니다 (1~{len(candidates)})")
        return candidates[idx_choice - 1]

    return candidates[0]


def _summarize_body(body: str, start_line: int, is_server: bool) -> list[str]:
    """메서드 본문을 파싱하여 중요 작업 흐름을 요약한다."""
    items = []
    lines = body.splitlines()

    for idx, line in enumerate(lines):
        line_num = start_line + idx
        s = line.strip()

        # 메시지 / alert
        m_msg = re.search(r'new\s+SimpleMessage\s*\(\s*"([^"]+)"', s)
        if m_msg:
            items.append(f'SimpleMessage "{m_msg.group(1)}" (L{line_num})')
            continue
        m_alert = re.search(r'alert\s*\(\s*"([^"]+)"', s)
        if m_alert:
            items.append(f'alert "{m_alert.group(1)}" (L{line_num})')
            continue
        if '"사원을 먼저 선택해주세요"' in s:
            items.append(f'경고: "사원을 먼저 선택해주세요" (L{line_num})')
            continue
        m_html = re.search(r'new\s+HtmlMessageBox\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', s)
        if m_html:
            items.append(f'HtmlMessageBox "{m_html.group(1)}", "{m_html.group(2)}" (L{line_num})')
            continue
        if "setEmptyText(" in s:
            m_empty = re.search(r'setEmptyText\s*\(\s*"([^"]+)"', s)
            if m_empty:
                items.append(f'setEmptyText "{m_empty.group(1)}" (L{line_num})')
                continue

        # 클라이언트 서비스 호출 (ServiceRequest("...") + addParam)
        m_srv = re.search(r'new\s+ServiceRequest\s*\(\s*"([a-z]\w*\.[A-Z]\w*\.\w+)"\s*\)', s)
        if m_srv:
            srv_name = m_srv.group(1)
            params = []
            for j in range(idx + 1, min(idx + 12, len(lines))):
                sub_line = lines[j].strip()
                m_param = re.search(r'addParam\s*\(\s*"([^"]+)"\s*,\s*([^)]+)\)', sub_line)
                if m_param:
                    p_k = m_param.group(1)
                    p_v = m_param.group(2).strip().rstrip(";")
                    params.append(f"{p_k}={p_v}")
                if "execute(" in sub_line or "new ServiceCall" in sub_line:
                    break
            param_str = f"({', '.join(params)})" if params else ""
            items.append(f"서비스 {srv_name}{param_str} (L{line_num})")
            continue

        # 기타 서비스 호출 문자열 (ex: "org.Org00_OrgInfo.selectByOrgCodeId")
        m_srv_raw = re.search(r'"([a-z]\w*\.[A-Z]\w*\.\w+)"', s)
        if m_srv_raw and not is_server:
            items.append(f"서비스 {m_srv_raw.group(1)} (L{line_num})")
            continue

        # GridInsertRow / insertRow / deselectAll
        if "deselectAll()" in s:
            items.append(f"grid.getSelectionModel().deselectAll() (L{line_num})")
            continue
        if "insertRow" in s and ("GridInsertRow" in s or ".insertRow" in s):
            items.append(f"GridInsertRow.insertRow (L{line_num})")
            continue

        # addChange
        m_chg = re.search(r'addChange\s*\(\s*([^)]+)\)', s)
        if m_chg:
            items.append(f"addChange {m_chg.group(1)} (L{line_num})")
            continue

        # 서버 전용: getSeq, UpdateDataModel, setXxx("리터럴"), sqlSession, commit
        if is_server:
            if "getSeq" in s:
                m_seq = re.search(r'(\w+)\s*=\s*(?:.*getSeq|.*dbConfig\.getSeq)', s)
                var = m_seq.group(1) if m_seq else "seq"
                items.append(f"getSeq ({var}) (L{line_num})")
                continue

            # UpdateDataModel: new UpdateDataModel 또는 updateModel(sqlSession, ..., "table", ...)
            m_udm = re.search(r'new\s+UpdateDataModel[^\n]*\(\s*["\']?(\w+)["\']?\s*\)', s)
            if m_udm:
                items.append(f"UpdateDataModel({m_udm.group(1)}) (L{line_num})")
                continue
            m_updm = re.search(r'\.updateModel\s*\([^,]+,[^,]+,\s*["\'](\w+)["\']', s)
            if m_updm:
                items.append(f"UpdateDataModel({m_updm.group(1)}) (L{line_num})")
                continue

            # 고정값 대입: transModel.setTransCode("100") -> transCode="100"
            m_set_val = re.search(r'\.set([A-Z]\w*)\s*\(\s*"([^"]+)"\s*\)', s)
            if m_set_val:
                prop = m_set_val.group(1)
                prop_name = prop[0].lower() + prop[1:]
                items.append(f'{prop_name}="{m_set_val.group(2)}" (L{line_num})')
                continue

            # sqlSession 호출
            # sqlSession.update("emp02_others.insert", ...)
            # sqlSession.selectList(mapperName + ".selectById", ...)
            m_sql_expr = re.search(
                r'sqlSession\.\w+\s*\(\s*(?:([a-zA-Z0-9_]+)\s*\+\s*)?["\']([^"\']+)["\']',
                s,
            )
            if m_sql_expr:
                prefix_var = m_sql_expr.group(1)
                sql_id = m_sql_expr.group(2)
                if prefix_var:
                    items.append(f"sqlSession: {prefix_var} + '{sql_id}' (L{line_num})")
                else:
                    items.append(f"sqlSession: {sql_id} (L{line_num})")
                continue

            if "commit()" in s:
                items.append(f"commit() (L{line_num})")
                continue

        # 조건 분기 (목록 선택 없음 등)
        if s.startswith(("if (", "if(")):
            cond = s[s.find("(") + 1 : s.rfind(")")]
            if "selected" in cond.lower() or "null" in cond.lower() or "size()" in cond.lower():
                items.append(f"분기: if ({cond}) (L{line_num})")
                continue

    return items


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if opts is None:
        opts = {}

    rel_file = obj["rel"]
    start_line = obj["start"]
    end_line = obj["end"]
    body = obj["body"]

    if fmt == "code":
        return f"{rel_file}:{start_line}-{end_line}\n{body}"

    # 기본 md 요약: caller_event가 있으면 기본으로 붙임
    header_event = ""
    if obj.get("caller_event"):
        header_event = f"  ← [{obj['caller_event']}]"
    cls_name = obj["cls"]
    meth_name = obj["method"]
    is_server = obj["is_server"]

    summary_items = _summarize_body(body, start_line, is_server)

    out = [f"{cls_name}.{meth_name}()  {rel_file}:{start_line}-{end_line}{header_event}"]
    if summary_items:
        for it in summary_items:
            out.append(f"- {it}")
    else:
        first_lines = [line.strip() for line in body.splitlines()[1:4] if line.strip()]
        for l in first_lines:
            out.append(f"- {l}")

    return "\n".join(out)
