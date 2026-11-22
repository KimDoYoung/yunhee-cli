"""test-scenario-skel: 업무분석 이벤트 문서로부터 파이썬 시나리오 테스트 뼈대 자동 생성."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

import psycopg
import yaml

from yunhee import config
from yunhee.tools.base import ToolResult
from yunhee.tools.biz.endpoints import collect_endpoints
from yunhee.tools.sql_runner import get_connection_string

_ENDPOINTS_CACHE: dict[str, list[dict[str, Any]]] = {}


def _get_cached_endpoints(root_dir: Path) -> list[dict[str, Any]]:
    key = str(root_dir.resolve())
    if key not in _ENDPOINTS_CACHE:
        _ENDPOINTS_CACHE[key] = collect_endpoints(root_dir=root_dir)
    return _ENDPOINTS_CACHE[key]

DEFAULT_ROLE_MAP = {
    "KFS 관리자": "kfs",
    "KFS관리자": "kfs",
    "KFS": "kfs",
    "직원": "401",
    "사원": "401",
    "팀장": "301",
    "과장": "301",
    "경영관리": "301",
    "경영관리팀": "301",
    "인사부": "301",
    "부장": "201",
    "본격": "201",
    "사장": "100",
    "대표이사": "100",
    "관리자": "admin",
}

ERROR_CODES = (
    "INVALID_INPUT",
    "ACCESS_DENIED",
    "DUPLICATE_DATA",
    "DATA_NOT_FOUND",
    "FORBIDDEN",
    "UNAUTHORIZED",
    "BAD_REQUEST",
)


class _DuplicateKeyStepLoader(yaml.SafeLoader):
    """YAML 매핑에서 중복 키(예: 한 step 안의 두 번째 api:)를 감지하고 보존하는 커스텀 로더."""

    dup_warnings: list[str]


def _construct_mapping_preserve_dups(loader: _DuplicateKeyStepLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    extra_segments: list[dict[str, Any]] = []
    current_segment: dict[str, Any] = {}

    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        val = loader.construct_object(value_node, deep=deep)
        if key is False and "no" not in mapping:
            key = "no"

        if key in mapping:
            step_no = mapping.get("no", "?")
            loader.dup_warnings.append(f"no {step_no}: '{key}' 키가 중복됨 — 앞 값을 버리지 않고 이어지는 단계로 병합합니다")
            current_segment[str(key)] = val
            if key == "api":
                extra_segments.append(dict(current_segment))
                current_segment = {}
        elif "api" in mapping and key == "actor":
            # 이미 api가 나온 뒤에 등장하는 actor는 이어지는 중복 api 구간의 actor로 보관
            current_segment["actor"] = val
        elif current_segment and key in ("actor", "api", "body", "expect"):
            current_segment[str(key)] = val
            if key == "api":
                extra_segments.append(dict(current_segment))
                current_segment = {}
        else:
            mapping[key] = val

    if current_segment:
        extra_segments.append(current_segment)
    if extra_segments:
        mapping["_extra_segments"] = extra_segments
    return mapping


_DuplicateKeyStepLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_preserve_dups,
)


def _find_event_doc(event_id: str, src_root: Path | None = None) -> Path | None:
    """docs/2-업무분석/biz-event 하위에서 event_id에 일치하는 마크다운 파일 탐색."""
    cand_roots = [
        src_root,
        config.WORK_DIR,
        getattr(config, "TOBE_SRC_DIR", None),
        Path.cwd(),
    ]
    for r in cand_roots:
        if not r:
            continue
        event_dir = r / "docs/2-업무분석/biz-event"
        if event_dir.is_dir():
            for f in sorted(event_dir.rglob(f"{event_id}*.md")):
                if f.is_file():
                    return f.resolve()
        for f in sorted(r.rglob(f"{event_id}*.md")):
            if "biz-event" in str(f) and f.is_file():
                return f.resolve()
    return None


def _find_all_event_docs(target: str | None = None, src_root: Path | None = None) -> list[Path]:
    """도메인(예: EMP) 또는 전체 이벤트 마크다운 파일 목록을 반환한다."""
    cand_roots = [
        src_root,
        config.WORK_DIR,
        getattr(config, "TOBE_SRC_DIR", None),
        Path.cwd(),
    ]
    for r in cand_roots:
        if not r:
            continue
        event_dir = r / "docs/2-업무분석/biz-event"
        if not event_dir.is_dir():
            continue
        if target:
            dom_dir = event_dir / target.upper()
            if dom_dir.is_dir():
                return sorted(f for f in dom_dir.glob("*-BZ-*.md") if f.is_file())
            matched = sorted(f for f in event_dir.rglob(f"{target.upper()}*.md") if f.is_file())
            if matched:
                return matched
        return sorted(f for f in event_dir.rglob("*-BZ-*.md") if f.is_file())
    return []


def _split_top_level_comma(s: str) -> list[str]:
    """중괄호 {}, 대괄호 [], 따옴표 내부의 쉼표를 무시하고 최상위 쉼표로만 문자열을 나눈다."""
    parts: list[str] = []
    curr: list[str] = []
    depth_brace = 0
    depth_bracket = 0
    in_quote: str | None = None

    for ch in s:
        if in_quote:
            curr.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            curr.append(ch)
        elif ch == "{":
            depth_brace += 1
            curr.append(ch)
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
            curr.append(ch)
        elif ch == "[":
            depth_bracket += 1
            curr.append(ch)
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
            curr.append(ch)
        elif ch == "," and depth_brace == 0 and depth_bracket == 0:
            tok = "".join(curr).strip()
            if tok:
                parts.append(tok)
            curr = []
        else:
            curr.append(ch)

    last = "".join(curr).strip()
    if last:
        parts.append(last)
    return parts


def _preprocess_yaml_text(yaml_content: str) -> str:
    """YAML 플로우 시퀀스 및 API 줄 끝의 # 주석이 YAML 파서에 의해 잘리지 않도록 따옴표로 보호한다."""
    def repl_api_list(m: re.Match[str]) -> str:
        inner = m.group(1)
        tokens = _split_top_level_comma(inner)
        fixed_tokens: list[str] = []
        for t in tokens:
            t_str = t.strip()
            if not t_str:
                continue
            if t_str.startswith(('"', "'")) and t_str.endswith(('"', "'")):
                fixed_tokens.append(t_str)
            else:
                escaped = t_str.replace("\\", "\\\\").replace('"', '\\"')
                fixed_tokens.append(f'"{escaped}"')
        return f"api: [{', '.join(fixed_tokens)}]"

    text = re.sub(r"api:\s*\[([^\n\]]+)\]", repl_api_list, yaml_content)

    # 단일 api: 줄이나 목록 - GET/POST/PUT/DELETE/PATCH 줄에 # 주석이나 중괄호가 있으면 문자열로 감싸서 주석 보존
    out_lines: list[str] = []
    for line in text.splitlines():
        m_single = re.match(r"^(\s*(?:api:\s+|-\s+))((?:GET|POST|PUT|DELETE|PATCH)\s+.+)$", line)
        if m_single:
            prefix, rest = m_single.group(1), m_single.group(2).strip()
            if not (rest.startswith(('"', "'")) and rest.endswith(('"', "'"))) and ("#" in rest or "{" in rest or ":" in rest):
                escaped = rest.replace("\\", "\\\\").replace('"', '\\"')
                line = f'{prefix}"{escaped}"'
        out_lines.append(line)

    return "\n".join(out_lines)


def _parse_doc_metadata(text: str) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """문서의 '누가' 행에서 역할->사번 매핑을, '따라 하기' 표에서 단계번호->(누가, 설명)을 추출한다."""
    role_map = dict(DEFAULT_ROLE_MAP)
    step_guides: dict[str, tuple[str, str]] = {}

    # 1. | 누가 | 직원(`kalpa/401/...`) -> 팀장 `kalpa/301` |
    who_m = re.search(r"\|\s*누가\s*\|\s*([^\n|]+)", text)
    if who_m:
        who_line = who_m.group(1)
        for role_ko in ("직원", "사원", "팀장", "과장", "부장", "사장", "대표이사", "경영관리팀", "경영관리", "인사부"):
            rm = re.search(rf"{role_ko}[^0-9\n]*?(?:[a-z]+/)?(\d{{3}})\b", who_line)
            if rm:
                role_map[role_ko] = rm.group(1)

    # 2. ## 따라 하기 표 파싱: | 단계 | 누가 | 화면 | 누르는 것 · 입력하는 것 | ... |
    for m in re.finditer(r"^\|\s*([0-9a-zA-Z~]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|", text, re.MULTILINE):
        st_no = m.group(1).strip()
        who_cell = m.group(2).strip()
        action_cell = m.group(4).strip()
        if st_no == "단계" or st_no.startswith("---"):
            continue
        if who_cell in ("〃", '"', "''", ""):
            who_cell = ""
        # 마크다운 서식 정리
        clean_desc = re.sub(r"\*\*([^*]+)\*\*", r"\1", action_cell)
        clean_desc = re.sub(r"`([^`]+)`", r"\1", clean_desc).strip()
        if len(clean_desc) > 48:
            clean_desc = clean_desc[:45] + "..."
        step_guides[st_no] = (who_cell, clean_desc)

    return role_map, step_guides


def _safe_int(val: Any, default: int = 1) -> int:
    """'+1(처음이면)', '>=1' 같은 문자열에서도 첫 정수를 안전하게 추출한다."""
    if isinstance(val, int):
        return val
    m = re.search(r"([+-]?\d+)", str(val))
    return int(m.group(1)) if m else default


def _resolve_role_to_user(text: str, role_map: dict[str, str]) -> str | None:
    """텍스트 안에 명시된 사번(100, 201, 301, 401 등)이나 역할어를 찾아 사번을 반환한다."""
    m_num = re.search(r"\b(100|201|202|301|302|401|402|admin)\b", text)
    if m_num:
        return m_num.group(1)
    for role_ko, emp_no in role_map.items():
        if role_ko in text:
            return emp_no
    return None


def _parse_api_line(api_str: str, prev_base_path: str) -> dict[str, Any]:
    """API 한 줄에서 method, path, inline_body, comment, expected_status를 분리한다.

    자리표시(<상신된 행> 등) 안의 공백에서 경로가 잘리지 않도록 보호한다.
    """
    # 1. # 주석 분리
    if "#" in api_str:
        main_part, comment = api_str.split("#", 1)
        main_part = main_part.strip()
        comment = comment.strip()
    else:
        main_part = api_str.strip()
        comment = ""

    # 2. 화살표 상태코드 분리 (예: POST /copy → 403)
    expected_status: int | None = None
    arrow_m = re.search(r"(?:→|->)\s*(\d{3})\b(.*)$", main_part)
    if arrow_m:
        expected_status = int(arrow_m.group(1))
        extra_note = arrow_m.group(2).strip()
        if extra_note and not comment:
            comment = extra_note
        main_part = main_part[:arrow_m.start()].strip()

    # 3. 인라인 본문 분리 (예: PUT /api/v1/emp/eval-list-stds/fix { fixYn: false })
    inline_body_str = ""
    # 경로 안의 {id}와 인라인 본문 { key: val } 구분: 공백 뒤에 오는 { ... }
    inline_m = re.search(r"\s+(\{[^{}]*:?[^{}]*\})\s*$", main_part)
    if inline_m:
        inline_body_str = inline_m.group(1).strip()
        main_part = main_part[:inline_m.start()].strip()

    # 4. METHOD와 path 분리
    m_verb = re.match(r"^(GET|POST|PUT|DELETE|PATCH)\s+(.+)$", main_part, re.IGNORECASE)
    if not m_verb:
        return {"valid": False, "raw": api_str, "comment": comment}

    method = m_verb.group(1).upper()
    raw_path = m_verb.group(2).strip()

    # "DELETE /api/v1/emp/benefit-infos?companyId=<kalpa> / ?companyId=0" 처럼 슬래시 대안 표기 정리
    if " / ?" in raw_path:
        raw_path = raw_path.split(" / ?")[0].strip()

    # 상대 경로/축약 경로 보정 (예: /copy, ?companyId=0, own company)
    is_relative = not raw_path.startswith("/api/")
    if is_relative:
        if raw_path.startswith("?") and prev_base_path:
            raw_path = prev_base_path + raw_path
        elif raw_path.startswith("/") and prev_base_path:
            raw_path = prev_base_path.rstrip("/") + raw_path
        elif prev_base_path:
            raw_path = prev_base_path

    base_only = raw_path.split("?")[0]
    return {
        "valid": True,
        "method": method,
        "path": raw_path,
        "base_path": prev_base_path if is_relative else (base_only if base_only.startswith("/api/") else prev_base_path),
        "inline_body": inline_body_str,
        "comment": comment,
        "expected_status": expected_status,
    }


def _parse_comment_json_like(text: str) -> dict[str, Any] | None:
    """주석이나 인라인의 '{ publicYn: true }' 또는 '{ apprId }' 같은 표현을 파싱한다."""
    # → 앞부분의 { ... } 우선
    before_arrow = text.split("→")[0].split("->")[0]
    m = re.search(r"\{([^{}]+)\}", before_arrow)
    if not m:
        return None
    inner = m.group(1).strip()
    if not inner:
        return None

    result: dict[str, Any] = {}
    for tok in _split_top_level_comma(inner):
        if ":" in tok:
            k, v = tok.split(":", 1)
            k = k.strip().strip("\"'")
            v = v.strip()
            try:
                parsed_v = yaml.safe_load(v)
            except Exception:  # noqa: BLE001
                parsed_v = v
            result[k] = parsed_v
        else:
            # { apprId } 또는 { benefitIds, apprId } 축약 표기
            k = tok.strip().strip("\"'")
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                result[k] = f"__VAR_REF__:{k}"
    return result if result else None


def _get_table_filter_col(table_name: str, db_name: str = "asseterpdb") -> tuple[str | None, str]:
    """테이블의 행 수 확인 쿼리에 쓸 필터 열(person_id, company_id, parent_id)을 찾는다."""
    prefix = table_name.split("_")[0] if "_" in table_name else table_name
    conn_str = get_connection_string(db_name)
    cols: set[str] = set()
    if conn_str:
        try:
            with psycopg.connect(conn_str, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                      FROM information_schema.columns
                     WHERE table_schema = 'public'
                       AND table_name = %s
                    """,
                    (table_name.lower(),),
                )
                cols = {r[0].lower() for r in cur.fetchall()}
        except Exception:  # noqa: BLE001, S110
            pass

    order = (
        (("_parent_id", "parent"), ("_person_id", "person"), ("_company_id", "company"))
        if "__last_id__" in table_name or "share" in table_name
        else (("_person_id", "person"), ("_company_id", "company"), ("_parent_id", "parent"))
    )
    for suffix, kind in order:
        cand = f"{prefix}{suffix}"
        if cols:
            if cand in cols:
                return cand, kind
        elif kind != "parent" or "share" in table_name:
            return cand, kind
    return None, "none"


def generate_scenario_code(
    event_id: str,
    company: str = "kova",
    module: str | None = None,
    src_root: Path | None = None,
) -> ToolResult:
    """이벤트 문서의 YAML 시나리오 데이터를 분석하여 실행 가능한 파이썬 함수 코드를 생성한다."""
    doc_path = _find_event_doc(event_id, src_root)
    if not doc_path or not doc_path.is_file():
        return ToolResult(ok=False, error=f"업무분석 이벤트 문서를 찾을 수 없습니다: {event_id}")

    text = doc_path.read_text(encoding="utf-8", errors="replace")

    title_m = re.search(r"^#\s+([^\n]+)", text, re.MULTILINE)
    title_raw = title_m.group(1).strip() if title_m else event_id
    scenario_desc = re.sub(r"^[A-Z]+-BZ-\d+\s*[—\-:]?\s*", "", title_raw).strip()

    yaml_match = re.search(
        r"<details>\s*<summary>\s*시나리오\s*데이터.*?</summary>.*?(```yaml\s*\n.*?\n```)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not yaml_match:
        yaml_match = re.search(r"```yaml\s*\nid:\s*" + re.escape(event_id) + r".*?\n```", text, re.DOTALL)

    if not yaml_match:
        return ToolResult(ok=False, error=f"{doc_path.name} 내에서 '시나리오 데이터' yaml을 찾을 수 없습니다.")

    yaml_block = yaml_match.group(1) if "```yaml" in yaml_match.group(0) else yaml_match.group(0)
    yaml_content = re.sub(r"^```yaml\s*\n|```$", "", yaml_block.strip())
    yaml_content = _preprocess_yaml_text(yaml_content)

    _DuplicateKeyStepLoader.dup_warnings = []
    try:
        data = yaml.load(yaml_content, Loader=_DuplicateKeyStepLoader)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"YAML 파싱 오류 ({doc_path.name}): {exc}")

    dup_warnings = [f"⚠ {event_id} {w}" for w in _DuplicateKeyStepLoader.dup_warnings]
    for dw in dup_warnings:
        sys.stderr.write(f"{dw}\n")

    raw_steps = data.get("steps", []) if isinstance(data, dict) else []
    if not raw_steps:
        return ToolResult(ok=False, error="YAML 내에 steps 항목이 없습니다.")

    # 중복 키(_extra_segments) 및 then: 절을 평탄화하여 순서대로 단계 확장
    steps: list[dict[str, Any]] = []
    for st in raw_steps:
        if not isinstance(st, dict):
            continue
        extra_segs = st.pop("_extra_segments", [])
        then_part = st.pop("then", None)
        steps.append(st)
        base_no = str(st.get("no", ""))
        for seg_idx, seg in enumerate(extra_segs, start=1):
            seg_copy = dict(seg)
            seg_copy.setdefault("no", f"{base_no}-dup{seg_idx}")
            steps.append(seg_copy)
        if then_part:
            if isinstance(then_part, dict):
                t_copy = dict(then_part)
                t_copy.setdefault("no", f"{base_no}-then")
                steps.append(t_copy)
            elif isinstance(then_part, list):
                steps.append({"no": f"{base_no}-then", "api": then_part})

    role_map, step_guides = _parse_doc_metadata(text)

    ev_prefix = event_id.split("-")[0].lower()
    ev_num = "".join(c for c in event_id.split("-")[-1] if c.isdigit())
    mod_name = module or ev_prefix
    func_name = f"{mod_name}_bz_{ev_num}"

    root_dir = src_root or getattr(config, "TOBE_SRC_DIR", None) or config.WORK_DIR
    all_endpoints = _get_cached_endpoints(root_dir)

    def find_endpoint_body_info(method: str, path: str) -> dict[str, Any] | None:
        clean_p = path.split("?")[0].strip()
        for ep in all_endpoints:
            if ep.get("method", "").upper() != method.upper():
                continue
            ep_p = ep.get("path", "")
            pat_str = "^" + re.sub(r"\{[^}]+\}", "[^/?]+", ep_p) + "$"
            try:
                if re.match(pat_str, clean_p):
                    return ep.get("body")
            except re.error:
                pass
        return None

    # 1차 패스: 사용된 모든 계정(사번 및 admin/kfs) 수집
    virtual_users: set[str] = set()
    needs_kfs_admin = False
    needs_tree = False

    def register_actor_dict(act: Any) -> tuple[str | None, bool]:
        nonlocal needs_kfs_admin
        if isinstance(act, dict):
            comp = str(act.get("company", "")).strip()
            usr = str(act.get("user", "")).strip()
            if comp == "admin" and usr == "admin":
                needs_kfs_admin = True
                return "kfs", True
            if usr:
                virtual_users.add(usr)
                return usr, False
        elif isinstance(act, str) and act.strip():
            usr = act.strip()
            virtual_users.add(usr)
            return usr, False
        return None, False

    for st in steps:
        register_actor_dict(st.get("actor"))
        no_raw = str(st.get("no", ""))
        r_usr = _resolve_role_to_user(no_raw, role_map)
        if r_usr and r_usr != "admin":
            virtual_users.add(r_usr)
        apis = st.get("api", [])
        if isinstance(apis, str):
            apis = [apis]
        for a_str in apis:
            if not isinstance(a_str, str):
                continue
            if "classTreeId" in a_str or "/apr/apprs" in a_str:
                needs_tree = True
            if "#" in a_str:
                cmt = a_str.split("#", 1)[1]
                for m_emp in re.finditer(r"\b(100|201|202|301|302|401|402)\b", cmt):
                    virtual_users.add(m_emp.group(1))
        if "dcrClassTreeId" in str(st.get("body", "")) or "classTreeId" in str(st.get("body", "")):
            needs_tree = True

    if not virtual_users and not needs_kfs_admin:
        default_first = role_map.get("직원", "401")
        virtual_users.add(default_first)

    sorted_users = sorted(virtual_users)
    client_inits: list[tuple[str, str]] = []
    if needs_kfs_admin:
        client_inits.append(("kfs", 'Client("admin", "admin", PW)'))
    for u in sorted_users:
        v_name = "adm" if u == "admin" else f"c{u}"
        client_inits.append((v_name, f'Client(COMPANY, "{u}", PW)'))

    def client_var_for(user_key: str) -> str:
        if user_key == "kfs":
            return "kfs"
        if user_key == "admin":
            return "adm"
        return f"c{user_key}"

    lines: list[str] = []
    lines.append(f"def {func_name}(emp):")
    lines.append(f'    sc = Scenario("{event_id}", "{scenario_desc}")')
    lines.append("    try:")
    lhs = ", ".join(k for k, _ in client_inits)
    rhs = ", ".join(v for _, v in client_inits)
    lines.append(f"        {lhs} = {rhs}")
    lines.append("    except Exception as e:")
    lines.append('        sc.check("0", "직원 로그인", False, str(e))')
    lines.append("        return sc")
    lines.append("    cid = company_id()")
    if needs_tree:
        lines.append('    t = tree(cid, "휴가신청")  # 문서분류 (필요 시 분류명 조정)')
    lines.append("")

    # 상태 추적 변수들
    current_actor = "kfs" if (needs_kfs_admin and not sorted_users) else (sorted_users[0] if sorted_users else "401")
    prev_base_path = ""
    known_vars: dict[str, str] = {
        "companyId": "cid",
        "kalpa": "cid",
        "kova": "cid",
        "classTreeId": "t",
    }
    has_opened_appr = False
    unresolved_todos = 0

    def resolve_placeholder_expr(raw_val: str, in_fstring: bool = False) -> tuple[str, str | None]:
        """자리표시 문자열(<402>, <휴가신청서>, <3>, <운용본부> 등)을 파이썬 코드 표현식과 주석으로 변환한다."""
        nonlocal unresolved_todos
        inner = raw_val.strip()
        if inner.startswith("<") and inner.endswith(">"):
            inner = inner[1:-1].strip()

        # 1. 사번 (<401>, <402>, ...)
        if re.match(r"^(100|201|202|301|302|401|402)$", inner):
            expr = f"emp['{inner}']" if in_fstring else f'emp["{inner}"]'
            return expr, None

        # 2. 이미 생성된 앞 단계 변수 (errandId, benefitId, 3 등)
        if inner in known_vars:
            return known_vars[inner], None
        if inner.endswith((",…", ",...")):
            list_var = known_vars.get("__last_list_ids__")
            if list_var:
                return list_var, None
        if ("행" in inner or inner.lower().endswith("id")) and "__last_id__" in known_vars:
            return known_vars["__last_id__"], f"자리표시 <{inner}>"

        # 3. 문서분류 (<휴가신청서>, <휴가/휴가신청>, <A42 분류>, <신청서분류>, <분류>)
        if "분류" in inner or "신청서" in inner or "휴가" in inner:
            return ("t" if needs_tree else 'tree(cid, "휴가신청")'), f"자리표시 <{inner}>"

        # 4. 미해결 자리표시 -> None # TODO <...>
        unresolved_todos += 1
        return "None", f"TODO <{inner}>"

    def replace_path_placeholders(raw_path: str) -> tuple[str, bool, list[str]]:
        """경로 및 쿼리의 {xxxId}, <...>, classTreeId=… 등을 변수 바인딩된 문자열 또는 f-string으로 변환한다."""
        nonlocal unresolved_todos
        uses_fstring = False
        todo_notes: list[str] = []
        out_path = raw_path

        # {xxxId} 치환
        def repl_brace(m: re.Match[str]) -> str:
            nonlocal uses_fstring, unresolved_todos
            key = m.group(1).strip()
            if key in known_vars:
                uses_fstring = True
                return "{" + known_vars[key] + "}"
            if key.endswith("Id") and "__last_id__" in known_vars:
                uses_fstring = True
                return "{" + known_vars["__last_id__"] + "}"
            unresolved_todos += 1
            todo_notes.append(f"TODO {{{key}}}")
            uses_fstring = True
            return "{None}"

        out_path = re.sub(r"\{([^}]*)\}", repl_brace, out_path)

        # classTreeId=… 처리 ({...} 치환 뒤에 수행하여 {t}가 다시 치환되지 않게 함)
        if "classTreeId=…" in out_path or "classTreeId=..." in out_path:
            out_path = out_path.replace("classTreeId=…", "classTreeId={t}").replace("classTreeId=...", "classTreeId={t}")
            uses_fstring = True

        # <...> 치환
        def repl_angle(m: re.Match[str]) -> str:
            nonlocal uses_fstring
            token = m.group(0)
            expr, note = resolve_placeholder_expr(token, in_fstring=True)
            if note:
                todo_notes.append(note)
            uses_fstring = True
            return "{" + expr + "}"

        out_path = re.sub(r"<[^>]+>", repl_angle, out_path)
        return out_path, uses_fstring, todo_notes

    def format_value_code(val: Any) -> tuple[str, str | None]:
        """단일 값을 파이썬 코드 문자열과 선택적 주석으로 변환한다."""
        if isinstance(val, str):
            if val.startswith("__VAR_REF__:"):
                v_key = val.split(":", 1)[1]
                if v_key in known_vars:
                    return known_vars[v_key], None
                if v_key.endswith("Ids") and "__last_id__" in known_vars:
                    return f"[{known_vars['__last_id__']}]", None
                if v_key.endswith("Id") and "__last_id__" in known_vars:
                    return known_vars["__last_id__"], None
                return "None", f"TODO {v_key}"
            if val.startswith("<") and val.endswith(">"):
                return resolve_placeholder_expr(val, in_fstring=False)
            return repr(val), None
        if isinstance(val, list):
            return format_body_structure(val, indent=12)
        if isinstance(val, dict):
            return format_body_structure(val, indent=12)
        return repr(val), None

    def format_body_structure(body_obj: Any, indent: int = 8) -> tuple[str, str | None]:
        """본문 dict/list를 파이썬 코드로 변환한다. 주석이 있거나 길면 멀티라인으로 안전하게 포맷팅한다."""
        if isinstance(body_obj, dict):
            entries: list[tuple[str, str, str | None]] = []
            has_comment = False
            for k, v in body_obj.items():
                v_code, v_note = format_value_code(v)
                if v_note:
                    has_comment = True
                entries.append((str(k), v_code, v_note))

            single_line = "{" + ", ".join(f'"{k}": {vc}' for k, vc, _ in entries) + "}"
            if not has_comment and len(single_line) <= 95:
                return single_line, None

            # 멀티라인 dict: 주석은 반드시 각 줄의 쉼표 뒤에만 배치하여 닫는 }가 주석에 먹히지 않게 함!
            pad = " " * indent
            inner_pad = " " * (indent + 4)
            m_lines = ["{"]
            for k, vc, vnote in entries:
                cmt = f"  # {vnote}" if vnote else ""
                m_lines.append(f'{inner_pad}"{k}": {vc},{cmt}')
            m_lines.append(f"{pad}}}")
            return "\n".join(m_lines), None

        if isinstance(body_obj, list):
            if body_obj == ["ids"] and "__last_id__" in known_vars:
                return f"[{known_vars['__last_id__']}]", None
            item_pairs: list[tuple[str, str | None]] = []
            has_item_comment = False
            for it in body_obj:
                if isinstance(it, (dict, list)):
                    c_str, c_note = format_body_structure(it, indent=indent + 4)
                else:
                    c_str, c_note = format_value_code(it)
                if c_note:
                    has_item_comment = True
                item_pairs.append((c_str, c_note))
            single = "[" + ", ".join(s for s, _ in item_pairs) + "]"
            if not has_item_comment and "\n" not in single and len(single) <= 95:
                return single, None
            pad = " " * indent
            inner_pad = " " * (indent + 4)
            l_lines = ["["]
            for s, note in item_pairs:
                cmt = f"  # {note}" if note else ""
                l_lines.append(f"{inner_pad}{s.lstrip()},{cmt}")
            l_lines.append(f"{pad}]")
            return "\n".join(l_lines), None

        return format_value_code(body_obj)

    for step_item in steps:
        raw_no = step_item.get("no") if "no" in step_item else (step_item.get(False) if False in step_item else "")
        raw_no_str = str(raw_no).strip() if raw_no is not None else ""

        # 번호와 섞인 설명 분리 (예: "6 이후 직원 수정", "2~6 (402 도 같게)")
        if "도 같게" in raw_no_str:
            note_txt = step_item.get("note", "")
            act_u, _ = register_actor_dict(step_item.get("actor"))
            lines.append(f"    # TODO 반복 단계 ({raw_no_str}): 사원 {act_u or '402'} 로 앞 단계 반복 ({note_txt})")
            continue

        no_m = re.match(r"^([0-9a-zA-Z~]+)\s+(.+)$", raw_no_str)
        if no_m:
            step_no = no_m.group(1).strip()
            extra_step_desc = no_m.group(2).strip()
        else:
            step_no = raw_no_str
            extra_step_desc = ""

        # Actor 결정: 1) step.actor 명시 -> 2) 단계 설명 역할어 -> 3) 따라하기 표 역할어 -> 4) 직전 actor 이어받기
        explicit_actor, _ = register_actor_dict(step_item.get("actor"))
        if explicit_actor:
            current_actor = explicit_actor
        elif extra_step_desc:
            role_u = _resolve_role_to_user(extra_step_desc, role_map)
            if role_u:
                current_actor = role_u
        elif step_no in step_guides:
            who_ko, _ = step_guides[step_no]
            role_u = _resolve_role_to_user(who_ko, role_map)
            if role_u:
                current_actor = role_u

        apis = step_item.get("api", [])
        if isinstance(apis, str):
            apis = [apis]
        if not apis:
            if step_item.get("note"):
                lines.append(f"    # {step_no}: {step_item.get('note')}")
            continue

        body_raw = step_item.get("body")
        expect_raw = step_item.get("expect")

        # linkCodeList=A42,A43 쉼표 목록 자동 분할
        expanded_apis: list[str] = []
        for a_str in apis:
            if not isinstance(a_str, str):
                continue
            m_lc = re.search(r"(linkCodeList=)([A-Z0-9]+,[A-Z0-9,]+)", a_str)
            if m_lc:
                for code_tok in m_lc.group(2).split(","):
                    if code_tok.strip():
                        expanded_apis.append(a_str.replace(m_lc.group(0), f"linkCodeList={code_tok.strip()}"))
            else:
                expanded_apis.append(a_str)

        for api_idx, api_str in enumerate(expanded_apis):
            parsed_api = _parse_api_line(api_str, prev_base_path)
            if not parsed_api.get("valid"):
                lines.append(f"    # TODO 단계 {step_no}: {api_str}")
                continue

            method = parsed_api["method"]
            raw_path = parsed_api["path"]
            if parsed_api.get("base_path"):
                prev_base_path = parsed_api["base_path"]
            inline_body_str = parsed_api["inline_body"]
            comment_line = parsed_api["comment"]
            expected_status = parsed_api["expected_status"]

            sub_no = f"{step_no}-{api_idx + 1}" if (len(expanded_apis) > 1 and step_no) else (step_no or str(api_idx + 1))
            is_last_in_group = api_idx == len(expanded_apis) - 1

            # 줄 단위 주석에서 사번 오버라이드 (예: # 301, { action: confirm })
            line_actor = current_actor
            if comment_line:
                m_actor_cmt = re.match(r"^(100|201|202|301|302|401|402)\b", comment_line)
                if m_actor_cmt:
                    line_actor = m_actor_cmt.group(1)
            c_var = client_var_for(line_actor)

            # 설명 결정: 따라하기 표 설명 -> extra_step_desc -> 주석 -> METHOD path
            guide_desc = step_guides.get(step_no, ("", ""))[1] if step_no in step_guides else ""
            if len(expanded_apis) == 1 and guide_desc:
                step_desc = guide_desc
            elif extra_step_desc:
                step_desc = extra_step_desc
            elif comment_line and not comment_line.startswith("{"):
                step_desc = comment_line.split("→")[0].strip()
            else:
                step_desc = f"{method} {raw_path.split('?')[0]}"
            step_desc = step_desc.replace('"', "'")

            # PUT /api/v1/apr/apprs/{apprId} 인데 앞에 /apprs/new가 없었던 경우 자동 삽입
            if method == "PUT" and "/api/v1/apr/apprs/{" in raw_path and not has_opened_appr:
                t_expr = "t" if needs_tree else 'tree(cid, "휴가신청")'
                lines.append(
                    f'    new = sc.step("{sub_no}-new", "새 결재문서를 연다", {c_var}, "GET", f"/api/v1/apr/apprs/new?classTreeId={{{t_expr}}}")'
                )
                lines.append('    appr = (new or {}).get("apprId")')
                known_vars["apprId"] = "appr"
                has_opened_appr = True

            # 경로 자리표시 치환
            resolved_path, uses_fstring, path_todos = replace_path_placeholders(raw_path)
            path_lit = f'f"{resolved_path}"' if uses_fstring else f'"{resolved_path}"'

            # 요청 본문 결정
            body_code = "None"
            body_todo_note = ""
            cmt_json = _parse_comment_json_like(inline_body_str or comment_line)

            if method == "PUT" and "/api/v1/apr/apprs/" in raw_path and not raw_path.endswith("/appr-id"):
                # 결재 상신 표준 틀 생성
                lc_m = re.search(r"linkCode\s*[:=]?\s*([A-Z]\d{2})", comment_line)
                link_code = lc_m.group(1) if lc_m else "A01"
                step_emps = re.findall(r"\b(100|201|202|301|302|401|402)\b", comment_line)
                writer_emp = step_emps[0] if len(step_emps) >= 1 else (line_actor if line_actor.isdigit() else "401")
                approver_emp = step_emps[1] if len(step_emps) >= 2 else "301"
                t_var = "t" if needs_tree else "0"
                title_expr = 'seed["title"]' if "seed" in known_vars else f'"{scenario_desc}"'
                lines.append(
                    f'    body = apr.save_body("request", {t_var}, {title_expr}, '
                    f'[apr.line(emp["{writer_emp}"], "00", "001"), apr.line(emp["{approver_emp}"], "10", "002")], '
                    'new, message="신청합니다")'
                )
                lines.append(
                    f'    body.update({{"linkCode": "{link_code}", "effectDate": "2026-12-01T00:00:00", "content": "<p>{scenario_desc}</p>"}})'
                )
                body_code = "body"
            elif body_raw is not None and (len(expanded_apis) == 1 or api_idx == 0):
                ep_body = find_endpoint_body_info(method, raw_path)
                merged_body = body_raw
                if isinstance(body_raw, dict) and ep_body and not ep_body.get("is_list"):
                    merged_body = dict(body_raw)
                    for f_info in ep_body.get("fields", []):
                        fn = f_info["name"]
                        if fn not in merged_body:
                            merged_body[fn] = None
                body_code, _ = format_body_structure(merged_body, indent=8)
            elif cmt_json is not None:
                body_code, _ = format_body_structure(cmt_json, indent=8)
            elif method == "POST" and raw_path.endswith("/confirm"):
                body_code = '{"action": "confirm", "message": "승인"}'
            elif method == "PUT" and raw_path.split("?")[0].endswith("/appr-id") and "apprId" in known_vars:
                body_code = f'{{"apprId": {known_vars["apprId"]}}}'
            elif method in ("POST", "PUT", "PATCH"):
                ep_body = find_endpoint_body_info(method, raw_path)
                if ep_body and ep_body.get("fields"):
                    fields = ep_body["fields"]
                    inner_pad = " " * 12
                    b_lines = ["{"]
                    for f_info in fields:
                        b_lines.append(f'{inner_pad}"{f_info["name"]}": None,  # TODO {f_info["type"]}')
                    b_lines.append("        }")
                    dict_str = "\n".join(b_lines)
                    body_code = f"[{dict_str}]" if ep_body.get("is_list") else dict_str

            # 오류를 기대하는 단계인지 판별 (4절, 10절)
            is_error_expected = bool(expected_status and expected_status >= 400) or any(
                ec in comment_line for ec in ERROR_CODES
            )
            err_msg_match = re.search(r'"([^"]+)"', comment_line) if is_error_expected else None

            if is_error_expected:
                st_cond = f"st == {expected_status}" if expected_status else "st >= 400"
                if err_msg_match:
                    expected_phrase = err_msg_match.group(1)[:12]
                    check_lambda = (
                        f'lambda st, js: ({st_cond} and "{expected_phrase}" in str((js or {{}}).get("message")), '
                        'f"message={(js or {}).get(\'message\')}")'
                    )
                else:
                    check_lambda = f'lambda st, js: ({st_cond}, f"HTTP {{st}} body={{js}}")'
                lines.append(
                    f'    sc.raw("{sub_no}", "{step_desc}", {c_var}, "{method}", {path_lit}, {body_code}, {check_lambda})'
                )
                continue

            # 기대값(expect) 및 전후 테이블 count_rows 처리 (묶음의 마지막 줄에만 적용)
            expect_code = "None"
            table_deltas: list[tuple[str, int]] = []
            follow_up_api: str | None = None
            follow_up_expect: dict[str, Any] = {}
            again_status: int | None = None

            if is_last_in_group and isinstance(expect_raw, dict):
                exp_dict: dict[str, str] = {}
                if "api" in expect_raw:
                    follow_up_api = str(expect_raw["api"])
                    if "field" in expect_raw and "value" in expect_raw:
                        follow_up_expect[str(expect_raw["field"])] = repr(expect_raw["value"])
                    elif "rows" in expect_raw:
                        follow_up_expect[""] = f"lambda v: len(v or []) == {_safe_int(expect_raw['rows'])}"
                else:
                    if "field" in expect_raw and "value" in expect_raw:
                        exp_dict[str(expect_raw["field"])] = repr(expect_raw["value"])
                    if "returns" in expect_raw:
                        exp_dict[""] = repr(expect_raw["returns"])
                    elif "data" in expect_raw:
                        exp_dict[""] = repr(expect_raw["data"])
                    if "rows" in expect_raw:
                        exp_dict[""] = f"lambda v: len(v or []) == {_safe_int(expect_raw['rows'])}"

                if "table" in expect_raw and "delta" in expect_raw:
                    table_deltas.append((str(expect_raw["table"]), _safe_int(expect_raw["delta"])))
                if "tables" in expect_raw and isinstance(expect_raw["tables"], dict):
                    for t_nm, t_del in expect_raw["tables"].items():
                        table_deltas.append((str(t_nm), _safe_int(t_del)))
                if "again" in expect_raw:
                    m_ag = re.search(r"(\d{3})", str(expect_raw["again"]))
                    if m_ag:
                        again_status = int(m_ag.group(1))

                if exp_dict:
                    expect_code = "{" + ", ".join(f'"{k}": {v}' for k, v in exp_dict.items()) + "}"

            # 테이블 delta가 있으면 호출 전 count_rows 생성
            pre_count_vars: list[tuple[str, str, str, int]] = []
            for t_idx, (t_name, t_delta) in enumerate(table_deltas):
                f_col, f_kind = _get_table_filter_col(t_name)
                if f_col and f_kind == "person" and line_actor.isdigit():
                    where_sql = f" where {f_col} = {{emp['{line_actor}']}}"
                elif f_col and f_kind == "company":
                    where_sql = f" where {f_col} = 0" if "companyId=0" in raw_path else f" where {f_col} = {{cid}}"
                elif f_col and f_kind == "parent" and "__last_id__" in known_vars:
                    where_sql = f" where {f_col} = {{{known_vars['__last_id__']}}}"
                else:
                    where_sql = ""
                q_str = f'f"select count(*) from {t_name}{where_sql}"'
                v_before = f"n0_{re.sub(r'[^a-z0-9]', '_', str(sub_no).lower())}_{t_idx}"
                lines.append(f"    {v_before} = count_rows({q_str})")
                pre_count_vars.append((v_before, t_name, q_str, t_delta))

            # 응답 결과를 변수에 바인딩할지 결정
            assign_lhs = ""
            post_extract_lines: list[str] = []
            if "/api/v1/apr/apprs/new" in raw_path:
                assign_lhs = "new = "
                post_extract_lines.append('    appr = (new or {}).get("apprId")')
                known_vars["apprId"] = "appr"
                has_opened_appr = True
            elif "/api/v1/apr/apprs/link-seed" in raw_path:
                assign_lhs = "seed = "
                known_vars["seed"] = "seed"
            elif method in ("POST", "PUT"):
                if isinstance(body_raw, list) and body_raw and isinstance(body_raw[0], dict):
                    first_keys = [k for k in body_raw[0] if k.endswith("Id")]
                    if first_keys:
                        id_key = first_keys[0]
                        var_snake = re.sub(r"([A-Z])", r"_\1", id_key).lower()
                        assign_lhs = "rows = "
                        post_extract_lines.append(f'    {var_snake} = rows[0]["{id_key}"] if rows else None')
                        post_extract_lines.append(
                            f'    {var_snake}_list = ",".join(str(r["{id_key}"]) for r in (rows or []) if isinstance(r, dict) and "{id_key}" in r)'
                        )
                        known_vars[id_key] = var_snake
                        known_vars["id"] = var_snake
                        known_vars["__last_id__"] = var_snake
                        known_vars["__last_list_ids__"] = f"{var_snake}_list"
                elif "relate-apprs/status" in raw_path or "my-transport-expenses/appr" in raw_path:
                    assign_lhs = "rel = "
                    post_extract_lines.append('    relate_appr_id = rel["relateApprId"] if isinstance(rel, dict) else rel')
                    known_vars["relateApprId"] = "relate_appr_id"
                    known_vars["__last_id__"] = "relate_appr_id"
                elif raw_path.endswith("/benefits"):
                    assign_lhs = "b = "
                    post_extract_lines.append('    benefit_id = b["benefitId"] if isinstance(b, dict) else b')
                    known_vars["benefitId"] = "benefit_id"
                    known_vars["benefitIds"] = "[benefit_id]"
                    known_vars["__last_id__"] = "benefit_id"
                elif raw_path.endswith("/eval-list-stds"):
                    assign_lhs = "sid = "
                    known_vars[step_no] = "sid"
                    known_vars["evalListStdId"] = "sid"
                    known_vars["id"] = "sid"
                    known_vars["확정 적용일"] = "sid"
                    known_vars["__last_id__"] = "sid"

            # sc.step 호출문 조립
            step_call = f'    {assign_lhs}sc.step("{sub_no}", "{step_desc}", {c_var}, "{method}", {path_lit}'
            if body_code != "None" or expect_code != "None":
                step_call += f", body={body_code}"
            if expect_code != "None":
                step_call += f", expect={expect_code}"
            step_call += ")"
            if path_todos or body_todo_note:
                all_notes = ", ".join(path_todos + ([body_todo_note] if body_todo_note else []))
                step_call += f"  # {all_notes}"

            lines.append(step_call)
            lines.extend(post_extract_lines)

            # 테이블 delta 검증 sc.check 생성
            for v_before, t_name, q_str, t_delta in pre_count_vars:
                sign_str = f"+ {t_delta}" if t_delta >= 0 else f"- {abs(t_delta)}"
                label_sign = f"+{t_delta}" if t_delta >= 0 else str(t_delta)
                lines.append(
                    f'    sc.check("{sub_no}-db", "{t_name} {label_sign}", count_rows({q_str}) == {v_before} {sign_str}, "")'
                )

            # again: 409 등 재호출 에러 검증
            if again_status:
                lines.append(
                    f'    sc.raw("{sub_no}-again", "중복 실행 시 {again_status}", {c_var}, "{method}", {path_lit}, {body_code}, '
                    f'lambda st, js: (st == {again_status}, f"HTTP {{st}}"))'
                )

            # expect.api 별도 조회 단계 생성 (9절)
            if follow_up_api:
                f_parsed = _parse_api_line(follow_up_api, prev_base_path)
                if f_parsed.get("valid"):
                    f_path, f_fstr, _ = replace_path_placeholders(f_parsed["path"])
                    f_path_lit = f'f"{f_path}"' if f_fstr else f'"{f_path}"'
                    f_exp_code = "{" + ", ".join(f'"{k}": {v}' for k, v in follow_up_expect.items()) + "}" if follow_up_expect else "None"
                    lines.append(
                        f'    sc.step("{sub_no}-check", "상태 확인", {c_var}, "{f_parsed["method"]}", {f_path_lit}, expect={f_exp_code})'
                    )

    lines.append("    return sc")
    full_code = "\n".join(lines) + "\n"

    # 생성 코드 파이썬 AST 문법 검증 (13절)
    try:
        ast.parse(full_code)
    except SyntaxError as syn_exc:
        return ToolResult(
            ok=False,
            error=f"생성된 시나리오 코드 문법 오류 ({event_id} line {syn_exc.lineno}): {syn_exc.msg}\n{full_code}",
        )

    return ToolResult(
        ok=True,
        data={
            "event_id": event_id,
            "func_name": func_name,
            "module": mod_name,
            "code": full_code,
            "doc_path": str(doc_path),
            "dup_warnings": dup_warnings,
            "unresolved_todos": unresolved_todos,
        },
    )


def check_scenario_docs(
    target: str | None = None,
    src_root: Path | None = None,
) -> ToolResult:
    """여러 이벤트 문서의 YAML 파싱·중복 키·미해결 자리표시·생성 코드 AST 문법을 일괄 점검한다 (14절)."""
    docs = _find_all_event_docs(target, src_root=src_root)
    if not docs:
        single = _find_event_doc(target or "", src_root=src_root)
        if single:
            docs = [single]
    if not docs:
        return ToolResult(ok=False, error=f"점검할 이벤트 문서를 찾을 수 없습니다: {target or '전체'}")

    report_lines: list[str] = []
    fail_cnt = 0
    ok_cnt = 0
    skip_cnt = 0

    for doc in docs:
        m_id = re.match(r"^([A-Z]+-BZ-\d+)", doc.stem)
        ev_id = m_id.group(1) if m_id else doc.stem
        txt = doc.read_text(encoding="utf-8", errors="replace")
        if "시나리오 데이터" not in txt and "```yaml" not in txt:
            skip_cnt += 1
            continue

        res = generate_scenario_code(ev_id, src_root=src_root)
        if not res.ok:
            fail_cnt += 1
            first_err = (res.error or "오류").splitlines()[0]
            report_lines.append(f"❌ {ev_id}: {first_err}")
        else:
            ok_cnt += 1
            dups = len(res.data.get("dup_warnings", []))
            todos = res.data.get("unresolved_todos", 0)
            extra = []
            if dups:
                extra.append(f"중복키 {dups}")
            if todos:
                extra.append(f"TODO {todos}")
            tag = f" ({', '.join(extra)})" if extra else ""
            report_lines.append(f"✅ {ev_id}: 문법 통과{tag}")

    summary_header = f"점검 {ok_cnt + fail_cnt}건 (통과 {ok_cnt} · 실패 {fail_cnt} · YAML없음 {skip_cnt})"
    full_text = summary_header + ("\n" + "\n".join(report_lines) if report_lines else "")
    return ToolResult(
        ok=fail_cnt == 0,
        data={
            "summary": full_text,
            "ok_cnt": ok_cnt,
            "fail_cnt": fail_cnt,
            "skip_cnt": skip_cnt,
        },
        error=None if fail_cnt == 0 else f"{fail_cnt}개 문서에서 YAML/문법 오류 발견",
    )


def apply_scenario_skel(
    event_id: str,
    company: str = "kova",
    module: str | None = None,
    print_only: bool = False,
    src_root: Path | None = None,
) -> ToolResult:
    """test-scenario-skel 진입 함수. --print면 코드 출력, 아니면 scenario/<module>.py 및 all.py에 등록."""
    res = generate_scenario_code(event_id, company=company, module=module, src_root=src_root)
    if not res.ok:
        return res

    code = res.data["code"]
    func_name = res.data["func_name"]
    mod_name = res.data["module"]

    if print_only:
        return ToolResult(ok=True, data={"summary": code, "code": code})

    root_dir = src_root or getattr(config, "TOBE_SRC_DIR", None) or config.WORK_DIR
    scenario_dir = root_dir / "tools/tests/scenario"
    if not scenario_dir.is_dir():
        return ToolResult(ok=False, error=f"시나리오 디렉터리를 찾을 수 없습니다: {scenario_dir}")

    mod_file = scenario_dir / f"{mod_name}.py"
    all_file = scenario_dir / "all.py"

    if not mod_file.is_file():
        return ToolResult(ok=False, error=f"모듈 파일이 없습니다: {mod_file}")

    mod_content = mod_file.read_text(encoding="utf-8", errors="replace")
    if f"def {func_name}(" in mod_content:
        return ToolResult(ok=False, error=f"이미 같은 이름의 함수가 존재합니다: {func_name} ({mod_file.name})")

    new_mod_content = mod_content.rstrip() + "\n\n\n" + code
    # 전체 모듈 파일 AST 문법 검증 후 저장
    try:
        ast.parse(new_mod_content)
    except SyntaxError as exc:
        return ToolResult(ok=False, error=f"{mod_file.name} 병합 후 문법 검증 실패: {exc}")

    mod_file.write_text(new_mod_content, encoding="utf-8")

    if all_file.is_file():
        all_content = all_file.read_text(encoding="utf-8", errors="replace")
        reg_entry = f"{mod_name}.{func_name}"
        if reg_entry not in all_content:
            m = re.search(r"SCENARIOS\s*=\s*\[(.*?)\]", all_content, re.DOTALL)
            if m:
                bracket_content = m.group(1).rstrip()
                new_bracket = bracket_content + f"\n    {reg_entry},\n"
                all_content = all_content[:m.start(1)] + new_bracket + all_content[m.end(1):]
                all_file.write_text(all_content, encoding="utf-8")

    return ToolResult(
        ok=True,
        data={
            "summary": f"✓ {mod_file.name} 끝에 {func_name} 추가 및 all.py 등록 완료",
            "func_name": func_name,
            "mod_file": str(mod_file),
        },
    )
