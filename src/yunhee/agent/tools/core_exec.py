"""
yunhee-cli Agent Core Execution Tools
외부 명령어를 안전하게 실행하고 결과를 요약/압축하는 도구.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from yunhee import config


def run_command(command: str, timeout_seconds: int = 30) -> str:
    """
    작업 디렉터리(WORK_DIR)에서 셸 명령어를 실행하고 표준 출력 및 표준 에러를 반환합니다.

    Args:
        command: 실행할 셸 명령어 문자열
        timeout_seconds: 최대 대기 시간 (초, 기본 30초)
    """
    work_dir = Path(config.WORK_DIR).resolve()

    start_time = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = time.time() - start_time
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode

        combined = []
        if stdout.strip():
            combined.append(f"STDOUT:\n{stdout.strip()}")
        if stderr.strip():
            combined.append(f"STDERR:\n{stderr.strip()}")
        if not combined:
            combined.append("(출력 없음)")

        full_output = f"[Exit Code: {exit_code}, Elapsed: {elapsed:.2f}s]\n" + "\n\n".join(combined)

        # 1,500자를 초과할 경우 앞/뒤 요약
        if len(full_output) > 1500:
            return (
                f"{full_output[:700]}\n\n"
                f"... [총 {len(full_output)}자 중 중간 내용 생략] ...\n\n"
                f"{full_output[-700:]}"
            )

        return full_output
    except subprocess.TimeoutExpired:
        return f"error: 명령어 실행 시간({timeout_seconds}초)을 초과하여 강제 종료되었습니다: {command}"
    except Exception as e:  # noqa: BLE001
        return f"error executing command '{command}': {e}"
