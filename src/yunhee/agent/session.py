"""
yunhee-cli Agent Session Logger
대화 세션의 모든 질문, 답변, 도구 호출 및 결과를 JSONL 및 마크다운 파일로 영구 기록하는 로거.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yunhee import config


def _current_time() -> datetime:
    """로컬 타임존 기반 현재 시각 반환."""
    return datetime.now(UTC).astimezone()


class SessionLogger:
    """단일 대화 세션의 트랜스크립트를 관리하고 파일에 기록하는 클래스."""

    def __init__(self, session_id: str | None = None, base_dir: Path | str | None = None) -> None:
        now = _current_time()
        self.session_id = session_id or now.strftime("%Y-%m-%d_%H%M%S")

        if base_dir:
            self.sessions_dir = Path(base_dir).resolve()
        else:
            self.sessions_dir = (Path(config.WORK_DIR) / ".yunhee" / "sessions").resolve()

        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.sessions_dir / f"{self.session_id}.jsonl"
        self.md_path = self.sessions_dir / f"{self.session_id}.md"

        # 마크다운 헤더 초기화 (처음 생성 시)
        if not self.md_path.exists():
            header = f"# yunhee 대화 세션 기록 ({self.session_id})\n\n- 시작 일시: {now.strftime('%Y-%m-%d %H:%M:%S')}\n- 작업 디렉터리: `{config.WORK_DIR}`\n\n---\n\n"
            self.md_path.write_text(header, encoding="utf-8")

    def _append_jsonl(self, record: dict[str, Any]) -> None:
        try:
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001, S110
            pass

    def _append_md(self, text: str) -> None:
        try:
            with self.md_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n\n")
        except Exception:  # noqa: BLE001, S110
            pass

    def log_user_message(self, content: str) -> None:
        """사용자 입력 메시지 기록."""
        now = _current_time()
        time_str = now.strftime("%H:%M:%S")

        self._append_jsonl(
            {
                "timestamp": now.isoformat(),
                "role": "user",
                "content": content,
            }
        )

        md = f"### 👤 User ({time_str})\n\n{content}"
        self._append_md(md)

    def log_tool_call(self, name: str, arguments: dict[str, Any]) -> None:
        """도구 호출 요청 기록."""
        now = _current_time()
        time_str = now.strftime("%H:%M:%S")

        self._append_jsonl(
            {
                "timestamp": now.isoformat(),
                "role": "tool_call",
                "name": name,
                "arguments": arguments,
            }
        )

        args_preview = json.dumps(arguments, ensure_ascii=False)
        md = f"> 🛠 **도구 호출** ({time_str}): `{name}({args_preview})`"
        self._append_md(md)

    def log_tool_result(self, name: str, result: str) -> None:
        """도구 실행 결과 기록."""
        now = _current_time()
        time_str = now.strftime("%H:%M:%S")

        # 10,000자 초과 시 jsonl 저장용 truncate
        json_res = result if len(result) <= 5000 else f"{result[:2500]}\n... [생략] ...\n{result[-2500:]}"
        self._append_jsonl(
            {
                "timestamp": now.isoformat(),
                "role": "tool_result",
                "name": name,
                "result": json_res,
            }
        )

        # 마크다운용 미리보기
        lines = result.strip().splitlines()
        if len(lines) <= 8:
            body = "\n".join(lines)
        else:
            body = "\n".join(lines[:5]) + f"\n... (외 {len(lines) - 5}줄 생략)"

        md = f"> ↳ **결과** ({name}, {time_str}):\n```text\n{body}\n```"
        self._append_md(md)

    def log_assistant_message(self, content: str) -> None:
        """어시스턴트 최종 응답 기록."""
        now = _current_time()
        time_str = now.strftime("%H:%M:%S")

        self._append_jsonl(
            {
                "timestamp": now.isoformat(),
                "role": "assistant",
                "content": content,
            }
        )

        md = f"### 🤖 Yunhee ({time_str})\n\n{content}\n\n---"
        self._append_md(md)
