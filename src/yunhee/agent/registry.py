"""
yunhee-cli Agent Tool Registry
도구 등록, 스키마 변환(OpenAI Tool Schema) 및 실행 디스패치 관리.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yunhee.agent.knowledge import (
    save_knowledge,
    search_knowledge,
)
from yunhee.agent.memory import save_rule
from yunhee.agent.tools.core_exec import run_command
from yunhee.agent.tools.core_fs import (
    edit_file,
    find_files,
    grep_search,
    list_files,
    read_file,
    write_file,
)
from yunhee.agent.tools.db_sql import (
    execute_sql,
    get_db_definition,
    get_table_schema,
)
from yunhee.agent.tools.domain_helper import (
    lookup_config,
    read_recent_errors,
)
from yunhee.agent.tools.mcp_adapter import MCPManager
from yunhee.agent.tools.screen_scout import export_spec_tool


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
        self.mcp_manager: MCPManager | None = None

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


def create_default_registry(load_mcp: bool = True) -> ToolRegistry:
    """기본 Core 파일 시스템, 장기 기억, 도메인 헬퍼 및 MCP 도구가 등록된 ToolRegistry 인스턴스 생성."""
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

    # 8. save_rule (L1 메모리)
    reg.register(
        name="save_rule",
        func=save_rule,
        description="프로젝트 영구 코딩 컨벤션이나 핵심 규칙을 .yunhee/memory.md에 저장합니다 (최대 40줄 제한).",
        parameters={
            "type": "object",
            "properties": {
                "rule": {
                    "type": "string",
                    "description": "기억할 핵심 규칙 한 문장 (예: 'DTO는 항상 Java Record로 작성한다')",
                },
            },
            "required": ["rule"],
        },
    )

    # 9. save_knowledge (L2 시맨틱 지식)
    reg.register(
        name="save_knowledge",
        func=save_knowledge,
        description="에러 해결 노하우, 비즈니스 특이사항, 코드 포팅 팁 등 재사용 가능한 지식을 ChromaDB 벡터 스토어에 영구 저장합니다.",
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "지식의 핵심 요약 제목",
                },
                "content": {
                    "type": "string",
                    "description": "지식의 상세 내용 및 해결 방법",
                },
                "category": {
                    "type": "string",
                    "description": "지식 카테고리 (예: 'mybatis', 'react', 'api', 'db', 기본값 'general')",
                },
                "screen_id": {
                    "type": "string",
                    "description": "연관된 화면 코드(예: 'sys01', 생략 가능)",
                },
            },
            "required": ["title", "content"],
        },
    )

    # 10. search_knowledge (L2 시맨틱 지식)
    reg.register(
        name="search_knowledge",
        func=search_knowledge,
        description="과거에 축적된 지식 베이스(ChromaDB)에서 현재 작업과 유사한 노하우 및 해결 사례를 벡터 검색합니다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 질문 또는 키워드",
                },
                "limit": {
                    "type": "integer",
                    "description": "가져올 최대 지식 개수 (기본 3)",
                },
            },
            "required": ["query"],
        },
    )

    # 11. lookup_config (도메인 헬퍼)
    reg.register(
        name="lookup_config",
        func=lookup_config,
        description="yunhee의 현재 환경 설정(작업 폴더 WORK_DIR, ASIS 소스 폴더, DB 접속 정보, Ollama/ChromaDB 설정 등)을 확인합니다.",
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "조회할 특정 설정 키 (생략 시 전체 설정 요약)",
                },
            },
        },
    )

    # 12. read_recent_errors (도메인 헬퍼)
    reg.register(
        name="read_recent_errors",
        func=read_recent_errors,
        description="서버 로그에서 최근 발생한 WARN 및 ERROR 로그들을 요약하여 확인합니다.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "최대 에러 묶음 개수 (기본 5)",
                },
            },
        },
    )

    # 13. export_spec (마이그레이션 명세서 및 PDF 발간)
    reg.register(
        name="export_spec",
        func=export_spec_tool,
        description="화면 코드(예: 'sys01') 또는 마크다운 파일로부터 종합 기술 명세서를 마크다운 또는 Gotenberg PDF로 자동 발간합니다.",
        parameters={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "분석할 화면 코드(예: 'sys01', 'Ast01_Trade') 또는 마크다운 파일 경로",
                },
                "format": {
                    "type": "string",
                    "description": "발간 포맷: 'markdown' (기본값) 또는 'pdf'",
                },
            },
            "required": ["target"],
        },
    )

    # 14. run_sql (PostgreSQL 안전 조회)
    reg.register(
        name="run_sql",
        func=execute_sql,
        description="PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하여 테이블 목록, 컬럼 구조, 건수, 데이터를 조회합니다. (읽기 전용, DDL/임의COMMIT 차단)",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "실행할 SELECT SQL 쿼리문 (예: 'SELECT count(*) FROM information_schema.tables WHERE table_schema = \\'public\\'', 'SELECT * FROM sys01_company LIMIT 5')",
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 조회 행 수 (기본값 20)",
                },
            },
            "required": ["query"],
        },
    )

    # 15. get_db_definition (DB 객체 DDL / 함수 본체 소스 / 뷰 정의 조회)
    reg.register(
        name="get_db_definition",
        func=get_db_definition,
        description="PostgreSQL DB 객체(스토어드 함수/프로시저 소스 본체, 테이블 DBML DDL, 뷰 정의 등)의 전체 소스 코드 및 DDL을 조회합니다. 테이블 DDL뿐 아니라 DB 함수(f_..., fn_... 등)의 본체 소스코드를 확인할 때 최우선으로 호출하세요.",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "조회할 DB 객체 이름 (예: 'act02_journal_backup', 'f_ast_class_tree_nm', 'sys06_menu')",
                },
            },
            "required": ["name"],
        },
    )

    # 16. get_table_schema (하위 호환)
    reg.register(
        name="get_table_schema",
        func=get_table_schema,
        description="지정한 테이블 또는 DB 객체의 DDL 스키마를 조회합니다.",
        parameters={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "조회할 테이블 또는 DB 객체 이름 (예: 'sys06_menu', 'sys01_company')",
                },
            },
            "required": ["table_name"],
        },
    )

    # 17. MCP 도구 동적 로드 (mcp.json 존재 시)
    if load_mcp:
        try:
            mcp_mgr = MCPManager()
            if mcp_mgr.config_path.is_file():
                mcp_mgr.connect_all()
                mcp_mgr.register_tools_to_registry(reg)
                reg.mcp_manager = mcp_mgr
        except Exception:  # noqa: BLE001, S110
            pass

    return reg
