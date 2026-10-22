"""
yunhee-cli Agent Core File System Tools
작업 디렉터리(WORK_DIR) 기준 안전한 파일 탐색, 읽기, 쓰기 및 부분 치환 도구.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from yunhee import config

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "target",
    "build",
    ".idea",
    ".vscode",
    ".ruff_cache",
}


def _safe_resolve(filename: str) -> Path:
    """WORK_DIR을 벗어나는 상위 디렉터리 순회(탈출)를 차단하고 절대 경로를 반환."""
    work_dir = Path(config.WORK_DIR).resolve()
    target = (work_dir / filename).resolve()
    try:
        target.relative_to(work_dir)
    except ValueError:
        raise PermissionError(f"작업 디렉터리({work_dir}) 외부의 파일({target})에는 접근할 수 없습니다.") from None
    return target


def list_files(directory: str = ".", pattern: str = "*") -> str:
    """
    작업 디렉터리 내의 파일 및 폴더 목록을 조회합니다.

    Args:
        directory: 탐색할 하위 폴더 경로 (기본값 '.')
        pattern: 파일 필터 패턴 (예: '*.java', '*.md')
    """
    try:
        target_dir = _safe_resolve(directory)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"

    if not target_dir.exists():
        return f"error: 디렉터리가 존재하지 않습니다: {directory}"
    if not target_dir.is_dir():
        return f"error: 디렉터리가 아닙니다: {directory}"

    entries = []
    try:
        # 디렉터리 내 엔트리 조회 (최대 100개 제한)
        all_items = sorted(target_dir.glob(pattern), key=lambda p: (not p.is_dir(), p.name.lower()))
        for p in all_items[:100]:
            rel = p.relative_to(Path(config.WORK_DIR).resolve())
            if p.is_dir():
                entries.append(f"[DIR]  {rel}/")
            else:
                size_kb = p.stat().st_size / 1024
                entries.append(f"[FILE] {rel} ({size_kb:.1f} KB)")

        total = len(all_items)
        suffix = f"\n... 총 {total}개 중 100개 표시됨" if total > 100 else ""
        return "\n".join(entries) + suffix if entries else "(파일이 없습니다)"
    except Exception as e:  # noqa: BLE001
        return f"error listing files: {e}"


def read_file(filename: str, start_line: int = 1, max_lines: int = 300) -> str:
    """
    파일의 내용을 지정한 줄 번호부터 최대 줄 수만큼 읽습니다.

    Args:
        filename: 읽을 파일 경로 (WORK_DIR 기준 상대 경로)
        start_line: 읽기 시작할 줄 번호 (1부터 시작, 기본 1)
        max_lines: 최대로 읽을 줄 수 (기본 300줄)
    """
    try:
        target_file = _safe_resolve(filename)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"

    if not target_file.exists():
        return f"error: 파일이 존재하지 않습니다: {filename}"
    if not target_file.is_file():
        return f"error: 파일이 아닙니다: {filename}"

    # 인코딩 처리 (utf-8 시도 후 cp949/euc-kr fallback)
    raw_content = ""
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            raw_content = target_file.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return f"error: 지원하는 인코딩(UTF-8, CP949)으로 파일을 읽을 수 없습니다: {filename}"

    lines = raw_content.splitlines()
    total_lines = len(lines)

    start_idx = max(0, start_line - 1)
    end_idx = min(total_lines, start_idx + max_lines)
    selected_lines = lines[start_idx:end_idx]

    # 줄 번호 접두사 부착
    output = []
    for idx, line in enumerate(selected_lines, start=start_idx + 1):
        output.append(f"{idx:4d} | {line}")

    result_str = "\n".join(output)
    if end_idx < total_lines:
        result_str += f"\n\n... (총 {total_lines}줄 중 {end_idx}줄까지 표시됨. 다음 내용을 보려면 start_line={end_idx + 1}로 다시 호출하세요)"

    return result_str


def write_file(filename: str, content: str) -> str:
    """
    파일을 생성하고 내용을 작성(저장)합니다.

    Args:
        filename: 저장할 파일 경로 (WORK_DIR 기준 상대 경로)
        content: 파일에 기록할 전체 문자열 내용
    """
    try:
        target_file = _safe_resolve(filename)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"

    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        byte_len = len(content.encode("utf-8"))
        line_count = len(content.splitlines())
        return f"success: {filename} 저장 완료 ({line_count}줄, {byte_len} bytes)"
    except Exception as e:  # noqa: BLE001
        return f"error writing file {filename}: {e}"


def edit_file(filename: str, target: str, replacement: str) -> str:
    """
    파일의 특정 텍스트 블록(target)을 새로운 텍스트(replacement)로 치환합니다.

    Args:
        filename: 수정할 파일 경로
        target: 바꿀 원본 문자열 (정확히 일치해야 함)
        replacement: 새로 치환할 문자열
    """
    try:
        target_file = _safe_resolve(filename)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"

    if not target_file.is_file():
        return f"error: 파일이 존재하지 않습니다: {filename}"

    try:
        content = target_file.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return f"error reading file {filename}: {e}"

    occurrences = content.count(target)
    if occurrences == 0:
        return "error: 파일 내에서 일치하는 target 문자열을 찾을 수 없습니다. (공백 및 줄바꿈을 확인하세요)"
    if occurrences > 1:
        return f"error: 일치하는 target 문자열이 {occurrences}곳 발견되었습니다. 더 구체적인 컨텍스트를 포함해 고유하게 지정하세요."

    new_content = content.replace(target, replacement, 1)
    try:
        target_file.write_text(new_content, encoding="utf-8")
        return f"success: {filename} 내용 치환 완료"
    except Exception as e:  # noqa: BLE001
        return f"error saving edited file {filename}: {e}"


def find_files(pattern: str, directory: str = ".", max_results: int = 50) -> str:
    """
    작업 디렉터리 내에서 glob 패턴에 일치하는 파일들을 재귀적으로 검색합니다.
    (빌드/가상환경/캐시 디렉터리는 자동 제외)

    Args:
        pattern: 찾을 파일 이름 패턴 (예: '*Mapper.java', '*.xml', '*sys01*')
        directory: 탐색 시작 디렉터리 (기본값 '.')
        max_results: 최대 결과 건수 (기본값 50)
    """
    try:
        target_dir = _safe_resolve(directory)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"

    if not target_dir.exists():
        return f"error: 디렉터리가 존재하지 않습니다: {directory}"
    if not target_dir.is_dir():
        return f"error: 디렉터리가 아닙니다: {directory}"

    work_dir = Path(config.WORK_DIR).resolve()
    matched: list[tuple[Path, float]] = []

    for root, dirs, files in os.walk(target_dir):
        # 무시할 디렉터리는 탐색에서 제외
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for file in sorted(files):
            if fnmatch.fnmatch(file, pattern):
                full_path = Path(root) / file
                try:
                    rel_path = full_path.relative_to(work_dir)
                    size_kb = full_path.stat().st_size / 1024
                    matched.append((rel_path, size_kb))
                except Exception:  # noqa: BLE001, S110
                    pass
                if len(matched) >= max_results:
                    break
        if len(matched) >= max_results:
            break

    if not matched:
        return f"'{pattern}' 패턴과 일치하는 파일을 찾을 수 없습니다 (검색 대상: {directory})"

    output = [f"[FILE] {p} ({sz:.1f} KB)" for p, sz in matched]
    suffix = f"\n... (최대 {max_results}개까지 표시됨)" if len(matched) >= max_results else ""
    return "\n".join(output) + suffix


def grep_search(
    query: str,
    path: str = ".",
    file_pattern: str = "*",
    max_matches: int = 50,
    case_sensitive: bool = False,
) -> str:
    """
    지정한 경로 내의 텍스트 파일들에서 특정 키워드나 정규식을 검색하여 일치하는 파일, 줄 번호, 내용을 반환합니다.

    Args:
        query: 검색할 문자열 또는 정규식
        path: 검색 대상 디렉터리 또는 파일 경로 (기본값 '.')
        file_pattern: 검색할 파일 확장자 필터 (예: '*.java', '*.xml', '*.py', 기본값 '*')
        max_matches: 최대 반환 결과 수 (기본값 50)
        case_sensitive: 대소문자 구분 여부 (기본값 False)
    """
    try:
        target_path = _safe_resolve(path)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"

    if not target_path.exists():
        return f"error: 경로가 존재하지 않습니다: {path}"

    work_dir = Path(config.WORK_DIR).resolve()
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(query, flags)
    except re.error as e:
        return f"error: 잘못된 검색어/정규식 패턴입니다: {e}"

    matches: list[str] = []

    def search_in_file(file_path: Path) -> None:
        nonlocal matches
        try:
            # 바이너리 파일 스킵
            with open(file_path, "rb") as f:
                sample = f.read(1024)
                if b"\x00" in sample:
                    return
        except Exception:  # noqa: BLE001
            return

        text = ""
        for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
            try:
                text = file_path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return

        rel_path = file_path.relative_to(work_dir)
        for idx, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                clean_line = line.strip()
                if len(clean_line) > 160:
                    clean_line = clean_line[:157] + "..."
                matches.append(f"{rel_path}:{idx}: {clean_line}")
                if len(matches) >= max_matches:
                    return

    if target_path.is_file():
        search_in_file(target_path)
    else:
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for file in sorted(files):
                if fnmatch.fnmatch(file, file_pattern):
                    search_in_file(Path(root) / file)
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break

    if not matches:
        return f"'{query}' 검색어와 일치하는 내용을 찾을 수 없습니다 (경로: {path}, 패턴: {file_pattern})"

    suffix = f"\n... (최대 {max_matches}개 결과까지 표시됨)" if len(matches) >= max_matches else ""
    return "\n".join(matches) + suffix

