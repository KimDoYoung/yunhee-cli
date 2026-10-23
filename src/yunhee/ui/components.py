"""
yunhee-cli UI Components & Helpers
스피너 상태 관리, 키 인터럽트(ESC 연타 취소), 도구 실행 카드 및 포맷터.
"""

from __future__ import annotations

import select
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from rich.table import Table

try:
    import termios
    import tty
except ImportError:  # Windows 등 비 POSIX 환경 호환
    termios = None
    tty = None


class EscCancelListener:
    """
    터미널에서 ESC 키 2회(더블 탭) 입력을 감지하여 실행 중인 작업을 취소하는 백그라운드 리스너.
    """

    def __init__(self, cancel_callback: Callable[[], None], double_tap_timeout: float = 0.8) -> None:
        self.cancel_callback = cancel_callback
        self.double_tap_timeout = double_tap_timeout
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.old_settings = None

    def start(self) -> None:
        if termios is None or tty is None or not sys.stdin.isatty():
            return
        try:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception:  # noqa: BLE001
            self.old_settings = None
            return

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.old_settings and termios and sys.stdin.isatty():
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            except Exception:  # noqa: BLE001, S110
                pass

    def _run(self) -> None:
        last_esc_time = 0.0
        while not self.stop_event.is_set():
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not r:
                    continue

                ch = sys.stdin.read(1)
                if ch == "\x1b":  # ESC 바이트 (ASCII 27)
                    # 화살표 키나 기능키 시퀀스(예: \x1b[A) 여부 확인을 위해 짧게 대기
                    r_seq, _, _ = select.select([sys.stdin], [], [], 0.04)
                    if r_seq:
                        sys.stdin.read(10)  # 기능키 시퀀스 소비 후 무시
                        continue

                    now = time.time()
                    if (now - last_esc_time) <= self.double_tap_timeout:
                        # ESC 2회 연속 감지! 취소 트리거
                        self.cancel_callback()
                        break
                    else:
                        last_esc_time = now
                        sys.stdout.write("\n  \033[33m⚡ ESC를 한 번 더 누르면 실행이 취소됩니다...\033[0m\n")
                        sys.stdout.flush()
            except Exception:  # noqa: BLE001
                break


@contextmanager
def listen_esc_cancel(cancel_callback: Callable[[], None], double_tap_timeout: float = 0.8):
    """ESC 2회 취소 리스너 컨텍스트 매니저."""
    listener = EscCancelListener(cancel_callback, double_tap_timeout=double_tap_timeout)
    listener.start()
    try:
        yield listener
    finally:
        listener.stop()


def format_tool_call_status(name: str, args: dict[str, Any]) -> str:
    """스피너에 표시할 도구 호출 상태 문자열 포맷팅."""
    args_repr = ", ".join(f"{k}={v!r}" for k, v in args.items())
    if len(args_repr) > 60:
        args_repr = args_repr[:57] + "..."
    return f"[bold yellow]⠋ 도구 실행 중:[/bold yellow] [bold]{name}[/bold]({args_repr}) [dim](취소: ESC 2회)[/dim]"


def format_tool_result_preview(name: str, result: str, max_lines: int = 4) -> str:
    """콘솔에 출력할 도구 실행 완료 미리보기 문자열 포맷팅."""
    clean_res = result.strip()
    if not clean_res:
        return f"  [green]✔ 도구 완료 ({name}):[/green] [dim](빈 결과)[/dim]"

    lines = clean_res.splitlines()
    if len(lines) <= max_lines:
        body = "\n    ".join(lines)
        return f"  [green]✔ 도구 완료 ({name}):[/green]\n    [dim]{body}[/dim]"

    top = "\n    ".join(lines[:max_lines])
    remaining = len(lines) - max_lines
    return f"  [green]✔ 도구 완료 ({name}):[/green]\n    [dim]{top}\n    ... (외 {remaining}줄 생략)[/dim]"


def render_tools_table(schemas: list[dict[str, Any]]) -> Table:
    """등록된 도구 목록을 Rich Table로 렌더링."""
    table = Table(title="🤖 등록된 에이전트 도구 목록", show_header=True, header_style="bold cyan")
    table.add_column("도구 이름", style="bold green", no_wrap=True)
    table.add_column("설명", style="white")
    table.add_column("주요 인자", style="dim")

    for item in schemas:
        fn = item.get("function", {})
        name = fn.get("name", "")
        desc = fn.get("description", "").splitlines()[0] if fn.get("description") else ""
        params = fn.get("parameters", {}).get("properties", {})
        params_str = ", ".join(params.keys()) if params else "(없음)"
        table.add_row(name, desc, params_str)

    return table
