"""AS-IS 소스 기준 커밋 기록, 원본 변경 감지(drift), 변환 시점 기준(baseline) 관리 도구."""

from __future__ import annotations

import getpass
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from yunhee import config, project

KST = timezone(timedelta(hours=9))


def _run_git(src_root: Path, args: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    """src_root에서 읽기 전용 git 명령을 실행한다."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(src_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def git_toplevel(src_root: Path) -> Path | None:
    """src_root가 속한 git 저장소의 최상위 경로 (없으면 None)."""
    if not src_root or not src_root.is_dir():
        return None
    rc, out, _ = _run_git(src_root, ["rev-parse", "--show-toplevel"])
    if rc != 0 or not out.strip():
        return None
    return Path(out.strip()).resolve()


def is_git_repo(src_root: Path, vcs_root: Path | str | None = None) -> bool:
    """src_root가 git 저장소의 루트인지 확인한다.

    조상 디렉터리의 바깥 저장소는 무시한다. 소스 루트가 저장소의 하위 폴더이면
    vcs_root로 그 저장소 루트를 명시해야 git 정보를 쓴다.
    """
    top = git_toplevel(src_root)
    if top is None:
        return False
    allowed = {src_root.resolve()}
    if vcs_root:
        allowed.add(Path(vcs_root).resolve())
    if top not in allowed:
        return False
    rc_head, _, _ = _run_git(src_root, ["rev-parse", "--verify", "HEAD"])
    return rc_head == 0


def collect_source_info(src_root: Path, vcs_root: Path | str | None = None) -> dict[str, Any]:
    """소스 루트의 git 커밋·브랜치·dirty·blob 해시(또는 비-git mtime) 정보를 수집한다."""
    now_kst = datetime.now(tz=KST)
    indexed_at = now_kst.isoformat(timespec="seconds")
    indexed_at_short = now_kst.strftime("%Y-%m-%d %H:%M")
    ver = project.current_version()
    repo_name = src_root.resolve().name

    outer_top = None if is_git_repo(src_root, vcs_root) else git_toplevel(src_root)
    if not is_git_repo(src_root, vcs_root):
        max_mtime = 0.0
        for p in src_root.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                try:
                    mt = p.stat().st_mtime
                    max_mtime = max(max_mtime, mt)
                except OSError:
                    pass
        mtime_dt = datetime.fromtimestamp(max_mtime, tz=KST) if max_mtime > 0 else now_kst
        return {
            "vcs": "none",
            "outer_repo": str(outer_top) if outer_top else None,
            "src_root": str(src_root.resolve()),
            "repo_name": repo_name,
            "commit": None,
            "commit_short": None,
            "branch": None,
            "commit_time": None,
            "commit_time_short": None,
            "commit_date": None,
            "dirty": False,
            "dirty_files": [],
            "remote": None,
            "max_mtime": mtime_dt.isoformat(timespec="seconds"),
            "max_mtime_short": mtime_dt.strftime("%Y-%m-%d %H:%M"),
            "indexed_at": indexed_at,
            "indexed_at_short": indexed_at_short,
            "yunhee_version": ver,
            "tree_blobs": {},
        }

    _, commit_out, _ = _run_git(src_root, ["rev-parse", "HEAD"])
    commit = commit_out.strip()
    commit_short = commit[:7]

    _, branch_out, _ = _run_git(src_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_out.strip() or "HEAD"

    _, ct_out, _ = _run_git(src_root, ["log", "-1", "--format=%ct"])
    try:
        ct_dt = datetime.fromtimestamp(int(ct_out.strip()), tz=KST)
    except ValueError:
        ct_dt = now_kst
    commit_time = ct_dt.isoformat(timespec="seconds")
    commit_time_kst = ct_dt.strftime("%Y-%m-%d %H:%M +0900")
    commit_time_short = ct_dt.strftime("%Y-%m-%d %H:%M")
    commit_date = ct_dt.strftime("%Y-%m-%d")

    _, remote_out, _ = _run_git(src_root, ["config", "--get", "remote.origin.url"])
    remote = remote_out.strip() or None

    # 추적 파일의 미커밋 변경 확인 (git status --porcelain -uno)
    _, status_out, _ = _run_git(src_root, ["status", "--porcelain", "-uno"])
    dirty_files: list[str] = []
    for line in status_out.splitlines():
        if len(line) > 3:
            path_part = line[3:].strip()
            if " -> " in path_part:
                old_p, new_p = path_part.split(" -> ", 1)
                dirty_files.append(old_p.strip().strip('"'))
                dirty_files.append(new_p.strip().strip('"'))
            else:
                dirty_files.append(path_part.strip('"'))
    dirty = len(dirty_files) > 0

    # git ls-tree -r HEAD 한 번으로 전체 blob 해시 수집
    tree_blobs: dict[str, str] = {}
    rc_tree, tree_out, _ = _run_git(src_root, ["ls-tree", "-r", "HEAD"])
    if rc_tree == 0:
        for line in tree_out.splitlines():
            if "\t" not in line:
                continue
            meta, rel_p = line.split("\t", 1)
            parts = meta.split()
            if len(parts) >= 3:
                tree_blobs[rel_p.strip('"')] = parts[2]

    return {
        "vcs": "git",
        "vcs_root": str(Path(vcs_root).resolve()) if vcs_root else None,
        "src_root": str(src_root.resolve()),
        "repo_name": repo_name,
        "commit": commit,
        "commit_short": commit_short,
        "branch": branch,
        "commit_time": commit_time,
        "commit_time_kst": commit_time_kst,
        "commit_time_short": commit_time_short,
        "commit_date": commit_date,
        "dirty": dirty,
        "dirty_files": sorted(set(dirty_files)),
        "remote": remote,
        "indexed_at": indexed_at,
        "indexed_at_kst": now_kst.strftime("%Y-%m-%d %H:%M +0900"),
        "indexed_at_short": indexed_at_short,
        "yunhee_version": ver,
        "tree_blobs": tree_blobs,
    }


def get_git_branch_sync_status(src_root: Path) -> str:
    """git fetch 없이 로컬 origin/<branch> 대비 ahead/behind 상태를 문자열로 반환한다."""
    if not src_root or not src_root.is_dir() or not is_git_repo(src_root):
        return "(git 아님)"
    _, branch_out, _ = _run_git(src_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_out.strip() or "HEAD"

    upstream = f"origin/{branch}"
    rc_up, _, _ = _run_git(src_root, ["rev-parse", "--verify", upstream])
    if rc_up != 0:
        rc_u2, up_out, _ = _run_git(src_root, ["rev-parse", "--abbrev-ref", "@{upstream}"])
        if rc_u2 == 0 and up_out.strip():
            upstream = up_out.strip()
        else:
            return branch

    rc_cnt, cnt_out, _ = _run_git(src_root, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
    if rc_cnt != 0 or not cnt_out.strip():
        return branch
    parts = cnt_out.strip().split()
    if len(parts) != 2:
        return branch
    ahead, behind = int(parts[0]), int(parts[1])
    if ahead > 0 and behind > 0:
        return f"{branch} ({upstream} 대비 ahead {ahead}, behind {behind})"
    if behind > 0:
        return f"{branch} ({upstream} 대비 behind {behind})"
    if ahead > 0:
        return f"{branch} ({upstream} 대비 ahead {ahead})"
    return f"{branch} ({upstream}와 동일)"


def check_commit_mismatch_warning(src_root: Path | None, src_index: Path | None) -> str | None:
    """소스 HEAD와 색인(_source.json)의 commit이 다르면 경고 문구를 반환한다."""
    if not src_root or not src_root.is_dir() or not src_index or not src_index.is_dir():
        return None
    source_json = src_index / "_source.json"
    if not source_json.is_file():
        return None
    try:
        idx_meta = json.loads(source_json.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    idx_commit = idx_meta.get("commit")
    if not idx_commit or idx_meta.get("vcs") != "git":
        return None
    if not is_git_repo(src_root, idx_meta.get("vcs_root")):
        return None
    rc, head_out, _ = _run_git(src_root, ["rev-parse", "HEAD"])
    if rc != 0 or not head_out.strip():
        return None
    head_commit = head_out.strip()
    if head_commit != idx_commit:
        return (
            f"⚠ 소스 HEAD({head_commit[:7]})가 색인 기준({idx_commit[:7]})과 다릅니다 "
            f"— 색인을 다시 만들거나 git pull 상태를 확인하세요"
        )
    return None


def compute_sha256_file(path: Path) -> str:
    """파일의 sha256 해시를 'sha256:<hex>' 형식으로 반환한다."""
    data = path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_git_blob_file(path: Path) -> str:
    """파일의 git blob sha1 해시를 계산한다."""
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def compute_source_file_hash(src_root: Path, rel_path: str, source_info: dict[str, Any]) -> str:
    """색인 기록용 파일 해시: clean git 추적 파일이면 blob 해시, 아니면 sha256:<hex>."""
    abs_path = src_root / rel_path
    if source_info.get("vcs") == "git":
        dirty_set = set(source_info.get("dirty_files") or [])
        tree_blobs = source_info.get("tree_blobs") or {}
        if rel_path in tree_blobs and rel_path not in dirty_set:
            return tree_blobs[rel_path]
    if abs_path.is_file():
        return compute_sha256_file(abs_path)
    return ""


def render_frontmatter(
    source_commit: str | None,
    indexed_at: str,
    source_files: dict[str, str],
    shared_links: list[str] | None = None,
) -> list[str]:
    """화면 마크다운 상단 YAML frontmatter 줄 목록을 생성한다."""
    commit_val = source_commit if source_commit else "none"
    lines = [
        "---",
        f"source_commit: {commit_val}",
        f"indexed_at: {indexed_at}",
    ]
    if source_files:
        lines.append("source_files:")
        for rel_p, h in sorted(source_files.items()):
            lines.append(f"  {rel_p}: {h}")
    else:
        lines.append("source_files: {}")
    if shared_links:
        lines.append("shared_links:")
        for link in sorted(shared_links):
            lines.append(f"  - {link}")
    lines.append("---")
    return lines


def parse_frontmatter(md_text: str) -> tuple[dict[str, Any] | None, str]:
    """마크다운 텍스트에서 YAML frontmatter를 분리해 (frontmatter_dict, 본문)을 반환한다.

    frontmatter가 없는 옛 색인은 (None, md_text)를 반환한다.
    """
    if not md_text.startswith("---\n"):
        return None, md_text
    end_idx = md_text.find("\n---\n", 4)
    if end_idx < 0:
        if md_text.endswith("\n---"):
            end_idx = len(md_text) - 4
        else:
            return None, md_text
    fm_block = md_text[4:end_idx]
    body = md_text[end_idx + 5 :].lstrip("\n")

    fm: dict[str, Any] = {
        "source_commit": None,
        "indexed_at": None,
        "source_files": {},
        "shared_links": [],
    }
    section: str | None = None
    for raw_line in fm_block.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" "):
            section = None
            if ":" in raw_line:
                k, v = raw_line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k == "source_commit":
                    fm["source_commit"] = None if v in ("none", "null", "") else v
                elif k == "indexed_at":
                    fm["indexed_at"] = v
                elif k == "source_files":
                    if v == "{}":
                        fm["source_files"] = {}
                    else:
                        section = "source_files"
                elif k == "shared_links":
                    if v == "[]":
                        fm["shared_links"] = []
                    else:
                        section = "shared_links"
        else:
            stripped = raw_line.strip()
            if section == "source_files" and ":" in stripped:
                # 경로에는 ':'가 없고 해시 값은 'sha256:...'일 수 있으므로 첫 ':'로 분리
                k, v = stripped.split(":", 1)
                fm["source_files"][k.strip()] = v.strip()
            elif section == "shared_links" and stripped.startswith("- "):
                fm["shared_links"].append(stripped[2:].strip())
    return fm, body


def categorize_source_files(screen_name: str, source_files: dict[str, str]) -> dict[str, int]:
    """화면의 source_files를 client, server, service, mapper 4개 범주로 집계한다."""
    m_pref = re.match(r"^([A-Za-z]+\d+)_", screen_name)
    screen_prefix = m_pref.group(1).lower() if m_pref else ""

    counts = {"client": 0, "server": 0, "service": 0, "mapper": 0}
    for rel_p in source_files:
        p = Path(rel_p)
        parts_lower = [pt.lower() for pt in p.parts]
        stem_lower = p.stem.lower()
        if p.suffix.lower() == ".xml" or "mapper" in parts_lower:
            counts["mapper"] += 1
        elif "service" in parts_lower or "services" in parts_lower or p.stem.endswith(("Service", "ServiceAsync")):
            counts["service"] += 1
        elif "server" in parts_lower:
            m_f = re.match(r"^([A-Za-z]+\d+)_", p.stem)
            f_pref = m_f.group(1).lower() if m_f else ""
            if (screen_prefix and f_pref and f_pref != screen_prefix) or "common" in stem_lower:
                counts["service"] += 1
            else:
                counts["server"] += 1
        else:
            counts["client"] += 1
    return counts


def format_screen_source_section(screen_name: str, fm: dict[str, Any] | None) -> str:
    """analysis screen <화면> --section source 출력 문자열을 생성한다."""
    if fm is None:
        return f"{screen_name}: 기준 없음 (색인에 frontmatter가 없습니다 — `yunhee index-src`를 다시 실행하세요)"
    commit = fm.get("source_commit") or "none"
    commit_short = commit[:7] if commit != "none" else "none"
    sfiles: dict[str, str] = fm.get("source_files") or {}
    if not sfiles:
        return f"source_commit {commit_short} · 기준 불완전 (의존 파일 0개)"
    cats = categorize_source_files(screen_name, sfiles)
    head = (
        f"source_commit {commit_short} · 의존 파일 {len(sfiles)}개 "
        f"(client {cats['client']} · server {cats['server']} · service {cats['service']} · mapper {cats['mapper']})"
    )
    lines = [head]
    for rel_p, h in sorted(sfiles.items()):
        h_disp = h[:14] if h.startswith("sha256:") else h[:7]
        lines.append(f"- `{rel_p}`: `{h_disp}`")
    shared_links = fm.get("shared_links") or []
    if shared_links:
        lines.append(f"- shared_links: {', '.join(shared_links)}")
    return "\n".join(lines)


def save_prev_generation(target_dir: Path) -> None:
    """index-src가 기존 색인을 덮어쓰기 직전에 이전 기준(_source.json, 화면별 source_files)을 _prev/에 1세대 보관한다."""
    source_json = target_dir / "_source.json"
    screen_mds = list(target_dir.glob("*/screens/*.md")) + list(target_dir.glob("*/components/*.md"))
    if not source_json.is_file() and not screen_mds:
        return

    screens_data: dict[str, Any] = {}
    for md_file in screen_mds:
        if "_prev" in md_file.parts:
            continue
        raw = md_file.read_text(encoding="utf-8", errors="replace")
        fm, _ = parse_frontmatter(raw)
        is_comp = "components" in md_file.parts
        if fm is not None:
            screens_data[md_file.stem] = {
                "kind": "component" if is_comp else "screen",
                "source_commit": fm.get("source_commit"),
                "source_files": fm.get("source_files") or {},
                "shared_links": fm.get("shared_links") or [],
            }
        else:
            screens_data[md_file.stem] = {
                "kind": "component" if is_comp else "screen",
                "source_commit": None,
                "source_files": None,
                "shared_links": [],
            }

    if not source_json.is_file() and not screens_data:
        return

    prev_dir = target_dir / "_prev"
    prev_dir.mkdir(parents=True, exist_ok=True)
    if source_json.is_file():
        (prev_dir / "_source.json").write_text(source_json.read_text(encoding="utf-8"), encoding="utf-8")
    (prev_dir / "_screens.json").write_text(
        json.dumps(screens_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def compute_prev_index_diff(
    target_dir: Path,
    curr_screens: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """_prev/에 보관된 지난 색인과 방금 생성한 색인을 비교해 변경·신규·삭제 화면 수를 계산한다."""
    prev_screens_file = target_dir / "_prev" / "_screens.json"
    if not prev_screens_file.is_file():
        return None
    try:
        prev_all = json.loads(prev_screens_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None

    prev_source_file = target_dir / "_prev" / "_source.json"
    prev_commit_short = "이전"
    if prev_source_file.is_file():
        try:
            ps = json.loads(prev_source_file.read_text(encoding="utf-8"))
            prev_commit_short = ps.get("commit_short") or (ps.get("commit") or "")[:7] or "이전"
        except Exception:  # noqa: BLE001, S110
            pass

    prev_sc = {k: v for k, v in prev_all.items() if v.get("kind", "screen") == "screen"}
    curr_sc = {k: v for k, v in curr_screens.items() if v.get("kind", "screen") == "screen"}

    prev_names = set(prev_sc.keys())
    curr_names = set(curr_sc.keys())

    added = len(curr_names - prev_names)
    deleted = len(prev_names - curr_names)
    changed = 0
    for name in curr_names & prev_names:
        p_files = prev_sc[name].get("source_files")
        c_files = curr_sc[name].get("source_files")
        if p_files != c_files:
            changed += 1
            continue
        # 연결 컴포넌트 변경도 확인
        c_links = curr_sc[name].get("shared_links") or []
        if any(
            prev_all.get(lk, {}).get("source_files") != curr_screens.get(lk, {}).get("source_files")
            for lk in c_links
        ):
            changed += 1

    summary_line = (
        f"지난 색인 대비 변경 화면 {changed}개, 신규 {added}개, 삭제 {deleted}개 "
        f"(지난 색인({prev_commit_short}) 대비 변경 {changed}개)"
    )
    return {
        "prev_commit_short": prev_commit_short,
        "changed": changed,
        "added": added,
        "deleted": deleted,
        "summary": summary_line,
    }


def resolve_drift_config(work_dir: Path | None = None) -> dict[str, Any]:
    """TOBE 저장소의 .yunhee.toml [drift] 설정을 읽어 기본값과 합쳐 반환한다."""
    wd = (work_dir or Path.cwd()).resolve()
    toml_file, toml_cfg = config._find_yunhee_toml(wd)
    drift_cfg = toml_cfg.get("drift", {}) if isinstance(toml_cfg, dict) else {}
    base_root = toml_file.parent if toml_file else wd

    raw_status = drift_cfg.get("record_status", ["완료", "확인"])
    if isinstance(raw_status, str):
        status_list = [s.strip() for s in raw_status.split(",") if s.strip()]
    elif isinstance(raw_status, list):
        status_list = [str(s).strip() for s in raw_status if str(s).strip()]
    else:
        status_list = ["완료", "확인"]

    return {
        "base_root": base_root,
        "baseline": drift_cfg.get("baseline"),
        "done_from": drift_cfg.get("done_from", "docs/01-변환목록.md"),
        "record_status": status_list,
        "note_dir": drift_cfg.get("note_dir", "docs/work"),
        "note_suffix": drift_cfg.get("note_suffix", "-작업기록.md"),
    }


def resolve_baseline_path(work_dir: Path | None = None) -> Path:
    """TOBE 저장소의 baseline.json 경로를 결정한다 (.yunhee.toml [drift] baseline 우선, 기본 .yunhee/baseline.json)."""
    wd = (work_dir or Path.cwd()).resolve()
    d_cfg = resolve_drift_config(wd)
    custom_rel = d_cfg.get("baseline")
    if custom_rel:
        p = Path(custom_rel)
        return p if p.is_absolute() else (d_cfg["base_root"] / p)
    return wd / ".yunhee" / "baseline.json"


def _clean_md_cell_text(val: str) -> str:
    """마크다운 셀에서 링크·백틱·강조 기호를 벗기고 공백을 정리한다."""
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", val)
    return re.sub(r"[`*_~]", "", s).strip()


def _clean_class_cell(raw_cls: str) -> str:
    """표의 클래스 칸에서 마크다운 링크·백틱·부가 설명을 벗겨 순수 클래스명을 추출한다."""
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw_cls).strip()
    m_bt = re.search(r"`([A-Za-z_][A-Za-z0-9_./]*)`", s)
    if m_bt:
        cand = m_bt.group(1)
    else:
        cand = re.sub(r"[`*_~]", "", s).strip()
        if cand:
            cand = cand.split()[0].rstrip(",;)")
    if "/" in cand or cand.endswith(".java"):
        cand = Path(cand).stem
    return cand


def parse_conversion_table(
    md_text: str,
    id_col: str = "ID",
    class_col: str = "클래스",
    status_col: str = "상태",
) -> list[dict[str, str]]:
    """마크다운 문서 안의 표들을 스캔해 헤더 이름으로 ID·클래스·상태 열을 찾아 행 목록을 반환한다."""
    lines = md_text.splitlines()
    results: list[dict[str, str]] = []
    i = 0
    n = len(lines)

    target_id_h = id_col.strip().lower()
    target_cls_h = class_col.strip().lower()
    target_st_h = status_col.strip().lower()

    def _split_row(line: str) -> list[str]:
        return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]

    def _is_sep_row(line: str) -> bool:
        s = line.strip()
        if not s.startswith("|"):
            return False
        cells = _split_row(s)
        return bool(cells) and all(bool(re.match(r"^:?-+:?$", c)) for c in cells)

    while i < n:
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < n and _is_sep_row(lines[i + 1]):
            headers = [_clean_md_cell_text(c).lower() for c in _split_row(line)]
            id_idx = headers.index(target_id_h) if target_id_h in headers else -1
            cls_idx = headers.index(target_cls_h) if target_cls_h in headers else -1
            st_idx = headers.index(target_st_h) if target_st_h in headers else -1

            i += 2
            if id_idx >= 0 and cls_idx >= 0 and st_idx >= 0:
                max_idx = max(id_idx, cls_idx, st_idx)
                while i < n:
                    r_line = lines[i].strip()
                    if not r_line.startswith("|"):
                        break
                    if _is_sep_row(r_line):
                        i += 1
                        continue
                    cells = _split_row(r_line)
                    if len(cells) > max_idx:
                        r_id = _clean_md_cell_text(cells[id_idx])
                        r_cls = _clean_class_cell(cells[cls_idx])
                        r_st = _clean_md_cell_text(cells[st_idx])
                        if r_id or r_cls:
                            results.append({"id": r_id, "class": r_cls, "status": r_st})
                    i += 1
                continue
        i += 1

    return results


def resolve_done_screens(work_dir: Path | None = None, baseline_data: dict[str, Any] | None = None) -> set[str]:
    """--done-only 대상 화면 집합을 반환한다 (.yunhee.toml [drift] done_from 파일 + baseline.json 키)."""
    wd = (work_dir or Path.cwd()).resolve()
    done_set: set[str] = set()
    if baseline_data:
        done_set |= set(baseline_data.keys())

    d_cfg = resolve_drift_config(wd)
    done_from = d_cfg.get("done_from")
    if done_from:
        df_path = Path(done_from)
        if not df_path.is_absolute():
            cand = d_cfg["base_root"] / df_path
            df_path = cand if cand.is_file() else (wd / df_path)
        if df_path.is_file():
            text = df_path.read_text(encoding="utf-8", errors="replace")
            status_set = set(d_cfg.get("record_status") or ["완료", "확인"])
            parsed = parse_conversion_table(text)
            if parsed:
                for r in parsed:
                    if r["status"] in status_set and r["class"]:
                        done_set.add(r["class"])
            else:
                for line in text.splitlines():
                    if any(tok in line for tok in ("완료", "확인", "[x]", "[X]", "✅", "DONE", "done")) or "|" in line:
                        for m in re.finditer(r"\b([A-Z][a-z0-9]+_[A-Za-z0-9_]+)\b", line):
                            done_set.add(m.group(1))
    return done_set


def load_index_screens(src_index: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, Any]]:
    """색인 폴더에서 모든 화면/컴포넌트 frontmatter, _files.json, _source.json을 로드한다."""
    source_meta: dict[str, Any] = {}
    source_json = src_index / "_source.json"
    if source_json.is_file():
        try:
            source_meta = json.loads(source_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            source_meta = {}

    files_map: dict[str, list[str]] = {}
    files_json = src_index / "_files.json"
    if files_json.is_file():
        try:
            files_map = json.loads(files_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            files_map = {}

    screens: dict[str, dict[str, Any]] = {}
    for md_file in sorted(list(src_index.glob("*/screens/*.md")) + list(src_index.glob("*/components/*.md"))):
        if "_prev" in md_file.parts:
            continue
        raw = md_file.read_text(encoding="utf-8", errors="replace")
        fm, _ = parse_frontmatter(raw)
        is_comp = "components" in md_file.parts
        screens[md_file.stem] = {
            "name": md_file.stem,
            "kind": "component" if is_comp else "screen",
            "md_file": md_file,
            "has_frontmatter": fm is not None,
            "source_commit": fm.get("source_commit") if fm else None,
            "indexed_at": fm.get("indexed_at") if fm else None,
            "source_files": fm.get("source_files") if fm else None,
            "shared_links": (fm.get("shared_links") or []) if fm else [],
        }

    # _files.json이 없을 경우 화면 frontmatter로부터 즉석 복원
    if not files_map:
        rev: dict[str, set[str]] = defaultdict(set)
        for s_name, info in screens.items():
            if info["kind"] != "screen":
                continue
            for rel_p in info.get("source_files") or {}:
                rev[rel_p].add(s_name)
            for lk in info.get("shared_links") or []:
                comp_info = screens.get(lk)
                if comp_info:
                    for rel_p in comp_info.get("source_files") or {}:
                        rev[rel_p].add(s_name)
        files_map = {k: sorted(v) for k, v in rev.items()}

    return screens, files_map, source_meta


def _check_index_freshness(
    src_root: Path | None,
    src_index: Path | None,
) -> tuple[int, str, dict[str, dict[str, Any]], dict[str, Any]]:
    """record 계열 명령을 위한 색인 유효성 및 최신성 검사."""
    if not src_index or not src_index.is_dir():
        return 2, f"오류: 색인 폴더를 찾을 수 없습니다: {src_index} — `index-src` 먼저 실행하세요.", {}, {}

    screens, _, source_meta = load_index_screens(src_index)
    if not source_meta:
        return 2, "오류: 색인이 오래됨 (_source.json 없음) — `index-src` 먼저 실행하세요.", {}, {}

    if source_meta.get("dirty"):
        return 2, "오류: 색인이 dirty 상태입니다 (미커밋 변경 포함) — 커밋 후 `index-src` 먼저 실행하세요.", {}, {}

    if src_root and src_root.is_dir() and is_git_repo(src_root, source_meta.get("vcs_root")):
        curr_info = collect_source_info(src_root, source_meta.get("vcs_root"))
        if curr_info.get("dirty"):
            return 2, "오류: 소스에 미커밋 변경(dirty)이 있습니다 — 커밋 후 `index-src` 먼저 실행하세요.", {}, {}
        if curr_info.get("commit") != source_meta.get("commit"):
            msg = (
                f"오류: 색인이 오래됨 (소스 HEAD {curr_info.get('commit_short')} != 색인 {source_meta.get('commit_short')}) "
                f"— `index-src` 먼저 실행하세요."
            )
            return 2, msg, {}, {}

    return 0, "", screens, source_meta


def record_baseline(
    screen_names: list[str],
    src_root: Path,
    src_index: Path,
    task_id: str | None = None,
    note_file: Path | None = None,
    force: bool = False,
    work_dir: Path | None = None,
) -> tuple[int, str]:
    """화면의 현재 색인 기준을 baseline.json에 기록하고, 선택적으로 --note-file 머리에 AS-IS 기준 줄을 갱신한다.

    반환: (exit_code, output_message)
    """
    if note_file and not note_file.is_file():
        return 1, f"오류: 작업기록 파일이 존재하지 않습니다: {note_file} (현재 디렉터리를 확인하세요)"

    code, err_msg, screens, source_meta = _check_index_freshness(src_root, src_index)
    if code != 0:
        return code, err_msg

    targets = list(screen_names)
    if not targets and task_id:
        # --id A21로 화면을 찾거나 task_id 자체를 탐색
        if note_file and note_file.is_file():
            nt = note_file.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"\b([A-Z][a-z0-9]+_[A-Za-z0-9_]+)\b", nt):
                if m.group(1) in screens:
                    targets.append(m.group(1))
        if not targets:
            targets = [task_id]

    if not targets:
        return 2, "오류: baseline을 기록할 화면 이름(또는 --id)을 지정하세요."

    wd = (work_dir or Path.cwd()).resolve()
    baseline_path = resolve_baseline_path(wd)
    baseline_data: dict[str, Any] = {}
    if baseline_path.is_file():
        try:
            baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            baseline_data = {}

    now_iso = datetime.now(tz=KST).isoformat(timespec="seconds")
    user = getpass.getuser()
    commit = source_meta.get("commit") or "none"
    commit_short = source_meta.get("commit_short") or (commit[:7] if commit != "none" else "none")
    branch = source_meta.get("branch") or "-"
    commit_date = source_meta.get("commit_date") or now_iso[:10]
    repo_name = source_meta.get("repo_name") or (src_root.name if src_root else "AS-IS")

    try:
        rel_bl = baseline_path.resolve().relative_to(wd).as_posix()
    except ValueError:
        rel_bl = str(baseline_path)

    recorded_msgs: list[str] = []
    unchanged_msgs: list[str] = []
    total_files_last = 0

    for t_name in targets:
        # 대소문자 무관 매칭
        matched_key = t_name
        if matched_key not in screens:
            for k in screens:
                if k.lower() == t_name.lower():
                    matched_key = k
                    break
        if matched_key not in screens:
            return 2, f"오류: 색인에서 화면 '{t_name}'을(를) 찾을 수 없습니다."

        sc_info = screens[matched_key]
        if not sc_info.get("has_frontmatter") or sc_info.get("source_files") is None:
            return 2, f"오류: 화면 '{matched_key}' 색인에 기준 정보가 없습니다 — `index-src` 먼저 실행하세요."

        s_files = dict(sc_info["source_files"])
        total_files_last = len(s_files)
        prev_entry = baseline_data.get(matched_key)
        if isinstance(prev_entry, dict) and not force:
            if prev_entry.get("files") == s_files:
                unchanged_msgs.append(matched_key)
                continue
            return (
                2,
                f"오류: {matched_key} — 기준 변경: 원본이 바뀜 — drift로 먼저 확인 (덮어쓰려면 --force)",
            )

        history: list[dict[str, Any]] = []
        if isinstance(prev_entry, dict):
            history = list(prev_entry.get("history") or [])
            history.append({
                "commit": prev_entry.get("commit"),
                "commit_short": prev_entry.get("commit_short"),
                "recorded_at": prev_entry.get("recorded_at"),
                "recorded_by": prev_entry.get("recorded_by"),
                "files": prev_entry.get("files"),
                "note": prev_entry.get("note"),
            })

        new_entry: dict[str, Any] = {
            "commit": commit,
            "commit_short": commit_short,
            "branch": branch,
            "commit_date": commit_date,
            "repo_name": repo_name,
            "files": s_files,
            "shared_links": sc_info.get("shared_links") or [],
            "recorded_at": now_iso,
            "recorded_by": user,
            "note": str(note_file) if note_file else (prev_entry.get("note") if isinstance(prev_entry, dict) else None),
            "history": history,
        }
        if task_id:
            new_entry["id"] = task_id

        baseline_data[matched_key] = new_entry
        recorded_msgs.append(f"{matched_key} @ {commit_short} (의존 {len(s_files)}개)")

    if note_file:
        asis_line = (
            f"AS-IS 기준: {repo_name} {commit} ({branch}, {commit_date}) "
            f"· 의존 파일 {total_files_last}개 해시는 {rel_bl}"
        )
        _update_note_file_header(note_file, asis_line)

    if not recorded_msgs and unchanged_msgs:
        return 0, f"변경 없음 {len(unchanged_msgs)}개 ({', '.join(unchanged_msgs)})"

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline_data, ensure_ascii=False, indent=2), encoding="utf-8")

    note_suffix = " · 작업기록 머리에 'AS-IS 기준:' 줄 추가" if note_file else ""
    return 0, f"baseline 기록: {', '.join(recorded_msgs)}{note_suffix}"


def record_baseline_from_table(
    table_file: Path | None,
    src_root: Path,
    src_index: Path,
    statuses: list[str] | None = None,
    id_col: str = "ID",
    class_col: str = "클래스",
    status_col: str = "상태",
    note_dir: Path | str | None = None,
    note_suffix: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    work_dir: Path | None = None,
) -> tuple[int, str]:
    """마크다운 변환목록 표에서 대상 행을 읽어 색인을 한 번만 로드한 뒤 일괄로 baseline을 기록한다."""
    wd = (work_dir or Path.cwd()).resolve()
    d_cfg = resolve_drift_config(wd)

    eff_table = table_file if table_file is not None else Path(d_cfg["done_from"])
    if not eff_table.is_absolute() and not eff_table.is_file():
        cand_wd = wd / eff_table
        cand_root = d_cfg["base_root"] / eff_table
        eff_table = cand_wd if cand_wd.is_file() else cand_root

    if not eff_table.is_file():
        return 2, f"오류: 변환목록 표 파일을 찾을 수 없습니다: {table_file or d_cfg['done_from']}"

    code, err_msg, screens, source_meta = _check_index_freshness(src_root, src_index)
    if code != 0:
        return code, err_msg

    rows = parse_conversion_table(
        eff_table.read_text(encoding="utf-8", errors="replace"),
        id_col=id_col,
        class_col=class_col,
        status_col=status_col,
    )
    if not rows:
        return 2, f"오류: '{eff_table}'에서 ({id_col}, {class_col}, {status_col}) 열을 가진 표를 찾을 수 없습니다."

    eff_statuses = statuses if statuses is not None else d_cfg["record_status"]
    status_set = {s.strip() for s in eff_statuses if s.strip()}

    raw_nd = note_dir if note_dir is not None else d_cfg["note_dir"]
    nd_path = Path(raw_nd) if raw_nd else None
    if nd_path and not nd_path.is_absolute():
        nd_path = wd / nd_path
    eff_suffix = note_suffix if note_suffix is not None else d_cfg["note_suffix"]

    baseline_path = resolve_baseline_path(wd)
    baseline_data: dict[str, Any] = {}
    if baseline_path.is_file():
        try:
            baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            baseline_data = {}

    now_iso = datetime.now(tz=KST).isoformat(timespec="seconds")
    user = getpass.getuser()
    commit = source_meta.get("commit") or "none"
    commit_short = source_meta.get("commit_short") or (commit[:7] if commit != "none" else "none")
    branch = source_meta.get("branch") or "-"
    commit_date = source_meta.get("commit_date") or now_iso[:10]
    repo_name = source_meta.get("repo_name") or (src_root.name if src_root else "AS-IS")

    try:
        rel_bl = baseline_path.resolve().relative_to(wd).as_posix()
    except ValueError:
        rel_bl = str(baseline_path)

    target_rows = [r for r in rows if r["status"] in status_set]
    status_filtered = [r for r in rows if r["status"] not in status_set]

    valid_targets: list[tuple[str, str]] = []
    other_skips: list[str] = []
    warnings_out: list[str] = []
    recorded_count = 0
    note_updated_count = 0
    unchanged_count = 0
    has_hash_conflict = False

    for r in target_rows:
        t_id = r["id"]
        t_cls = r["class"]
        matched_key = t_cls
        if matched_key not in screens:
            for k in screens:
                if k.lower() == t_cls.lower():
                    matched_key = k
                    break
        if not matched_key or matched_key not in screens:
            other_skips.append(f"{t_id}({t_cls or '-'}): 색인에 없음")
            continue

        sc_info = screens[matched_key]
        if not sc_info.get("has_frontmatter") or sc_info.get("source_files") is None:
            other_skips.append(f"{t_id}({matched_key}): 기준 정보 없음")
            continue

        s_files = dict(sc_info["source_files"])
        prev_entry = baseline_data.get(matched_key)

        if dry_run:
            if isinstance(prev_entry, dict) and not force and prev_entry.get("files") != s_files:
                other_skips.append(f"{t_id}({matched_key}): 기준 변경: 원본이 바뀜 — drift로 먼저 확인")
            else:
                valid_targets.append((t_id, matched_key))
            continue

        asis_line = (
            f"AS-IS 기준: {repo_name} {commit} ({branch}, {commit_date}) "
            f"· 의존 파일 {len(s_files)}개 해시는 {rel_bl}"
        )

        if isinstance(prev_entry, dict) and not force:
            if prev_entry.get("files") == s_files:
                unchanged_count += 1
                if nd_path and t_id:
                    nf = nd_path / f"{t_id}{eff_suffix}"
                    if nf.is_file():
                        _update_note_file_header(nf, asis_line)
                continue
            warn_item = f"{t_id}({matched_key}): 기준 변경: 원본이 바뀜 — drift로 먼저 확인"
            other_skips.append(warn_item)
            warnings_out.append(f"⚠ {warn_item}")
            has_hash_conflict = True
            continue

        history: list[dict[str, Any]] = []
        if isinstance(prev_entry, dict):
            history = list(prev_entry.get("history") or [])
            history.append({
                "commit": prev_entry.get("commit"),
                "commit_short": prev_entry.get("commit_short"),
                "recorded_at": prev_entry.get("recorded_at"),
                "recorded_by": prev_entry.get("recorded_by"),
                "files": prev_entry.get("files"),
                "note": prev_entry.get("note"),
            })

        nf_path: Path | None = (nd_path / f"{t_id}{eff_suffix}") if (nd_path and t_id) else None
        new_entry: dict[str, Any] = {
            "commit": commit,
            "commit_short": commit_short,
            "branch": branch,
            "commit_date": commit_date,
            "repo_name": repo_name,
            "files": s_files,
            "shared_links": sc_info.get("shared_links") or [],
            "recorded_at": now_iso,
            "recorded_by": user,
            "note": str(nf_path) if nf_path else (prev_entry.get("note") if isinstance(prev_entry, dict) else None),
            "history": history,
        }
        if t_id:
            new_entry["id"] = t_id

        baseline_data[matched_key] = new_entry
        recorded_count += 1
        if nf_path:
            _update_note_file_header(nf_path, asis_line)
            note_updated_count += 1

    if dry_run:
        skip_items = list(other_skips)
        if status_filtered:
            st_part = ", ".join(f"{r['id']}: 상태 {r['status']}" for r in status_filtered) + " — 상태 필터"
            skip_items.append(st_part)
        total_skips = len(other_skips) + len(status_filtered)
        skip_detail = f" ({', '.join(skip_items)})" if skip_items else ""
        head = f"대상 {len(valid_targets)}개 · 건너뜀 {total_skips}개{skip_detail}"
        if valid_targets:
            t_preview = ", ".join(f"{tid}({cls})" for tid, cls in valid_targets[:20])
            more = f" 외 {len(valid_targets) - 20}개" if len(valid_targets) > 20 else ""
            return 0, f"{head}\n대상 목록: {t_preview}{more}"
        return 0, head

    if recorded_count > 0:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if recorded_count == 0 and unchanged_count > 0 and not other_skips:
        return 0, f"변경 없음 {unchanged_count}개"

    parts = [f"기록 {recorded_count}개"]
    if note_updated_count > 0:
        parts.append(f"작업기록 {note_updated_count}개 갱신")
    if unchanged_count > 0:
        parts.append(f"변경 없음 {unchanged_count}개")
    skip_str = f"건너뜀 {len(other_skips)}개"
    if other_skips:
        skip_str += f" ({', '.join(other_skips)})"
    parts.append(skip_str)

    out_lines = [*warnings_out, " · ".join(parts)]
    exit_code = 2 if has_hash_conflict else 0
    return exit_code, "\n".join(out_lines)



def _update_note_file_header(note_file: Path, asis_line: str) -> None:
    """note_file 머리의 'AS-IS 기준:' 줄을 중복 없이 만들거나 갱신한다."""
    if not note_file.is_file():
        note_file.parent.mkdir(parents=True, exist_ok=True)
        note_file.write_text(asis_line + "\n", encoding="utf-8")
        return

    text = note_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if re.match(r"^(?:-\s*)?AS-IS\s*기준\s*:", line.strip()):
            if not replaced:
                new_lines.append(asis_line)
                replaced = True
            # 이미 교체했으면 중복된 이전 'AS-IS 기준:' 줄은 건너뛴다
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and new_lines[0].startswith("# "):
            new_lines.insert(1, asis_line)
        else:
            new_lines.insert(0, asis_line)

    note_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def show_baseline_info(screen_names: list[str], work_dir: Path | None = None) -> tuple[int, str]:
    """저장된 baseline 정보를 조회한다."""
    baseline_path = resolve_baseline_path(work_dir)
    if not baseline_path.is_file():
        return 1, f"baseline 파일이 없습니다: {baseline_path}"
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return 1, f"baseline 파일 읽기 실패: {exc}"

    targets = screen_names or sorted(data.keys())
    if not targets:
        return 0, "기록된 baseline이 없습니다."

    lines: list[str] = []
    for name in targets:
        entry = data.get(name)
        if not entry:
            lines.append(f"{name}: 기준 없음")
            continue
        c_short = entry.get("commit_short") or (entry.get("commit") or "")[:7]
        files = entry.get("files") or {}
        rec_at = entry.get("recorded_at") or "-"
        rec_by = entry.get("recorded_by") or "-"
        lines.append(f"### {name} @ {c_short} ({entry.get('branch') or '-'}, {rec_at}, by {rec_by}) — 의존 파일 {len(files)}개")
        for f_p, f_h in sorted(files.items()):
            lines.append(f"  - {f_p}: {f_h[:14] if f_h.startswith('sha256:') else f_h[:7]}")
        hist = entry.get("history") or []
        if hist:
            lines.append(f"  - history ({len(hist)}건):")
            for h_it in hist:
                hc = h_it.get("commit_short") or (h_it.get("commit") or "")[:7]
                lines.append(f"    - {hc} ({h_it.get('recorded_at') or '-'}, by {h_it.get('recorded_by') or '-'})")
    return 0, "\n".join(lines)


def _is_common_named_file(rel_path: str, total_screens: int) -> bool:
    """여러 화면이 있는 저장소에서 이름 자체가 공통 매퍼·서비스(00_, Common, shared)인 경우 공유 파일로 판정."""
    if total_screens <= 1:
        return False
    p = Path(rel_path)
    parts_lower = [pt.lower() for pt in p.parts]
    if "_common" in parts_lower:
        return True
    stem = p.stem
    if re.match(r"^[A-Za-z]+00_", stem):
        return True
    return "common" in stem.lower() or "shared" in stem.lower()


def _is_commit_in_head_history(src_root: Path, commit: str) -> bool:
    """commit이 현재 소스 저장소 HEAD의 조상(이력)에 존재하는지 확인한다."""
    if not commit or commit == "none":
        return False
    rc, _, _ = _run_git(src_root, ["merge-base", "--is-ancestor", commit, "HEAD"])
    return rc == 0


def _commit_object_exists(src_root: Path, commit: str) -> bool:
    """commit 객체가 git 저장소에 존재하는지 확인한다."""
    if not commit or commit == "none":
        return False
    rc, _, _ = _run_git(src_root, ["cat-file", "-e", f"{commit}^{{commit}}"])
    return rc == 0


def _build_current_blob_index(src_root: Path, git_mode: bool) -> dict[str, list[str]]:
    """이동(rename) 감지를 위해 현재 소스의 blob_hash -> [rel_path] 맵을 만든다."""
    blob_to_paths: dict[str, list[str]] = defaultdict(list)
    if git_mode:
        rc, out, _ = _run_git(src_root, ["ls-tree", "-r", "HEAD"])
        if rc == 0:
            for line in out.splitlines():
                if "\t" not in line:
                    continue
                meta, rel_p = line.split("\t", 1)
                parts = meta.split()
                if len(parts) >= 3:
                    rp = rel_p.strip('"')
                    if (src_root / rp).is_file():
                        blob_to_paths[parts[2]].append(rp)
    for ext in ("*.java", "*.xml"):
        for f in src_root.rglob(ext):
            if ".git" in f.parts or "target" in f.parts:
                continue
            rel_p = f.resolve().relative_to(src_root.resolve()).as_posix()
            try:
                b_hash = compute_git_blob_file(f)
                if rel_p not in blob_to_paths[b_hash]:
                    blob_to_paths[b_hash].append(rel_p)
                s_hash = compute_sha256_file(f)
                if rel_p not in blob_to_paths[s_hash]:
                    blob_to_paths[s_hash].append(rel_p)
            except OSError:
                pass
    return blob_to_paths


def _file_numstat(
    src_root: Path,
    rel_path: str,
    base_commit: str | None,
    base_hash: str,
    ignore_space: bool,
    commit_exists: bool,
) -> tuple[int, int]:
    """git diff --numstat으로 단일 파일의 (+added, -removed) 줄 수를 구한다."""
    w_args = ["-w"] if ignore_space else []
    if base_commit and commit_exists:
        rc, out, _ = _run_git(src_root, ["diff", "--numstat", *w_args, base_commit, "--", rel_path])
        if rc == 0 and out.strip():
            parts = out.strip().splitlines()[0].split("\t")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
    # base_hash가 git blob인 경우 blob 대 현재 파일 비교 시도
    if not base_hash.startswith("sha256:") and len(base_hash) >= 7:
        abs_p = src_root / rel_path
        if abs_p.is_file():
            curr_blob = compute_git_blob_file(abs_p)
            rc, out, _ = _run_git(src_root, ["diff", "--numstat", *w_args, base_hash, curr_blob])
            if rc == 0 and out.strip():
                parts = out.strip().splitlines()[0].split("\t")
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    return int(parts[0]), int(parts[1])
    return 0, 0


def _last_commit_for_files(src_root: Path, rel_paths: list[str], deleted: bool = False) -> dict[str, str] | None:
    """파일 목록에 대한 가장 최근 git 커밋 정보를 반환한다."""
    if not rel_paths:
        return None
    extra = ["--diff-filter=D"] if deleted else []
    rc, out, _ = _run_git(
        src_root,
        ["log", "-1", *extra, "--format=%H\t%h\t%ad\t%an\t%s", "--date=format:%m-%d", "--", *rel_paths],
    )
    if rc != 0 or not out.strip():
        return None
    parts = out.strip().splitlines()[0].split("\t", 4)
    if len(parts) < 5:
        return None
    return {
        "full_hash": parts[0],
        "hash": parts[1],
        "date": parts[2],
        "author": parts[3],
        "subject": parts[4],
    }


def _find_new_screens(src_root: Path, src_index: Path, indexed_screens: dict[str, dict[str, Any]], files_map: dict[str, list[str]]) -> list[dict[str, str]]:
    """--new 옵션용: 메뉴 TSV 또는 소스에 새로 생긴 화면 클래스를 찾는다."""
    from yunhee.tools.as_is.src_indexer import find_app, load_menus, parse_menu_opener

    new_items: list[dict[str, str]] = []
    seen_names: set[str] = set()

    app = find_app(src_root)
    menus_tsv = src_index.parent / "menus.tsv"
    if app:
        opener = parse_menu_opener(app)
        menus = load_menus(menus_tsv if menus_tsv.is_file() else None)
        for m in menus:
            cls_name = opener.get(m["key"], m["key"])
            if cls_name and cls_name not in indexed_screens and cls_name not in seen_names:
                seen_names.add(cls_name)
                new_items.append({"screen": cls_name, "source": "menus.tsv", "path": m["path"]})
        for _k, cls_name in sorted(opener.items()):
            if cls_name not in indexed_screens and cls_name not in seen_names:
                seen_names.add(cls_name)
                new_items.append({"screen": cls_name, "source": "MenuOpener", "path": cls_name})

    # 소스의 client/vi 아래 화면 패턴(*.java) 중 색인(_files.json 및 screens)에 없는 파일
    search_dir = (app / "client") if app and (app / "client").is_dir() else src_root
    for jf in sorted(search_dir.rglob("*.java")):
        if ".git" in jf.parts or "target" in jf.parts or "model" in jf.parts:
            continue
        rel_p = jf.resolve().relative_to(src_root.resolve()).as_posix()
        stem = jf.stem
        if stem in indexed_screens or stem in seen_names or rel_p in files_map:
            continue
        if re.search(r"_(Tab|Page|Lookup|Edit|Popup|Tree)_|^Main", stem):
            seen_names.add(stem)
            new_items.append({"screen": stem, "source": "source", "path": rel_p})

    return new_items


def run_drift(
    screen_args: list[str] | None = None,
    all_screens: bool = False,
    src_root: Path | None = None,
    src_index: Path | None = None,
    base: str = "index",
    done_only: bool = False,
    min_lines: int = 0,
    output_fmt: str = "table",
    max_lines: int = 200,
    show_new: bool = False,
    fail_on_drift: bool = False,
    ignore_space: bool = False,
    work_dir: Path | None = None,
) -> tuple[int, str, list[str]]:
    """yunhee drift 실행 본체.

    반환: (exit_code, stdout_text, warnings_list)
    """
    warnings: list[str] = []
    if output_fmt not in ("table", "diff", "full", "json"):
        return 2, f"오류: 지원하지 않는 출력 형식입니다: {output_fmt} (table|diff|full|json)", warnings

    if not src_index or not src_index.is_dir():
        return 2, f"오류: 색인 폴더를 찾을 수 없습니다: {src_index}", warnings

    indexed_screens, files_map, source_meta = load_index_screens(src_index)
    eff_src = src_root
    if (not eff_src or not eff_src.is_dir()) and source_meta.get("src_root"):
        cand = Path(source_meta["src_root"])
        if cand.is_dir():
            eff_src = cand
    if not eff_src or not eff_src.is_dir():
        return 2, f"오류: AS-IS 소스 디렉터리를 찾을 수 없습니다: {eff_src}", warnings

    if not screen_args and not all_screens and not show_new:
        return 2, "오류: 비교할 화면 이름을 지정하거나 --all 옵션을 사용하세요.", warnings

    git_mode = is_git_repo(eff_src, source_meta.get("vcs_root"))
    head_commit = None
    head_short = "-"
    if git_mode:
        _, h_out, _ = _run_git(eff_src, ["rev-parse", "HEAD"])
        head_commit = h_out.strip()
        head_short = head_commit[:7] if head_commit else "-"

    # 5-1: 소스 HEAD와 색인 기준 커밋 불일치 경고
    mismatch_warn = check_commit_mismatch_warning(eff_src, src_index)
    if mismatch_warn:
        warnings.append(mismatch_warn)

    wd = (work_dir or Path.cwd()).resolve()
    baseline_path = resolve_baseline_path(wd)
    baseline_data: dict[str, Any] = {}
    if baseline_path.is_file():
        try:
            baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            baseline_data = {}

    prev_screens_data: dict[str, Any] = {}
    if base == "prev-index":
        prev_file = src_index / "_prev" / "_screens.json"
        if prev_file.is_file():
            try:
                prev_screens_data = json.loads(prev_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                prev_screens_data = {}

    commit_base_blobs: dict[str, str] = {}
    resolved_commit_base: str | None = None
    if base not in ("index", "baseline", "prev-index"):
        if not git_mode:
            return 2, f"오류: git 저장소가 아니므로 커밋 기준(--base {base})을 사용할 수 없습니다.", warnings
        rc_v, rev_out, _ = _run_git(eff_src, ["rev-parse", "--verify", f"{base}^{{commit}}"])
        if rc_v != 0 or not rev_out.strip():
            return 2, f"오류: 소스 저장소에서 기준 커밋을 찾을 수 없습니다: {base}", warnings
        resolved_commit_base = rev_out.strip()
        rc_t, t_out, _ = _run_git(eff_src, ["ls-tree", "-r", resolved_commit_base])
        if rc_t == 0:
            for line in t_out.splitlines():
                if "\t" in line:
                    meta, rp = line.split("\t", 1)
                    pts = meta.split()
                    if len(pts) >= 3:
                        commit_base_blobs[rp.strip('"')] = pts[2]

    # 대상 화면 결정
    only_screen_units = {k: v for k, v in indexed_screens.items() if v["kind"] == "screen"}
    if screen_args:
        target_names: list[str] = []
        for arg in screen_args:
            matched = arg
            if matched not in indexed_screens:
                for k in indexed_screens:
                    if k.lower() == arg.lower():
                        matched = k
                        break
            if matched not in indexed_screens and matched not in baseline_data:
                return 2, f"오류: 화면 '{arg}'을(를) 색인에서 찾을 수 없습니다.", warnings
            target_names.append(matched)
    elif all_screens:
        target_names = sorted(only_screen_units.keys())
    else:
        target_names = []

    if done_only:
        done_set = resolve_done_screens(wd, baseline_data)
        target_names = [n for n in target_names if n in done_set]

    total_screens_count = len(only_screen_units)
    blob_index = _build_current_blob_index(eff_src, git_mode)

    # 5-3: baseline 커밋이 현재 소스 이력에 없는 경우 감지
    missing_history_commits: set[str] = set()

    screen_results: list[dict[str, Any]] = []
    shared_changes_global: dict[str, dict[str, Any]] = {}
    base_commits_seen: set[str] = set()

    for s_name in target_names:
        idx_info = indexed_screens.get(s_name, {})
        base_commit: str | None = None
        base_files: dict[str, str] | None = None
        shared_links: list[str] = list(idx_info.get("shared_links") or [])

        if base == "index":
            if not idx_info.get("has_frontmatter"):
                screen_results.append({
                    "screen": s_name,
                    "status": "기준 없음",
                    "files": [],
                    "added": 0,
                    "removed": 0,
                    "last_commit": None,
                    "dedicated_count": 0,
                    "shared_count": 0,
                })
                continue
            base_commit = idx_info.get("source_commit")
            base_files = idx_info.get("source_files")
        elif base == "baseline":
            bl_entry = baseline_data.get(s_name)
            if not bl_entry:
                screen_results.append({
                    "screen": s_name,
                    "status": "기준 없음",
                    "files": [],
                    "added": 0,
                    "removed": 0,
                    "last_commit": None,
                    "dedicated_count": 0,
                    "shared_count": 0,
                })
                continue
            base_commit = bl_entry.get("commit")
            base_files = bl_entry.get("files")
            shared_links = list(bl_entry.get("shared_links") or shared_links)
            if git_mode and base_commit and base_commit != "none" and not _is_commit_in_head_history(eff_src, base_commit):
                missing_history_commits.add(base_commit)
        elif base == "prev-index":
            pv_entry = prev_screens_data.get(s_name)
            if not pv_entry or pv_entry.get("source_files") is None:
                screen_results.append({
                    "screen": s_name,
                    "status": "기준 없음",
                    "files": [],
                    "added": 0,
                    "removed": 0,
                    "last_commit": None,
                    "dedicated_count": 0,
                    "shared_count": 0,
                })
                continue
            base_commit = pv_entry.get("source_commit")
            base_files = pv_entry.get("source_files")
            shared_links = list(pv_entry.get("shared_links") or shared_links)
        else:
            # 임의 커밋 기준
            base_commit = resolved_commit_base
            idx_sfiles = idx_info.get("source_files") or {}
            base_files = {rp: commit_base_blobs.get(rp, "") for rp in idx_sfiles}

        if base_files is not None and len(base_files) == 0:
            screen_results.append({
                "screen": s_name,
                "status": "기준 불완전",
                "files": [],
                "added": 0,
                "removed": 0,
                "last_commit": None,
                "dedicated_count": 0,
                "shared_count": 0,
            })
            continue

        if base_commit and base_commit != "none":
            base_commits_seen.add(base_commit)

        commit_reachable = bool(git_mode and base_commit and _commit_object_exists(eff_src, base_commit))

        # 이 화면의 검사 대상 파일들: (rel_path, base_hash, is_from_linked_component)
        check_entries: list[tuple[str, str, bool]] = [
            (rp, bh, False) for rp, bh in sorted((base_files or {}).items())
        ]
        seen_paths = {rp for rp, _, _ in check_entries}
        for lk in shared_links:
            comp_info = indexed_screens.get(lk)
            if comp_info and comp_info.get("source_files"):
                for rp, bh in sorted(comp_info["source_files"].items()):
                    if rp not in seen_paths:
                        seen_paths.add(rp)
                        check_entries.append((rp, bh, True))

        file_records: list[dict[str, Any]] = []
        ded_added = 0
        ded_removed = 0
        ded_changed_paths: list[str] = []
        ded_deleted_paths: list[str] = []
        shared_changed_paths: list[str] = []
        moved_items: list[tuple[str, str]] = []

        for rel_p, b_hash, from_comp in check_entries:
            affected = files_map.get(rel_p, [s_name])
            is_shared = (
                from_comp
                or len(affected) > 1
                or _is_common_named_file(rel_p, total_screens_count)
            )
            abs_p = eff_src / rel_p

            if not abs_p.is_file():
                # 이동(rename)인지 삭제인지 판정
                moved_candidates = [p for p in blob_index.get(b_hash, []) if p != rel_p] if b_hash else []
                if moved_candidates:
                    new_rel = moved_candidates[0]
                    moved_items.append((rel_p, new_rel))
                    file_records.append({
                        "path": rel_p,
                        "moved_to": new_rel,
                        "status": "이동",
                        "added": 0,
                        "removed": 0,
                        "shared": is_shared,
                    })
                else:
                    del_commit = _last_commit_for_files(eff_src, [rel_p], deleted=True) if git_mode else None
                    file_records.append({
                        "path": rel_p,
                        "status": "삭제",
                        "added": 0,
                        "removed": 0,
                        "shared": is_shared,
                        "deleted_commit": del_commit,
                    })
                    if is_shared:
                        shared_changed_paths.append(rel_p)
                        shared_changes_global.setdefault(
                            rel_p,
                            {"affected": max(len(affected), 1), "added": 0, "removed": 0, "status": "삭제"},
                        )
                    else:
                        ded_deleted_paths.append(rel_p)
                continue

            # 파일이 존재하는 경우 해시 비교
            if not git_mode or b_hash.startswith("sha256:"):
                curr_hash = compute_sha256_file(abs_p)
                expected_hash = b_hash if b_hash.startswith("sha256:") else compute_sha256_file(abs_p)
                # git 색인을 비-git으로 비교하는 예외 상황 대비
                if not b_hash.startswith("sha256:"):
                    curr_blob = compute_git_blob_file(abs_p)
                    is_same = curr_blob == b_hash
                else:
                    is_same = curr_hash == expected_hash
            else:
                curr_blob = compute_git_blob_file(abs_p)
                is_same = curr_blob == b_hash

            if is_same:
                continue

            f_add, f_rem = (
                _file_numstat(eff_src, rel_p, base_commit, b_hash, ignore_space, commit_reachable)
                if git_mode
                else (0, 0)
            )
            # --ignore-space 일 때 공백 외에 변경이 전혀 없으면 동일로 취급
            if ignore_space and git_mode and f_add == 0 and f_rem == 0 and commit_reachable:
                rc_w, diff_w, _ = _run_git(eff_src, ["diff", "-w", base_commit, "--", rel_p])
                if rc_w == 0 and not diff_w.strip():
                    continue

            file_records.append({
                "path": rel_p,
                "status": "변경",
                "added": f_add,
                "removed": f_rem,
                "shared": is_shared,
                "base_commit": base_commit,
                "base_hash": b_hash,
            })
            if is_shared:
                shared_changed_paths.append(rel_p)
                shared_changes_global.setdefault(
                    rel_p,
                    {"affected": max(len(affected), 1), "added": f_add, "removed": f_rem, "status": "변경"},
                )
            else:
                ded_changed_paths.append(rel_p)
                ded_added += f_add
                ded_removed += f_rem

        # 화면 상태 결정 (이동만 있으면 이동으로 표시하고 변경으로 세지 않는다)
        if ded_deleted_paths:
            sc_status = "삭제" if not ded_changed_paths else "변경"
        elif ded_changed_paths or shared_changed_paths:
            sc_status = "변경"
        elif moved_items:
            sc_status = "이동"
        else:
            sc_status = "동일"

        last_c = None
        if git_mode and (ded_changed_paths or ded_deleted_paths or shared_changed_paths):
            query_paths = ded_changed_paths + ded_deleted_paths
            is_del_only = bool(ded_deleted_paths and not ded_changed_paths)
            if not query_paths:
                query_paths = shared_changed_paths
            last_c = _last_commit_for_files(eff_src, query_paths, deleted=is_del_only)

        screen_results.append({
            "screen": s_name,
            "status": sc_status,
            "files": file_records,
            "added": ded_added,
            "removed": ded_removed,
            "last_commit": (
                {
                    "hash": last_c["hash"],
                    "date": last_c["date"],
                    "subject": last_c["subject"],
                    "author": last_c["author"],
                }
                if last_c
                else None
            ),
            "dedicated_count": len(ded_changed_paths) + len(ded_deleted_paths),
            "shared_count": len(shared_changed_paths),
            "moved_items": moved_items,
            "base_commit": base_commit,
        })

    if missing_history_commits:
        c_list = ", ".join(sorted(c[:7] for c in missing_history_commits))
        warnings.append(f"⚠ 기준 커밋을 소스에서 찾을 수 없음 ({c_list}) — git fetch 필요 (해시 비교로 대체)")

    new_items = _find_new_screens(eff_src, src_index, indexed_screens, files_map) if show_new else []
    if show_new:
        for ni in new_items:
            screen_results.append({
                "screen": ni["screen"],
                "status": "신규",
                "files": [{"path": ni["path"], "status": "신규", "added": 0, "removed": 0, "shared": False}],
                "added": 0,
                "removed": 0,
                "last_commit": None,
                "dedicated_count": 1,
                "shared_count": 0,
                "moved_items": [],
                "base_commit": None,
            })

    # --min-lines 필터링
    if min_lines > 0 and git_mode:
        filtered_results = []
        for sr in screen_results:
            if sr["status"] == "변경":
                total_changed_lines = sr["added"] + sr["removed"]
                if total_changed_lines == 0:
                    total_changed_lines = sum(
                        f.get("added", 0) + f.get("removed", 0) for f in sr.get("files", [])
                    )
                if total_changed_lines >= min_lines or (min_lines == 1 and total_changed_lines == 0 and sr["files"]):
                    filtered_results.append(sr)
            else:
                filtered_results.append(sr)
        screen_results = filtered_results

    has_drift = any(sr["status"] in ("변경", "삭제", "신규") for sr in screen_results)
    exit_code = 1 if (fail_on_drift and has_drift) else 0

    if output_fmt == "json":
        json_payload = [
            {
                "screen": sr["screen"],
                "status": sr["status"],
                "files": sr["files"],
                "added": sr["added"],
                "removed": sr["removed"],
                "last_commit": sr["last_commit"],
            }
            for sr in screen_results
        ]
        return exit_code, json.dumps(json_payload, ensure_ascii=False, indent=2), warnings

    if output_fmt in ("diff", "full"):
        diff_text = _render_diff_output(
            eff_src,
            screen_results,
            git_mode=git_mode,
            ignore_space=ignore_space,
            max_lines=max_lines if output_fmt == "diff" else None,
        )
        return exit_code, diff_text, warnings

    # 기본 table 출력
    s_menu = source_meta.get("screens_menu")
    s_frame = source_meta.get("screens_frame")
    if s_menu is None or s_frame is None:
        s_frame = sum(1 for v in only_screen_units.values() if "_frame" in v["md_file"].parts)
        s_menu = len(only_screen_units) - s_frame

    table_text = _render_table_output(
        screen_results=screen_results,
        shared_changes_global=shared_changes_global,
        git_mode=git_mode,
        head_short=head_short,
        base=base,
        done_only=done_only,
        base_commits_seen=base_commits_seen,
        single_query=len(target_names) == 1 and not all_screens,
        screens_menu=s_menu if all_screens and not done_only else None,
        screens_frame=s_frame if all_screens and not done_only else None,
    )
    return exit_code, table_text, warnings


def _render_table_output(
    screen_results: list[dict[str, Any]],
    shared_changes_global: dict[str, dict[str, Any]],
    git_mode: bool,
    head_short: str,
    base: str,
    done_only: bool,
    base_commits_seen: set[str],
    single_query: bool = False,
    screens_menu: int | None = None,
    screens_frame: int | None = None,
) -> str:
    """기본 1화면 1줄 요약 테이블 출력을 렌더링한다."""
    changed_list = [s for s in screen_results if s["status"] in ("변경", "삭제")]
    same_list = [s for s in screen_results if s["status"] == "동일"]
    no_base_list = [s for s in screen_results if s["status"] == "기준 없음"]
    incomplete_list = [s for s in screen_results if s["status"] == "기준 불완전"]
    moved_list = [s for s in screen_results if s["status"] == "이동"]
    new_list = [s for s in screen_results if s["status"] == "신규"]

    # 변경 큰 순 정렬 (전용 파일 변경 줄 수 내림차순 -> 전용 파일 수 내림차순 -> 화면명)
    changed_list.sort(
        key=lambda s: (s["added"] + s["removed"], s["dedicated_count"], s["shared_count"], s["screen"]),
        reverse=True,
    )

    scope_label = "완료 화면" if done_only else "화면"
    total_cnt = len([s for s in screen_results if s["status"] != "신규"])

    extra_counts = [f"동일 {len(same_list)}", f"기준 없음 {len(no_base_list)}"]
    if moved_list:
        extra_counts.append(f"이동 {len(moved_list)}")
    if incomplete_list:
        extra_counts.append(f"기준 불완전 {len(incomplete_list)}")
    if new_list:
        extra_counts.append(f"신규 {len(new_list)}")

    if git_mode:
        short_bases = sorted({c[:7] for c in base_commits_seen if c})
        range_str = f"{short_bases[0]}..{head_short}" if short_bases else f"..{head_short}"
        head_info = f"소스 HEAD {head_short}, 기준 커밋 범위 {range_str}"
    else:
        head_info = "소스 (git 정보 없음 — sha256 비교)"

    lines: list[str] = []

    if single_query and len(changed_list) == 1:
        s0 = changed_list[0]
        b_short = (s0.get("base_commit") or "")[:7] or base
        lines.append(
            f"변경 {s0['dedicated_count']}파일 +{s0['added']}/-{s0['removed']} "
            f"({base} {b_short} → HEAD {head_short})"
        )

    if screens_menu is not None and screens_frame is not None and total_cnt == (screens_menu + screens_frame):
        count_label = f"{scope_label} {total_cnt}개(메뉴 {screens_menu} · 프레임 {screens_frame})"
    else:
        count_label = f"{scope_label} {total_cnt}개"

    lines.append(
        f"기준 대비 변경 {len(changed_list)}개 / {count_label} "
        f"({' · '.join(extra_counts)}) — {head_info}"
    )

    if changed_list:
        lines.append("")
        lines.append(f"{'화면':<28} {'파일':<8} {'+/-줄':<12} 마지막 커밋")
        for s in changed_list:
            ded_n = s["dedicated_count"]
            sh_n = s["shared_count"]
            if ded_n > 0 and sh_n > 0:
                file_col = f"{ded_n}(공유 {sh_n})"
            elif ded_n > 0:
                file_col = f"{ded_n}"
            else:
                file_col = f"(공유 {sh_n})"

            if not git_mode or (ded_n == 0 and sh_n > 0):
                lines_col = "-"
            else:
                lines_col = f"+{s['added']}/-{s['removed']}"

            lc = s.get("last_commit")
            if git_mode and lc:
                commit_col = f"{lc['date']} {lc['author']} {lc['subject']}"
            else:
                commit_col = "-"

            status_tag = " [삭제]" if s["status"] == "삭제" else ""
            lines.append(f"{s['screen'] + status_tag:<28} {file_col:<8} {lines_col:<12} {commit_col}")

    if moved_list:
        lines.append("")
        for s in moved_list:
            moves_str = ", ".join(f"{old_p} → {new_p}" for old_p, new_p in s.get("moved_items", []))
            lines.append(f"이동: {s['screen']} ({moves_str})")

    if new_list:
        lines.append("")
        for s in new_list:
            f_path = s["files"][0]["path"] if s.get("files") else ""
            lines.append(f"신규: {s['screen']} ({f_path})")

    if no_base_list:
        names_preview = ", ".join(s["screen"] for s in no_base_list[:5])
        more = f" 외 {len(no_base_list) - 5}개" if len(no_base_list) > 5 else ""
        lines.append(f"기준 없음 ({len(no_base_list)}개): {names_preview}{more}")

    if incomplete_list:
        names_preview = ", ".join(s["screen"] for s in incomplete_list[:5])
        lines.append(f"기준 불완전 ({len(incomplete_list)}개): {names_preview}")

    if shared_changes_global:
        parts = []
        for rp, info in sorted(shared_changes_global.items(), key=lambda x: (-x[1]["affected"], x[0])):
            parts.append(f"{Path(rp).name} ({info['affected']})")
        lines.append(f"공유 변경(영향 화면 수): {' · '.join(parts)}")

    if changed_list:
        top_screen = changed_list[0]["screen"]
        lines.append(f"→ yunhee drift {top_screen} -o diff   # 파일별 diff")

    return "\n".join(lines)


def _render_diff_output(
    src_root: Path,
    screen_results: list[dict[str, Any]],
    git_mode: bool,
    ignore_space: bool,
    max_lines: int | None,
) -> str:
    """-o diff 및 -o full 출력을 생성한다."""
    out_blocks: list[str] = []
    w_args = ["-w"] if ignore_space else []

    for sr in screen_results:
        if sr["status"] not in ("변경", "삭제"):
            continue
        out_blocks.append(f"=== {sr['screen']} ({sr['status']}, +{sr['added']}/-{sr['removed']}) ===")
        for f_rec in sr["files"]:
            rel_p = f_rec["path"]
            b_commit = f_rec.get("base_commit")
            if not git_mode:
                out_blocks.append(f"--- {rel_p} ({f_rec['status']}, git 아님) ---")
                continue

            ref = b_commit if (b_commit and _commit_object_exists(src_root, b_commit)) else f_rec.get("base_hash")
            if not ref or ref.startswith("sha256:"):
                out_blocks.append(f"--- {rel_p} ({f_rec['status']}) ---")
                continue

            _, stat_out, _ = _run_git(src_root, ["diff", "--stat", *w_args, ref, "--", rel_p])
            stat_first = stat_out.strip().splitlines()[0] if stat_out.strip() else f"{rel_p} ({f_rec['status']})"
            out_blocks.append(stat_first)

            _, diff_out, _ = _run_git(src_root, ["diff", "-U3", *w_args, ref, "--", rel_p])
            d_lines = diff_out.splitlines()
            if max_lines is not None and len(d_lines) > max_lines:
                omitted = len(d_lines) - max_lines
                out_blocks.extend(d_lines[:max_lines])
                out_blocks.append(f"…({omitted}줄 생략, 원문 -o full)")
            else:
                out_blocks.extend(d_lines)
        out_blocks.append("")

    if not out_blocks:
        return "변경된 파일이 없습니다."
    return "\n".join(out_blocks).rstrip()
