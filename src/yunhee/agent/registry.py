"""
yunhee-cli Agent Tool Registry
도구 등록, 스키마 변환(OpenAI Tool Schema) 및 실행 디스패치 관리.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yunhee.agent.tools.core_exec import run_command
from yunhee.agent.tools.core_fs import (
    edit_file,
    find_files,
    grep_search,
    list_files,
    read_file,
    write_file,
)


@dataclass
class ToolDefinition:
    name: str
    func: Callable[..., Any]
    description: str
    parameters: dict[str, Any]


class ToolRegistry:
    """에이전트가 호출 가능한 도구들을 보관하고 실행을 중개하는 레지스트리."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        """도구를 등록합니다."""
        self._tools[name] = ToolDefinition(
            name=name,
            func=func,
            description=description.strip(),
            parameters=parameters,
        )

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_schemas(self) -> list[dict[str, Any]]:
        """OpenAI API 규격의 tools 파라미터 리스트 반환."""
        schemas = []
        for tool in self._tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """도구 이름과 인자를 받아 실제 함수를 실행하고 문자열 결과를 반환."""
        if name not in self._tools:
            return f"error: 알 수 없는 도구입니다: '{name}'"

        tool_def = self._tools[name]
        try:
            # 인자 매핑 및 호출
            result = tool_def.func(**arguments)
            return str(result)
        except TypeError as e:
            return f"error calling {name}: 잘못된 인자 구성입니다 ({e})"
        except Exception as e:  # noqa: BLE001
            return f"error in {name}: {e}"


def create_default_registry() -> ToolRegistry:
    """기본 Core 파일 시스템 및 실행 도구가 등록된 ToolRegistry 인스턴스 생성."""
    reg = ToolRegistry()

    # 1. list_files
    reg.register(
        name="list_files",
        func=list_files,
        description="지정한 디렉터리 바로 아래의 직계 파일 및 폴더 목록을 1단계만 조회합니다. (하위 폴더를 재귀 탐색하지 마세요)",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "조회할 하위 디렉터리 경로 (기본값 '.')",
                },
                "pattern": {
                    "type": "string",
                    "description": "와일드카드 파일 필터 (예: '*.java', '*.md', 기본값 '*')",
                },
            },
        },
    )

    # 2. read_file
    reg.register(
        name="read_file",
        func=read_file,
        description="지정한 파일의 내용을 줄 번호와 함께 읽습니다.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "읽을 파일의 상대 경로",
                },
                "start_line": {
                    "type": "integer",
                    "description": "시작 줄 번호 (1부터 시작, 기본 1)",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "최대로 읽을 줄 수 (기본 300줄)",
                },
            },
            "required": ["filename"],
        },
    )

    # 3. write_file
    reg.register(
        name="write_file",
        func=write_file,
        description="지정한 파일에 새로운 내용을 작성(덮어쓰기)합니다.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "작성할 파일의 상대 경로",
                },
                "content": {
                    "type": "string",
                    "description": "파일에 기록할 전체 문자열",
                },
            },
            "required": ["filename", "content"],
        },
    )

    # 4. edit_file
    reg.register(
        name="edit_file",
        func=edit_file,
        description="파일 내용 중 정확히 일치하는 단일 target 블록을 replacement로 부분 치환합니다.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "수정할 대상 파일 경로",
                },
                "target": {
                    "type": "string",
                    "description": "기존 파일에서 바꿀 정확한 원본 문자열",
                },
                "replacement": {
                    "type": "string",
                    "description": "새로 교체할 문자열",
                },
            },
            "required": ["filename", "target", "replacement"],
        },
    )

    # 5. run_command
    reg.register(
        name="run_command",
        func=run_command,
        description="작업 디렉터리(WORK_DIR)에서 셸 명령어를 실행하고 표준 출력/에러를 반환합니다.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "실행할 셸 명령어",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "최대 대기 시간(초, 기본 30초)",
                },
            },
            "required": ["command"],
        },
    )

    # 6. find_files
    reg.register(
        name="find_files",
        func=find_files,
        description="프로젝트 전체 또는 특정 폴더 트리에서 이름 패턴(glob)에 일치하는 파일들을 재귀 검색합니다.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "찾을 파일명 와일드카드 패턴 (예: '*Mapper.java', '*.xml', '*sys01*')",
                },
                "directory": {
                    "type": "string",
                    "description": "검색 시작 하위 폴더 (기본값 '.')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "최대 결과 건수 (기본 50)",
                },
            },
            "required": ["pattern"],
        },
    )

    # 7. grep_search
    reg.register(
        name="grep_search",
        func=grep_search,
        description="텍스트 파일들의 내용 중에서 특정 키워드나 정규식을 검색하여 일치하는 파일명, 줄 번호, 내용을 찾아냅니다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 텍스트 키워드 또는 정규식",
                },
                "path": {
                    "type": "string",
                    "description": "검색 대상 디렉터리 또는 파일 경로 (기본값 '.')",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "특정 파일 확장자로 좁힐 때만 지정하세요. (기본값 '*'는 모든 텍스트 파일 대상, 지정하지 않는 것을 권장)",
                },
                "max_matches": {
                    "type": "integer",
                    "description": "최대 결과 건수 (기본 50)",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "대소문자 구분 여부 (기본 false)",
                },
            },
            "required": ["query"],
        },
    )

    return reg
