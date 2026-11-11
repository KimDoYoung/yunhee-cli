"""변경반영용 drift-* 명령군 및 단위 기반 drift 감지·대장·기준선 관리 도구.

- drift-unit: 바뀐 파일을 SQL ID·메서드·UI·모델 단위로 세분화하고 영향 화면 및 TOBE 대응 탐색
- drift-done: 단위 또는 파일 기준선을 갱신하고 반영대장(반영대장.md)의 상태·처리일·비고 기록
- drift-ledger: drift-unit 결과를 반영대장.md 끝에 추가/갱신
- drift-diff: 단일 단위(SQL ID 또는 Class#method 등)의 AS-IS 전후 diff 및 TOBE 대응 비교
- drift-db: DBML 스냅샷 전후(테이블/컬럼/함수) 차이 및 영향 SQL/TOBE 매퍼 탐색
- drift-log: 기준 이후 커밋들을 파일/종류(DB·SQL·LOGIC·MODEL·UI·ETC) 단위로 요약
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.as_is.drift import (
    KST,
    _last_commit_for_files,
    _run_git,
    compute_git_blob_file,
    is_git_repo,
    load_index_screens,
    resolve_baseline_path,
    resolve_done_screens,
)

logger = logging.getLogger(__name__)

# --- 단위 판별 및 종류 판정 ---

STATEMENT_TAG_RE = re.compile(
    r"<(select|insert|update|delete)\b[^>]*?\bid\s*=\s*\"([^\"]+)\"", re.IGNORECASE
)


def resolve_ledger_path(work_dir: Path | None = None, explicit: Path | None = None) -> Path:
    """반영대장 파일 경로를 탐색한다 (explicit 지정 우선, 없으면 변경반영-대장.md -> 반영대장.md -> 대장.md)."""
    if explicit:
        return explicit
    wd = (work_dir or Path.cwd()).resolve()
    cands = [
        wd / "docs" / "3-변경반영" / "변경반영-대장.md",
        wd / "docs" / "3-변경반영" / "반영대장.md",
        wd / "docs" / "3-변경반영" / "대장.md",
    ]
    for c in cands:
        if c.is_file():
            return c
    return cands[0]


def parse_ledger_header(lines: list[str]) -> tuple[int, list[str], dict[str, int]]:
    """대장 마크다운 줄들에서 표 머리줄(header) 행 번호, 컬럼 목록, 컬럼명->인덱스 맵을 추출한다.
    
    헤더 판정:
    - 파이프(|)로 시작하고 끝나는 행
    - '키'와 '상태' 컬럼이 모두 포함되어 있는 행
    """
    for idx, line in enumerate(lines):
        line_s = line.strip()
        if not line_s.startswith("|") or not line_s.endswith("|"):
            continue
        parts = [p.strip() for p in line_s.split("|")[1:-1]]
        if "키" in parts and "상태" in parts:
            col_map = {name: i for i, name in enumerate(parts)}
            return idx, parts, col_map
    return -1, [], {}


def split_table_row(line: str) -> list[str] | None:
    """마크다운 테이블 행을 파싱하여 셀 문자열 리스트 반환. 유효한 행이 아니면 None."""
    line_s = line.strip()
    if not line_s.startswith("|") or not line_s.endswith("|"):
        return None
    return [p.strip() for p in line_s.split("|")[1:-1]]


def format_table_row(cells: list[str]) -> str:
    """셀 리스트를 마크다운 테이블 행 문자열로 변환 (| c1 | c2 | ... |)."""
    return "| " + " | ".join(cells) + " |"


def extract_mapper_statement_block(xml_text: str, sid: str) -> tuple[str, str, list[str], int] | None:
    """매퍼 XML에서 id가 sid인 <select|insert|update|delete> 블록을 (kind, body, includes, line_no)로 추출."""
    stmt_re = re.compile(
        r"<(select|insert|update|delete)\b[^>]*?\bid\s*=\s*[\"']" + re.escape(sid) + r"[\"'][^>]*>",
        re.IGNORECASE,
    )
    m = stmt_re.search(xml_text)
    if not m:
        return None
    kind = m.group(1).lower()
    end_tag = f"</{kind}>"
    pos = xml_text.lower().find(end_tag, m.end())
    if pos == -1:
        stmt_body = xml_text[m.start():]
    else:
        stmt_body = xml_text[m.start(): pos + len(end_tag)]
    line_no = xml_text[:m.start()].count("\n") + 1
    includes = re.findall(r"<include\s+refid\s*=\s*[\"']([^\"']+)[\"']", stmt_body)
    return kind, stmt_body, includes, line_no


def extract_mapper_include_block(xml_text: str, refid: str) -> str | None:
    """매퍼 XML에서 id가 refid인 <sql> 블록 본문을 추출."""
    sql_re = re.compile(
        r"<sql\b[^>]*?\bid\s*=\s*[\"']" + re.escape(refid) + r"[\"'][^>]*>",
        re.IGNORECASE,
    )
    m = sql_re.search(xml_text)
    if not m:
        return None
    end_tag = "</sql>"
    pos = xml_text.lower().find(end_tag, m.end())
    if pos == -1:
        return xml_text[m.start():]
    return xml_text[m.start(): pos + len(end_tag)]


def extract_mapper_resultmap_columns(xml_text: str, result_map_id: str) -> list[str]:
    """매퍼 XML에서 id가 result_map_id인 <resultMap> 블록의 result/id 컬럼/프로퍼티 목록 추출."""
    rm_re = re.compile(
        r"<resultMap\b[^>]*?\bid\s*=\s*[\"']" + re.escape(result_map_id) + r"[\"'][^>]*>",
        re.IGNORECASE,
    )
    m = rm_re.search(xml_text)
    if not m:
        return []
    end_tag = "</resultmap>"
    pos = xml_text.lower().find(end_tag, m.end())
    body = xml_text[m.start(): pos + len(end_tag)] if pos != -1 else xml_text[m.start():]
    cols = re.findall(r"\b(?:column|property)\s*=\s*[\"']([^\"']+)[\"']", body)
    return list(dict.fromkeys(cols))


def classify_file_kind(rel_path: str) -> str:
    """파일 경로 기반 종류(DB, SQL, LOGIC, MODEL, UI, ETC) 분류."""
    p = Path(rel_path)
    ext = p.suffix.lower()
    stem = p.stem
    parts = [pt.lower() for pt in p.parts]

    if ext == ".sql" or "dbsource" in parts or "db_source" in parts:
        return "DB"
    if ext == ".xml" or "mapper" in parts:
        return "SQL"
    if ext == ".java":
        if "model" in parts or stem.endswith(("Model", "Properties")):
            return "MODEL"
        if "client" in parts:
            if re.search(r"_(Tab|Page|Lookup|Edit|Popup|Tree)_|^Main|Grid|Field|Picker|Bar", stem):
                return "UI"
            return "UI"
        if "server" in parts:
            return "LOGIC"
        return "LOGIC"
    return "ETC"


def parse_xml_statements_positions(xml_text: str, namespace: str = "") -> list[dict[str, Any]]:
    """MyBatis XML 파일 내 statement의 시작/종료 줄 번호 및 id 수집."""
    stmts: list[dict[str, Any]] = []
    lines = xml_text.splitlines()

    # namespace 추출
    if not namespace:
        m_ns = re.search(r"<mapper\s+namespace\s*=\s*\"([^\"]+)\"", xml_text)
        namespace = m_ns.group(1) if m_ns else ""

    curr_stmt: dict[str, Any] | None = None
    tag_name = ""

    for line_idx, line in enumerate(lines, 1):
        if curr_stmt is None:
            m = STATEMENT_TAG_RE.search(line)
            if m:
                tag = m.group(1).lower()
                sid = m.group(2)
                full_id = f"{namespace}.{sid}" if namespace else sid
                end_tag = f"</{tag}>"
                if end_tag in line:
                    stmts.append({
                        "id": sid,
                        "key": full_id,
                        "kind": tag,
                        "start_line": line_idx,
                        "end_line": line_idx,
                    })
                else:
                    curr_stmt = {
                        "id": sid,
                        "key": full_id,
                        "kind": tag,
                        "start_line": line_idx,
                    }
                    tag_name = tag
        else:
            end_tag = f"</{tag_name}>"
            if end_tag in line:
                curr_stmt["end_line"] = line_idx
                stmts.append(curr_stmt)
                curr_stmt = None
                tag_name = ""

    if curr_stmt is not None:
        curr_stmt["end_line"] = len(lines)
        stmts.append(curr_stmt)

    return stmts


def parse_java_methods_positions(java_text: str, class_name: str) -> list[dict[str, Any]]:
    """Java 파일 내 메서드의 시작/종료 줄 번호 및 이름 수집."""
    from yunhee.tools.as_is.src_indexer import find_methods, strip_java

    _no_comment, bare = strip_java(java_text)
    methods = find_methods(bare)
    results: list[dict[str, Any]] = []

    for name, name_pos, body_start, body_end, is_public, params in methods:
        start_line = bare.count("\n", 0, name_pos) + 1
        end_line = bare.count("\n", 0, body_end) + 1
        results.append({
            "name": name,
            "unit": f"{class_name}#{name}()",
            "start_line": start_line,
            "end_line": end_line,
            "is_public": is_public,
        })
    return results


def parse_diff_hunks(diff_text: str) -> list[dict[str, Any]]:
    """git diff 출력에서 파일별 및 hunk(@@ -old_start,old_count +new_start,new_count @@) 정보 파싱."""
    files: list[dict[str, Any]] = []
    current_file: dict[str, Any] | None = None
    current_hunk: dict[str, Any] | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_file:
                if current_hunk:
                    current_file["hunks"].append(current_hunk)
                    current_hunk = None
                files.append(current_file)
            m = re.search(r"diff --git a/(.*) b/(.*)", line)
            old_p = m.group(1) if m else ""
            new_p = m.group(2) if m else ""
            current_file = {
                "old_path": old_p,
                "new_path": new_p,
                "hunks": [],
                "added_lines": 0,
                "removed_lines": 0,
                "is_new": False,
                "is_deleted": False,
            }
        elif current_file is not None:
            if line.startswith("new file mode"):
                current_file["is_new"] = True
            elif line.startswith("deleted file mode"):
                current_file["is_deleted"] = True
            elif line.startswith("@@ "):
                if current_hunk:
                    current_file["hunks"].append(current_hunk)
                m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if m:
                    old_start = int(m.group(1))
                    old_len = int(m.group(2)) if m.group(2) else 1
                    new_start = int(m.group(3))
                    new_len = int(m.group(4)) if m.group(4) else 1
                    current_hunk = {
                        "header": line,
                        "old_start": old_start,
                        "old_end": old_start + max(old_len - 1, 0),
                        "new_start": new_start,
                        "new_end": new_start + max(new_len - 1, 0),
                        "added": 0,
                        "removed": 0,
                        "lines": [],
                    }
            elif current_hunk is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk["added"] += 1
                    current_file["added_lines"] += 1
                    current_hunk["lines"].append(line)
                elif line.startswith("-") and not line.startswith("---"):
                    current_hunk["removed"] += 1
                    current_file["removed_lines"] += 1
                    current_hunk["lines"].append(line)
                elif line.startswith(" "):
                    current_hunk["lines"].append(line)

    if current_file:
        if current_hunk:
            current_file["hunks"].append(current_hunk)
        files.append(current_file)

    return files


def load_tobe_matches(work_dir: Path | None = None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """TOBE 인덱스에서 SQL ID -> [TOBE Mapper XML/Statement], 서비스/메서드 -> [TOBE Service/Controller] 매칭 맵 로드."""
    wd = (work_dir or Path.cwd()).resolve()
    from yunhee.tools.trace.tobe import build_index, find_layout

    layout = find_layout(wd)
    sql_map: dict[str, list[str]] = defaultdict(list)
    method_map: dict[str, list[str]] = defaultdict(list)

    if not layout.usable:
        return sql_map, method_map

    tobe_idx = build_index(str(layout.root))

    # 1. SQL 문장 매핑
    for stmt in tobe_idx.statements.values():
        tobe_ref = f"{Path(stmt.file).name} · {stmt.id}"
        for asis_id in stmt.as_is_ids:
            if tobe_ref not in sql_map[asis_id]:
                sql_map[asis_id].append(tobe_ref)
            bare = asis_id.split(".")[-1]
            if tobe_ref not in sql_map[bare]:
                sql_map[bare].append(tobe_ref)

    # 2. 서비스/컨트롤러 매핑
    for (svc_cls, m_name), sm in tobe_idx.services.items():
        tobe_ref = f"{svc_cls}#{m_name}()"
        for k in sm.keys:
            if tobe_ref not in method_map[k]:
                method_map[k].append(tobe_ref)
            bare_m = k.split(".")[-1]
            if tobe_ref not in method_map[bare_m]:
                method_map[bare_m].append(tobe_ref)

    for ep in tobe_idx.endpoints:
        tobe_ref = f"{ep.controller}#{ep.method}()"
        for k in ep.keys:
            if tobe_ref not in method_map[k]:
                method_map[k].append(tobe_ref)
            bare_m = k.split(".")[-1]
            if tobe_ref not in method_map[bare_m]:
                method_map[bare_m].append(tobe_ref)

    return sql_map, method_map


def build_unit_screens_map(src_index: Path) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    """색인(_index.json, screens/*.md)에서 SQL ID -> [화면번호/이름], 서버메서드 -> [화면], 파일 -> [화면] 매핑 생성."""
    sql_to_screens: dict[str, set[str]] = defaultdict(set)
    method_to_screens: dict[str, set[str]] = defaultdict(set)
    file_to_screens: dict[str, set[str]] = defaultdict(set)

    # 1. 화면 md 파일 파싱 (메뉴 번호와 연결 서비스/SQL)
    for md_file in sorted(src_index.glob("*/screens/*.md")):
        raw = md_file.read_text(encoding="utf-8", errors="replace")
        s_name = md_file.stem
        # 메뉴 번호 탐색: #1029
        m_no = re.search(r"\(#(\d+)\)", raw)
        disp_name = f"#{m_no.group(1)}" if m_no else s_name

        # 파일 목록 수집
        fm_part = raw.split("\n---\n")[0] if raw.startswith("---\n") else ""
        for line in fm_part.splitlines():
            line = line.strip()
            if line.endswith(":") and not line.startswith("source_"):
                continue
            if ":" in line:
                p_cand = line.split(":", 1)[0].strip()
                if p_cand.startswith("application/") or "/" in p_cand:
                    file_to_screens[p_cand].add(disp_name)

        # 서비스 및 SQL ID 추출
        for sm in re.finditer(r"\|\s*`([^`]+)`\s*\|\s*[^|]*\s*\|\s*\[`([^`]+)`\][^|]*\|\s*\[`([^`]+)`\]", raw):
            srv_key = sm.group(1).strip()
            sql_key = sm.group(3).strip()
            if srv_key:
                method_to_screens[srv_key].add(disp_name)
                # Class.method
                parts = srv_key.split(".")
                if len(parts) >= 2:
                    cls_m = f"{parts[-2]}#{parts[-1]}()"
                    method_to_screens[cls_m].add(disp_name)
                    method_to_screens[parts[-1]].add(disp_name)
            if sql_key:
                sql_to_screens[sql_key].add(disp_name)
                bare = sql_key.split(".")[-1]
                sql_to_screens[bare].add(disp_name)

    # _files.json 보강
    files_json = src_index / "_files.json"
    if files_json.is_file():
        try:
            fmap = json.loads(files_json.read_text(encoding="utf-8"))
            for rel_p, sc_list in fmap.items():
                for sc in sc_list:
                    file_to_screens[rel_p].add(sc)
        except Exception:  # noqa: BLE001, S110
            pass

    return (
        {k: sorted(v) for k, v in sql_to_screens.items()},
        {k: sorted(v) for k, v in method_to_screens.items()},
        {k: sorted(v) for k, v in file_to_screens.items()},
    )


# --- 1. drift-unit 구현 ---

def analyze_drift_units(
    src_root: Path,
    src_index: Path,
    base: str = "baseline",
    done_only: bool = False,
    kind_filter: list[str] | None = None,
    work_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """AS-IS git diff hunk를 분석하여 변경된 단위를 SQL/LOGIC/MODEL/UI/DB/ETC로 세분화하고 화면 및 TOBE 대응 연결."""
    wd = (work_dir or Path.cwd()).resolve()
    _indexed_screens, _files_map, source_meta = load_index_screens(src_index)

    # 기준 커밋 결정
    baseline_path = resolve_baseline_path(wd)
    baseline_data: dict[str, Any] = {}
    if baseline_path.is_file():
        try:
            baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            baseline_data = {}

    base_commit: str | None = None
    if base == "baseline":
        # baseline.json의 최신/대표 커밋
        __base__ = baseline_data.get("__base__", {})
        if isinstance(__base__, dict) and __base__.get("commit"):
            base_commit = __base__["commit"]
        else:
            commits = [v.get("commit") for v in baseline_data.values() if isinstance(v, dict) and v.get("commit") and v.get("commit") != "none"]
            base_commit = commits[0] if commits else None
        if not base_commit and source_meta.get("commit"):
            base_commit = source_meta.get("commit")
    elif base == "index":
        base_commit = source_meta.get("commit")
    else:
        base_commit = base

    if not base_commit:
        base_commit = "HEAD~1"

    # git diff -w <base_commit> HEAD 실행
    rc, diff_out, _err = _run_git(src_root, ["diff", "-w", "-U0", base_commit, "HEAD"])
    if rc != 0:
        return []

    diff_files = parse_diff_hunks(diff_out)
    sql_screens, method_screens, file_screens = build_unit_screens_map(src_index)
    tobe_sql_matches, tobe_method_matches = load_tobe_matches(wd)
    done_set = resolve_done_screens(wd, baseline_data) if done_only else set()

    units: list[dict[str, Any]] = []

    for df in diff_files:
        rel_p = df["new_path"] or df["old_path"]
        abs_p = src_root / rel_p
        kind = classify_file_kind(rel_p)
        file_lines_added = df["added_lines"]
        file_lines_removed = df["removed_lines"]

        # 마지막 커밋 조회
        lc = _last_commit_for_files(src_root, [rel_p], deleted=df["is_deleted"])
        commit_str = f"{lc['hash']} {lc['date']} {lc['subject'][:30]}" if lc else "-"

        # 1. 매퍼 XML인 경우: hunk가 걸친 statement 탐색
        if kind == "SQL" and abs_p.is_file():
            xml_text = abs_p.read_text(encoding="utf-8", errors="replace")
            # old xml text가 필요하면 이전 커밋에서 읽기
            old_xml_text = ""
            rc_old, old_out, _ = _run_git(src_root, ["show", f"{base_commit}:{rel_p}"])
            if rc_old == 0:
                old_xml_text = old_out

            new_stmts = parse_xml_statements_positions(xml_text)
            old_stmts = parse_xml_statements_positions(old_xml_text) if old_xml_text else []
            old_keys = {s["key"] for s in old_stmts}
            new_keys = {s["key"] for s in new_stmts}

            matched_keys: set[str] = set()

            for h in df["hunks"]:
                n_start, n_end = h["new_start"], h["new_end"]
                h_matched = False
                for st in new_stmts:
                    if not (n_end < st["start_line"] or n_start > st["end_line"]):
                        matched_keys.add(st["key"])
                        h_matched = True
                if not h_matched and old_stmts:
                    # 삭제된 SQL 확인
                    o_start, o_end = h["old_start"], h["old_end"]
                    for st in old_stmts:
                        if not (o_end < st["start_line"] or o_start > st["end_line"]):
                            matched_keys.add(st["key"])

            if not matched_keys:
                # include나 resultType 등 mapper 머리/공통부 변경
                u_item = {
                    "kind": "SQL",
                    "unit": f"`{rel_p}` · (공통/조각)",
                    "raw_unit": f"{rel_p}:common",
                    "file": rel_p,
                    "change": f"+{file_lines_added} −{file_lines_removed}줄",
                    "added": file_lines_added,
                    "removed": file_lines_removed,
                    "status": "변경",
                    "screens": file_screens.get(rel_p, []),
                    "tobe": "",
                    "commit": commit_str,
                    "lc": lc,
                }
                units.append(u_item)
            else:
                for k in sorted(matched_keys):
                    status = "변경"
                    if k not in old_keys:
                        status = "새로 생김"
                    elif k not in new_keys:
                        status = "없어짐"

                    scs = sql_screens.get(k) or sql_screens.get(k.split(".")[-1]) or file_screens.get(rel_p, [])
                    tobe_cand = ", ".join(tobe_sql_matches.get(k, []) or tobe_sql_matches.get(k.split(".")[-1], []))

                    units.append({
                        "kind": "SQL",
                        "unit": f"`{rel_p}` · `{k.split('.')[-1]}`",
                        "raw_unit": k,
                        "file": rel_p,
                        "change": f"{status} +{file_lines_added} −{file_lines_removed}줄" if status == "새로 생김" else f"+{file_lines_added} −{file_lines_removed}줄",
                        "added": file_lines_added,
                        "removed": file_lines_removed,
                        "status": status,
                        "screens": scs,
                        "tobe": tobe_cand,
                        "commit": commit_str,
                        "lc": lc,
                    })

        # 2. 서버 Java인 경우: hunk가 걸친 메서드 탐색
        elif kind == "LOGIC" and abs_p.is_file():
            java_text = abs_p.read_text(encoding="utf-8", errors="replace")
            cls_name = abs_p.stem
            methods = parse_java_methods_positions(java_text, cls_name)
            matched_methods: set[str] = set()

            for h in df["hunks"]:
                n_start, n_end = h["new_start"], h["new_end"]
                for m in methods:
                    if not (n_end < m["start_line"] or n_start > m["end_line"]):
                        matched_methods.add(m["name"])

            if not matched_methods:
                # import, 필드, 어노테이션 등만 바뀜
                units.append({
                    "kind": "LOGIC",
                    "unit": f"`{rel_p}` · `(기타/필드)`",
                    "raw_unit": f"{cls_name}#(ETC)",
                    "file": rel_p,
                    "change": f"+{file_lines_added} −{file_lines_removed}줄",
                    "added": file_lines_added,
                    "removed": file_lines_removed,
                    "status": "변경",
                    "screens": file_screens.get(rel_p, []),
                    "tobe": "",
                    "commit": commit_str,
                    "lc": lc,
                })
            else:
                for m_name in sorted(matched_methods):
                    full_m = f"{cls_name}#{m_name}()"
                    scs = method_screens.get(full_m) or method_screens.get(m_name) or file_screens.get(rel_p, [])
                    tobe_cand = ", ".join(tobe_method_matches.get(full_m, []) or tobe_method_matches.get(m_name, []))

                    units.append({
                        "kind": "LOGIC",
                        "unit": f"`{rel_p}` · `{m_name}`",
                        "raw_unit": full_m,
                        "file": rel_p,
                        "change": f"+{file_lines_added} −{file_lines_removed}줄",
                        "added": file_lines_added,
                        "removed": file_lines_removed,
                        "status": "변경",
                        "screens": scs,
                        "tobe": tobe_cand,
                        "commit": commit_str,
                        "lc": lc,
                    })

        # 3. 화면 UI / MODEL / DB / NEW / ETC
        else:
            status = "새로 생김" if df["is_new"] else ("없어짐" if df["is_deleted"] else "변경")
            act_kind = "NEW" if df["is_new"] else kind
            scs = file_screens.get(rel_p, [])
            u_disp = f"`{rel_p}`"

            units.append({
                "kind": act_kind,
                "unit": u_disp,
                "raw_unit": rel_p,
                "file": rel_p,
                "change": f"{status} +{file_lines_added} −{file_lines_removed}줄" if status == "새로 생김" else f"+{file_lines_added} −{file_lines_removed}줄",
                "added": file_lines_added,
                "removed": file_lines_removed,
                "status": status,
                "screens": scs,
                "tobe": "",
                "commit": commit_str,
                "lc": lc,
            })

    # 필터링: --done-only
    if done_only and done_set:
        filtered = []
        for u in units:
            u_scs = u["screens"]
            # 화면 목록 중 하나라도 done_set에 포함되어 있는지 확인
            is_done_related = any(
                sc in done_set or sc.lstrip("#") in [re.sub(r"^[A-Za-z0-9_]+#", "", d) for d in done_set]
                for sc in u_scs
            )
            if is_done_related:
                filtered.append(u)
        units = filtered

    # 필터링: kind
    if kind_filter:
        k_set = {k.upper() for k in kind_filter}
        units = [u for u in units if u["kind"].upper() in k_set]

    return units


def render_drift_unit_table(units: list[dict[str, Any]], all_units: bool = False) -> str:
    """drift-unit 표 형식 렌더링."""
    if not units:
        return "감지된 변경 단위가 없습니다."

    # "쓰는 화면 없음"인 단위 분리
    has_screen_units: list[dict[str, Any]] = []
    no_screen_units: list[dict[str, Any]] = []

    for u in units:
        if u["screens"]:
            has_screen_units.append(u)
        else:
            no_screen_units.append(u)

    disp_units = units if all_units else has_screen_units

    lines: list[str] = [
        f"{'종류':<6} {'단위':<42} {'변경':<12} {'화면':<22} {'TOBE 대응':<28} 커밋",
        f"{'-'*6} {'-'*42} {'-'*12} {'-'*22} {'-'*28} {'-'*25}",
    ]

    for u in disp_units:
        k_str = u["kind"]
        u_str = u["unit"]
        if len(u_str) > 40:
            u_str = u_str[:39] + "…"
        chg_str = u["change"]
        sc_str = " ".join(u["screens"][:3])
        if len(u["screens"]) > 3:
            sc_str += f" 외 {len(u['screens']) - 3}"
        if not sc_str:
            sc_str = "(없음)"
        tobe_str = u["tobe"] or "(없음)"
        if len(tobe_str) > 26:
            tobe_str = tobe_str[:25] + "…"
        c_str = u["commit"]

        lines.append(f"{k_str:<6} {u_str:<42} {chg_str:<12} {sc_str:<22} {tobe_str:<28} {c_str}")

    if not all_units and no_screen_units:
        lines.append("")
        lines.append(f"(쓰는 화면 없음 {len(no_screen_units)}단위 접음 — 전체 표시는 --all-units)")

    return "\n".join(lines)


# --- 2. drift-done 구현 ---

def update_drift_done(
    keys: list[str],
    status: str = "반영",
    check: str = "",
    tobe: str = "",
    note: str = "",
    note_append: bool = False,
    force: bool = False,
    dry_run: bool = False,
    work_dir: Path | None = None,
    ledger_path: Path | None = None,
) -> tuple[int, str]:
    """단위/파일 또는 CH-키를 받아 기준선(baseline.json)을 최신화하고 반영대장(반영대장.md) 행 갱신."""
    wd = (work_dir or Path.cwd()).resolve()
    baseline_path = resolve_baseline_path(wd)
    if not baseline_path.is_file():
        return 1, f"기준선 파일을 찾을 수 없습니다: {baseline_path}"

    try:
        baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return 1, f"기준선 파일 읽기 실패: {exc}"

    ledger_file = resolve_ledger_path(wd, ledger_path)
    ledger_lines: list[str] = []
    if ledger_file.is_file():
        ledger_lines = ledger_file.read_text(encoding="utf-8", errors="replace").splitlines()

    now_kst = datetime.now(tz=KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    now_iso = now_kst.isoformat(timespec="seconds")

    # 대상 식별
    ch_keys = [k for k in keys if k.startswith("CH-")]
    raw_units = [k for k in keys if not k.startswith("CH-")]

    header_idx = -1
    col_names: list[str] = []
    col_map: dict[str, int] = {}
    if ledger_lines:
        header_idx, col_names, col_map = parse_ledger_header(ledger_lines)
        if header_idx == -1:
            return 1, f"대장 표 머리줄(| 키 | ... | 상태 | ...)을 찾을 수 없습니다: {ledger_file.name}"
        for req in ("키", "상태", "처리일"):
            if req not in col_map:
                return 1, f"대장 표 머리줄에 필수 칸 '{req}'이(가) 없습니다: {ledger_file.name}"

    # 대장 행 매칭
    matched_rows: list[tuple[int, list[str], str, str]] = []  # (line_idx, parts, row_ch, row_unit)
    all_table_rows: list[tuple[int, list[str], str, str, str]] = []  # (line_idx, parts, row_ch, row_unit, row_status)

    if ledger_lines and col_map:
        for line_idx, line in enumerate(ledger_lines):
            parts = split_table_row(line)
            if parts is None:
                continue
            if len(parts) != len(col_names):
                if line_idx != header_idx and not line.strip().startswith("|:"):
                    logger.warning(
                        "대장 %s:%d 줄의 칸 수가 머리줄과 다릅니다(%d != %d), 건너뜁니다: %s",
                        ledger_file.name,
                        line_idx + 1,
                        len(parts),
                        len(col_names),
                        line,
                    )
                continue
            row_ch = parts[col_map["키"]]
            if not row_ch.startswith("CH-"):
                continue
            row_status = parts[col_map["상태"]]
            row_unit = re.sub(r"[`*]", "", parts[col_map["단위"]]).strip() if "단위" in col_map else ""
            all_table_rows.append((line_idx, parts, row_ch, row_unit, row_status))

            if row_ch in ch_keys or any(ru in row_unit for ru in raw_units):
                matched_rows.append((line_idx, parts, row_ch, row_unit))

    # 검증: status가 '반영'인데 '확인' 칸이 비어있는 경우
    if status == "반영" and "확인" in col_map:
        for _line_idx, parts, row_ch, _row_unit in matched_rows:
            curr_check = parts[col_map["확인"]].strip()
            if not check.strip() and not curr_check and not force:
                return (
                    1,
                    (
                        f"키 {row_ch}: 상태가 '반영'이지만 '확인' 칸이 비어 있습니다. "
                        f"(--check \"<확인내용>\"을 지정하거나 --force로 진행하세요)"
                    ),
                )

    # 대장 행 갱신 및 diff 미리보기 준비
    new_ledger_lines = list(ledger_lines)
    diff_previews: list[str] = []
    updated_ledger_rows: list[str] = []
    updated_units: set[str] = set(raw_units)

    for line_idx, parts, row_ch, row_unit in matched_rows:
        old_line = ledger_lines[line_idx]
        parts[col_map["상태"]] = status
        parts[col_map["처리일"]] = today_str
        if check and "확인" in col_map:
            parts[col_map["확인"]] = check
        if tobe and "TOBE 대응" in col_map:
            parts[col_map["TOBE 대응"]] = tobe
        if note and "비고" in col_map:
            old_note = parts[col_map["비고"]].strip()
            if note_append and old_note:
                parts[col_map["비고"]] = f"{old_note} · {note}".strip()
            else:
                parts[col_map["비고"]] = note

        new_line = format_table_row(parts)
        new_ledger_lines[line_idx] = new_line
        diff_previews.append(f"- {old_line}\n+ {new_line}")
        updated_ledger_rows.append(row_ch)
        if row_unit:
            updated_units.add(row_unit)

    # baseline.json에 단위 기준선(__units__, __files__) 기록
    if "__units__" not in baseline_data or not isinstance(baseline_data["__units__"], dict):
        baseline_data["__units__"] = {}
    if "__files__" not in baseline_data or not isinstance(baseline_data["__files__"], dict):
        baseline_data["__files__"] = {}

    eff_src = Path(config.ASIS_SRC_DIR or "").resolve() if config.ASIS_SRC_DIR else None
    head_commit = None
    if eff_src and is_git_repo(eff_src):
        rc_c, c_out, _ = _run_git(eff_src, ["rev-parse", "HEAD"])
        if rc_c == 0 and c_out.strip():
            head_commit = c_out.strip()

    # 대장 내 파일별 남은 대기 단위 집계 (이번에 갱신되는 row 제외)
    updated_row_set = set(updated_ledger_rows)
    waiting_units_by_file: dict[str, list[str]] = defaultdict(list)
    for _l_idx, _pts, r_ch, r_u, r_st in all_table_rows:
        if r_ch in updated_row_set:
            continue
        if r_st == "대기" and r_u:
            f_part = r_u.split(" · ")[0].strip("`")
            waiting_units_by_file[f_part].append(r_ch)

    pending_file_msgs: list[str] = []
    updated_files: list[str] = []

    for u in updated_units:
        unit_entry = {
            "status": status,
            "updated_at": now_iso,
            "note": note,
        }
        if head_commit:
            unit_entry["commit"] = head_commit

        baseline_data["__units__"][u] = unit_entry

        # 파일 경로인 경우 __files__ 기록 여부 판정
        if "/" in u or u.endswith((".java", ".xml", ".sql")):
            f_clean = u.split(" · ")[0].strip("`")
            # 해당 파일에 아직 대기 중인 다른 단위가 남아있는지 확인
            waiting_remains = waiting_units_by_file.get(f_clean, [])
            if waiting_remains:
                pending_file_msgs.append(
                    f"파일 기준선 보류: {f_clean} (대기 단위 {len(waiting_remains)}건: {', '.join(waiting_remains)})"
                )
            else:
                file_entry = {
                    "status": status,
                    "updated_at": now_iso,
                    "note": note,
                }
                if head_commit:
                    file_entry["commit"] = head_commit
                if eff_src and (eff_src / f_clean).is_file():
                    file_entry["blob"] = compute_git_blob_file(eff_src / f_clean)
                baseline_data["__files__"][f_clean] = file_entry
                updated_files.append(f_clean)

    msg_parts = []
    if updated_ledger_rows:
        msg_parts.append(f"대장 갱신 {len(updated_ledger_rows)}건 ({', '.join(updated_ledger_rows)})")
    if updated_units:
        msg_parts.append(f"단위 기준선 갱신 {len(updated_units)}건 ({status})")
    if updated_files:
        msg_parts.append(f"파일 기준선 갱신 {len(updated_files)}건")
    if pending_file_msgs:
        msg_parts.extend(pending_file_msgs)

    final_msg = " · ".join(msg_parts) if msg_parts else "갱신 대상이 없습니다."

    # --dry-run인 경우 파일에 쓰지 않고 전/후 diff 및 예정 메시지 반환
    if dry_run:
        preview_lines = [f"[dry-run] {final_msg}"]
        if diff_previews:
            preview_lines.append("\n대장 변경 예정 diff:")
            preview_lines.extend(diff_previews)
        return 0, "\n".join(preview_lines)

    if ledger_lines and new_ledger_lines != ledger_lines:
        ledger_file.write_text("\n".join(new_ledger_lines) + "\n", encoding="utf-8")

    baseline_path.write_text(json.dumps(baseline_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0, final_msg


# --- 3. drift-ledger 구현 ---

def append_to_ledger(
    ledger_path: Path,
    units: list[dict[str, Any]],
    dry_run: bool = False,
) -> tuple[int, str]:
    """drift-unit 결과를 반영대장.md 끝에 추가하거나 기존 대기 건 갱신."""
    if not ledger_path.is_file():
        return 1, f"반영대장 파일을 찾을 수 없습니다: {ledger_path}"

    text = ledger_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # 대장 머리줄 파싱 (11칸/12칸 동적 대응)
    header_idx, col_names, col_map = parse_ledger_header(lines)
    if header_idx == -1:
        # 헤더가 없으면 기본 12칸 양식 채택
        col_names = [
            "키", "발견일", "AS-IS 커밋", "종류", "단위",
            "변경 요약", "영향 화면", "TOBE 대응", "확인", "상태", "처리일", "비고",
        ]
        col_map = {name: i for i, name in enumerate(col_names)}

    existing_rows: dict[str, dict[str, Any]] = {}
    max_num = 0

    for idx, line in enumerate(lines):
        parts = split_table_row(line)
        if not parts or len(parts) != len(col_names):
            continue
        k = parts[col_map["키"]]
        if k.startswith("CH-"):
            m_num = re.search(r"CH-(\d+)", k)
            if m_num:
                max_num = max(max_num, int(m_num.group(1)))
            existing_rows[k] = {
                "line_idx": idx,
                "parts": parts,
                "key": k,
                "unit": parts[col_map["단위"]] if "단위" in col_map else "",
                "status": parts[col_map["상태"]] if "상태" in col_map else "",
            }

    now_kst = datetime.now(tz=KST)
    today_str = now_kst.strftime("%Y-%m-%d")

    added_rows: list[str] = []
    updated_rows: list[str] = []

    # 단위별 기존 행 확인
    unit_to_existing: dict[str, dict[str, Any]] = {}
    for r in existing_rows.values():
        u_clean = re.sub(r"[`*]", "", r["unit"]).strip()
        unit_to_existing[u_clean] = r

    for u in units:
        u_str = u["unit"]
        u_clean = re.sub(r"[`*]", "", u_str).strip()
        matched = unit_to_existing.get(u_clean)

        c_disp = f"`{u['lc']['hash']}` {u['lc']['date']} {u['lc']['subject'][:20]}" if u.get("lc") else "-"
        sc_disp = " ".join(u["screens"]) if u["screens"] else "(없음)"
        tobe_disp = u.get("tobe") or ""
        summary_disp = u["change"]

        if matched and matched["status"] == "대기":
            # 대기 상태이면 커밋·요약·화면·TOBE 갱신
            pts = matched["parts"]
            if "AS-IS 커밋" in col_map:
                pts[col_map["AS-IS 커밋"]] = c_disp
            if "변경 요약" in col_map:
                pts[col_map["변경 요약"]] = summary_disp
            if "영향 화면" in col_map:
                pts[col_map["영향 화면"]] = sc_disp
            if tobe_disp and "TOBE 대응" in col_map:
                pts[col_map["TOBE 대응"]] = tobe_disp
            lines[matched["line_idx"]] = format_table_row(pts)
            updated_rows.append(matched["key"])
        else:
            # 새 줄 추가
            max_num += 1
            new_key = f"CH-{max_num:04d}"
            row_cells = []
            for col in col_names:
                if col == "키":
                    row_cells.append(new_key)
                elif col == "발견일":
                    row_cells.append(today_str)
                elif col == "AS-IS 커밋":
                    row_cells.append(c_disp)
                elif col == "종류":
                    row_cells.append(u["kind"])
                elif col == "단위":
                    row_cells.append(u_str)
                elif col == "변경 요약":
                    row_cells.append(summary_disp)
                elif col == "영향 화면":
                    row_cells.append(sc_disp)
                elif col == "TOBE 대응":
                    row_cells.append(tobe_disp)
                elif col == "확인":
                    row_cells.append("")
                elif col == "상태":
                    row_cells.append("대기")
                elif col in ("확인", "처리일", "비고"):
                    row_cells.append("")
                else:
                    row_cells.append("")
            added_rows.append(format_table_row(row_cells))

    if dry_run:
        return 0, f"[dry-run] 추가 예정 {len(added_rows)}건, 대기 갱신 예정 {len(updated_rows)}건"

    lines.extend(added_rows)
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0, f"대장 반영 완료: 신규 추가 {len(added_rows)}건, 갱신 {len(updated_rows)}건 → {ledger_path.name}"


# --- 4. drift-diff 구현 ---

def render_unit_diff(
    unit: str,
    src_root: Path,
    base: str = "baseline",
    work_dir: Path | None = None,
) -> tuple[int, str]:
    """단일 단위(SQL id 또는 Class#method 등)의 AS-IS 전후 diff 및 TOBE 대응 본문 대조 출력."""
    wd = (work_dir or Path.cwd()).resolve()
    from yunhee.tools.trace.tobe import build_index, find_layout

    layout = find_layout(wd)
    tobe_idx = build_index(str(layout.root)) if layout.usable else None

    # 기준 커밋
    baseline_path = resolve_baseline_path(wd)
    base_commit = "HEAD~1"
    if base != "baseline":
        base_commit = base
    elif baseline_path.is_file():
        try:
            b_data = json.loads(baseline_path.read_text(encoding="utf-8"))
            commits = [v.get("commit") for v in b_data.values() if isinstance(v, dict) and v.get("commit") and v.get("commit") != "none"]
            if commits:
                base_commit = commits[0]
        except Exception:  # noqa: BLE001, S110
            pass

    out_lines: list[str] = [f"=== drift-diff: {unit} ==="]

    # SQL ID 여부 판별 (점 포함 및 xml 매퍼에 존재)
    is_sql = "." in unit and "#" not in unit and not unit.endswith(".java")
    if is_sql:
        ns = unit.split(".")[0]
        sid = unit.split(".")[-1]
        xml_matches = list(src_root.rglob(f"{ns}.xml"))
        if xml_matches:
            xml_p = xml_matches[0]
            rel_p = xml_p.relative_to(src_root).as_posix()

            # 이전(base_commit) 및 현재(작업 트리) 파일 내용 조회
            rc_base, base_raw, _ = _run_git(src_root, ["show", f"{base_commit}:{rel_p}"])
            base_content = base_raw if rc_base == 0 else ""
            curr_content = xml_p.read_text(encoding="utf-8", errors="replace")

            base_stmt = extract_mapper_statement_block(base_content, sid) if base_content else None
            curr_stmt = extract_mapper_statement_block(curr_content, sid)

            out_lines.append(f"--- AS-IS Diff ({rel_p} #{sid} @ {base_commit}..HEAD) ---")

            if base_stmt is None and curr_stmt is None:
                out_lines.append(f"(SQL ID '{sid}'를 base({base_commit})와 현재 파일 모두에서 찾을 수 없습니다)")
            elif base_stmt is None and curr_stmt is not None:
                kind, body, _incs, line_no = curr_stmt
                out_lines.append(f"[신규 추가] <{kind} id=\"{sid}\"> (L{line_no})")
                out_lines.append(body.strip())
            elif base_stmt is not None and curr_stmt is None:
                kind, body, _incs, line_no = base_stmt
                out_lines.append(f"[삭제됨] <{kind} id=\"{sid}\"> (base L{line_no})")
                out_lines.append(body.strip())
            else:
                assert base_stmt is not None and curr_stmt is not None
                _b_kind, b_body, _b_incs, b_lno = base_stmt
                _c_kind, c_body, c_incs, c_lno = curr_stmt

                # 공백 정규화 비교 (-w)
                b_norm = re.sub(r"\s+", " ", b_body.strip())
                c_norm = re.sub(r"\s+", " ", c_body.strip())

                if b_norm == c_norm:
                    out_lines.append(f"(해당 SQL 변경 없음 — 동일 또는 공백만 다름 @ L{c_lno})")
                else:
                    b_lines = [ln.rstrip() for ln in b_body.splitlines()]
                    c_lines = [ln.rstrip() for ln in c_body.splitlines()]
                    diff_lines = list(
                        difflib.unified_diff(
                            b_lines,
                            c_lines,
                            fromfile=f"{base_commit}:{rel_p} #{sid} L{b_lno}",
                            tofile=f"HEAD:{rel_p} #{sid} L{c_lno}",
                            lineterm="",
                        )
                    )
                    out_lines.extend(diff_lines)

                # 연관 <include refid="..."> 변경점 추적
                if c_incs and base_content:
                    for ref in dict.fromkeys(c_incs):
                        b_inc = extract_mapper_include_block(base_content, ref)
                        c_inc = extract_mapper_include_block(curr_content, ref)
                        if b_inc and c_inc:
                            b_inc_norm = re.sub(r"\s+", " ", b_inc.strip())
                            c_inc_norm = re.sub(r"\s+", " ", c_inc.strip())
                            if b_inc_norm != c_inc_norm:
                                out_lines.append(f"\n--- 연관 <sql id=\"{ref}\"> diff ---")
                                inc_diff = list(
                                    difflib.unified_diff(
                                        b_inc.splitlines(),
                                        c_inc.splitlines(),
                                        fromfile=f"include:{ref}@{base_commit}",
                                        tofile=f"include:{ref}@HEAD",
                                        lineterm="",
                                    )
                                )
                                out_lines.extend(inc_diff)

                # 연관 resultMap 변경 요약 (curr_stmt 내에 resultMap="foo" 참조 시)
                rm_match = re.search(r"resultMap\s*=\s*[\"']([^\"']+)[\"']", c_body)
                if rm_match and base_content:
                    rm_id = rm_match.group(1).split(".")[-1]
                    b_cols = set(extract_mapper_resultmap_columns(base_content, rm_id))
                    added_rm_cols = [c for c in extract_mapper_resultmap_columns(curr_content, rm_id) if c not in b_cols]
                    if added_rm_cols:
                        out_lines.append(f"\n(연관 resultMap '{rm_id}' +{len(added_rm_cols)}: {', '.join(added_rm_cols)})")

        else:
            out_lines.append(f"AS-IS 매퍼 XML({ns}.xml)을 찾지 못했습니다.")

        # TOBE 매퍼 대응 본문 (네임스페이스/AS-IS 주석 일치 우선)
        if tobe_idx:
            # 1순위: as_is_ids에 ns.sid 또는 unit이 들어있는 경우
            # 2순위: 네임스페이스와 sid가 모두 일치하는 경우
            tobe_stmts = [
                s for s in tobe_idx.statements.values()
                if unit in s.as_is_ids or f"{ns}.{sid}" in s.as_is_ids or (s.namespace.lower() == ns.lower() and s.id == sid)
            ]
            if tobe_stmts:
                out_lines.append("\n--- TOBE 대응 문장 ---")
                for ts in tobe_stmts:
                    out_lines.append(f"[{ts.namespace}.{ts.id}] {ts.file}:{ts.line} ({ts.kind})")
                    t_xml = Path(ts.file).read_text(encoding="utf-8", errors="replace").splitlines()
                    out_lines.extend(t_xml[max(0, ts.line - 1):min(len(t_xml), ts.line + 25)])
            else:
                out_lines.append("\n--- TOBE 대응 문장: 없음 ---")

    else:
        # 메서드 또는 클래스
        m_match = re.match(r"^([A-Za-z0-9_]+)#([A-Za-z0-9_]+)", unit)
        cls_name = m_match.group(1) if m_match else unit.replace(".java", "")
        m_name = m_match.group(2) if m_match else ""

        j_matches = list(src_root.rglob(f"{cls_name}.java"))
        if j_matches:
            j_p = j_matches[0]
            rel_p = j_p.relative_to(src_root).as_posix()
            _rc, diff_txt, _ = _run_git(src_root, ["diff", "-w", base_commit, "HEAD", "--", rel_p])
            out_lines.append(f"--- AS-IS Diff ({rel_p} @ {base_commit}..HEAD) ---")
            out_lines.append(diff_txt.strip() if diff_txt.strip() else "(diff 없음)")
        else:
            out_lines.append(f"AS-IS 클래스({cls_name}.java)를 찾지 못했습니다.")

        # TOBE 서비스/컨트롤러 대응 본문
        if tobe_idx:
            tobe_svcs = [
                sm for (s_cls, sm_name), sm in tobe_idx.services.items()
                if (sm_name == m_name and (cls_name.lower() in s_cls.lower() or not cls_name))
                or any(unit in k for k in sm.keys)
            ]
            if tobe_svcs:
                out_lines.append("\n--- TOBE 대응 서비스 메서드 ---")
                for sm in tobe_svcs:
                    out_lines.append(f"[{sm.service}#{sm.name}()] {sm.file}:{sm.line}")
            else:
                out_lines.append("\n--- TOBE 대응 서비스: 없음 ---")

    return 0, "\n".join(out_lines)


# --- 5. drift-db 구현 ---

def compare_dbml_snapshots(
    from_dbml: Path,
    to_dbml: Path,
    work_dir: Path | None = None,
) -> tuple[int, str]:
    """DBML 스냅샷 파일 간의 테이블, 컬럼, 함수 본문 추가/변경/삭제 및 영향 TOBE 매퍼 출력."""
    if not from_dbml.is_file():
        return 1, f"이전 DBML 파일을 찾을 수 없습니다: {from_dbml}"
    if not to_dbml.is_file():
        return 1, f"새 DBML 파일을 찾을 수 없습니다: {to_dbml}"

    from yunhee.tools.as_is.dbml_indexer import (
        parse_subsections,
        parse_tables,
        split_sections,
    )
    from yunhee.tools.trace.tobe import build_index, find_layout

    wd = (work_dir or Path.cwd()).resolve()
    layout = find_layout(wd)
    tobe_idx = build_index(str(layout.root)) if layout.usable else None

    s_from = split_sections(from_dbml.read_text(encoding="utf-8", errors="replace"))
    s_to = split_sections(to_dbml.read_text(encoding="utf-8", errors="replace"))

    t_from = dict(parse_tables(s_from.get("DBML", "")))
    t_to = dict(parse_tables(s_to.get("DBML", "")))

    f_from = dict(parse_subsections(s_from.get("Functions", "")))
    f_to = dict(parse_subsections(s_to.get("Functions", "")))

    lines: list[str] = [
        f"=== drift-db: {from_dbml.name} → {to_dbml.name} ===",
    ]

    # 테이블 및 컬럼 비교
    names_from = set(t_from.keys())
    names_to = set(t_to.keys())

    added_tables = sorted(names_to - names_from)
    deleted_tables = sorted(names_from - names_to)
    common_tables = sorted(names_from & names_to)

    if added_tables:
        lines.append(f"\n[신규 테이블 {len(added_tables)}개]")
        for t in added_tables:
            lines.append(f"  + {t}")

    if deleted_tables:
        lines.append(f"\n[삭제 테이블 {len(deleted_tables)}개]")
        for t in deleted_tables:
            lines.append(f"  - {t}")

    col_changes: list[str] = []

    def _parse_cols(body: str) -> dict[str, str]:
        cols = {}
        for line in body.splitlines():
            line = line.strip()
            if line.startswith('"') and not line.startswith('Note:'):
                m = re.match(r'^"([^"]+)"\s+"([^"]+)"(?:\s*\[(.*)\])?', line)
                if m:
                    cols[m.group(1)] = f"{m.group(2)} [{m.group(3) or ''}]"
        return cols

    for t in common_tables:
        cols_a = _parse_cols(t_from[t])
        cols_b = _parse_cols(t_to[t])
        a_set = set(cols_a.keys())
        b_set = set(cols_b.keys())
        add_c = sorted(b_set - a_set)
        del_c = sorted(a_set - b_set)
        mod_c = [c for c in sorted(a_set & b_set) if cols_a[c] != cols_b[c]]

        if add_c or del_c or mod_c:
            col_changes.append(f"### {t}")
            for c in add_c:
                col_changes.append(f"  + 컬럼 추가: {c} ({cols_b[c]})")
            for c in del_c:
                col_changes.append(f"  - 컬럼 삭제: {c}")
            for c in mod_c:
                col_changes.append(f"  * 컬럼 변경: {c} ({cols_a[c]} → {cols_b[c]})")

            # TOBE 매퍼 연관 탐색
            if tobe_idx:
                matched_stmts = [
                    s for s in tobe_idx.statements.values()
                    if t in s.tables
                ]
                if matched_stmts:
                    stmts_preview = ", ".join(s.id for s in matched_stmts[:8])
                    more = f" 외 {len(matched_stmts) - 8}개" if len(matched_stmts) > 8 else ""
                    col_changes.append(f"    → 영향 TOBE 매퍼 ({len(matched_stmts)}건): {stmts_preview}{more}")

    if col_changes:
        lines.append(f"\n[컬럼 변경 테이블 {len(col_changes)}개]")
        lines.extend(col_changes)

    # 함수 비교
    fn_a = set(f_from.keys())
    fn_b = set(f_to.keys())
    add_f = sorted(fn_b - fn_a)
    del_f = sorted(fn_a - fn_b)
    mod_f = [f for f in sorted(fn_a & fn_b) if f_from[f].strip() != f_to[f].strip()]

    if add_f or del_f or mod_f:
        lines.append("\n[DB 함수 변경]")
        for f in add_f:
            lines.append(f"  + 함수 추가: {f}")
        for f in del_f:
            lines.append(f"  - 함수 삭제: {f}")
        for f in mod_f:
            lines.append(f"  * 함수 본문 변경: {f}")

    if not added_tables and not deleted_tables and not col_changes and not (add_f or del_f or mod_f):
        lines.append("DBML 간에 변경 사항이 없습니다.")

    return 0, "\n".join(lines)


# --- 6. drift-log 구현 ---

def render_drift_log(
    src_root: Path,
    since: str = "baseline",
    work_dir: Path | None = None,
) -> tuple[int, str]:
    """커밋마다 파일과 종류(DB·SQL·LOGIC·MODEL·UI·ETC)를 요약하여 출력."""
    wd = (work_dir or Path.cwd()).resolve()

    since_commit = since
    if since == "baseline":
        baseline_path = resolve_baseline_path(wd)
        if baseline_path.is_file():
            try:
                b_data = json.loads(baseline_path.read_text(encoding="utf-8"))
                commits = [v.get("commit") for v in b_data.values() if isinstance(v, dict) and v.get("commit") and v.get("commit") != "none"]
                if commits:
                    since_commit = commits[0]
            except Exception:  # noqa: BLE001, S110
                pass
        if since_commit == "baseline":
            since_commit = "HEAD~5"

    rc, log_out, _ = _run_git(
        src_root,
        ["log", f"{since_commit}..HEAD", "--pretty=format:commit %h %cd %an %s", "--date=short", "--name-status"],
    )
    if rc != 0 or not log_out.strip():
        return 0, f"기준({since_commit}) 이후 들어온 커밋이 없습니다."

    lines: list[str] = [f"=== drift-log (since {since_commit}) ==="]
    curr_commit = ""
    curr_files: list[tuple[str, str]] = []

    def _flush_commit():
        if curr_commit:
            kinds_cnt: dict[str, int] = defaultdict(int)
            for status, p in curr_files:
                k = classify_file_kind(p)
                kinds_cnt[k] += 1
            kinds_str = " · ".join(f"{k} {cnt}" for k, cnt in sorted(kinds_cnt.items()))
            lines.append(f"- {curr_commit} ({kinds_str or '파일 없음'})")

    for line in log_out.splitlines():
        if line.startswith("commit "):
            _flush_commit()
            curr_commit = line[7:]
            curr_files = []
        elif line.strip() and "\t" in line:
            parts = line.split("\t")
            st = parts[0]
            p = parts[-1]
            curr_files.append((st, p))

    _flush_commit()

    return 0, "\n".join(lines)
