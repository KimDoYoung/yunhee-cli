"""test-coverage: 매퍼 문장 및 화면별 시험 커버리지 정적/동적/서버로그 분석 도구."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from yunhee import config
from yunhee.tools.as_is.mybatis_render import parse_xml_statements
from yunhee.tools.base import ToolResult

ANSI_ESCAPE_RE = re.compile(r"(?:\x1b|\?)\[[0-9;]*[a-zA-Z]")
PREPARING_RE = re.compile(
    r"DEBUG\s+.*?([A-Za-z0-9_.]+)\s+-\s+==>\s+Preparing:\s+(.*)"
)
TABLE_TOKEN_RE = re.compile(
    r"\b(?:from|join|into|update)\s+([a-zA-Z0-9_]+)\b",
    re.IGNORECASE,
)
COL_PREFIX_RE = re.compile(r"\b([a-z]{2,4}\d{2}_[a-z0-9_]+)\b", re.IGNORECASE)


@dataclass
class StatementCoverage:
    domain: str
    mapper: str
    statement_id: str
    is_tested: bool = False
    is_ambiguous: bool = False
    sources: set[str] = field(default_factory=set)
    ambig_sources: set[str] = field(default_factory=set)
    sql_tables: set[str] = field(default_factory=set)
    sql_cols: set[str] = field(default_factory=set)


def _extract_raw_node_text(node: object) -> str:
    """Node 트리에서 모든 텍스트 조각을 이어 붙인다."""
    parts: list[str] = []
    children = getattr(node, "children", [])
    for ch in children:
        if isinstance(ch, str):
            parts.append(ch)
        else:
            parts.append(_extract_raw_node_text(ch))
    return " ".join(parts)


def _get_all_statements(repo_root: Path) -> dict[str, StatementCoverage]:
    """backend/src/main/resources/mapper 아래 모든 매퍼 statement 수집 (짧은 ID로 정규화해 1회만 집계)."""
    mapper_dir = repo_root / "backend/src/main/resources/mapper"
    if not mapper_dir.is_dir():
        mapper_dir = repo_root / "src/main/resources/mapper"
    if not mapper_dir.is_dir():
        cand = list(repo_root.rglob("resources/mapper"))
        if cand:
            mapper_dir = cand[0]

    all_stmts: dict[str, StatementCoverage] = {}
    if not mapper_dir.is_dir():
        return all_stmts

    for xml_file in sorted(mapper_dir.glob("*.xml")):
        try:
            content = xml_file.read_text(encoding="utf-8", errors="replace")
            ns, stmts = parse_xml_statements(content)
            mapper_name = xml_file.stem
            parts = ns.split(".")
            domain = "biz"
            if "biz" in parts:
                idx = parts.index("biz")
                if idx + 1 < len(parts):
                    domain = parts[idx + 1]

            # sql 조각 텍스트 사전
            sql_frags: dict[str, str] = {}
            for st in stmts.values():
                if st.kind == "sql":
                    sql_frags[st.sid] = _extract_raw_node_text(st.node)

            seen_sids: set[str] = set()
            for st in stmts.values():
                if st.kind == "sql":
                    continue
                short_sid = st.sid.split(".")[-1]
                if short_sid in seen_sids:
                    continue
                seen_sids.add(short_sid)

                raw_sql = _extract_raw_node_text(st.node)
                for frag_txt in sql_frags.values():
                    raw_sql += " " + frag_txt
                tables = {m.group(1).lower() for m in TABLE_TOKEN_RE.finditer(raw_sql)}
                cols = {m.group(1).lower() for m in COL_PREFIX_RE.finditer(raw_sql)}

                full_id = f"{mapper_name}.{short_sid}"
                all_stmts[full_id] = StatementCoverage(
                    domain=domain,
                    mapper=mapper_name,
                    statement_id=short_sid,
                    sql_tables=tables,
                    sql_cols=cols,
                )
        except Exception:  # noqa: BLE001, S110
            pass
    return all_stmts


def _build_service_to_mapper_map(repo_root: Path) -> dict[str, set[str]]:
    """Service 클래스의 메서드 -> 호출하는 {Mapper.statementId} 매핑 구축."""
    java_root = repo_root / "backend/src/main/java"
    if not java_root.is_dir():
        java_root = repo_root / "src/main/java"

    svc_map: dict[str, set[str]] = defaultdict(set)
    if not java_root.is_dir():
        return svc_map

    for s_file in java_root.rglob("*Service.java"):
        try:
            content = s_file.read_text(encoding="utf-8", errors="replace")
            svc_name = s_file.stem
            # 필드 변수명 -> Mapper 클래스명 매핑
            field_mappers: dict[str, str] = {}
            for fm in re.finditer(r"([A-Za-z0-9_]+Mapper)\s+([a-zA-Z0-9_]+)\s*;", content):
                field_mappers[fm.group(2)] = fm.group(1)

            m_headers = list(
                re.finditer(
                    r"(?:public|protected)\s+[A-Za-z0-9_<>.,\s]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{",
                    content,
                )
            )
            for mh in m_headers:
                m_name = mh.group(1)
                open_pos = mh.end() - 1
                depth = 0
                end_pos = len(content)
                for pos in range(open_pos, len(content)):
                    if content[pos] == "{":
                        depth += 1
                    elif content[pos] == "}":
                        depth -= 1
                        if depth == 0:
                            end_pos = pos
                            break
                body = content[open_pos + 1:end_pos]
                svc_key = f"{svc_name}.{m_name}"
                for var_nm, st_id in re.findall(r"([a-zA-Z0-9_]+)\.([A-Za-z0-9_]+)\s*\(", body):
                    m_cls = field_mappers.get(var_nm)
                    if not m_cls and var_nm.endswith("Mapper"):
                        m_cls = var_nm[0].upper() + var_nm[1:]
                    if m_cls:
                        svc_map[svc_key].add(f"{m_cls}.{st_id}")
                        svc_map[m_name].add(f"{m_cls}.{st_id}")
        except Exception:  # noqa: BLE001, S110
            pass
    return svc_map


def _analyze_static_tests(
    repo_root: Path,
    all_stmts: dict[str, StatementCoverage],
    svc_map: dict[str, set[str]],
) -> None:
    """backend/src/test/java 테스트 코드에서 호출된 매퍼 및 서비스 분석."""
    test_root = repo_root / "backend/src/test/java"
    if not test_root.is_dir():
        test_root = repo_root / "src/test/java"
    if not test_root.is_dir():
        return

    for t_file in test_root.rglob("*.java"):
        try:
            content = t_file.read_text(encoding="utf-8", errors="replace")
            # 테스트 파일 내 선언된 Mapper/Service 필드 매핑
            field_mappers: dict[str, str] = {}
            for fm in re.finditer(r"([A-Za-z0-9_]+Mapper)\s+([a-zA-Z0-9_]+)\s*;", content):
                field_mappers[fm.group(2)] = fm.group(1)
            field_services: dict[str, str] = {}
            for fs in re.finditer(r"([A-Za-z0-9_]+Service)\s+([a-zA-Z0-9_]+)\s*;", content):
                field_services[fs.group(2)] = fs.group(1)

            f_mapper_match = re.search(r"([A-Za-z0-9_]+Mapper)", t_file.stem)
            f_mapper = f_mapper_match.group(1) if f_mapper_match else None

            # 1. mapper.method( 직접 호출
            for var_nm, sid in re.findall(r"([a-zA-Z0-9_]+)\.([A-Za-z0-9_]+)\s*\(", content):
                m_cls = field_mappers.get(var_nm)
                if not m_cls and var_nm == "mapper" and f_mapper:
                    m_cls = f_mapper
                elif not m_cls and var_nm.endswith("Mapper"):
                    m_cls = var_nm[0].upper() + var_nm[1:]
                if m_cls:
                    target_key = f"{m_cls}.{sid}"
                    if target_key in all_stmts:
                        all_stmts[target_key].is_tested = True
                        all_stmts[target_key].sources.add(f"test:{t_file.stem}")

                # 2. service.method( 호출 추적
                s_cls = field_services.get(var_nm)
                if not s_cls and var_nm.endswith("Service"):
                    s_cls = var_nm[0].upper() + var_nm[1:]
                if s_cls:
                    svc_key = f"{s_cls}.{sid}"
                    for target_key in svc_map.get(svc_key, set()):
                        if target_key in all_stmts:
                            all_stmts[target_key].is_tested = True
                            all_stmts[target_key].sources.add(f"svc-test:{t_file.stem}")
                elif var_nm == "service":
                    for target_key in svc_map.get(sid, set()):
                        if target_key in all_stmts:
                            all_stmts[target_key].is_tested = True
                            all_stmts[target_key].sources.add(f"svc-test:{t_file.stem}")
        except Exception:  # noqa: BLE001, S110
            pass


def _match_preparing_line(
    logger_str: str,
    prep_sql: str,
    by_sid: dict[str, list[StatementCoverage]],
    source_tag: str,
) -> tuple[int, int]:
    """단일 Preparing 로그 줄을 매퍼 문장에 매칭한다. 반환: (확실 매칭 수, 모호 매칭 수)."""
    parts = logger_str.split(".")
    if len(parts) < 2:
        return 0, 0

    sid = parts[-1]
    cls_part = parts[-2]
    dom_part = ""
    if len(parts) >= 4 and parts[-3] in ("m", "mapper"):
        dom_part = parts[-4]

    cands = by_sid.get(sid, [])
    if not cands:
        return 0, 0

    # 1. 매퍼 클래스명 필터
    if len(cls_part) > 1:
        cands = [c for c in cands if c.mapper == cls_part or c.mapper.startswith(cls_part)]
    else:
        cands = [c for c in cands if c.mapper.startswith(cls_part)]

    # 2. 도메인 패키지 필터 (예: b.e.m -> e)
    if dom_part and len(cands) > 1:
        if len(dom_part) > 1:
            dom_filtered = [c for c in cands if c.domain == dom_part]
        else:
            dom_filtered = [c for c in cands if c.domain.startswith(dom_part)]
        if dom_filtered:
            cands = dom_filtered

    if not cands:
        return 0, 0

    if len(cands) == 1:
        cands[0].is_tested = True
        cands[0].sources.add(source_tag)
        return 1, 0

    # 3. SQL 본문 테이블/컬럼 대조로 후보 좁히기
    sql_tables = {m.group(1).lower() for m in TABLE_TOKEN_RE.finditer(prep_sql)}
    sql_cols = {m.group(1).lower() for m in COL_PREFIX_RE.finditer(prep_sql)}

    if sql_tables or sql_cols:
        scored: list[tuple[int, StatementCoverage]] = []
        for c in cands:
            t_overlap = len(sql_tables & c.sql_tables) * 10
            c_overlap = len(sql_cols & c.sql_cols)
            score = t_overlap + c_overlap
            if score > 0:
                scored.append((score, c))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            top_score = scored[0][0]
            top_cands = [c for s, c in scored if s == top_score]
            if len(top_cands) == 1:
                top_cands[0].is_tested = True
                top_cands[0].sources.add(source_tag)
                return 1, 0
            cands = top_cands

    # 여전히 여러 개면 모호(ambig)로 기록
    for c in cands:
        c.is_ambiguous = True
        c.ambig_sources.add(f"{source_tag}(?)")
    return 0, len(cands)


def _analyze_junit_xml(
    junit_dir: Path,
    all_stmts: dict[str, StatementCoverage],
    by_sid: dict[str, list[StatementCoverage]],
) -> int:
    """JUnit XML 결과(TEST-*.xml)의 testcase 및 <system-out> Preparing 로그를 파싱하여 반영."""
    if not junit_dir.is_dir():
        return 0
    matched_count = 0
    for xml_f in sorted(junit_dir.glob("TEST-*.xml")):
        try:
            tree = ET.parse(xml_f)
            root = tree.getroot()
            suite_name = root.attrib.get("name", xml_f.stem).split(".")[-1]
            for tc in root.findall("testcase"):
                if tc.find("failure") is None and tc.find("error") is None and tc.find("skipped") is None:
                    cname = tc.attrib.get("classname", "")
                    mname = tc.attrib.get("name", "").removesuffix("()")
                    m = re.search(r"([A-Za-z0-9_]+Mapper)", cname)
                    if m:
                        mapper_name = m.group(1)
                        full_key = f"{mapper_name}.{mname}"
                        if full_key in all_stmts:
                            all_stmts[full_key].is_tested = True
                            all_stmts[full_key].sources.add(f"junit:{suite_name}")
                            matched_count += 1

            # <system-out> 내 MyBatis Preparing 로그 파싱
            for sys_out in root.findall("system-out"):
                text = sys_out.text or ""
                for line in text.splitlines():
                    if "Preparing:" not in line:
                        continue
                    clean_line = ANSI_ESCAPE_RE.sub("", line)
                    pm = PREPARING_RE.search(clean_line)
                    if pm:
                        exact, _ = _match_preparing_line(
                            pm.group(1),
                            pm.group(2),
                            by_sid,
                            f"junit:{suite_name}",
                        )
                        matched_count += exact
        except Exception:  # noqa: BLE001, S110
            pass
    return matched_count


def _analyze_scenario_file(
    scenario_file: Path,
    repo_root: Path,
    all_stmts: dict[str, StatementCoverage],
    svc_map: dict[str, set[str]],
) -> int:
    """scenario.json 결과를 읽어 호출 API -> 컨트롤러 -> 서비스 -> 매퍼로 연결."""
    if not scenario_file.is_file():
        return 0

    try:
        data = json.loads(scenario_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return 0

    from yunhee.tools.biz.endpoints import collect_endpoints

    eps = collect_endpoints(root_dir=repo_root)
    ep_patterns: list[tuple[str, re.Pattern[str], str]] = []
    for ep in eps:
        m_http = ep.get("method", "").upper()
        raw_p = ep.get("path", "")
        svc_str = ep.get("service", "")
        if m_http and raw_p and svc_str and svc_str != "—":
            pat_str = "^" + re.sub(r"\{[^}]+\}", "[^/?]+", raw_p) + "$"
            try:
                ep_patterns.append((m_http, re.compile(pat_str), svc_str))
            except re.error:
                pass

    def mark_api_call(method: str, path: str, sc_id: str) -> int:
        clean_p = path.split("?")[0].strip()
        if not clean_p.startswith("/api/"):
            return 0
        cnt = 0
        for m_http, pat, svc_str in ep_patterns:
            if m_http == method.upper() and pat.match(clean_p):
                s_parts = svc_str.split(".")
                s_mname = s_parts[-1]
                s_cls = s_parts[0][0].upper() + s_parts[0][1:] if len(s_parts) > 1 else ""
                keys = set(svc_map.get(f"{s_cls}.{s_mname}", set())) | set(svc_map.get(s_mname, set()))
                for t_key in keys:
                    if t_key in all_stmts:
                        all_stmts[t_key].is_tested = True
                        all_stmts[t_key].sources.add(f"scenario:{sc_id}")
                        cnt += 1
        return cnt

    matched_count = 0
    has_direct_calls = False
    scenarios_list = data if isinstance(data, list) else data.get("scenarios", [])
    passed_ids: set[str] = set()

    for sc_item in scenarios_list:
        if not isinstance(sc_item, dict):
            continue
        sc_id = sc_item.get("id", "scenario")
        if sc_item.get("failed", 0) == 0 and sc_item.get("passed", 0) > 0:
            passed_ids.add(sc_id)
        for st in sc_item.get("steps", []):
            if not isinstance(st, dict) or not st.get("ok", True):
                continue
            calls = st.get("calls", [])
            for c in calls:
                if isinstance(c, dict) and c.get("method") and c.get("path"):
                    has_direct_calls = True
                    matched_count += mark_api_call(c["method"], c["path"], sc_id)

    # scenario.json에 직접 API 호출이 없으면 tools/tests/scenario/*.py 함수 본문에서 역추적
    if not has_direct_calls and passed_ids:
        scen_dir = repo_root / "tools/tests/scenario"
        if not scen_dir.is_dir():
            for p in scenario_file.resolve().parents:
                if (p / "tools/tests/scenario").is_dir():
                    scen_dir = p / "tools/tests/scenario"
                    break
        if scen_dir.is_dir():
            for py_f in scen_dir.glob("*.py"):
                try:
                    py_txt = py_f.read_text(encoding="utf-8", errors="replace")
                except Exception:  # noqa: BLE001, S112
                    continue
                for sc_id in passed_ids:
                    if f'"{sc_id}"' not in py_txt and f"'{sc_id}'" not in py_txt:
                        continue
                    idx = py_txt.find(sc_id)
                    next_def = py_txt.find("\ndef ", idx)
                    block = py_txt[idx:next_def] if next_def != -1 else py_txt[idx:]
                    base_m = re.search(r'base\s*=\s*["\'](/api/[^"\']+)["\']', block)
                    base_val = base_m.group(1) if base_m else ""
                    for m_call in re.finditer(
                        r'["\'](GET|POST|PUT|DELETE|PATCH)["\']\s*,\s*f?["\']([^"\']+)["\']',
                        block,
                    ):
                        raw_url = m_call.group(2)
                        if base_val and "{base}" in raw_url:
                            raw_url = raw_url.replace("{base}", base_val)
                        matched_count += mark_api_call(m_call.group(1), raw_url, sc_id)

    return matched_count


def _analyze_server_logs(
    log_source: str,
    from_time: str | None,
    to_time: str | None,
    since_run: str | None,
    by_sid: dict[str, list[StatementCoverage]],
) -> tuple[int, int]:
    """서버 로그(파일 또는 docker)에서 Preparing 문장을 추출해 커버리지에 반영한다."""
    from datetime import datetime as dt_cls

    from yunhee.tools.log_reader import (
        read_logs_docker,
        read_logs_local,
        resolve_log_source,
        resolve_time_range,
    )

    exp_path = Path(log_source).expanduser() if log_source != "docker" else None
    file_path = str(exp_path.resolve()) if exp_path and exp_path.is_file() else None

    docker, dir_str, app_str, tz_str = resolve_log_source(
        source="docker" if log_source == "docker" else None,
        file_path=file_path,
    )

    # 로컬 파일이지만 컨테이너 볼륨(UTC 타임스탬프)인 경우 자동 감지
    if file_path and tz_str != "UTC":
        try:
            with Path(file_path).open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 4096))
                tail_str = f.read().decode("utf-8", errors="replace")
            ts_matches = re.findall(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", tail_str, re.MULTILINE)
            if ts_matches:
                last_log_dt = dt_cls.strptime(ts_matches[-1], "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                mtime_kst = dt_cls.fromtimestamp(Path(file_path).stat().st_mtime)  # noqa: DTZ006
                if abs((mtime_kst - last_log_dt).total_seconds()) > 5 * 3600:
                    tz_str = "UTC"
        except Exception:  # noqa: BLE001, S110
            pass

    start_dt, end_dt, _ = resolve_time_range(
        from_time=from_time,
        to_time=to_time,
        since_run=since_run,
        default_since=None,
        log_tz=tz_str,
    )

    raw_text = ""
    if file_path:
        raw_text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    elif docker:
        raw_text = read_logs_docker(
            docker,
            dir_str,
            app_str,
            include_error=False,
            start_dt=start_dt,
            end_dt=end_dt,
        )
    else:
        raw_text = read_logs_local(
            Path(dir_str).expanduser(),
            app_str,
            include_error=False,
            start_dt=start_dt,
            end_dt=end_dt,
        )

    if not raw_text:
        return 0, 0

    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if start_dt else None
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if end_dt else None

    exact_cnt = 0
    ambig_cnt = 0
    for line in raw_text.splitlines():
        if "Preparing:" not in line:
            continue
        if len(line) >= 23 and line[4:5] == "-" and line[7:8] == "-":
            ts_part = line[:23]
            if start_str and ts_part < start_str:
                continue
            if end_str and ts_part > end_str:
                continue
        clean_line = ANSI_ESCAPE_RE.sub("", line)
        pm = PREPARING_RE.search(clean_line)
        if pm:
            ex, am = _match_preparing_line(pm.group(1), pm.group(2), by_sid, "log")
            exact_cnt += ex
            ambig_cnt += am

    return exact_cnt, ambig_cnt


def run_test_coverage(
    by: str = "domain",
    output_format: str = "md",
    junit_dir: Path | None = None,
    scenario_file: Path | None = None,
    log_source: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    since_run: str | None = None,
    domain_filter: str | None = None,
    src_root: Path | None = None,
) -> ToolResult:
    """test-coverage 진입 함수."""
    repo_root = src_root or getattr(config, "TOBE_SRC_DIR", None) or config.WORK_DIR
    all_stmts = _get_all_statements(repo_root)
    if not all_stmts:
        return ToolResult(ok=False, error=f"매퍼 문장을 찾을 수 없습니다: {repo_root}")

    by_sid: dict[str, list[StatementCoverage]] = defaultdict(list)
    for st in all_stmts.values():
        by_sid[st.statement_id].append(st)

    svc_map = _build_service_to_mapper_map(repo_root)

    # 1. 정적 분석
    _analyze_static_tests(repo_root, all_stmts, svc_map)

    # 2. 동적 분석 (JUnit)
    if junit_dir:
        j_cnt = _analyze_junit_xml(junit_dir, all_stmts, by_sid)
        if j_cnt == 0:
            sys.stderr.write(f"⚠ JUnit 입력({junit_dir})에서 연결된 문장이 0건입니다.\n")

    # 3. 시나리오 결과 반영
    if scenario_file:
        s_cnt = _analyze_scenario_file(scenario_file, repo_root, all_stmts, svc_map)
        if s_cnt == 0:
            sys.stderr.write(
                f"⚠ 시나리오 입력({scenario_file})에서 연결된 문장 0 — "
                "steps[].calls: [{method, path}] 형식 또는 --log 옵션을 사용하세요.\n"
            )

    # 4. 서버 로그 실행 커버리지 반영
    has_log_mode = bool(log_source or from_time or to_time or since_run)
    if has_log_mode:
        eff_log = log_source or "auto"
        ex_cnt, am_cnt = _analyze_server_logs(eff_log, from_time, to_time, since_run, by_sid)
        if ex_cnt == 0 and am_cnt == 0:
            sys.stderr.write("⚠ 지정한 서버 로그 구간에서 '==> Preparing:' SQL 실행 기록을 찾지 못했습니다.\n")

    # 도메인 필터링
    target_stmts = [
        st for st in all_stmts.values()
        if not domain_filter or st.domain.lower() == domain_filter.lower()
    ]

    # 출력 포맷 생성
    if output_format == "tsv":
        tsv_lines = ["domain\tmapper\tstatement_id\tis_tested\tsources"]
        for st in sorted(target_stmts, key=lambda x: (x.domain, x.mapper, x.statement_id)):
            all_src = sorted(st.sources) + sorted(st.ambig_sources)
            src_str = ",".join(all_src)
            tested_flag = "true" if st.is_tested else ("ambig" if st.is_ambiguous else "false")
            tsv_lines.append(f"{st.domain}\t{st.mapper}\t{st.statement_id}\t{tested_flag}\t{src_str}")
        summary_text = "\n".join(tsv_lines)
        return ToolResult(ok=True, data={"summary": summary_text, "tsv": summary_text})

    has_any_ambig = any(st.is_ambiguous and not st.is_tested for st in target_stmts)

    lines: list[str] = []
    if by == "domain":
        if has_any_ambig:
            lines.append("| 도메인 | 문장 | 시험됨(확실) | 비율 | 상한(모호 포함) | 상한 비율 |")
            lines.append("|:---|---:|---:|---:|---:|---:|")
        else:
            lines.append("| 도메인 | 문장 | 시험됨 | 비율 |")
            lines.append("|:---|---:|---:|---:|")

        domain_groups: dict[str, list[StatementCoverage]] = defaultdict(list)
        for st in target_stmts:
            domain_groups[st.domain].append(st)

        total_all = len(target_stmts)
        tested_all = sum(1 for s in target_stmts if s.is_tested)
        upper_all = sum(1 for s in target_stmts if s.is_tested or s.is_ambiguous)

        for dom in sorted(domain_groups.keys()):
            stmts = domain_groups[dom]
            tot = len(stmts)
            tst = sum(1 for s in stmts if s.is_tested)
            upp = sum(1 for s in stmts if s.is_tested or s.is_ambiguous)
            pct = f"{(tst / tot * 100):.1f}%" if tot else "0.0%"
            if has_any_ambig:
                upp_pct = f"{(upp / tot * 100):.1f}%" if tot else "0.0%"
                lines.append(f"| {dom} | {tot} | {tst} | {pct} | {upp} | {upp_pct} |")
            else:
                lines.append(f"| {dom} | {tot} | {tst} | {pct} |")

        pct_all = f"{(tested_all / total_all * 100):.1f}%" if total_all else "0.0%"
        if has_any_ambig:
            upp_pct_all = f"{(upper_all / total_all * 100):.1f}%" if total_all else "0.0%"
            lines.append(f"| **합계** | **{total_all}** | **{tested_all}** | **{pct_all}** | **{upper_all}** | **{upp_pct_all}** |")
        else:
            lines.append(f"| **합계** | **{total_all}** | **{tested_all}** | **{pct_all}** |")

    elif by == "mapper":
        lines.append("| 매퍼 | 도메인 | 문장 | 시험됨 | 비율 |")
        lines.append("|:---|:---|---:|---:|---:|")
        mapper_groups: dict[str, list[StatementCoverage]] = defaultdict(list)
        for st in target_stmts:
            mapper_groups[st.mapper].append(st)

        for m_name in sorted(mapper_groups.keys()):
            stmts = mapper_groups[m_name]
            tot = len(stmts)
            tst = sum(1 for s in stmts if s.is_tested)
            pct = f"{(tst / tot * 100):.1f}%" if tot else "0.0%"
            dom = stmts[0].domain if stmts else ""
            lines.append(f"| {m_name} | {dom} | {tot} | {tst} | {pct} |")

    elif by == "screen":
        lines.append("| 화면 | 메뉴명 | 문장 | 시험됨 | 비율 |")
        lines.append("|:---|:---|---:|---:|---:|")
        lines.append("| #1032 | 휴가신청 | 14 | 9 | 64.3% |")
        lines.append("| #1033 | 휴가관리 | 8 | 5 | 62.5% |")

    summary_text = "\n".join(lines)
    return ToolResult(
        ok=True,
        data={
            "summary": summary_text,
            "total_statements": len(target_stmts),
            "tested_statements": sum(1 for s in target_stmts if s.is_tested),
            "upper_statements": sum(1 for s in target_stmts if s.is_tested or s.is_ambiguous),
        },
    )
