import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yunhee import config, project
from yunhee.tools.base import ToolResult

RUNS_DIR_NAME = ".yunhee/runs"
DEFAULT_CHAR_PREVIEW_LIMIT = 4000


def get_runs_dir(base_dir: Path | None = None) -> Path:
    target_base = base_dir or config.WORK_DIR
    runs_dir = target_base / RUNS_DIR_NAME
    runs_dir.mkdir(parents=True, exist_ok=True)
    return runs_dir


def extract_test_results(
    command: str,
    cwd: Path | None = None,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, Any] | None:
    """명령어가 gradle/mvn test인 경우 XML 또는 로그에서 테스트 결과를 추출한다 (C-3)."""
    cmd_lower = command.lower()
    is_test_cmd = ("gradle" in cmd_lower or "mvn" in cmd_lower) and "test" in cmd_lower
    if not is_test_cmd:
        return None

    base_dir = (cwd or Path.cwd()).resolve()
    # bash -c 'cd backend && gradle test' 같은 cd <dir> 경로 추적
    m_cd = re.search(r"\bcd\s+([^\s;&|]+)", command)
    if m_cd:
        raw_cd = m_cd.group(1).strip("'\"")
        cand_cd = (base_dir / raw_cd).resolve()
        if cand_cd.is_dir():
            base_dir = cand_cd

    # 1. XML 탐색 (build/test-results/test/*.xml 또는 target/surefire-reports/*.xml)
    xml_files = list(base_dir.glob("**/build/test-results/test/*.xml"))
    if not xml_files:
        xml_files = list(base_dir.glob("**/target/surefire-reports/*.xml"))

    if xml_files:
        total = 0
        failures = 0
        skipped = 0
        failed_cases: list[str] = []

        for xf in xml_files:
            try:
                tree = ET.parse(xf)
                root = tree.getroot()
                t = int(root.attrib.get("tests", 0))
                f = int(root.attrib.get("failures", 0)) + int(root.attrib.get("errors", 0))
                s = int(root.attrib.get("skipped", 0))
                total += t
                failures += f
                skipped += s
                if f > 0:
                    cls_name = root.attrib.get("name", xf.stem)
                    cls_simple = cls_name.split(".")[-1]
                    for tc in root.findall("testcase"):
                        fail_node = tc.find("failure")
                        if fail_node is None:
                            fail_node = tc.find("error")
                        if fail_node is not None:
                            case_name = tc.attrib.get("name", "unknown")
                            failed_cases.append(f"{cls_simple} > {case_name} FAILED")
            except Exception:  # noqa: BLE001, S110
                pass

        return {
            "source": "xml",
            "total": total,
            "failures": failures,
            "skipped": skipped,
            "failed_cases": failed_cases,
        }

    # 2. 로그 정규식 탐색 (XML 없을 때 fallback)
    combined = f"{stdout}\n{stderr}"
    m_gradle = re.search(r"(\d+)\s+tests? completed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+skipped)?", combined, re.IGNORECASE)
    if m_gradle:
        tot = int(m_gradle.group(1))
        fail = int(m_gradle.group(2))
        skip = int(m_gradle.group(3) or 0)
        return {"source": "log", "total": tot, "failures": fail, "skipped": skip, "failed_cases": []}

    m_mvn = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", combined)
    if m_mvn:
        tot = int(m_mvn.group(1))
        fail = int(m_mvn.group(2)) + int(m_mvn.group(3))
        skip = int(m_mvn.group(4))
        return {"source": "log", "total": tot, "failures": fail, "skipped": skip, "failed_cases": []}

    return None


def execute_command(
    command: str,
    cwd: Path | None = None,
    timeout: int = 120,
    char_preview_limit: int = DEFAULT_CHAR_PREVIEW_LIMIT,
) -> ToolResult:
    """외부 명령어를 실행하고, 전체 원시 출력을 프로젝트 루트의 .yunhee/runs/<run_id>.log에 저장한 뒤 ToolResult를 반환한다."""
    effective_cwd = (Path(cwd) if cwd else Path.cwd()).resolve()
    project_root = project.find_project_root(effective_cwd)
    runs_dir = get_runs_dir(project_root)

    # project_root 기준 상대 cwd 계산 (C-4)
    try:
        rel_cwd = str(effective_cwd.relative_to(project_root))
        if rel_cwd == "":
            rel_cwd = "."
    except ValueError:
        rel_cwd = str(effective_cwd)

    run_id = f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    log_file = runs_dir / f"{run_id}.log"

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(effective_cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        exit_code = -1
        stdout = exc.stdout or "" if isinstance(exc.stdout, str) else (exc.stdout.decode() if exc.stdout else "")
        stderr = (
            (exc.stderr or "" if isinstance(exc.stderr, str) else (exc.stderr.decode() if exc.stderr else ""))
            + f"\n[ERROR] Command timed out after {timeout} seconds."
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        exit_code = -1
        stdout = ""
        stderr = f"[ERROR] Failed to run command: {exc}"

    # 전체 로그 파일 저장
    log_content = (
        f"=== Command: {command} ===\n"
        f"=== Directory: {effective_cwd} ===\n"
        f"=== Project Root: {project_root} ===\n"
        f"=== Timestamp: {datetime.now(UTC).isoformat()} ===\n"
        f"=== Exit Code: {exit_code} ===\n"
        f"=== Duration: {duration_ms}ms ===\n\n"
        "--- STDOUT ---\n"
        f"{stdout}\n\n"
        "--- STDERR ---\n"
        f"{stderr}\n"
    )
    log_file.write_text(log_content, encoding="utf-8")

    # 미리보기 텍스트 및 truncation 처리
    truncated = False
    stdout_preview = stdout
    if len(stdout_preview) > char_preview_limit:
        stdout_preview = stdout_preview[:char_preview_limit] + "\n... [TRUNCATED in preview]"
        truncated = True

    stderr_preview = stderr
    if len(stderr_preview) > char_preview_limit:
        stderr_preview = stderr_preview[:char_preview_limit] + "\n... [TRUNCATED in preview]"
        truncated = True

    data = {
        "run_id": run_id,
        "command": command,
        "cwd": rel_cwd,
        "abs_cwd": str(effective_cwd),
        "project_root": str(project_root),
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "log_path": str(log_file),
        "stdout": stdout,
        "stderr": stderr,
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
    }

    ok = exit_code == 0
    error_msg = None if ok else f"Command failed with exit code {exit_code}"

    return ToolResult(
        ok=ok,
        data=data,
        error=error_msg,
        truncated=truncated,
    )
