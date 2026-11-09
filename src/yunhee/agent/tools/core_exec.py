"""
yunhee-cli Agent Core Execution Tools
외부 명령어를 안전하게 실행하고 결과를 요약/압축하는 도구.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from yunhee import config


def _strip_code_fences(code: str) -> str:
    """마크다운 코드펜스(```python ... ```)가 포함된 경우 내부 코드만 추출한다."""
    stripped = code.strip()
    m = re.match(r"^```(?:python|py)?\s*\n([\s\S]*?)\n```\s*$", stripped, re.IGNORECASE)
    if m:
        return m.group(1)
    return code


def execute_python(code: str, description: str = "", timeout_seconds: int = 30) -> str:
    """
    에이전트가 작성한 Python 코드를 임시 스크립트(.yunhee/scratch/)로 저장하고 실행하여
    표준 출력(STDOUT)과 표준 에러(STDERR)를 반환합니다.

    Args:
        code: 실행할 Python 3 소스 코드 문자열
        description: 스크립트 수행 목적 요약 (선택)
        timeout_seconds: 최대 대기 시간 (초, 기본 30초)
    """
    work_dir = Path(config.WORK_DIR).resolve()
    scratch_dir = work_dir / ".yunhee" / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    clean_code = _strip_code_fences(code)
    ts_ms = int(time.time() * 1000)
    script_path = scratch_dir / f"agent_script_{ts_ms}.py"
    header = f"# Description: {description}\n" if description else ""
    script_path.write_text(f"{header}{clean_code}\n", encoding="utf-8")

    env = os.environ.copy()
    yunhee_src = str((Path(config.YUNHEE_DIR) / "src").resolve())
    prev_py_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{yunhee_src}:{prev_py_path}" if prev_py_path else yunhee_src

    start_time = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=work_dir,
            env=env,
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
            combined.append("(출력 없음 — 결과를 확인하려면 print() 문을 사용하세요)")

        full_output = f"[Exit Code: {exit_code}, Elapsed: {elapsed:.2f}s, Script: {script_path.name}]\n" + "\n\n".join(combined)

        if len(full_output) > 4000:
            return (
                f"{full_output[:2000]}\n\n"
                f"... [총 {len(full_output)}자 중 중간 내용 생략] ...\n\n"
                f"{full_output[-1500:]}"
            )
        return full_output
    except subprocess.TimeoutExpired:
        return f"error: Python 스크립트 실행 시간({timeout_seconds}초)을 초과하여 강제 종료되었습니다."
    except Exception as e:  # noqa: BLE001
        return f"error executing python script: {e}"


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
