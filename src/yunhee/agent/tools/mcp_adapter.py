"""
yunhee-cli MCP (Model Context Protocol) Adapter
.yunhee/mcp.json에 정의된 외부 Stdio MCP 서버들을 백그라운드 이벤트 루프 스레드에서
안전하게 연결하고 제공 도구들을 ToolRegistry에 동적으로 등록/중계합니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from yunhee import config

if TYPE_CHECKING:
    from yunhee.agent.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MCP_TIMEOUT = 30.0
CONNECT_TIMEOUT = 15.0


class MCPManager:
    """외부 Stdio MCP 서버 프로세스를 관리하고 도구 실행을 중계하는 매니저."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or (Path(config.WORK_DIR) / ".yunhee" / "mcp.json")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}  # server_name -> ClientSession
        self._tool_to_server: dict[str, str] = {}  # tool_name -> server_name
        self._tools_meta: list[dict[str, Any]] = []
        self._started = False
        self._lock = threading.Lock()

    def _ensure_event_loop(self) -> None:
        """백그라운드 스레드에서 독립된 asyncio 이벤트 루프를 기동합니다."""
        if self._started and self._loop and self._loop.is_running():
            return

        with self._lock:
            if self._started and self._loop and self._loop.is_running():
                return

            ready_event = threading.Event()

            def _thread_target() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready_event.set()
                loop.run_forever()

            self._thread = threading.Thread(target=_thread_target, name="yunhee-mcp-worker", daemon=True)
            self._thread.start()
            ready_event.wait(timeout=5.0)
            self._started = True

    def _run_coro_sync(self, coro: Any, timeout: float = DEFAULT_MCP_TIMEOUT) -> Any:
        """백그라운드 이벤트 루프에 비동기 코루틴을 제출하고 동기 블로킹으로 대기합니다."""
        self._ensure_event_loop()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def load_config(self) -> dict[str, Any]:
        """mcp.json 파일을 읽어 딕셔너리로 반환합니다."""
        if not self.config_path.is_file():
            return {}
        try:
            content = self.config_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            return {}
        except Exception as e:  # noqa: BLE001
            logger.warning("mcp.json 파싱 실패 (%s): %s", self.config_path, e)
            return {}

    async def _connect_server(self, name: str, srv_conf: dict[str, Any]) -> list[dict[str, Any]]:
        """단일 MCP 서버에 연결하고 제공 도구 목록을 반환합니다."""
        command = srv_conf.get("command")
        if not command:
            logger.warning("MCP 서버 '%s': 'command' 필드가 누락되어 건너뜁니다.", name)
            return []

        args = [str(a) for a in srv_conf.get("args", [])]
        env = srv_conf.get("env")
        if env is not None:
            env = {str(k): str(v) for k, v in env.items()}

        params = StdioServerParameters(command=command, args=args, env=env)
        assert self._exit_stack is not None

        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools_res = await session.list_tools()
        tools_list: list[dict[str, Any]] = []

        self._sessions[name] = session
        for t in tools_res.tools:
            self._tool_to_server[t.name] = name
            schema_params = t.inputSchema if hasattr(t, "inputSchema") else getattr(t, "input_schema", {})
            meta = {
                "server": name,
                "name": t.name,
                "description": t.description or f"MCP tool from {name}",
                "parameters": schema_params or {"type": "object", "properties": {}},
            }
            tools_list.append(meta)

        return tools_list

    async def _connect_all_async(self) -> list[dict[str, Any]]:
        """설정된 모든 MCP 서버를 연결합니다."""
        cfg = self.load_config()
        servers = cfg.get("mcpServers", {})
        if not isinstance(servers, dict) or not servers:
            return []

        self._exit_stack = AsyncExitStack()
        all_tools: list[dict[str, Any]] = []

        for name, srv_conf in servers.items():
            if not isinstance(srv_conf, dict):
                continue
            try:
                # 개별 서버 연결 타임아웃 적용
                tools = await asyncio.wait_for(
                    self._connect_server(name, srv_conf),
                    timeout=CONNECT_TIMEOUT,
                )
                all_tools.extend(tools)
                logger.info("✔ MCP 서버 연결 성공: '%s' (%d개 도구)", name, len(tools))
            except Exception as e:  # noqa: BLE001
                logger.warning("⚠ MCP 서버 '%s' 연결 실패 (건너뜀): %s", name, e)

        self._tools_meta = all_tools
        return all_tools

    def connect_all(self) -> list[dict[str, Any]]:
        """모든 MCP 서버를 동기 방식으로 연결하고 등록된 도구 메타 목록을 반환합니다."""
        if not self.config_path.is_file():
            return []
        try:
            return self._run_coro_sync(self._connect_all_async(), timeout=CONNECT_TIMEOUT * 2)
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP 서버 일괄 연결 중 오류: %s", e)
            return []

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """지정한 MCP 도구를 비동기 호출합니다."""
        server_name = self._tool_to_server.get(tool_name)
        if not server_name or server_name not in self._sessions:
            return f"error: 실행 가능한 MCP 세션을 찾을 수 없습니다: '{tool_name}'"

        session = self._sessions[server_name]
        res = await session.call_tool(tool_name, arguments=arguments)

        parts: list[str] = []
        for content in getattr(res, "content", []):
            if hasattr(content, "text"):
                parts.append(str(content.text))
            else:
                parts.append(str(content))

        output = "\n".join(parts) if parts else "(결과 없음)"
        if getattr(res, "isError", False) or getattr(res, "is_error", False):
            return f"error from MCP ({tool_name}): {output}"
        return output

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """지정한 MCP 도구를 동기 방식으로 호출하고 텍스트 결과를 반환합니다."""
        try:
            return str(self._run_coro_sync(self._call_tool_async(tool_name, arguments)))
        except Exception as e:  # noqa: BLE001
            return f"error calling MCP tool '{tool_name}': {e}"

    def register_tools_to_registry(self, registry: ToolRegistry) -> int:
        """연결된 모든 MCP 도구를 ToolRegistry에 등록합니다."""
        registered_count = 0
        for meta in self._tools_meta:
            name = meta["name"]
            desc = meta["description"]
            params = meta["parameters"]

            def make_handler(t_name: str):
                return lambda **kwargs: self.call_tool(t_name, kwargs)

            registry.register(
                name=name,
                func=make_handler(name),
                description=desc,
                parameters=params,
            )
            registered_count += 1

        return registered_count

    def close(self) -> None:
        """모든 활성 세션과 백그라운드 이벤트 루프를 안전하게 종료합니다."""
        if not self._started or not self._loop:
            return

        async def _close_stack() -> None:
            if self._exit_stack:
                await self._exit_stack.aclose()
            self._sessions.clear()
            self._tool_to_server.clear()
            self._tools_meta.clear()

        try:
            if self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_close_stack(), self._loop)
                future.result(timeout=5.0)
                self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception as e:  # noqa: BLE001
            logger.debug("MCP 세션 닫기 중 예외 (무시): %s", e)
        finally:
            self._started = False
            self._loop = None
            self._thread = None
