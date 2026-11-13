"""TOBE API 엔드포인트 정적 분석 도구 (`biz-endpoints`).

Spring Boot 컨트롤러, DTO, 서비스 소스를 정적으로 분석하여
API 엔드포인트 경로, 쿼리 파라미터, 본문 DTO 필드, 서비스 호출 및 권한 검사(Guards)를 추출한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yunhee.tools.trace.tobe import HTTP_ANNOTATION, _body, field_types, find_layout

# 기본 타입 목록 (DTO 필드 표기 시 타입 생략 대상)
_SIMPLE_TYPES = {"String", "Long", "long", "Integer", "int", "Boolean", "boolean", "Double", "double"}


def _find_controller_files(target: str | Path | None, root_dir: Path) -> list[Path]:
    java_root = root_dir / "backend" / "src" / "main" / "java"
    if not target:
        if java_root.is_dir():
            return sorted(java_root.rglob("*Controller.java"))
        return sorted(root_dir.rglob("*Controller.java"))

    p = Path(target)
    if p.is_file():
        return [p.resolve()]
    if p.is_dir():
        return sorted(p.rglob("*Controller.java"))

    target_str = str(target).strip()

    # target이 컨트롤러 클래스명(예: AstRelateApprController)인 경우 (062 #6)
    clean_target = target_str.removesuffix(".java")
    if clean_target.endswith("Controller"):
        if java_root.is_dir():
            matched = sorted(java_root.rglob(f"{clean_target}.java"))
            if matched:
                return matched
        matched = sorted(root_dir.rglob(f"{clean_target}.java"))
        if matched:
            return matched

    # target이 도메인명(예: att, pay, ast)인 경우
    if not java_root.is_dir():
        # fixture 또는 테스트 경로 fallback
        if (root_dir / "controller").is_dir():
            return sorted((root_dir / "controller").glob("*.java"))
        return sorted(root_dir.rglob(f"*{target_str}*Controller.java"))

    pattern = f"**/biz/{target_str}/controller/*Controller.java"
    files = sorted(java_root.glob(pattern))
    if not files:
        # 하위 디렉터리 전체에서 검색
        files = sorted(java_root.glob(f"**/{target_str}/**/*Controller.java"))
    return files


def _find_type_source(type_name: str, root_dir: Path, base_file: Path) -> Path | None:
    """DTO 또는 서비스 소스 파일을 검색한다."""
    # 1. base_file 근처 (dto/ 또는 service/)
    parent = base_file.parent.parent
    for sub in ("dto", "service", ""):
        cand = parent / sub / f"{type_name}.java"
        if cand.is_file():
            return cand

    # 2. root_dir 전체에서 검색
    cands = list(root_dir.rglob(f"{type_name}.java"))
    return cands[0] if cands else None


def _format_dto_fields(dto_type: str, root_dir: Path, base_file: Path) -> str:
    """DTO 클래스 또는 레코드 소스를 분석하여 'DtoName{field1, field2(LocalDate)}' 형식으로 변환한다."""
    src_file = _find_type_source(dto_type, root_dir, base_file)
    if not src_file or not src_file.is_file():
        return dto_type

    text = src_file.read_text(encoding="utf-8", errors="replace")
    fields: list[str] = []

    # 1. record 파싱
    rec_m = re.search(r"\bpublic\s+record\s+" + re.escape(dto_type) + r"\s*\(([^)]*)\)", text, re.DOTALL)
    if rec_m:
        params_str = rec_m.group(1).strip()
        if params_str:
            # 쉼표 구분 분리 (제네릭 내 쉼표 고려)
            parts: list[str] = []
            curr: list[str] = []
            depth = 0
            for ch in params_str:
                if ch in "<[(":
                    depth += 1
                elif ch in ">])":
                    depth -= 1
                if ch == "," and depth == 0:
                    parts.append("".join(curr).strip())
                    curr = []
                else:
                    curr.append(ch)
            if curr:
                parts.append("".join(curr).strip())

            for part in parts:
                tokens = part.split()
                if len(tokens) >= 2:
                    f_name = tokens[-1]
                    f_type = tokens[-2]
                    # 어노테이션 제거
                    f_name = re.sub(r"@\w+(?:\([^)]*\))?", "", f_name).strip()
                    f_type = re.sub(r"@\w+(?:\([^)]*\))?", "", f_type).strip()
                    if f_type in _SIMPLE_TYPES:
                        fields.append(f_name)
                    else:
                        fields.append(f"{f_name}({f_type})")
        return f"{dto_type}{{{', '.join(fields)}}}" if fields else dto_type

    # 2. 일반 클래스 필드 (private <type> <name>;)
    field_matches = re.findall(r"private\s+([\w<>\[\], ?]+?)\s+(\w+)\s*;", text)
    if field_matches:
        for f_type, f_name in field_matches:
            f_type = f_type.strip()
            if f_type in _SIMPLE_TYPES:
                fields.append(f_name)
            else:
                fields.append(f"{f_name}({f_type})")
        return f"{dto_type}{{{', '.join(fields)}}}" if fields else dto_type

    return dto_type


def _extract_dto_fields_list(dto_type: str, root_dir: Path, base_file: Path) -> list[dict[str, str]]:
    """JSON 출력을 위해 DTO 필드 목록을 dict 리스트로 추출한다."""
    src_file = _find_type_source(dto_type, root_dir, base_file)
    if not src_file or not src_file.is_file():
        return []

    text = src_file.read_text(encoding="utf-8", errors="replace")
    results: list[dict[str, str]] = []

    rec_m = re.search(r"\bpublic\s+record\s+" + re.escape(dto_type) + r"\s*\(([^)]*)\)", text, re.DOTALL)
    if rec_m:
        params_str = rec_m.group(1).strip()
        if params_str:
            parts: list[str] = []
            curr: list[str] = []
            depth = 0
            for ch in params_str:
                if ch in "<[(":
                    depth += 1
                elif ch in ">])":
                    depth -= 1
                if ch == "," and depth == 0:
                    parts.append("".join(curr).strip())
                    curr = []
                else:
                    curr.append(ch)
            if curr:
                parts.append("".join(curr).strip())

            for part in parts:
                tokens = part.split()
                if len(tokens) >= 2:
                    f_name = re.sub(r"@\w+(?:\([^)]*\))?", "", tokens[-1]).strip()
                    f_type = re.sub(r"@\w+(?:\([^)]*\))?", "", tokens[-2]).strip()
                    results.append({"name": f_name, "type": f_type})
        return results

    field_matches = re.findall(r"private\s+([\w<>\[\], ?]+?)\s+(\w+)\s*;", text)
    for f_type, f_name in field_matches:
        results.append({"name": f_name.strip(), "type": f_type.strip()})
    return results


def _analyze_guards(
    service_name: str,
    method_name: str,
    controller_annotations: str,
    root_dir: Path,
    base_file: Path,
) -> list[str]:
    """서비스 메서드 본문 및 컨트롤러 어노테이션에서 권한 검사를 분석한다."""
    guards: list[str] = []

    # 1. 컨트롤러 레벨 검사
    if "@PreAuthorize" in controller_annotations:
        guards.append("메뉴/역할")

    if not service_name:
        return guards or ["⚠없음"]

    # 2. 서비스 파일 찾기
    svc_file = _find_type_source(service_name, root_dir, base_file)
    if not svc_file or not svc_file.is_file():
        return guards or ["⚠없음"]

    svc_text = svc_file.read_text(encoding="utf-8", errors="replace")

    # 서비스 메서드 본문 탐색
    method_pat = re.compile(
        r"^[ \t]*(?:public|protected)\s+(?!class)[\w<>\[\], ?.]+?\s+"
        + re.escape(method_name)
        + r"\s*\([^)]*\)[^{;]*\{",
        re.MULTILINE,
    )
    m = method_pat.search(svc_text)
    if not m:
        return guards or ["⚠없음"]

    brace_pos = m.end() - 1
    body = _body(svc_text, brace_pos)

    # 서비스가 호출하는 내부 private 메서드 1단계 추적
    internal_calls = re.findall(r"\b([A-Za-z_]\w*)\s*\(", body)
    for fn in set(internal_calls):
        if fn != method_name:
            priv_m = re.search(
                r"^[ \t]{2,8}private\s+[\w<>\[\], ?.]+?\s+" + re.escape(fn) + r"\s*\([^)]*\)[^{;]*\{",
                svc_text,
                re.MULTILINE,
            )
            if priv_m:
                priv_brace = priv_m.end() - 1
                priv_body = _body(svc_text, priv_brace)
                body += "\n" + priv_body

    # 권한 검사 순서대로 판정:
    # 1) KFS관리자
    if "requireSysAdmin(" in body or "isSysAdmin()" in body or "requireSysAdmin" in body:
        guards.append("KFS관리자")

    # 2) 메뉴/역할
    if (
        "requireRole(" in body
        or "hasMenu(" in body
        or "checkMenu(" in body
        or "@PreAuthorize" in body
    ) and "메뉴/역할" not in guards:
        guards.append("메뉴/역할")

    # 3) 본인
    if (
        "getUserId()" in body
        or "countMine(" in body
        or "checkMine(" in body
        or "Mine(" in body
    ):
        guards.append("본인")

    # 4) 회사
    if "getCompanyId()" in body:
        guards.append("회사")

    # 5) 서비스 내부 검사 호출 확인 (064 #13)
    # 메서드 본문에서 check*, require*, verify*, load* 호출 탐색 (기존 등록 제외)
    guard_call_pat = re.compile(r"\b(check[A-Z]\w*|require[A-Z]\w*|verify[A-Z]\w*|load[A-Z]\w*)\s*\(")
    head_body = body[:1200]
    for gm in guard_call_pat.finditer(head_body):
        call_name = gm.group(1)
        if call_name in ("requireSysAdmin", "requireRole", "checkMenu", "checkMine"):
            continue
        guards.append(f"서비스내부({call_name})")

    if not guards:
        guards.append("⚠없음")

    # 중복 제거 및 순서 보존
    seen: set[str] = set()
    ordered_guards = []
    for g in guards:
        if g not in seen:
            seen.add(g)
            ordered_guards.append(g)

    return ordered_guards


def _match_parens(text: str, open_pos: int) -> tuple[str, int]:
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_pos + 1 : i], i
    return text[open_pos + 1 :], len(text)


def _extract_screen_api_paths(screen_input: str | int | list[str | int], root_dir: Path) -> list[str]:
    """화면 번호(단일 또는 쉼표/공백 구분 복수)와 관련된 TOBE API 경로 목록을 추출한다 (063 #5, 064 #7)."""
    if isinstance(screen_input, list):
        screens = [str(s).strip() for s in screen_input if str(s).strip()]
    elif isinstance(screen_input, (str, int)):
        screens = [s.strip().lstrip("#") for s in re.split(r"[\s,]+", str(screen_input).strip()) if s.strip()]
    else:
        screens = []

    found_paths: set[str] = set()

    # 1. screen_desc 기반 정밀 추출 시도
    try:
        from yunhee.tools.trace.screen_desc import describe_screens

        desc_res = describe_screens(screens, root_dir=root_dir)
        for sc_data in desc_res.get("screens", []):
            tb = sc_data.get("tobe") or {}
            for api_entry in tb.get("apis", []):
                parts = api_entry.split()
                p_part = parts[1] if len(parts) > 1 and parts[0] in ("GET", "POST", "PUT", "DELETE", "PATCH") else parts[0]
                clean_p = p_part.split("?")[0].strip()
                if clean_p.startswith("/api/v1/"):
                    clean_p = clean_p[len("/api/v1/"):]
                elif clean_p.startswith("/api/"):
                    clean_p = clean_p[len("/api/"):]
                clean_p = clean_p.strip("/")
                if clean_p:
                    found_paths.add(clean_p)
    except Exception:  # noqa: BLE001, S110
        pass

    # 2. 파일 스캔 fallback (docs 및 frontend TSX)
    for s_str in screens:
        s_clean = s_str.lstrip("#")
        for doc in root_dir.glob(f"docs/as-is/src/**/screens/*{s_clean}*.md"):
            txt = doc.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"/api/v1/([a-zA-Z0-9_\-]+(?:/[a-zA-Z0-9_\-]+)?)", txt):
                found_paths.add(m.group(1).strip("/"))

        for tsx in root_dir.glob(f"frontend/src/**/*{s_clean}*.tsx"):
            txt = tsx.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"/api/v1/([a-zA-Z0-9_\-]+(?:/[a-zA-Z0-9_\-]+)?)", txt):
                found_paths.add(m.group(1).strip("/"))

    return sorted(found_paths)


def collect_endpoints(
    target: str | Path | None = None,
    path_filter: str | list[str] | None = None,
    screen: str | int | list[str | int] | None = None,
    root_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """지정된 도메인 또는 컨트롤러 파일에서 엔드포인트 목록을 정적 분석하여 반환한다."""
    if root_dir is None:
        root_dir = find_layout().root

    filters: list[str] = []
    if path_filter:
        if isinstance(path_filter, str):
            for part in path_filter.split(","):
                if part.strip():
                    filters.append(part.strip())
        else:
            for item in path_filter:
                if isinstance(item, str):
                    for part in item.split(","):
                        if part.strip():
                            filters.append(part.strip())

    if screen:
        screen_paths = _extract_screen_api_paths(screen, root_dir)
        filters.extend(screen_paths)
        if not screen_paths:
            # 화면이 지정되었으나 연관 API 경로를 하나도 찾지 못한 경우 (064 #7: 도메인 전체 유출 방지)
            return []

    ctrl_files = _find_controller_files(target, root_dir)
    endpoints: list[dict[str, Any]] = []

    for ctrl_file in ctrl_files:
        text = ctrl_file.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # 컨트롤러 필드 타입 (commuteService -> AttCommuteService)
        ftypes = field_types(text)
        svc_fields = {name: typ for name, typ in ftypes.items() if typ.endswith("Service")}

        # 클래스 레벨 @RequestMapping
        base_match = re.search(r"@RequestMapping\(\s*(?:value\s*=\s*)?\"([^\"]*)\"", text)
        prefix = base_match.group(1).rstrip("/") if base_match else ""

        offsets = [0]
        for ln in lines:
            offsets.append(offsets[-1] + len(ln) + 1)

        for i, line in enumerate(lines):
            m = HTTP_ANNOTATION.search(line)
            if not m:
                continue

            verb = m.group(1).upper()
            mapping_sub = (m.group(2) or "").strip("/")
            full_path = (prefix + "/" + mapping_sub).rstrip("/") if (prefix or mapping_sub) else "/"
            if not full_path.startswith("/"):
                full_path = "/" + full_path

            if filters and not any(f in full_path for f in filters):
                continue

            # 메서드 선언부 탐색 (최대 15줄 아래까지)
            method_text = "\n".join(lines[i : min(i + 15, len(lines))])
            sig_m = re.search(
                r"public\s+[\w<>\[\], ?.]+?\s+(\w+)\s*\(",
                method_text,
            )
            if not sig_m:
                continue

            open_pos = sig_m.end() - 1
            params_raw, close_pos = _match_parens(method_text, open_pos)

            # 본문 위치
            body_from = text.find("{", offsets[i] + close_pos)
            method_body = _body(text, body_from) if body_from >= 0 else ""

            # 서비스 호출 찾기 (service.xxx( 또는 field.xxx()
            service_call_str = ""
            for field_name, svc_type in svc_fields.items():
                call_pat = re.compile(r"\b" + re.escape(field_name) + r"\s*\.\s*(\w+)\s*\(")
                cm = call_pat.search(method_body)
                if cm:
                    service_call_str = f"{svc_type}.{cm.group(1)}"
                    break

            # 파라미터 파싱 (@RequestParam, @RequestBody, @PathVariable)
            query_items: list[dict[str, Any]] = []
            body_info: dict[str, Any] = {"type": None, "list": False, "fields": []}
            body_display_str = "—"

            if params_raw:
                # 쉼표 구분 분리 (제네릭 내 쉼표 방지)
                param_chunks: list[str] = []
                cur_chunk: list[str] = []
                depth = 0
                for ch in params_raw:
                    if ch in "<[(":
                        depth += 1
                    elif ch in ">])":
                        depth -= 1
                    if ch == "," and depth == 0:
                        param_chunks.append("".join(cur_chunk).strip())
                        cur_chunk = []
                    else:
                        cur_chunk.append(ch)
                if cur_chunk:
                    param_chunks.append("".join(cur_chunk).strip())

                for p_chunk in param_chunks:
                    clean_chunk = " ".join(p_chunk.split())
                    if "@AuthenticationPrincipal" in clean_chunk:
                        continue

                    # 1. @RequestParam
                    if "@RequestParam" in clean_chunk:
                        is_optional = "required = false" in clean_chunk or "required=false" in clean_chunk or "defaultValue" in clean_chunk
                        name_match = re.search(r'(?:value|name)\s*=\s*"([^"]+)"', clean_chunk)
                        # 어노테이션 제거 후 순수 타입과 변수명 추출
                        chunk_no_anno = re.sub(r"@\w+(?:\([^)]*\))?", "", clean_chunk).strip()
                        tokens = chunk_no_anno.split()
                        var_name = tokens[-1] if tokens else ""
                        var_type = tokens[-2] if len(tokens) >= 2 else "String"
                        param_name = name_match.group(1) if name_match else var_name
                        query_items.append({
                            "name": param_name,
                            "required": not is_optional,
                            "type": var_type,
                        })
                    elif "@RequestBody" in clean_chunk:
                        # 2. @RequestBody
                        # 예: @RequestBody List<Long> ids, @RequestBody FooReq req
                        clean_req = re.sub(r"@\w+(?:\([^)]*\))?", "", clean_chunk).strip()
                        tokens = clean_req.split()
                        if len(tokens) >= 2:
                            b_type = tokens[-2].strip()
                        else:
                            b_type = tokens[0].strip()

                        is_list = b_type.startswith("List<")
                        if is_list:
                            inner_type = b_type[5:-1].strip()
                            if inner_type in _SIMPLE_TYPES:
                                body_display_str = b_type
                                body_info = {"type": b_type, "list": True, "fields": []}
                            else:
                                expanded = _format_dto_fields(inner_type, root_dir, ctrl_file)
                                body_display_str = f"List<{expanded}>"
                                body_info = {
                                    "type": b_type,
                                    "list": True,
                                    "fields": _extract_dto_fields_list(inner_type, root_dir, ctrl_file),
                                }
                        else:
                            expanded = _format_dto_fields(b_type, root_dir, ctrl_file)
                            body_display_str = expanded
                            body_info = {
                                "type": b_type,
                                "list": False,
                                "fields": _extract_dto_fields_list(b_type, root_dir, ctrl_file),
                            }

            # 쿼리 스트링 포맷팅 (personId?, baseDate)
            q_strs: list[str] = []
            for q in query_items:
                suffix = "?" if not q["required"] else ""
                q_strs.append(f"{q['name']}{suffix}")
            query_str = ", ".join(q_strs) if q_strs else "—"

            # 서비스명 / 메서드명 분리
            svc_name = service_call_str.split(".")[0] if "." in service_call_str else ""
            svc_meth = service_call_str.split(".")[1] if "." in service_call_str else ""

            # 검사 (Guards) 분석
            guards = _analyze_guards(
                svc_name,
                svc_meth,
                line,
                root_dir,
                ctrl_file,
            )

            endpoints.append({
                "method": verb,
                "path": full_path,
                "query": query_items,
                "query_str": query_str,
                "body": body_info,
                "body_str": body_display_str,
                "service": service_call_str or "—",
                "guards": guards,
                "guard_str": "·".join(guards),
                "file": f"{ctrl_file.name}:{i + 1}",
                "line": i + 1,
            })

    return endpoints


def format_endpoints_md(endpoints: list[dict[str, Any]]) -> str:
    """마크다운 테이블 및 요약 문자열을 생성한다."""
    lines: list[str] = [
        "| 메서드 | 경로 | 쿼리 | 본문 | 서비스 | 검사 | 줄 |",
        "|:---|:---|:---|:---|:---|:---|:---|",
    ]
    writes = 0
    kfs_cnt = 0
    mine_cnt = 0
    company_only_cnt = 0
    no_guard_write = 0
    no_guard_read = 0

    for ep in endpoints:
        is_write = ep["method"] in ("POST", "PUT", "DELETE", "PATCH")
        has_no_guard = "⚠없음" in ep["guards"]
        if is_write:
            writes += 1
            if "KFS관리자" in ep["guards"]:
                kfs_cnt += 1
            if "본인" in ep["guards"]:
                mine_cnt += 1
            if ep["guards"] == ["회사"]:
                company_only_cnt += 1
            if has_no_guard:
                no_guard_write += 1
        else:
            if has_no_guard:
                no_guard_read += 1

        lines.append(
            f"| {ep['method']} | {ep['path']} | {ep['query_str']} | {ep['body_str']} | "
            f"{ep['service']} | {ep['guard_str']} | {ep['file']} |"
        )

    no_guard_total = no_guard_write + no_guard_read
    no_guard_str = f" · ⚠없음 {no_guard_total}개(쓰기 {no_guard_write}·조회 {no_guard_read})" if no_guard_total > 0 else ""

    summary = (
        f"\n엔드포인트 {len(endpoints)}개 · 쓰기 {writes}개{no_guard_str} · "
        f"쓰기 중 'KFS관리자' {kfs_cnt} · '본인' {mine_cnt} · '회사'만 {company_only_cnt} ← biz-authz 후보"
    )
    return "\n".join(lines) + "\n" + summary


def format_endpoints_json(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON 출력을 위해 직렬화 가능한 딕셔너리 리스트를 반환한다."""
    res = []
    for ep in endpoints:
        res.append({
            "method": ep["method"],
            "path": ep["path"],
            "query": ep["query"],
            "body": ep["body"],
            "service": ep["service"],
            "guards": ep["guards"],
            "file": ep["file"],
            "line": ep["line"],
        })
    return res


def format_endpoints_tsv(endpoints: list[dict[str, Any]]) -> str:
    """TSV 형식 문자열을 생성한다."""
    lines = ["method\tpath\tquery\tbody\tservice\tguards\tfile\tline"]
    for ep in endpoints:
        lines.append(
            f"{ep['method']}\t{ep['path']}\t{ep['query_str']}\t{ep['body_str']}\t"
            f"{ep['service']}\t{ep['guard_str']}\t{ep['file']}\t{ep['line']}"
        )
    return "\n".join(lines)
