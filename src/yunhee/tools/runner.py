import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from yunhee import config
from yunhee.tools.base import ToolResult

RUNS_DIR_NAME = ".yunhee/runs"
DEFAULT_CHAR_PREVIEW_LIMIT = 4000


def get_runs_dir(base_dir: Path | None = None) -> Path:
    target_base = base_dir or config.WORK_DIR
    runs_dir = target_base / RUNS_DIR_NAME
    runs_dir.mkdir(parents=True, exist_ok=True)
    return runs_dir


def execute_command(
    command: str,
    cwd: Path | None = None,
    timeout: int = 120,
    char_preview_limit: int = DEFAULT_CHAR_PREVIEW_LIMIT,
) -> ToolResult:
    """외부 명령어를 실행하고, 전체 원시 출력을 .yunhee/runs/<run_id>.log에 저장한 뒤 ToolResult를 반환한다."""
    effective_cwd = Path(cwd) if cwd else config.WORK_DIR
    runs_dir = get_runs_dir(effective_cwd)

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
        "cwd": str(effective_cwd),
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
