"""
yunhee-cli Agent Loop Engine
로컬 모델(Qwen 14B)을 위한 다단계 자율 에이전트 루프 및 Fallback 실행 엔진.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from openai import AsyncOpenAI, OpenAI

from yunhee import config
from yunhee.agent.knowledge import prefetch_relevant_knowledge
from yunhee.agent.memory import get_rules_prompt_section
from yunhee.agent.parser import extract_tool_calls_from_text
from yunhee.agent.registry import ToolRegistry, create_default_registry
from yunhee.agent.session import SessionLogger

DEFAULT_SYSTEM_PROMPT = """\
당신은 vibe-coding 마이그레이션 전문 보조 에이전트 'yunhee'입니다.
작업 디렉터리 내의 파일들을 확인하고, 내용을 읽고, 수정하거나 명령어를 실행하여 사용자의 요청을 해결하세요.

[핵심 행동 지침]
1. [결과 전달 필수]: 사용자가 파일 목록, 디렉터리 구조, 파일 내용, 명령어 실행 결과 등을 물어보거나 조회를 요청한 경우, 절대로 "확인했습니다"나 "조회했습니다"라는 단순 확인 멘트로만 끝내지 마십시오. 도구를 통해 얻은 실제 내용(파일명 목록, 읽은 코드 내용, 명령어 출력 등)을 사용자 답변 본문에 마크다운 목록이나 코드블록으로 빠짐없이 정리하여 보여주어야 합니다.
2. [과도한 재귀 탐색 금지]: 사용자가 특정 디렉터리의 파일 목록을 요청했을 때는 해당 디렉터리 직계 목록만 1회 조회(`list_files`)한 후 즉시 그 목록을 답변에 정리하여 출력하세요. 사용자가 명시적으로 하위 폴더 조사를 요구하지 않는 한, 발견된 하위 디렉터리들을 재귀적으로 계속 파고들지 마세요.
3. [도구 활용]: 등록된 전문 도구들을 능동적으로 호출하세요:
   - 파일/코드 탐색: list_files, read_file, write_file, edit_file, find_files, grep_search
   - 실행: run_command (셸 명령 실행)
   - 장기 기억: save_rule(프로젝트 헌법/규칙 저장), save_knowledge(해결 노하우/특이사항 저장), search_knowledge(과거 노하우 벡터 검색)
   - 환경/로그: lookup_config(작업경로/DB/설정 확인), read_recent_errors(최근 서버 에러 확인)
4. [도구 이름 및 인자 규격]: 반드시 등록된 정확한 도구 이름을 호출하세요. arguments는 반드시 올바른 JSON 키-값 객체 형태여야 합니다.
5. [루프 방지]: 동일한 인자로 동일한 도구를 무의미하게 반복 호출하지 마세요.
"""


def build_system_prompt(base_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    """기본 시스템 프롬프트에 .yunhee/memory.md의 L1 핵심 규칙을 자동 주입합니다."""
    rules_section = get_rules_prompt_section()
    if rules_section:
        return f"{base_prompt.strip()}\n\n{rules_section}".strip()
    return base_prompt.strip()


class AgentLoop:
    """자율 에이전트 실행 루프."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        registry: ToolRegistry | None = None,
        system_prompt: str | None = None,
        max_steps: int = 10,
        session_logger: SessionLogger | None = None,
        auto_log: bool = True,
    ) -> None:
        self.model = model or config.OLLAMA_MODEL
        url = base_url or getattr(config, "OLLAMA_HOST", "http://localhost:11434")
        self.v1_url = f"{str(url).rstrip('/')}/v1"
        self.registry = registry or create_default_registry()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_steps = max_steps

        # 세션 로거 초기화
        if session_logger:
            self.session_logger: SessionLogger | None = session_logger
        elif auto_log:
            self.session_logger = SessionLogger()
        else:
            self.session_logger = None

        # OpenAI 클라이언트 초기화
        self._async_client = AsyncOpenAI(base_url=self.v1_url, api_key="ollama")
        self._sync_client = OpenAI(base_url=self.v1_url, api_key="ollama")

    def get_active_system_prompt(self) -> str:
        """기본 시스템 프롬프트에 동적 L1 규칙을 주입한 최종 프롬프트 반환."""
        return build_system_prompt(self.system_prompt)

    def run(
        self,
        user_message: str,
        messages_history: list[dict[str, Any]] | None = None,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        동기 방식으로 에이전트 루프를 실행합니다.

        Returns:
            (최종 응답 텍스트, 갱신된 메시지 히스토리)
        """
        schemas = self.registry.get_schemas()
        messages: list[dict[str, Any]] = []

        if messages_history:
            messages = list(messages_history)
        else:
            messages.append({"role": "system", "content": self.get_active_system_prompt()})

        # L2 시맨틱 지식 사전 검색 (Prefetch RAG)
        context_knowledge = prefetch_relevant_knowledge(user_message)
        effective_message = f"{context_knowledge}{user_message}" if context_knowledge else user_message

        messages.append({"role": "user", "content": effective_message})

        if self.session_logger:
            self.session_logger.log_user_message(user_message)

        step = 0
        last_calls_signature: Any = None

        while step < self.max_steps:
            step += 1

            # OpenAI Completion API 호출 (Ollama num_ctx 보장)
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=schemas if schemas else None,
                temperature=0.0,
                extra_body={"options": {"num_ctx": config.NUM_CTX}},
            )
            message = response.choices[0].message

            # -------------------------------------------------------------
            # Case 1: OpenAI SDK 표준 tool_calls 응답
            # -------------------------------------------------------------
            if message.tool_calls:
                current_sig = tuple(
                    (c.function.name, c.function.arguments) for c in message.tool_calls
                )
                if current_sig == last_calls_signature:
                    # 동일 호출 무한루프 가드
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append(message)

                for call in message.tool_calls:
                    fn_name = call.function.name
                    raw_args = call.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    if on_tool_call:
                        on_tool_call(fn_name, args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, args)

                    result = self.registry.dispatch(fn_name, args)

                    if on_tool_result:
                        on_tool_result(fn_name, result)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, result)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": f"{result}\n\n[안내]: 사용자가 조회를 요청한 정보라면 위 도구 결과의 상세 내용(목록/코드/로그 등)을 생략하지 말고 사용자 최종 답변 본문에 마크다운으로 직접 나열하여 보여주세요.",
                        }
                    )
                continue

            # -------------------------------------------------------------
            # Case 2: 본문 텍스트 내 Fallback 도구 호출 탐색
            # -------------------------------------------------------------
            content = (message.content or "").strip()
            extracted_calls = extract_tool_calls_from_text(content)
            valid_calls = [
                (name, args) for name, args in extracted_calls if self.registry.has_tool(name)
            ]

            if valid_calls:
                current_sig = tuple(
                    (name, json.dumps(args, sort_keys=True)) for name, args in valid_calls
                )
                if current_sig == last_calls_signature:
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append({"role": "assistant", "content": content})
                feedbacks = []

                for fn_name, fn_args in valid_calls:
                    if on_tool_call:
                        on_tool_call(fn_name, fn_args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, fn_args)

                    res = self.registry.dispatch(fn_name, fn_args)

                    if on_tool_result:
                        on_tool_result(fn_name, res)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, res)

                    feedbacks.append(f"[{fn_name} 결과]:\n{res}")

                # Fallback 피드백을 사용자 메시지로 주입
                feedback_content = (
                    "\n\n".join(feedbacks)
                    + "\n\n[안내]: 사용자가 조회를 요청한 정보라면 위 결과의 상세 내용을 생략하지 말고 최종 답변 본문에 직접 마크다운으로 나열하여 보여주세요."
                )
                messages.append({"role": "user", "content": feedback_content})
                continue

            # -------------------------------------------------------------
            # Case 3: 도구 호출이 없는 최종 텍스트 응답
            # -------------------------------------------------------------
            messages.append({"role": "assistant", "content": content})
            if self.session_logger:
                self.session_logger.log_assistant_message(content)
            return content, messages

        max_msg = f"최대 스텝 수({self.max_steps})를 초과하여 실행이 중단되었습니다."
        if self.session_logger:
            self.session_logger.log_assistant_message(max_msg)
        return max_msg, messages

    async def run_async(
        self,
        user_message: str,
        messages_history: list[dict[str, Any]] | None = None,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """비동기 방식으로 에이전트 루프를 실행합니다."""
        schemas = self.registry.get_schemas()
        messages: list[dict[str, Any]] = []

        if messages_history:
            messages = list(messages_history)
        else:
            messages.append({"role": "system", "content": self.get_active_system_prompt()})

        # L2 시맨틱 지식 사전 검색 (Prefetch RAG)
        context_knowledge = prefetch_relevant_knowledge(user_message)
        effective_message = f"{context_knowledge}{user_message}" if context_knowledge else user_message

        messages.append({"role": "user", "content": effective_message})

        if self.session_logger:
            self.session_logger.log_user_message(user_message)

        step = 0
        last_calls_signature: Any = None

        while step < self.max_steps:
            step += 1

            response = await self._async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=schemas if schemas else None,
                temperature=0.0,
                extra_body={"options": {"num_ctx": config.NUM_CTX}},
            )
            message = response.choices[0].message

            if message.tool_calls:
                current_sig = tuple(
                    (c.function.name, c.function.arguments) for c in message.tool_calls
                )
                if current_sig == last_calls_signature:
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append(message)

                for call in message.tool_calls:
                    fn_name = call.function.name
                    raw_args = call.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    if on_tool_call:
                        on_tool_call(fn_name, args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, args)

                    result = self.registry.dispatch(fn_name, args)

                    if on_tool_result:
                        on_tool_result(fn_name, result)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, result)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": f"{result}\n\n[안내]: 사용자가 조회를 요청한 정보라면 위 도구 결과의 상세 내용(목록/코드/로그 등)을 생략하지 말고 사용자 최종 답변 본문에 마크다운으로 직접 나열하여 보여주세요.",
                        }
                    )
                continue

            content = (message.content or "").strip()
            extracted_calls = extract_tool_calls_from_text(content)
            valid_calls = [
                (name, args) for name, args in extracted_calls if self.registry.has_tool(name)
            ]

            if valid_calls:
                current_sig = tuple(
                    (name, json.dumps(args, sort_keys=True)) for name, args in valid_calls
                )
                if current_sig == last_calls_signature:
                    msg = "동일한 작업이 반복 감지되어 작업을 종료합니다."
                    if self.session_logger:
                        self.session_logger.log_assistant_message(msg)
                    return msg, messages
                last_calls_signature = current_sig

                messages.append({"role": "assistant", "content": content})
                feedbacks = []

                for fn_name, fn_args in valid_calls:
                    if on_tool_call:
                        on_tool_call(fn_name, fn_args)
                    if self.session_logger:
                        self.session_logger.log_tool_call(fn_name, fn_args)

                    res = self.registry.dispatch(fn_name, fn_args)

                    if on_tool_result:
                        on_tool_result(fn_name, res)
                    if self.session_logger:
                        self.session_logger.log_tool_result(fn_name, res)

                    feedbacks.append(f"[{fn_name} 결과]:\n{res}")

                feedback_content = (
                    "\n\n".join(feedbacks)
                    + "\n\n[안내]: 사용자가 조회를 요청한 정보라면 위 결과의 상세 내용을 생략하지 말고 최종 답변 본문에 직접 마크다운으로 나열하여 보여주세요."
                )
                messages.append({"role": "user", "content": feedback_content})
                continue

            messages.append({"role": "assistant", "content": content})
            if self.session_logger:
                self.session_logger.log_assistant_message(content)
            return content, messages

        max_msg = f"최대 스텝 수({self.max_steps})를 초과하여 실행이 중단되었습니다."
        if self.session_logger:
            self.session_logger.log_assistant_message(max_msg)
        return max_msg, messages
