import os
import re
import sys
from pathlib import Path
from typing import Annotated

import typer

from yunhee import config, project
from yunhee.config import (
    ASIS_SRC_DIR,
    OLLAMA_MODEL,
    SCHEMA_ENV,
    WORK_DIR,
    YUNHEE_DIR,
    redact,
)
from yunhee.ollama_client import chat, embed
from yunhee.tools.as_is import find_as_is_dir
from yunhee.tools.as_is.dbml_indexer import index_dbml
from yunhee.tools.as_is.events import (
    extract_buttons,
    extract_events_and_methods,
    extract_grid_spec,
    get_source_label,
    render_events_markdown,
)
from yunhee.tools.as_is.sql_checker import check_sql
from yunhee.tools.as_is.src_indexer import index_src
from yunhee.tools.trace import register_trace_commands

app = typer.Typer(
    rich_markup_mode="rich",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"yunhee {project.current_version()}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = OLLAMA_MODEL,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="버전 출력"
    ),
):
    """[bold cyan]yunhee[/bold cyan]: AI 에이전트 토큰 절약용 로컬 CLI (무인자 실행: REPL `=chat-cmd`)

[bold yellow]🤖 AI Agent 권장 워크플로우 (상세: `yunhee agent-guide`)[/bold yellow]
  1. [bold green]코드 파악[/bold green]: [cyan]yunhee outline <경로>[/cyan] (시그니처·줄 번호 추출, 전체 읽기 금지)
  2. [bold green]DB 스키마[/bold green]: [cyan]yunhee table <패턴>[/cyan] (필요한 테이블 DBML만 추출)
  3. [bold green]빌드/테스트[/bold green]: [cyan]yunhee run "<명령>"[/cyan] (1줄 성공/에러 요약, 셸 직실행 금지)
  4. [bold green]API/로그[/bold green]: [cyan]yunhee api <METHOD> <경로> [--log] [--track <테이블>][/cyan] · [cyan]yunhee log trace|req|errors|tail[/cyan]
  5. [bold green]AS-IS 분석[/bold green]: [cyan]yunhee analysis screen|ui|method|sql|grid|callers <대상>[/cyan] · [cyan]yunhee page-style <화면>[/cyan]
  6. [bold green]미연결/원본변경[/bold green]: [cyan]yunhee trace-gap --stubs[/cyan] · [cyan]yunhee drift --all --base baseline[/cyan] · [cyan]yunhee sql-check --new-since-index[/cyan]
  7. [bold green]설정/이력[/bold green]: [cyan]yunhee config[/cyan] · [cyan]yunhee changelog --since <버전>[/cyan]
"""
    if ctx.invoked_subcommand is None:
        from yunhee.ui.repl import run_repl
        run_repl(model=model)


@app.command(hidden=True)
def chat_cmd(model: str = OLLAMA_MODEL):
    """대화형 REPL 시작 (명시적으로)"""
    from yunhee.ui.repl import run_repl
    run_repl(model=model)


@app.command(hidden=True)
def hello():
    """스캐폴드 동작 확인용"""
    print("yunhee-cli ready")


@app.command(name="intro", help="yunhee 에이전트 자기소개")
@app.command(name="about", hidden=True)
@app.command(name="자기소개", hidden=True)
@app.command(name="자기소개?", hidden=True)
def intro_cmd():
    """yunhee 에이전트 자기소개 및 전문 영역 안내"""
    from rich.console import Console
    from rich.markdown import Markdown

    from yunhee.intro import get_intro_text

    Console().print(Markdown(get_intro_text()))


@app.command(name="init")
def init_cmd():
    """현재 작업 디렉터리를 yunhee 프로젝트로 등록 및 필수 폴더/파일 초기화"""
    from yunhee import project

    data = project.init()
    pdir = Path(data.get("project_dir", project.PROJECT_DIR))
    typer.secho(f"✔ yunhee 프로젝트 등록 완료: {pdir}", fg=typer.colors.GREEN)
    typer.echo(f"  • 이름: {data['name']}")
    typer.echo(f"  • 버전: {data['yunhee_version']}")
    typer.echo("  • 생성된 파일 및 디렉터리:")
    typer.echo(f"    - project.json: {pdir / 'project.json'}")
    if data.get("mcp_created"):
        typer.echo(f"    - mcp.json: {pdir / 'mcp.json'}")
    if data.get("memory_created"):
        typer.echo(f"    - memory.md: {pdir / 'memory.md'}")
    typer.echo(f"    - sessions/: {pdir / 'sessions'}")
    typer.echo(f"    - runs/: {pdir / 'runs'}")
    if data.get("gitignore_created"):
        typer.echo(f"    - .gitignore: {pdir / '.gitignore'}")


def _run_single_agent_query(prompt: str, model: str = OLLAMA_MODEL) -> None:
    """단발성 자율 에이전트(AgentLoop) 질의 실행."""
    from rich.console import Console
    from rich.markdown import Markdown

    from yunhee.agent import AgentLoop
    from yunhee.ui.components import format_tool_call_status, format_tool_result_preview

    console = Console()
    loop = AgentLoop(model=model)

    with console.status(
        "[bold cyan]yunhee 에이전트가 생각 중입니다...[/bold cyan]",
        spinner="dots",
    ) as status:

        def on_tool_call(name: str, args: dict) -> None:
            status.update(format_tool_call_status(name, args))

        def on_tool_result(name: str, result: str) -> None:
            status.update("[bold cyan]도구 결과 분석 및 답변 정리 중...[/bold cyan]")
            console.print(format_tool_result_preview(name, result))

        response, _ = loop.run(
            prompt,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )

    console.print("\n[bold green]yunhee>[/bold green]")
    console.print(Markdown(response))


@app.command()
def ask(
    prompt: str,
    model: str = OLLAMA_MODEL,
    agent: Annotated[
        bool,
        typer.Option("--agent", "-a", help="도구 호출(execute_python 등)을 포함한 에이전트 모드로 실행"),
    ] = False,
):
    """로컬 LLM(qwen2.5-coder) 단발 질의 (--agent/-a 지정 시 도구 사용 자율 에이전트 모드)"""
    if agent:
        _run_single_agent_query(prompt, model=model)
        return
    print(chat(prompt, model=model))


@app.command(name="agent")
def agent_cmd(
    prompt: Annotated[
        str,
        typer.Argument(help="에이전트에게 요청할 자연어 질문 (예: \"제목이 '계정과목'인 모달 찾아줘\")"),
    ],
    model: str = OLLAMA_MODEL,
):
    """로컬 LLM 자율 에이전트 단발 실행 (Python 스크립트 생성·실행 및 도구 활용)"""
    _run_single_agent_query(prompt, model=model)


@app.command(name="rag-index")
def rag_index_cmd(
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 프로젝트 루트 경로 (생략 시 YUNHEE_TOBE_SRC_DIR 또는 WORK_DIR)"),
    ] = None,
    no_vector: Annotated[
        bool,
        typer.Option("--no-vector", help="ChromaDB 임베딩을 건너뛰고 카탈로그 스냅샷(.yunhee/tobe_catalog.json)과 docs/to-be/만 생성"),
    ] = False,
    reset: Annotated[
        bool,
        typer.Option("--reset", help="ChromaDB yunhee_tobe_kb 컬렉션과 스냅샷을 완전히 삭제한 뒤 처음부터 재학습"),
    ] = False,
    reset_all: Annotated[
        bool,
        typer.Option("--reset-all", help="수동 노하우 컬렉션(yunhee_knowledge)까지 포함해 모두 삭제 후 재학습"),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="결과를 JSON으로 출력"),
    ] = False,
):
    """TOBE 프로젝트 전체(화면·메뉴·컴포넌트·그리드·모달·API·백엔드)를 스냅샷 및 ChromaDB에 증분 학습"""
    import json as _json

    from yunhee.tools.trace.tobe_rag import rag_index

    res = rag_index(tobe=tobe, no_vector=no_vector, reset=reset, reset_all=reset_all)
    if as_json:
        print(_json.dumps(res, ensure_ascii=False, indent=2))
        return

    mode_str = "완전 초기화 후 재학습" if (reset or reset_all) else "증분 학습"
    typer.secho(f"✔ TOBE RAG {mode_str} 완료 ({res['elapsed_sec']}s)", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  • 대상 프로젝트 : {res['tobe_root']}")
    typer.echo(f"  • 카탈로그 파일 : {res['snapshot_path']}")
    typer.echo(f"  • 마크다운 문서 : {res['docs_dir']}")
    typer.echo(f"  • 스캔 화면 수  : {res['screen_count']}개 (메뉴 매핑: {res['migrated_menu_count']}/{res['menu_count']}개 변환)")
    if no_vector:
        typer.echo("  • 벡터 임베딩   : 건너뜀 (--no-vector)")
    elif res.get("vector_error"):
        typer.secho(f"  ⚠ ChromaDB 임베딩 오류: {res['vector_error']}", fg=typer.colors.YELLOW)
    else:
        typer.echo(
            f"  • ChromaDB 벡터 : 총 {res['vector_total']}건 "
            f"(신규/변경 upsert: {res['upserted']}, 변경없음 skip: {res['skipped']}, 삭제: {res['deleted']})"
        )


@app.command(name="rag-reset")
def rag_reset_cmd(
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 프로젝트 루트 경로"),
    ] = None,
    all_collections: Annotated[
        bool,
        typer.Option("--all", help="수동 노하우 컬렉션(yunhee_knowledge)까지 함께 삭제"),
    ] = False,
    no_reindex: Annotated[
        bool,
        typer.Option("--no-reindex", help="초기화(삭제)만 수행하고 재학습은 생략"),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="결과를 JSON으로 출력"),
    ] = False,
):
    """TOBE RAG 학습 데이터(ChromaDB 벡터 컬렉션 및 스냅샷)를 완전히 초기화하고 처음부터 재학습"""
    import json as _json

    from yunhee.tools.trace.tobe_rag import rag_reset

    res = rag_reset(tobe=tobe, reset_all=all_collections, reindex=not no_reindex)
    if as_json:
        print(_json.dumps(res, ensure_ascii=False, indent=2))
        return

    typer.secho("✔ TOBE RAG 초기화 완료", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  • 대상 프로젝트: {res['tobe_root']}")
    if not no_reindex:
        typer.echo(
            f"  • 재학습 결과  : 화면 {res['screen_count']}개, "
            f"ChromaDB 벡터 {res['vector_total']}건 적재 ({res['elapsed_sec']}s)"
        )


@app.command(name="rag-status")
def rag_status_cmd(
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 프로젝트 루트 경로"),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="결과를 JSON으로 출력"),
    ] = False,
):
    """현재 TOBE RAG 학습 상태(스냅샷·ChromaDB 벡터 건수) 및 미반영 변경 파일(Stale) 점검"""
    import json as _json

    from yunhee.tools.trace.tobe_rag import rag_status

    st = rag_status(tobe=tobe)
    if as_json:
        print(_json.dumps(st, ensure_ascii=False, indent=2))
        return

    typer.secho("📊 TOBE RAG 학습 상태", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  • 대상 프로젝트 : {st['tobe_root']}")
    typer.echo(f"  • 스냅샷 경로   : {st['snapshot_path']} ({'존재' if st['snapshot_exists'] else '없음 — yunhee rag-index 실행 필요'})")
    if st["indexed_at"]:
        typer.echo(f"  • 마지막 학습   : {st['indexed_at']}")
    typer.echo(
        f"  • 화면 카탈로그 : 인덱싱 {st['indexed_screen_count']}개 / 현재 디스크 TSX {st['disk_tsx_count']}개 "
        f"(메뉴 변환: {st['migrated_menu_count']}/{st['menu_count']})"
    )
    if st["chroma_ok"]:
        typer.echo(
            f"  • ChromaDB 벡터 : TOBE 자동학습({st['tobe_vector_count']}건), 수동 노하우({st['manual_vector_count']}건)"
        )
    else:
        typer.secho(f"  ⚠ ChromaDB 연결 실패: {st['chroma_error']}", fg=typer.colors.YELLOW)

    if not st["snapshot_exists"]:
        typer.secho("  👉 아직 학습된 스냅샷이 없습니다. 'yunhee rag-index'를 실행하세요.", fg=typer.colors.YELLOW)
    elif st["stale_count"] > 0:
        typer.secho(
            f"  ⚠ 마지막 학습 이후 변경된 파일 {st['stale_count']}건 감지 "
            f"(추가 {len(st['added_files'])}, 수정 {len(st['modified_files'])}, 삭제 {len(st['deleted_files'])}) "
            "— 'yunhee rag-index'로 증분 갱신을 권장합니다.",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho("  ✔ 모든 TOBE 화면 파일이 최신 학습 상태입니다.", fg=typer.colors.GREEN)


@app.command(name="rag-search")
def rag_search_cmd(
    query: Annotated[
        str,
        typer.Argument(help="검색할 화면번호(예: 1002), 메뉴명, 컴포넌트명, 또는 자연어 질문"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="최대 검색 결과 수"),
    ] = 5,
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 프로젝트 루트 경로"),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="결과를 JSON으로 출력"),
    ] = False,
):
    """학습된 TOBE 카탈로그(결정적 매칭) 및 ChromaDB 벡터에서 에이전트가 소환할 지식 카드 조회"""
    import json as _json

    from yunhee.tools.trace.tobe_rag import lookup_tobe, rag_search

    if as_json:
        print(_json.dumps(rag_search(query, limit=limit, tobe=tobe), ensure_ascii=False, indent=2))
        return
    print(lookup_tobe(query, tobe=tobe))


@app.command()
def vec(text: str):
    """bge-m3 임베딩 벡터 확인"""
    vector = embed(text)
    print(f"dim={len(vector)}")
    print(vector[:5], "...")


@app.command()
def index(text: str):
    """텍스트를 ChromaDB에 저장"""
    from yunhee.store.vectorstore import add_texts
    add_texts([text])
    print("indexed.")


@app.command()
def search(query_text: str, n: int = 3):
    """ChromaDB 유사 텍스트 검색"""
    from yunhee.store.vectorstore import search as vector_search
    results = vector_search(query_text, n_results=n)
    docs = results["documents"][0]
    dists = results["distances"][0]
    for doc, dist in zip(docs, dists):
        print(f"[{dist:.4f}] {doc}")


@app.command(name="config")
def config_cmd():
    """현재 설정(Source/Target 경로, 브랜치, DB, API) 확인"""
    from rich.console import Console
    from rich.table import Table

    from yunhee import config
    from yunhee.tools.as_is.drift import check_commit_mismatch_warning

    mismatch_warn = check_commit_mismatch_warning(config.ASIS_SRC_DIR, find_as_is_dir("src"))
    if mismatch_warn:
        typer.secho(mismatch_warn, fg=typer.colors.YELLOW)

    table = Table(title="yunhee 설정 정보")
    table.add_column("항목", style="cyan", no_wrap=True)
    table.add_column("현재 설정값", style="green")
    table.add_column("설명 및 변경 방법", style="dim")

    cfg = config.summary()
    table.add_row("Target (Work Dir)", cfg["work-dir"], "현재 터미널 작업 디렉터리 (cd로 이동하여 변경)")
    table.add_row("Target (TOBE)", cfg["tobe-src"], "설정 파일의 YUNHEE_TOBE_SRC_DIR (미지정 시 Work Dir)")
    table.add_row("타겟 브랜치", cfg["tobe-branch"], "TOBE 원격 추적 브랜치 대비 상태 (읽기 전용)")
    table.add_row("Source (ASIS)", cfg["asis-src"], "설정 파일의 YUNHEE_ASIS_SRC_DIR")
    table.add_row("소스 브랜치", cfg["asis-branch"], "원격 추적 브랜치(origin/<branch>) 대비 상태 (읽기 전용)")
    table.add_row("Yunhee DB", cfg.get("yunhee-db", cfg["local-db"]), "설정 파일(.env.yunhee)의 YUNHEE_DB")
    table.add_row("Local DB (호환)", cfg["local-db"], "YUNHEE_DB 하위 호환 별칭")
    table.add_row("Schema Snapshot", cfg["schema-env"], "설정 파일의 YUNHEE_SCHEMA_ENV")
    table.add_row("Yunhee Home", cfg["yunhee-dir"], "yunhee-cli 설치 경로")
    table.add_row("Env File", cfg["env-file"], "설정 파일 (.env.yunhee / .env.local)")
    table.add_row("Ollama URL", cfg["ollama-url"], ".env.local의 YUNHEE_OLLAMA_URL")
    table.add_row("Ollama Model", cfg["ollama-model"], ".env.local의 YUNHEE_OLLAMA_MODEL")
    table.add_row("API Base URL", cfg["api-base"], ".env.local의 YUNHEE_API_BASE_URL")
    table.add_row("API Login Path", cfg["api-login-path"], ".env.local의 YUNHEE_API_LOGIN_PATH")
    table.add_row("API Admin User", cfg["test-admin-user"], ".env.local의 YUNHEE_TEST_ADMIN_USER")
    table.add_row("API Company", cfg["test-company"], ".env.local의 YUNHEE_TEST_COMPANY")
    table.add_row("API Tenant Host", cfg["api-tenant-host"], ".env.local의 YUNHEE_API_TENANT_HOST")
    table.add_row("Log Docker", cfg.get("log-docker", config.LOG_DOCKER), "설정 파일(.env.yunhee)의 YUNHEE_LOG_DOCKER")
    table.add_row("Log Dir", cfg.get("log-dir", config.LOG_DIR), "설정 파일(.env.yunhee)의 YUNHEE_LOG_DIR")

    console = Console(width=200)
    console.print(table)
    typer.echo(f"ASIS 브랜치: {cfg['asis-branch']} | TOBE 브랜치: {cfg['tobe-branch']}")


@app.command(name="value")
def value_cmd(
    key: Annotated[
        str | None,
        typer.Argument(
            help="조회할 설정 키 (예: YUNHEE_ASIS_SRC_DIR, asis-src, LOCAL_DB). 생략 시 전체 키 목록 출력",
        ),
    ] = None,
    list_keys: Annotated[
        bool,
        typer.Option("--list", "-l", help="사용 가능한 설정 키 목록 및 현재 값 테이블 출력"),
    ] = False,
    only_keys: Annotated[
        bool,
        typer.Option("--keys", "-k", help="설정 키 이름만 한 줄씩 출력 (스크립트/자동완성용)"),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option("--raw", help="비밀번호나 DB URL을 마스킹하지 않고 실제 값 출력 (단일 키 조회 시 기본 true)"),
    ] = True,
):
    """현재 설정값 조회 (단일 키 조회 또는 전체 설정 키 목록 표시)"""
    from rich.console import Console
    from rich.table import Table

    from yunhee import config

    # 1. --keys 플래그: 키 이름만 한 줄씩 출력
    if only_keys:
        for item in config.get_config_items():
            typer.echo(item.key)
        return

    # 2. 키가 주어지지 않았거나 --list 플래그인 경우: 전체 목록 테이블 출력
    if key is None or list_keys:
        table = Table(title="yunhee 설정 키 목록")
        table.add_column("설정 키 (환경변수)", style="cyan bold", no_wrap=True)
        table.add_column("별칭", style="dim")
        table.add_column("현재 설정값", style="green", overflow="fold")
        table.add_column("설명", style="white")

        for item in config.get_config_items():
            val_display = item.get_value(raw=False)
            if not val_display:
                val_display = "[dim](not set)[/dim]"
            aliases_str = ", ".join(item.aliases)
            table.add_row(item.key, aliases_str, val_display, item.description)

        console = Console()
        console.print(table)
        console.print("\n[bold]사용법:[/bold]")
        console.print("  yunhee value <KEY>          설정값을 단일 텍스트로 출력 (스크립트/치환용)")
        console.print("  yunhee value --list (-l)    전체 설정 키 목록 및 현재 값 테이블 출력")
        console.print("  yunhee value --keys (-k)    설정 키 이름만 한 줄씩 출력")
        console.print("\n[dim]예시:[/dim]")
        console.print("  yunhee value YUNHEE_ASIS_SRC_DIR")
        console.print("  yunhee value asis-src")
        console.print("  export ASIS_DIR=$(yunhee value asis-src)")
        return

    # 3. 특정 키 조회
    val = config.get_config_value(key, raw=raw)
    if val is None:
        typer.secho(f"오류: 알 수 없는 설정 키입니다: '{key}'", fg=typer.colors.RED, err=True)
        typer.secho(
            "사용 가능한 키 목록을 확인하려면 'yunhee value' 또는 'yunhee value --list'를 실행하세요.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(val)



_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _make_dbml(
    env_name: str,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="출력 파일 (기본: <ENV_NAME>-dbml.md)")
    ] = None,
    schema: Annotated[
        list[str] | None,
        typer.Option("--schema", help="대상 스키마 (여러 번 지정 가능, 기본: 시스템 스키마 제외 전체)"),
    ] = None,
):
    """(=dbml) DB 스키마를 DBML 마크다운·스냅샷으로 저장"""
    from yunhee.dbml import counts, render_markdown
    from yunhee.tools.pg_schema import fetch_schema
    from yunhee.tools.schema_snapshot import save_snapshot

    if not _ENV_NAME_RE.match(env_name):
        print(f"오류: 환경변수 이름이 올바르지 않습니다: {env_name}")
        raise typer.Exit(code=1)

    dsn = os.getenv(env_name)
    if not dsn:
        print(f"오류: 환경변수 {env_name}가 설정되어 있지 않습니다 (.env.local 확인).")
        raise typer.Exit(code=1)
    if not dsn.startswith(("postgresql://", "postgres://")):
        print(f"오류: {env_name}가 PostgreSQL 접속 URL이 아닙니다: {redact(dsn)}")
        raise typer.Exit(code=1)

    result = fetch_schema(dsn, schemas=schema or None)
    if not result.ok:
        print(f"오류: {result.error}")
        raise typer.Exit(code=1)

    if output:
        out_file = output
    elif (WORK_DIR / ".yunhee").is_dir():
        out_file = WORK_DIR / ".yunhee" / f"{env_name}-dbml.md"
    else:
        out_file = WORK_DIR / f"{env_name}-dbml.md"

    out_file.write_text(render_markdown(result.data, source=env_name, source_url=redact(dsn)))
    summary = ", ".join(f"{k} {v}" for k, v in counts(result.data).items() if v)
    print(f"저장됨: {out_file} ({summary or '객체 없음'})")
    print(f"스냅샷: {save_snapshot(env_name, result.data)} ('yunhee table'/'prepare'가 사용)")


app.command(name="make-dbml")(_make_dbml)
app.command(name="dbml", hidden=True)(_make_dbml)


@app.command()
def table(
    names: Annotated[list[str] | None, typer.Argument(help="테이블 이름 (schema.table, glob * ? 가능)")] = None,
    page: Annotated[str | None, typer.Option("--page", help="ASIS 페이지 코드 — mapper가 참조하는 테이블 전부")] = None,
    db: Annotated[str, typer.Option("--db", help="스키마 스냅샷 (make-dbml의 환경변수 이름)")] = SCHEMA_ENV,
):
    """스키마 스냅샷에서 지정 테이블 DBML 출력

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  전체 DDL 파일을 검색하거나 DB에 임의 조회하지 마세요. 필요한 테이블 DBML만 이 명령으로 추출해 사용하세요.
"""
    from yunhee.tools.page_schema import page_tables
    from yunhee.tools.schema_snapshot import load_snapshot, slice_tables

    patterns = list(names or [])
    if page:
        found = page_tables(page)
        if not found.ok:
            print(f"오류: {found.error}")
            raise typer.Exit(code=1)
        patterns += found.data
    if not patterns:
        print("오류: 테이블 이름 또는 --page를 지정하세요.")
        raise typer.Exit(code=1)

    snapshot = load_snapshot(db)
    if not snapshot.ok:
        print(f"오류: {snapshot.error}")
        raise typer.Exit(code=1)

    result = slice_tables(snapshot.data, patterns)
    info = result.data
    if info["dbml"]:
        print(info["dbml"])
    # 안내는 stderr로 — stdout은 DBML만 남겨서 파이프/리다이렉트로 그대로 쓸 수 있게
    if info["omitted"]:
        typer.echo(f"// 예산 초과로 제외: {', '.join(info['omitted'])}", err=True)
    if info["missing"]:
        typer.echo(f"// 스냅샷에 없음: {', '.join(info['missing'])}", err=True)
    if not info["tables"]:
        raise typer.Exit(code=1)


def _get_project_name(root: Path | None = None) -> str:
    eff_root = root or project.find_project_root()
    proj_data = project.load(eff_root)
    if proj_data and proj_data.get("name"):
        return proj_data["name"]
    return eff_root.name


def _run_exec(
    command: Annotated[str, typer.Argument(help="실행할 셸 명령어")],
    cwd: Annotated[Path | None, typer.Option("-C", "--cwd", help="명령어를 실행할 작업 디렉터리")] = None,
    timeout: Annotated[int, typer.Option("--timeout", "-t", help="타임아웃(초)")] = 120,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="실패 시 로컬 Qwen 요약을 건너뜀")] = False,
    raw: Annotated[bool, typer.Option("--raw", help="요약 없이 원시 출력을 그대로 출력")] = False,
    health: Annotated[bool, typer.Option("--health/--no-health", help="배포 명령 실행 후 기동 완료/실패 자동 헬스체크")] = True,
    health_timeout: Annotated[int, typer.Option("--health-timeout", help="헬스체크 최대 대기 시간(초)")] = 90,
):
    """(=exec) 외부 명령 실행·로그 격리 및 에러 압축 리포트

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  mvn, gradle, npm, pytest 등을 직접 실행하지 마세요. 수천 줄의 빌드 로그 대신 이 명령으로 Qwen의 10~20줄 핵심 에러 요약만 받아 디버깅하세요.
"""
    from yunhee.context.run_analyzer import summarize_run
    from yunhee.store import run_tracker
    from yunhee.tools.runner import execute_command

    target_cwd = None
    if cwd is not None:
        target_cwd = (Path.cwd() / cwd).resolve()
    else:
        toml_cwd = config.TOML_CONFIG.get("run", {}).get("cwd")
        if toml_cwd:
            target_cwd = (Path.cwd() / toml_cwd).resolve()
        else:
            target_cwd = Path.cwd().resolve()

    if not target_cwd.is_dir():
        typer.echo("실행 전 오류: 디렉터리 없음", err=True)
        raise typer.Exit(code=1)

    print(f"cwd: {target_cwd}")

    project_root = project.find_project_root(target_cwd)
    result = execute_command(command, cwd=target_cwd, timeout=timeout)
    data = result.data
    project_name = _get_project_name(project_root)

    if raw:
        if data["stdout"]:
            print(data["stdout"], end="" if data["stdout"].endswith("\n") else "\n")
        if data["stderr"]:
            typer.echo(data["stderr"], err=True)
        summary = None
    else:
        summary = summarize_run(
            command=data["command"],
            exit_code=data["exit_code"],
            duration_ms=data["duration_ms"],
            log_path=data["log_path"],
            stdout=data["stdout"],
            stderr=data["stderr"],
            use_llm=not no_llm,
            cwd=target_cwd,
            start_time=data.get("start_time"),
        )
        print(summary)

    # 배포 명령 후 자동 헬스체크 (기동 성공/실패 감지)
    import re
    cmd_lower = command.lower()
    deploy_cmds = config.TOML_CONFIG.get("run", {}).get("deploy_cmds", [])
    is_deploy = "deploy" in cmd_lower or any(re.search(rf"\b{re.escape(dc)}\b", cmd_lower) for dc in deploy_cmds)

    if health and is_deploy and data["exit_code"] == 0:
        from datetime import UTC, datetime, timedelta

        from yunhee.tools.log_reader import wait_for_deploy_health

        start_ts = data.get("start_time")
        if start_ts:
            dep_start_utc = datetime.fromtimestamp(start_ts, tz=UTC)
        else:
            dep_start_utc = datetime.now(UTC) - timedelta(milliseconds=data.get("duration_ms") or 0)

        h_status, h_text = wait_for_deploy_health(
            deploy_start_dt_utc=dep_start_utc,
            timeout=health_timeout,
        )

        if h_status == "success":
            h_line = f"✅ {h_text}"
            print(h_line)
            if summary:
                summary = f"{summary}\n{h_line}"
            else:
                summary = h_line
        elif h_status == "failure":
            orig_code = data["exit_code"]
            data["exit_code"] = 1
            h_line = f"❌ 앱 기동 실패: {h_text} (원 exit: {orig_code})"
            print(h_line)
            if summary:
                summary = f"{summary}\n{h_line}"
            else:
                summary = h_line
        elif h_status == "timeout":
            h_line = f"⚠ {h_text}"
            print(h_line)
            if summary:
                summary = f"{summary}\n{h_line}"
            else:
                summary = h_line

    start_iso = data.get("created_at")
    if not start_iso:
        from datetime import UTC, datetime, timedelta
        if data.get("start_time"):
            start_iso = datetime.fromtimestamp(data["start_time"], tz=UTC).isoformat()
        else:
            now_dt = datetime.now(UTC)
            dur_ms = data.get("duration_ms") or 0
            start_iso = (now_dt - timedelta(milliseconds=dur_ms)).isoformat()

    run_tracker.save_run(
        run_id=data["run_id"],
        project=project_name,
        command=data["command"],
        exit_code=data["exit_code"],
        duration_ms=data["duration_ms"],
        log_path=data["log_path"],
        summary=summary,
        created_at=start_iso,
        cwd=data.get("cwd"),
    )

    if data["exit_code"] != 0:
        raise typer.Exit(code=data["exit_code"] if 0 <= data["exit_code"] <= 255 else 1)


app.command(name="run")(_run_exec)
app.command(name="exec", hidden=True)(_run_exec)


@app.command(name="last-run")
def last_run():
    """직전 실행 결과·요약 확인 (전체 이력 표: `yunhee runs`)"""
    from yunhee.store import run_tracker

    project_root = project.find_project_root()
    project_name = _get_project_name(project_root)
    last = run_tracker.get_last_run(project_name)
    if not last:
        print(f"프로젝트 '{project_name}'의 실행 이력이 없습니다.")
        return

    if last.get("summary"):
        print(last["summary"])
    else:
        status_icon = "✅" if last["exit_code"] == 0 else "❌"
        duration_sec = f"{last['duration_ms'] / 1000:.2f}s"
        cwd_info = f" (cwd: {last['cwd']})" if last.get("cwd") else ""
        print(f"{status_icon} Exit Code: {last['exit_code']} ({duration_sec}){cwd_info}")
        print(f"Command: {last['command']}")
        print(f"Log: {last['log_path']}")
        print(f"Created: {last['created_at']}")


@app.command(name="runs", hidden=True)
def list_runs_cmd(
    limit: Annotated[int, typer.Option("--limit", "-n", help="표시할 최근 실행 수")] = 10,
):
    """최근 실행 이력을 표 형태로 출력"""
    from rich.console import Console
    from rich.table import Table

    from yunhee.store import run_tracker

    project_root = project.find_project_root()
    project_name = _get_project_name(project_root)
    records = run_tracker.list_runs(project_name, limit=limit)
    if not records:
        print(f"프로젝트 '{project_name}'의 실행 이력이 없습니다.")
        return

    table = Table(title=f"실행 이력 (Project: {project_name})")
    table.add_column("Run ID", style="dim", no_wrap=True)
    table.add_column("Command", style="cyan")
    table.add_column("Exit", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("CWD", style="yellow", no_wrap=True)
    table.add_column("Created At", style="dim", no_wrap=True)
    table.add_column("Log Path", style="magenta")

    for r in records:
        exit_style = "green" if r["exit_code"] == 0 else "red"
        duration_str = f"{r['duration_ms'] / 1000:.2f}s"
        table.add_row(
            r["id"],
            r["command"],
            f"[{exit_style}]{r['exit_code']}[/{exit_style}]",
            duration_str,
            r.get("cwd") or ".",
            r["created_at"][:19].replace("T", " "),
            r["log_path"],
        )

    console = Console(width=200)
    console.print(table)


@app.command()
def outline(
    paths: Annotated[list[str], typer.Argument(help="분석할 파일 또는 디렉터리 경로 (하나 이상)")],
    limit: Annotated[int, typer.Option("--limit", help="최대 글자 수 제한")] = 30000,
    members: Annotated[bool, typer.Option("--members", "-m", help="interface/type의 필드(멤버) 목록 표시")] = False,
    symbol: Annotated[str | None, typer.Option("--symbol", "-s", help="특정 symbol(interface/type/함수 등)만 추출")] = None,
    tail: Annotated[int | None, typer.Option("--tail", help="파일 마지막 N줄 원문 함께 출력")] = None,
    range_spec: Annotated[str | None, typer.Option("--range", "-r", help="출력할 줄 번호 범위 (예: L1-60, 1-60)")] = None,
):
    """소스 파일·디렉터리의 클래스·메서드 시그니처와 줄 번호 추출

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  TOBE 기존 코드(Service, Controller, Mapper XML 등) 전체를 읽지 마세요. 이 명령으로 메서드 위치와 줄 번호를 파악한 뒤 필요한 줄만 핀포인트로 읽으세요.
"""
    from yunhee.tools.outliner import outline_path, read_file_range

    combined_outputs = []
    remaining_limit = limit

    for p in paths:
        if remaining_limit <= 0:
            combined_outputs.append("// ... [글자 수 예산 초과로 이하 생략]")
            break
        p_obj = Path(p)
        if not p_obj.exists():
            if (config.WORK_DIR / p).exists():
                p_obj = config.WORK_DIR / p
            elif getattr(config, "TOBE_SRC_DIR", None) and (config.TOBE_SRC_DIR / p).exists():
                p_obj = config.TOBE_SRC_DIR / p
            elif getattr(config, "ASIS_SRC_DIR", None) and (config.ASIS_SRC_DIR / p).exists():
                p_obj = config.ASIS_SRC_DIR / p

        if range_spec and p_obj.is_file():
            try:
                r_lines = read_file_range(p_obj, range_str=range_spec)
                out_text = f"// {p_obj} ({range_spec})\n" + "\n".join(f"{num:4d} | {l}" for num, l in r_lines)
                combined_outputs.append(out_text)
                remaining_limit -= len(out_text)
                continue
            except Exception as e:  # noqa: BLE001
                typer.echo(f"오류: {e}", err=True)
                raise typer.Exit(code=1)
        res = outline_path(p_obj if p_obj.exists() else p, char_limit=remaining_limit, members=members, symbol=symbol, tail=tail)
        if not res.ok:
            typer.echo(f"오류: {res.error}", err=True)
            raise typer.Exit(code=1)
        out_text = res.data or ""
        combined_outputs.append(out_text)
        remaining_limit -= len(out_text)

    print("\n\n".join(combined_outputs))


@app.command(name="cat")
def cat_cmd(
    specs: Annotated[list[str], typer.Argument(help="출력할 파일과 줄 범위 목록 (예: a.java:1-30 b.xml:100-140 또는 a.java)")],
    head: Annotated[int | None, typer.Option("--head", help="범위(또는 파일) 앞 N줄만 출력")] = None,
    tail: Annotated[int | None, typer.Option("--tail", help="범위(또는 파일) 뒤 N줄만 출력")] = None,
    no_number: Annotated[bool, typer.Option("--no-number", help="줄 번호 생략")] = False,
):
    """지정한 파일들의 줄 범위를 핀포인트 출력 (외부 훅 차단 방지용 안전 읽기)"""
    from yunhee.tools.outliner import read_file_range_with_meta, resolve_read_target

    if head is not None and tail is not None:
        typer.echo("오류: --head와 --tail은 동시에 지정할 수 없습니다.", err=True)
        raise typer.Exit(code=1)

    out_sections = []
    for spec in specs:
        range_str = None
        m = re.search(r":([Ll]?\d+(?:[-:,]\d+)?)$", spec)
        if m:
            file_part = spec[: m.start()]
            range_str = m.group(1)
        else:
            file_part = spec

        p, err = resolve_read_target(file_part)
        if err or p is None or not p.is_file():
            typer.echo(f"오류: {err or f'파일을 찾을 수 없습니다: {file_part}'}", err=True)
            raise typer.Exit(code=1)

        try:
            lines, omitted = read_file_range_with_meta(p, range_str=range_str, head=head, tail=tail)
        except Exception as e:  # noqa: BLE001
            typer.echo(f"오류: {p} 읽기 실패: {e}", err=True)
            raise typer.Exit(code=1)

        header = f"==> {p} "
        if lines:
            header += f"(L{lines[0][0]}-{lines[-1][0]}) <=="
        else:
            header += "<=="

        body_lines = []
        for lnum, ltext in lines:
            if no_number:
                body_lines.append(ltext)
            else:
                body_lines.append(f"{lnum:4d} | {ltext}")
        if omitted > 0:
            body_lines.append(f"… {omitted}줄 더 있음 — 범위를 좁히세요")
        section = header + ("\n" + "\n".join(body_lines) if body_lines else "")
        out_sections.append(section)

    print("\n\n".join(out_sections))


@app.command(name="grep")
def grep_cmd(
    pattern: Annotated[str, typer.Argument(help="검색할 정규식(ERE) 또는 고정 문자열(-F)")],
    paths: Annotated[list[str], typer.Argument(help="검색할 파일 또는 폴더 경로 (하나 이상)")],
    context: Annotated[int, typer.Option("-C", "--context", help="일치 줄 앞뒤 문맥 줄 수 (상한 10)")] = 0,
    after: Annotated[int | None, typer.Option("-A", "--after-context", help="일치 줄 뒤 문맥 줄 수 (상한 20)")] = None,
    before: Annotated[int | None, typer.Option("-B", "--before-context", help="일치 줄 앞 문맥 줄 수 (상한 20)")] = None,
    max_matches: Annotated[int, typer.Option("--max", "-m", help="최대 일치 건수 (기본 20)")] = 20,
    fixed_strings: Annotated[bool, typer.Option("-F", "--fixed-strings", help="정규식 대신 고정 문자열 검색")] = False,
    ignore_case: Annotated[bool, typer.Option("-i", "--ignore-case", help="대소문자 무시")] = False,
    files_with_matches: Annotated[bool, typer.Option("-l", "--files-with-matches", help="일치 내용 대신 일치 파일 목록만 출력")] = False,
):
    """문맥 출력 전용 안전 grep (출력 상한 80줄, 파일:줄: 내용 형식)"""
    from yunhee.tools.outliner import grep_files

    res = grep_files(
        pattern=pattern,
        paths=paths,
        context=context,
        after=after,
        before=before,
        max_matches=max_matches,
        fixed_strings=fixed_strings,
        ignore_case=ignore_case,
        files_with_matches=files_with_matches,
    )
    if not res.ok:
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=1)
    if res.data:
        print(res.data)


TENANT_REQUIRED_MSG = (
    "오류: 회사 선택 로그인(-c)은 admin 테넌트에서만 됩니다: -t admin "
    "(또는 .yunhee.toml [api] tenant / .env.local YUNHEE_API_DEFAULT_TENANT)"
)


@app.command()
def api(
    method: Annotated[str, typer.Argument(help="HTTP 메서드 (GET, POST, PUT, DELETE)")],
    path: Annotated[str, typer.Argument(help="호출할 API 경로 (예: /api/v1/sys/roles)")],
    as_role: Annotated[str, typer.Option("--as", "-u", help="로그인 계정/역할 (사원 ID, 로그인 ID, admin)")] = "admin",
    base: Annotated[str | None, typer.Option("--base", help="기본 URL")] = None,
    login_path: Annotated[str | None, typer.Option("--login-path", help="로그인 엔드포인트 경로 (기본: .env.local의 YUNHEE_API_LOGIN_PATH 또는 /api/auth/login)")] = None,
    company: Annotated[str | None, typer.Option("--company", "-c", help="로그인 시 전달할 회사 코드 (예: admin, kfstest — 회사 ID가 아님)")] = None,
    tenant: Annotated[str | None, typer.Option("--tenant", "-t", help="테넌트 식별자 (세션 분리 및 X-Tenant-Id 헤더)")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="쿼리 파라미터 key=val (반복 가능, LIKE용 '%'는 -p k=% 로 준다)")] = None,
    raw_param: Annotated[bool, typer.Option("--raw-param", help="-p 값의 %XX 패턴을 디코딩하지 않고 문자 그대로 다시 URL 인코딩")] = False,
    body: Annotated[str | None, typer.Option("--body", "-b", help="JSON 요청 본문")] = None,
    form: Annotated[list[str] | None, typer.Option("--form", "-F", help="멀티파트 폼 필드 name=@파일경로[;type=MIME] 또는 name=값 (반복 가능)")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="압축 요약 대신 원본 JSON 본문 출력")] = False,
    timeout: Annotated[float | None, typer.Option("--timeout", help="요청 타임아웃(초) (기본: .env.local의 YUNHEE_API_TIMEOUT 또는 15)")] = None,
    log: Annotated[bool, typer.Option("--log", help="호출 후 서버 로그(trace) 요약 출력")] = False,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
    wait_deploy: Annotated[float | None, typer.Option("--wait-deploy", help="배포 후 앱 기동 완료까지 대기(초, 기본 60초)")] = None,
    track: Annotated[str | None, typer.Option("--track", help="호출 전후 테이블 행 수 및 신규 PK 추적 (쉼표 구분, 예: biz02_person,biz05_relate_appr)")] = None,
    fresh: Annotated[bool, typer.Option("--fresh", "--no-session", help="기존 로그인 세션을 무시하고 새로 로그인 (기본: 테넌트·계정별 세션 재사용)")] = False,
    password: Annotated[str | None, typer.Option("--password", help="로그인 비밀번호 (직접 지정, 기본값 및 환경변수보다 우선)")] = None,
    force_login: Annotated[bool, typer.Option("--force-login", help="로그인 실패 3회 이상으로 잠금 직전인 경우에도 로그인을 강제 시도")] = False,
    fields: Annotated[str | None, typer.Option("--fields", help="출력할 필드 목록 (쉼표 구분 TSV)")] = None,
    where: Annotated[list[str] | None, typer.Option("--where", help="행 필터 key=val (반복 가능)")] = None,
    count_by: Annotated[str | None, typer.Option("--count-by", help="지정 필드의 값별 행 수 집계")] = None,
):
    """자동 로그인 기반 API 호출 및 응답(상태·행수·필드) 요약

    로그인 성공 세션을 테넌트·계정별로 재사용하며, --fresh(--no-session)로 재로그인을 강제할 수 있습니다.

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  수천 줄의 원시 응답 JSON 대신 이 명령으로 행 수(rows=N)와 키 목록만 2~3줄로 확인하여 토큰을 절약하세요.
"""
    import json

    from yunhee import config
    from yunhee.tools import api_client

    if body and form:
        typer.echo("오류: --body(-b)와 --form(-F) 옵션은 함께 사용할 수 없습니다.", err=True)
        raise typer.Exit(code=1)

    params_dict = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                if v == "null:" or v.startswith("null:"):
                    params_dict[k] = None
                elif k in params_dict:
                    params_dict[k] = f"{params_dict[k]},{v}"
                else:
                    params_dict[k] = v

    json_body = None
    if body:
        try:
            json_body = json.loads(body)
        except Exception as e:  # noqa: BLE001
            typer.echo(f"오류: JSON 본문 파싱 실패: {e}", err=True)
            raise typer.Exit(code=1)

    target_base = base or config.API_BASE_URL
    target_tenant = config.resolve_api_tenant(tenant, company=company, base_url=target_base)

    if company and not target_tenant:
        typer.echo(TENANT_REQUIRED_MSG, err=True)
        raise typer.Exit(code=1)

    kw = {"base_url": target_base}
    if login_path:
        kw["login_path"] = login_path
    if company:
        kw["company_code"] = company
    if target_tenant:
        kw["tenant"] = target_tenant

    res = api_client.request_api(
        method=method,
        path=path,
        as_role=as_role,
        params=params_dict or None,
        json_body=json_body,
        form_fields=form,
        timeout=timeout,
        mask=not no_mask,
        wait_deploy=wait_deploy,
        raw_param=raw_param,
        track=track,
        fresh=fresh,
        password=password,
        force_login=force_login,
        **kw,
    )

    if not res.ok and not res.data:
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=1)

    if raw and not (fields or where or count_by):
        print(res.data.get("text", ""))
        for tline in res.data.get("track") or []:
            print(tline)
    elif fields or where or count_by:
        raw_text = res.data.get("text", "")
        try:
            parsed_data = json.loads(raw_text)
        except Exception:  # noqa: BLE001
            parsed_data = None

        rows = []
        if isinstance(parsed_data, dict):
            if isinstance(parsed_data.get("data"), list):
                rows = parsed_data["data"]
            elif isinstance(parsed_data.get("items"), list):
                rows = parsed_data["items"]
            elif "data" in parsed_data and isinstance(parsed_data["data"], dict):
                rows = [parsed_data["data"]]
            else:
                rows = [parsed_data]
        elif isinstance(parsed_data, list):
            rows = parsed_data

        # 1. --where 필터 적용
        if where and rows:
            for w in where:
                if "=" in w:
                    wk, wv = w.split("=", 1)
                    wk, wv = wk.strip(), wv.strip()
                    filtered = []
                    for r in rows:
                        if not isinstance(r, dict):
                            continue
                        val = r.get(wk)
                        if wv.lower() in ("true", "false"):
                            if str(val).lower() == wv.lower():
                                filtered.append(r)
                        elif wv.lower() in ("null", "none"):
                            if val is None or val == "":
                                filtered.append(r)
                        elif wv == "%":
                            if val is not None:
                                filtered.append(r)
                        else:
                            if str(val) == wv:
                                filtered.append(r)
                    rows = filtered

        # 2. --count-by 집계
        if count_by:
            from collections import Counter
            counts = Counter()
            for r in rows:
                if isinstance(r, dict):
                    v = r.get(count_by)
                    k_str = "(null)" if v is None else str(v)
                    counts[k_str] += 1
            out_str = " · ".join(f"{k} {cnt}" for k, cnt in counts.most_common())
            print(out_str if out_str else "(건수 없음)")

        # 3. --fields TSV 출력
        elif fields:
            f_cols = [f.strip() for f in fields.split(",") if f.strip()]
            print("\t".join(f_cols))
            for r in rows:
                if isinstance(r, dict):
                    row_vals = [str(r.get(c, "")) if r.get(c) is not None else "" for c in f_cols]
                    print("\t".join(row_vals))

        # 4. where만 지정된 경우 필터링 결과 요약
        else:
            print(f"필터링 결과 {len(rows)}건")
            if rows:
                print(f"첫 행: {json.dumps(rows[0], ensure_ascii=False)[:300]}")

        for tline in res.data.get("track") or []:
            print(tline)
    else:
        print(res.data.get("summary", ""))

    if log:
        trace_id = (res.data or {}).get("trace_id")
        if trace_id:
            import time

            from yunhee.tools.log_reader import get_trace_summary

            time.sleep(0.5)
            trace_summary = None
            for attempt in range(5):
                try:
                    trace_summary = get_trace_summary(trace_id)
                    if trace_summary:
                        break
                except Exception:  # noqa: BLE001, S110
                    pass
                if attempt < 4:
                    time.sleep(1.0)
            if trace_summary:
                t_lines = trace_summary.splitlines()
                print("\n".join(t_lines[1:] if len(t_lines) > 1 else t_lines))

    if not res.ok:
        raise typer.Exit(code=1)


@app.command(name="sql")
def sql_cmd(
    query: Annotated[str | None, typer.Argument(help="실행할 SQL 쿼리")] = None,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="실행할 SQL 파일 경로")] = None,
    builtin: Annotated[str | None, typer.Option("--builtin", help="내장 SQL 이름 실행 (예: menus)")] = None,
    rollback: Annotated[bool, typer.Option("--rollback", help="쓰기를 허용하되 반드시 트랜잭션 종료 시 ROLLBACK")] = False,
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="출력할 최대 행 수 (table 기본 5, tsv/csv/json 기본 제한 없음)")] = None,
    timeout: Annotated[float, typer.Option("--timeout", help="statement_timeout 타임아웃(초) (기본: 10)")] = 10.0,
    var: Annotated[list[str] | None, typer.Option("--var", help="변수 설정 key=val 또는 key=\"select ...\" (반복 가능)")] = None,
    db: Annotated[str | None, typer.Option("--db", help="대상 데이터베이스 환경변수 이름 또는 연결 URL (기본: YUNHEE_DB)")] = None,
    output: Annotated[str, typer.Option("--output", "-o", help="출력 형식: table(기본) | tsv | csv | json")] = "table",
    no_header: Annotated[bool, typer.Option("--no-header", help="tsv·csv 출력 시 헤더 줄 생략")] = False,
    null: Annotated[str, typer.Option("--null", help="tsv·csv에서 NULL 값을 표기할 문자열 (기본: 빈 칸)")] = "",
    out: Annotated[Path | None, typer.Option("--out", help="결과를 파일에 저장하고 화면에는 요약 한 줄만 출력")] = None,
    scalar: Annotated[bool, typer.Option("--scalar", help="첫 행 첫 열 값만 단일 문자열로 출력 (쉘 스크립트 변수 할당용)")] = False,
):
    """PostgreSQL 읽기 전용 쿼리 실행 또는 --rollback 시험

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  psql 대신 이 명령으로 중복 검사나 행 수를 확인하고, 저장 SQL 시험 시 --rollback 옵션을 사용하세요.

[bold cyan]💡 쉘 스크립트 / 변수 할당 예시:[/bold cyan]
  # 단일 스칼라 값 추출 (행 수, ID 등):
  COUNT=$(yunhee sql "SELECT count(*) FROM sys01_company" --scalar)

  # TSV 및 헤더 생략을 통한 단일 행/열 추출:
  ID=$(yunhee sql "SELECT company_id FROM sys01_company LIMIT 1" -o tsv --no-header)
"""
    from yunhee.tools import sql_runner

    vars_dict = {}
    if var:
        for v in var:
            if "=" in v:
                k, val = v.split("=", 1)
                vars_dict[k.strip()] = val.strip()

    res = sql_runner.run_sql(
        query=query,
        file_path=file,
        builtin=builtin,
        rollback=rollback,
        limit=limit,
        timeout=timeout,
        vars_dict=vars_dict or None,
        db_name=db,
        output_fmt=output,
        no_header=no_header,
        null_str=null,
        out_file=out,
        scalar=scalar,
    )
    if not res.ok:
        exit_code = (res.data or {}).get("exit_code", 1) if isinstance(res.data, dict) else 1
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=exit_code)

    for w in (res.data or {}).get("warnings", []):
        typer.echo(w, err=True)

    print(res.data.get("summary", ""))



@app.command(name="port-sql")
def port_sql_cmd(
    sql_id: Annotated[str, typer.Argument(help="AS-IS SQL ID (예: sys04_role.selectByName)")],
    cols: Annotated[str | None, typer.Option("--cols", help="추출할 컬럼 목록 (쉼표 구분)")] = None,
    getter_defaults: Annotated[bool, typer.Option("--getter-defaults", help="AS-IS 모델 getter null 기본값을 COALESCE로 적용")] = False,
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
    db: Annotated[str, typer.Option("--db", help="스키마 환경 (기본 LOCAL_DB)")] = SCHEMA_ENV,
    package: Annotated[str | None, typer.Option("--package", help="DTO 패키지 (예: kr.co.kfs.asseterp.biz.sys.dto) — resultType FQN에 사용")] = None,
    raw: Annotated[bool, typer.Option("--raw", "--verbatim", help="원본 SQL을 그대로 #{var} 치환하여 CDATA <sql id>로 출력")] = False,
    insert_into: Annotated[str | None, typer.Option("--insert-into", help="INSERT INTO <table> 대상 테이블명")] = None,
    insert_cols: Annotated[str | None, typer.Option("--insert-cols", help="INSERT INTO 대상 컬럼 매핑 (쉼표 구분, 예: 'col=expr' 또는 'col')")] = None,
) -> None:
    """AS-IS SQL을 TOBE 매퍼 조각과 Record DTO로 변환"""
    from yunhee.tools.as_is.sql_porter import port_sql

    col_list = [c.strip() for c in cols.split(",") if c.strip()] if cols else None
    res = port_sql(
        sql_id=sql_id,
        cols=col_list,
        getter_defaults=getter_defaults,
        src_root=src,
        db_env=db,
        dto_package=package,
        raw=raw,
        insert_into=insert_into,
        insert_cols=insert_cols,
    )
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res.data["output"])


@app.command(name="port-save")
def port_save_cmd(
    table: Annotated[str, typer.Argument(help="대상 테이블명 (예: sys04_role)")],
    cols: Annotated[str, typer.Option("--cols", help="INSERT/UPDATE 대상 컬럼 목록 (쉼표 구분)")],
    insert_cols: Annotated[str | None, typer.Option("--insert-cols", help="INSERT에만 포함할 컬럼 목록 (쉼표 구분, UPDATE SET 제외)")] = None,
    company_col: Annotated[str | None, typer.Option("--company-col", help="회사 ID 컬럼명")] = None,
    id_col: Annotated[str | None, typer.Option("--id-col", help="PK ID 컬럼명")] = None,
    company_via: Annotated[str | None, typer.Option("--company-via", help="회사 조건 서브쿼리 경로 (예: emp01_person.emp01_person_id=emp03_person_id)")] = None,
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
) -> None:
    """테이블 스키마 기반 명시적 INSERT/UPDATE/DELETE 및 부수효과 생성"""
    from yunhee.tools.as_is.sql_porter import port_save

    col_list = [c.strip() for c in cols.split(",") if c.strip()]
    insert_col_list = [c.strip() for c in insert_cols.split(",") if c.strip()] if insert_cols else None
    res = port_save(
        table=table,
        cols=col_list,
        company_col=company_col,
        id_col=id_col,
        company_via=company_via,
        src_root=src,
        insert_only_cols=insert_col_list,
    )
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    for w in res.data.get("warnings", []):
        typer.secho(f"⚠ {w}", fg=typer.colors.YELLOW, err=True)
    typer.echo(res.data["output"])


@app.command(name="compare")
def compare_cmd(
    method: Annotated[str, typer.Argument(help="HTTP 메서드 (GET, POST 등)")],
    path: Annotated[str, typer.Argument(help="API 경로 (예: /api/v1/sys/companies)")],
    sql: Annotated[str, typer.Option("--sql", help="비교 대상 AS-IS SQL ID (예: sys01_company.selectByName)")],
    api_param: Annotated[list[str] | None, typer.Option("-p", "--param-api", help="API 요청 파라미터 (key=value, 반복 가능, LIKE용 '%'는 -p k=% 로 준다)")] = None,
    raw_param: Annotated[bool, typer.Option("--raw-param", help="-p 값의 %XX 패턴을 디코딩하지 않고 문자 그대로 다시 URL 인코딩")] = False,
    param: Annotated[list[str] | None, typer.Option("--param", help="SQL 파라미터 (key=value, 반복 가능)")] = None,
    base: Annotated[str | None, typer.Option("--base", "-b", help="API 기본 URL")] = None,
    tenant: Annotated[str | None, typer.Option("--tenant", "-t", help="테넌트 식별자")] = None,
    company: Annotated[str | None, typer.Option("--company", "-c", help="회사 코드 (예: admin, kfstest — 회사 ID가 아님)")] = None,
    db: Annotated[str, typer.Option("--db", help="대상 DB명 (기본: asseterpdb)")] = "asseterpdb",
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
    src_index: Annotated[Path | None, typer.Option("--src-index", help="AS-IS 색인 폴더 경로 (기본: docs/as-is/src)")] = None,
    grid: Annotated[str | None, typer.Option("--grid", help="대조할 화면/그리드 클래스 (예: Sys05_Page_UserRole)")] = None,
    no_grid: Annotated[bool, typer.Option("--no-grid", help="그리드 컬럼 대조를 수행하지 않고 건수만 비교")] = False,
    as_user: Annotated[str, typer.Option("--as", "-u", help="로그인 계정/역할 (사원 ID, 로그인 ID, admin)")] = "admin",
    sql_total: Annotated[str | None, typer.Option("--total-sql", "--sql-total", help="페이징 총건수 검증용 AS-IS SQL ID (예: apr40_download_history.selectByTextPagingTotal)")] = None,
    from_log: Annotated[bool, typer.Option("--from-log", help="최근 로그 trace에서 매퍼 파라미터를 읽어 기본값으로 사용")] = False,
    branch: Annotated[list[str] | None, typer.Option("--branch", help="분기 조건 강제 on/off (식=on|off, 반복 가능)")] = None,
) -> None:
    """조회 API와 AS-IS SQL 행 수 및 그리드 컬럼 커버리지 비교"""
    from yunhee.tools.comparator import compare_api_sql

    api_params_dict = {}
    if api_param:
        for p in api_param:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                if v == "null:" or v.startswith("null:"):
                    api_params_dict[k] = None
                else:
                    api_params_dict[k] = v

    sql_params_dict = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k in sql_params_dict:
                    sql_params_dict[k] = f"{sql_params_dict[k]},{v}"
                else:
                    sql_params_dict[k] = v

    branch_dict = {}
    if branch:
        for b in branch:
            if "=" in b:
                k, v = b.split("=", 1)
                branch_dict[k.strip()] = v.strip().lower() in ("on", "true", "1", "yes")

    effective_base = base or config.API_BASE_URL
    effective_tenant = config.resolve_api_tenant(tenant)

    if company and not effective_tenant:
        typer.echo(TENANT_REQUIRED_MSG, err=True)
        raise typer.Exit(code=1)

    res = compare_api_sql(
        method=method,
        path=path,
        sql_ref=sql,
        api_params=api_params_dict,
        sql_params=sql_params_dict,
        base_url=effective_base,
        tenant=effective_tenant,
        company=company,
        db_name=db,
        src_root=src,
        src_index=src_index,
        grid=grid,
        no_grid=no_grid,
        as_user=as_user,
        sql_total_ref=sql_total,
        from_log=from_log,
        branch_overrides=branch_dict or None,
        raw_param=raw_param,
    )
    if not res.ok:
        err_msg = res.error or "비교 실패"
        if err_msg.startswith("API 호출 실패: "):
            err_msg = err_msg.replace("API 호출 실패: ", "")
        if err_msg.startswith("❌"):
            typer.secho(err_msg, fg=typer.colors.RED, err=True)
        else:
            typer.secho(f"[ERROR] {err_msg}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    from yunhee.tools.api_client import header_tag

    trace_id = (res.data or {}).get("trace_id")
    tag = header_tag(effective_base, effective_tenant, company, trace_id=trace_id)
    if tag:
        typer.echo(tag)
    user_info = (res.data or {}).get("user_info")
    if user_info and user_info.get("user_id") is not None:
        u_id = user_info.get("user_id")
        o_id = user_info.get("org_id", 0)
        c_id = user_info.get("company_id", "")
        typer.echo(f"user={u_id} org={o_id} company={c_id}")
    typer.echo(res.data["summary"])


@app.command(name="mapper-run")
def mapper_run_cmd(
    target: Annotated[str, typer.Argument(help="실행할 TOBE 매퍼와 statement ID (예: backend/src/main/resources/mapper/FbxFileMapper.xml#selectByBoxId)")],
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="쿼리 파라미터 (key=value, 반복 가능. <foreach>는 -p <collection>=a,b,c)")] = None,
    compare: Annotated[str | None, typer.Option("--compare", help="비교할 AS-IS SQL ID (예: fbx03_file.selectByBoxId)")] = None,
    count: Annotated[bool, typer.Option("--count", help="행 수만 출력")] = False,
    rows: Annotated[int | None, typer.Option("--rows", "-n", help="출력할 최대 행 수")] = None,
    rollback: Annotated[bool, typer.Option("--rollback", help="트랜잭션 실행 후 롤백 (쓰기 문장 필수)")] = False,
    db: Annotated[str, typer.Option("--db", "-c", help="대상 DB명 (기본: asseterpdb)")] = "asseterpdb",
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
) -> None:
    """TOBE 매퍼 statement 실행 및 AS-IS SQL 비교.

    <foreach>는 -p <collection>=a,b,c로 준다.
    """
    from yunhee.tools.as_is.mapper_runner import run_mapper_statement

    params_dict = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                if v == "null:" or v.startswith("null:"):
                    params_dict[k] = None
                elif k in params_dict:
                    params_dict[k] = f"{params_dict[k]},{v}"
                else:
                    params_dict[k] = v

    res = run_mapper_statement(
        target=target,
        params=params_dict,
        db_name=db,
        compare_sql=compare,
        count_only=count,
        limit_rows=rows,
        rollback=rollback,
        src_root=src,
    )
    if not res.ok and not res.data:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res.data.get("summary", ""))
    if not res.ok:
        raise typer.Exit(code=1)


@app.command(name="changelog")
def changelog_cmd(
    version: Annotated[str | None, typer.Argument(help="볼 버전 (예: 0.1.3). 생략 시 현재 설치된 버전")] = None,
    since: Annotated[str | None, typer.Option("--since", help="이 버전 이후(미포함) 변경사항 전부")] = None,
    show_all: Annotated[bool, typer.Option("--all", help="전체 변경 이력")] = False,
):
    """버전별 변경 이력 출력"""
    from yunhee import changelog

    entries = changelog.select(
        changelog.parse(changelog.read_text()),
        version=version,
        since=since,
        show_all=show_all,
        current=project.current_version(),
    )
    if not entries:
        target = f"{since} 이후" if since else (version or project.current_version())
        typer.echo(f"변경 이력 없음: {target}", err=True)
        raise typer.Exit(code=1)
    print("\n\n".join(e.render() for e in entries))


@app.command(name="agent-guide")
def agent_guide():
    """AI 에이전트용 토큰 절약 행동 지침서(Markdown) 출력"""
    guide = """# YUNHEE AI AGENT PROTOCOL (토큰 절약 행동 수칙)

당신은 이 프로젝트를 작업하는 상용 AI 코딩 어시스턴트(Claude, Antigravity, Gemini 등)입니다.
이 환경에는 토큰 소모를 극적으로 줄이기 위한 독립 로컬 CLI인 `yunhee`가 설치되어 있습니다.
작업 시 아래 규칙을 반드시 준수하여 불필요한 토큰 낭비를 원천 차단하세요.

---

## 1. TOBE 기존 코드 위치 파악 시 (토큰 95% 절약)
- ❌ 절대 금지: Service, Controller, Mapper XML, TypeScript 파일을 통째로 view_file로 읽지 마세요.
- ✅ 권장 명령: `yunhee outline <파일 또는 디렉터리 경로>`
  - 예: `yunhee outline src/main/java/.../SysMenuService.java`
  - 예: `yunhee outline src/main/resources/mapper/`
  - 예: `yunhee outline frontend/src/api/sys.ts`
- 📄 산출물: 클래스/메서드 시그니처, 스프링 @GetMapping/PostMapping 경로, MyBatis statement id, TS export 함수와 **줄 번호**만 정밀 추출됩니다. 줄 번호를 확인한 뒤 꼭 필요한 몇 줄만 읽으세요.

## 2. DB 스키마 확인 시 (토큰 90% 절약)
- ❌ 절대 금지: 전체 DB DDL이나 거대한 스키마 파일을 검색하거나, PostgreSQL 카탈로그를 직접 조회하지 마세요.
- ✅ 권장 명령:
  - 특정 테이블: `yunhee table <테이블명>` (예: `yunhee table sys04_role`)
  - 패턴 검색: `yunhee table '<패턴>'` (예: `yunhee table 'emp00_*'`)
- 📄 산출물: 컬럼, 타입, 코멘트, PK/FK, Enum만 정제된 순수 DBML 블록으로 제공됩니다.

## 3. 컴파일, 빌드, 린트, 테스트 실행 시 (토큰 98% 절약)
- ❌ 절대 금지: `mvn compile`, `./gradlew build`, `npm run build`, `pytest` 등을 셸에서 직접 실행하지 마세요. (수천 줄의 빌드 로그로 컨텍스트가 오염됩니다)
- ✅ 권장 명령: `yunhee run "<실행명령어>"` (예: `yunhee run "./gradlew compileJava"`, `yunhee run "npx tsc -b --noEmit"`)
- 📄 산출물:
  - 성공 시: `✅ Execution Succeeded in X.Xs (log: ...)` 정확히 1줄만 반환됩니다.
  - 실패 시: 원시 전체 로그는 `.yunhee/runs/<run_id>.log`에 저장되고, 1) 실패 원인, 2) 관련 파일:라인, 3) 핵심 에러 원문 발췌만 요약 제공됩니다.
- 직전 실행 결과 재확인: `yunhee last-run`
- 최근 실행 이력 표: `yunhee runs`
- 실패/상세 로그 추출: `yunhee analysis run last --stderr` (에러/예외 출력만 확인), `yunhee analysis run last --stdout` (표준 출력만 확인)

## 4. 로그인 기반 API 스모크 검증 시 (토큰 95% 절약)
- ❌ 절대 금지: curl 등으로 직접 로그인하고 수천 줄의 JSON 응답을 그대로 터미널에 쏟아내지 마세요. 쓰기 시험 후 새 행 PK를 찾으려고 따로 SQL을 여러 번 돌리지 마세요.
- ✅ 권장 명령: `yunhee api <METHOD> <PATH> [--as admin|user] [--company CODE] [--tenant TENANT] [--track <테이블>[,<테이블>]]`
  - 예: `yunhee api GET /api/v1/sys/menus/company`
  - 예: `yunhee api GET /api/v1/sys/roles --as admin`
  - 예: `yunhee api POST /api/v1/biz/relate-apprs/promo -c kfstest -b '{"promoId":...}' --track biz05_relate_appr` (호출 전후 행 수와 새로 생긴 PK `biz05_relate_appr: 40 → 41 (+1: biz05_relate_appr_id=...)` 출력)
  - 예: `yunhee api DELETE /api/v1/biz/relate-apprs -c kfstest -b '[...]' --track biz05_relate_appr` (`41 → 40 (-1)` 한 줄로 삭제 확인)
- 📄 산출물: 세션 쿠키/JWT가 자동 관리되며(계정 잠금 방지 안전 가드 내장), 응답은 `HTTP 200 (rows=12, fields: [...])` 압축 헤더와 `--track` 테이블 행 수/신규 PK 변화로 요약됩니다.

## 5. AS-IS 정적 분석 및 폼 레이아웃·호출부 파악 (토큰 90% 절약)
- ❌ 절대 금지: 복잡한 GXT 폼 탭의 컴포넌트 크기, 라벨, 배치, 읽기 전용 속성이나 팝업 호출 인자를 파악하려고 수백 줄의 자바 소스를 직접 열거나 grep하지 마세요.
- ✅ 권장 명령:
    - `yunhee page-style <화면.java|tsx>`: 화면 파일의 페이지 스타일(SID: SG, SGP, SGVF, SGEF, SGTP, SGT, TG, GG, CG) 및 분할 레이아웃 판별 (대조: `yunhee page-style --compare <asis.java> <tobe.tsx>`)
    - `yunhee analysis screen <화면> --list`: 클래스 목록 및 줄/버튼/이벤트/그리드 통계 (연결 컴포넌트 포함(`(연결)` 표시), `--no-linked` 지원)
    - `yunhee analysis screen <화면> --section layout`: 폼 탭은 원본 Java를 열기 전에 이것부터 확인하세요.
    - `yunhee analysis screen <화면> --section source`: 화면의 색인 소스 및 커밋 정보 확인.
    - `yunhee analysis callers <클래스> [--tobe frontend/src]`: AS-IS에서 해당 팝업/창을 `new`하여 여는 모든 호출부(`파일:줄 | 부른 메서드(open/view/edit) | 리터럴 인자 | 감싼 메서드 | 메뉴`)와 TOBE 렌더링 짝(`<컴포넌트 ...>`)을 한 번에 대조하세요.
    - `yunhee analysis sql <매퍼ID 또는 dom.Class.method>` / `yunhee port-sql <매퍼ID 또는 dom.Class.method>`: 매퍼 이름(`ics40_dcr_preconfirm.selectByApprId`)뿐 아니라 화면 주석에 적힌 **서비스 이름(`ics.Ics40_DcrPreconfirm.selectByApprId`)을 그대로 넘겨도** 서버 메서드를 거쳐 매퍼 SQL을 자동 해석하며, DB에 없는 테이블/함수가 있으면 즉시 `⚠ DB에 없는 객체` 경고를 표시합니다.
    - `yunhee trace-gap --stubs [-d <도메인>]`: TOBE `frontend/src`에서 미연결 자리(`message.info/warning`의 '다음 단계'·'아직 변환'·'연결됩니다' 안내, `[E… 생략]`, 화면 머리에만 남은 `1단계:`/`다음 단계:` 주석)를 여는 `_Tab_` 화면 및 메뉴 번호(`#번호`)와 함께 표 및 `13-누락대장.md` 체크리스트 꼴로 수집합니다.
    - `yunhee sql-check --new-since-index`: 마지막 `sql-check.md` 생성 이후 AS-IS에 새로 추가·변경된 매퍼 XML만 빠르게 EXPLAIN 검증합니다.
    - `yunhee analysis ui <화면>`: TOBE 이벤트 구현율 및 `(생략 N)` (TOBE에서 생략하기로 결정된 이벤트 수) 확인 (연결 컴포넌트 포함(`(연결)` 표시)).

## 6. 서버 로그 및 실제 실행 SQL 확인 시 (grep 금지)
- ❌ 절대 금지: docker logs나 서버 로그 파일을 직접 grep하지 마세요. (호스트 같은 경로는 로컬 테스트 로그이며, 배포본은 docker 컨테이너(YUNHEE_LOG_DOCKER, 예: omen-tomcat) 안에 있습니다)
- ✅ 권장 명령:
  - `yunhee api <METHOD> <PATH> --log`: API 호출 직후 서버가 실제로 실행한 SQL과 바인딩 파라미터 요약 출력
  - `yunhee log trace <traceId>`: 특정 요청에서 실행된 모든 SQL 및 파라미터 확인
  - `yunhee log req <METHOD> <경로 일부>`: 접근 로그에서 최근 요청 검색
  - `yunhee log errors`: 서버 WARN/ERROR 묶음 요약
  - `yunhee log tail`: 최근 전체 흐름을 요청(trace) 단위로 접어서 확인

## 7. AS-IS 소스 변경(drift) 감지 및 기준선 관리
- 화면을 완성하면 `yunhee drift --record <화면> [--id <작업단위>] [--note-file <노트경로>]`, 주 1회·git pull 직후 `yunhee drift --all --base baseline --done-only`로 AS-IS 변경을 점검하세요.
- 특정 화면 점검: `yunhee drift <화면> [-o table|diff|full|json]`

## 8. 현재 설정 및 경로 확인
- `yunhee config`: Target 디렉터리, Source 디렉터리, 소스 브랜치 동기화 상태, DB URL 등 환경 확인.
"""
    print(guide.strip())


@app.command(name="index-db")
def index_db_cmd(
    dbml: Annotated[
        Path | None,
        typer.Argument(help="DBML markdown 파일 경로 (미지정 시 자동 탐색)"),
    ] = None,
    target: Annotated[
        Path | None,
        typer.Option("--target", "-t", help="색인 출력 폴더 (기본: {WORK_DIR}/docs/as-is/db)"),
    ] = None,
):
    """DBML 마크다운을 도메인·함수별 소형 파일로 분할 색인"""
    if dbml is None:
        candidates = [
            WORK_DIR / ".yunhee" / f"{SCHEMA_ENV}-dbml.md",
            WORK_DIR / f"{SCHEMA_ENV}-dbml.md",
            YUNHEE_DIR / "data" / "schema" / f"{SCHEMA_ENV}-dbml.md",
            YUNHEE_DIR / f"{SCHEMA_ENV}-dbml.md",
        ]
        for c in candidates:
            if c.is_file():
                dbml = c
                break
        if dbml is None:
            found = list((WORK_DIR / ".yunhee").glob("*-dbml.md")) or list(WORK_DIR.glob("*-dbml.md"))
            if found:
                dbml = found[0]

    if dbml is None or not dbml.is_file():
        typer.secho(
            "[ERROR] DBML markdown 파일을 찾을 수 없습니다. 경로를 인자로 넘겨주거나 'yunhee make-dbml'을 먼저 실행하세요.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    out_dir = target if target is not None else find_as_is_dir("db")
    res = index_dbml(dbml, out_dir)
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
        raise typer.Exit(1)

    d = res.data
    typer.secho(f"✅ DB 색인 생성 완료: {d['target_dir']}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  - 원본 DBML: {dbml}")
    typer.echo(f"  - 테이블: {d['tables_count']}개 → 도메인 {d['domains_count']}개 파일")
    typer.echo(f"  - 뷰: {d['views_count']}개, 함수·프로시저: {d['routines_count']}개 (트리거 함수 {d['trigger_fns_count']}개 제외)")


@app.command(name="index-src")
def index_src_cmd(
    src_root: Annotated[
        Path | None,
        typer.Argument(help="AS-IS 소스 루트 (미지정 시 YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    target: Annotated[
        Path | None,
        typer.Option("--target", "-t", help="색인 출력 폴더 (기본: {repo_root}/docs/as-is/src)"),
    ] = None,
    menus: Annotated[
        Path | None,
        typer.Option("--menus", help="메뉴 TSV 파일 (미지정 시 {target}/../menus.tsv 탐색)"),
    ] = None,
    menus_from_db: Annotated[
        str | None,
        typer.Option("--menus-from-db", help="--menus 파일이 없을 때 DB의 sys06_menu에서 바로 읽어 {target}/../menus.tsv 생성"),
    ] = None,
    db_index: Annotated[
        Path | None,
        typer.Option("--db-index", help="DB 색인 폴더 (미지정 시 {target}/../db 탐색)"),
    ] = None,
    events: Annotated[
        bool,
        typer.Option("--events/--no-events", help="화면 파일 UI 절에 `yunhee events` 결과(이벤트·메서드·Grid Spec·버튼) 포함"),
    ] = True,
    button_types: Annotated[
        Path | None,
        typer.Option("--button-types", "-b", help="버튼 타입 매핑 TSV 경로 (events와 동일한 기본 탐색)"),
    ] = None,
    vcs_root: Annotated[
        Path | None,
        typer.Option("--vcs-root", help="소스 루트가 git 저장소의 하위 폴더일 때 그 저장소 루트 경로 (기본: 소스 루트 자신이 저장소 루트일 때만 git 정보 사용)"),
    ] = None,
):
    """AS-IS 소스 호출 경로(화면→서비스→SQL→테이블) 및 UI 색인 생성"""
    root = src_root if src_root is not None else ASIS_SRC_DIR
    if not root or not root.is_dir():
        typer.secho(
            f"[ERROR] AS-IS 소스 디렉터리를 찾을 수 없습니다: {root}\n"
            f"인자로 소스 경로를 넘기거나 .env.local의 YUNHEE_ASIS_SRC_DIR를 설정하세요.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    out_dir = target if target is not None else find_as_is_dir("src")

    menus_path = menus
    target_menus_file = menus_path or (out_dir.parent / "menus.tsv")

    if menus_from_db:
        # DB의 sys06_menu 에서 menus.tsv 생성
        from yunhee.tools import sql_runner

        gen_res = sql_runner.run_sql(
            builtin="menus",
            db_name=menus_from_db,
            output_fmt="tsv",
            no_header=True,
            out_file=target_menus_file,
        )
        if not gen_res.ok:
            typer.secho(f"[ERROR] --menus-from-db 실행 실패: {gen_res.error}", fg=typer.colors.RED)
            raise typer.Exit(1)
        menus_path = target_menus_file
    elif menus_path is None:
        cand = out_dir.parent / "menus.tsv"
        if cand.is_file():
            menus_path = cand

    db_dir = db_index
    if db_dir is None:
        cand = out_dir.parent / "db"
        if cand.is_dir():
            db_dir = cand

    res = index_src(
        root, out_dir, menus_path=menus_path, db_index_dir=db_dir,
        with_events=events, button_types_path=button_types, vcs_root=vcs_root,
    )
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
        raise typer.Exit(1)

    d = res.data
    if d.get("mismatch_warning"):
        typer.secho(d["mismatch_warning"], fg=typer.colors.YELLOW)
    if d.get("vcs_warning"):
        typer.secho(d["vcs_warning"], fg=typer.colors.YELLOW)
    typer.secho(f"✅ AS-IS 소스 색인 생성 완료: {d['target_dir']}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  - 원본 소스: {root} ({d['app_package']})")
    src_info = d.get("source_info") or {}
    s_total = d.get("screens_count", 0)
    s_menu = d.get("screens_menu", s_total)
    s_frame = d.get("screens_frame", d.get("frame_screens_count", 0))
    screen_summary_str = f"화면 {s_total:,}개(메뉴 {s_menu:,} + 프레임 {s_frame:,})"
    if src_info.get("vcs") == "git":
        ct_short = str(src_info.get("commit_time", ""))[:16].replace("T", " ")
        clean_label = "dirty" if src_info.get("dirty") else "clean"
        typer.echo(
            f"  - 소스 {src_info.get('commit_short')} ({src_info.get('branch')}, {ct_short}) {clean_label}"
            f" · {screen_summary_str} · 의존 파일 {d.get('files_count', 0):,}개 기록"
        )
        if src_info.get("dirty"):
            typer.secho("  ⚠ 미커밋 변경이 색인에 포함됨 — 기준 커밋만으로 재현 불가", fg=typer.colors.YELLOW)
    else:
        typer.echo(
            "  - 소스 (비-git)"
            f" · {screen_summary_str} · 의존 파일 {d.get('files_count', 0):,}개 기록"
        )
    menu_detail = f"{s_menu}개" if d.get("has_menus") else "연결 안 됨(--menus 없음)"
    typer.echo(f"  - 클라이언트 클래스: {d['client_classes_count']}개, 메뉴 화면: {menu_detail}, 프레임: {d['frame_screens_count']}개, 컴포넌트: {d['components_count']}개")
    typer.echo(f"  - 서비스 메서드: {d['service_methods_count']}개, 매퍼 SQL: {d['statements_count']}개, 도메인: {d['domains_count']}개")
    if d["missing_service_keys_count"] or d["missing_sql_ids_count"]:
        typer.echo(f"  - 미해결 호출: 서비스 키 {d['missing_service_keys_count']}개, 매퍼 SQL ID {d['missing_sql_ids_count']}개 → unresolved.md")
    if events:
        typer.echo(f"  - events: 클래스 {d['events_classes_count']}개 분석 (화면 파일 UI 절에 포함)")
        for name, err in d["events_errors"]:
            typer.secho(f"    ⚠ {name}: {err}", fg=typer.colors.YELLOW, err=True)
    if d.get("prev_diff") and d["prev_diff"].get("summary"):
        typer.echo(f"  - {d['prev_diff']['summary']}")


@app.command(name="drift")
def drift_cmd(
    screens: Annotated[
        list[str] | None,
        typer.Argument(help="검사 또는 기록할 화면 클래스명/약칭 (여러 개 지정 가능)"),
    ] = None,
    all_screens: Annotated[
        bool,
        typer.Option("--all", help="색인된 전체 화면 검사"),
    ] = False,
    src: Annotated[
        Path | None,
        typer.Option("--src", help="현재 AS-IS 소스 루트 (기본: YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    src_index: Annotated[
        Path | None,
        typer.Option("--src-index", help="색인 폴더 (기본: docs/as-is/src)"),
    ] = None,
    base: Annotated[
        str,
        typer.Option("--base", help="비교 기준: index(기본) | baseline | prev-index | <커밋 해시>"),
    ] = "index",
    done_only: Annotated[
        bool,
        typer.Option("--done-only", help="baseline에 등록된(완성된) 화면만 검사"),
    ] = False,
    min_lines: Annotated[
        int,
        typer.Option("--min-lines", help="변경 줄 수(+와 -의 합)가 N 이상인 화면만 표시"),
    ] = 1,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="출력 형식: table(기본) | diff | full | json"),
    ] = "table",
    max_lines: Annotated[
        int,
        typer.Option("--max-lines", help="diff 출력 최대 줄 수 (기본: 200)"),
    ] = 200,
    new_flag: Annotated[
        bool,
        typer.Option("--new", help="색인에 없던 신규 화면·파일 후보 탐지"),
    ] = False,
    fail_on_drift: Annotated[
        bool,
        typer.Option("--fail-on-drift", help="변경이 1건이라도 있으면 종료 코드 1 반환"),
    ] = False,
    ignore_space: Annotated[
        bool,
        typer.Option("--ignore-space", help="공백/개행(CRLF) 차이 무시 (git diff -w)"),
    ] = False,
    record: Annotated[
        bool,
        typer.Option("--record", help="화면의 현재 색인 기준을 완성 기준선(baseline)으로 기록"),
    ] = False,
    record_from: Annotated[
        Path | None,
        typer.Option("--record-from", help="마크다운 표 파일에서 상태별로 일괄 baseline 기록"),
    ] = None,
    record_all: Annotated[
        bool,
        typer.Option("--record-all", help=".yunhee.toml [drift] 설정 기반으로 일괄 baseline 기록"),
    ] = False,
    status: Annotated[
        str | None,
        typer.Option("--status", help="일괄 기록할 상태 목록 (쉼표 구분, 기본: 완료,확인)"),
    ] = None,
    id_col: Annotated[
        str,
        typer.Option("--id-col", help="표의 ID 열 헤더 이름 (기본: ID)"),
    ] = "ID",
    class_col: Annotated[
        str,
        typer.Option("--class-col", help="표의 클래스 열 헤더 이름 (기본: 클래스)"),
    ] = "클래스",
    status_col: Annotated[
        str,
        typer.Option("--status-col", help="표의 상태 열 헤더 이름 (기본: 상태)"),
    ] = "상태",
    note_dir: Annotated[
        Path | None,
        typer.Option("--note-dir", help="일괄 기록 시 작업기록 폴더 (기본: docs/work)"),
    ] = None,
    note_suffix: Annotated[
        str | None,
        typer.Option("--note-suffix", help="일괄 기록 시 작업기록 파일 접미사 (기본: -작업기록.md)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="쓰지 않고 대상 목록과 건너뜀 사유만 표시"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="해시가 달라진 기존 baseline도 강제로 덮어쓰기"),
    ] = False,
    unit_id: Annotated[
        str | None,
        typer.Option("--id", help="작업 단위 식별자 (예: A21)"),
    ] = None,
    note_file: Annotated[
        Path | None,
        typer.Option("--note-file", help="작업 노트 마크다운 파일 상단에 AS-IS 기준 줄 삽입/갱신"),
    ] = None,
    show_baseline: Annotated[
        bool,
        typer.Option("--show-baseline", help="기록된 완성 기준선과 이력 표시"),
    ] = False,
):
    """색인·기준선(baseline) 대비 AS-IS 화면·파일 변경 감지"""
    from yunhee.tools.as_is.drift import (
        record_baseline,
        record_baseline_from_table,
        run_drift,
        show_baseline_info,
    )

    idx_dir = src_index if src_index is not None else find_as_is_dir("src")
    src_dir = src if src is not None else ASIS_SRC_DIR
    screen_list = list(screens) if screens else []

    if show_baseline:
        code, msg = show_baseline_info(screen_names=screen_list, work_dir=WORK_DIR)
        if code != 0:
            typer.secho(f"[ERROR] {msg}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=code)
        typer.echo(msg)
        return

    if record_from is not None or record_all:
        status_list = [s.strip() for s in status.split(",") if s.strip()] if status else None
        code, msg = record_baseline_from_table(
            table_file=record_from,
            src_root=src_dir,
            src_index=idx_dir,
            statuses=status_list,
            id_col=id_col,
            class_col=class_col,
            status_col=status_col,
            note_dir=note_dir,
            note_suffix=note_suffix,
            dry_run=dry_run,
            force=force,
            work_dir=WORK_DIR,
        )
        if code != 0 and msg.startswith("오류:"):
            typer.secho(f"[ERROR] {msg}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=code)
        typer.echo(msg)
        if code != 0:
            raise typer.Exit(code=code)
        return

    if record:
        code, msg = record_baseline(
            screen_names=screen_list,
            src_root=src_dir,
            src_index=idx_dir,
            task_id=unit_id,
            note_file=note_file,
            force=force,
            work_dir=WORK_DIR,
        )
        if code != 0:
            typer.secho(f"[ERROR] {msg}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=code)
        typer.echo(msg)
        return

    code, out_text, warnings = run_drift(
        screen_args=screen_list,
        all_screens=all_screens,
        src_root=src_dir,
        src_index=idx_dir,
        base=base,
        done_only=done_only,
        min_lines=min_lines,
        output_fmt=output,
        max_lines=max_lines,
        show_new=new_flag,
        fail_on_drift=fail_on_drift,
        ignore_space=ignore_space,
        work_dir=WORK_DIR,
    )
    for w in warnings:
        typer.secho(w, fg=typer.colors.YELLOW, err=True)
    if code == 2:
        typer.secho(f"[ERROR] {out_text}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    typer.echo(out_text)
    if code != 0:
        raise typer.Exit(code=code)


@app.command(name="drift-unit")
def drift_unit_cmd(
    base: Annotated[
        str,
        typer.Option("--base", help="비교 기준: baseline(기본) | index | <커밋>"),
    ] = "baseline",
    done_only: Annotated[
        bool,
        typer.Option("--done-only", help="완료(baseline) 화면 관련 단위만 표시"),
    ] = False,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="필터링할 종류 (쉼표 구분: SQL,LOGIC,UI,MODEL,DB,NEW,ETC)"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="출력 형식: table(기본) | json"),
    ] = "table",
    all_units: Annotated[
        bool,
        typer.Option("--all-units", help="쓰는 화면 없는 단위도 모두 표시"),
    ] = False,
    src: Annotated[
        Path | None,
        typer.Option("--src", help="AS-IS 소스 루트 (기본: YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    src_index: Annotated[
        Path | None,
        typer.Option("--src-index", help="색인 폴더 (기본: docs/as-is/src)"),
    ] = None,
):
    """바뀐 파일을 SQL ID·메서드·UI·모델 단위로 세분화하고 영향 화면 및 TOBE 대응 탐색"""
    from yunhee.tools.as_is.drift_ops import (
        analyze_drift_units,
        render_drift_unit_table,
    )

    src_dir = (src or (Path(config.ASIS_SRC_DIR).resolve() if config.ASIS_SRC_DIR else None))
    if not src_dir or not src_dir.is_dir():
        typer.secho("오류: AS-IS 소스 루트(--src 또는 YUNHEE_ASIS_SRC_DIR)가 지정되지 않았습니다.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    idx_dir = (src_index or (WORK_DIR / "docs" / "as-is" / "src")).resolve()
    if not idx_dir.is_dir():
        typer.secho(f"오류: 색인 폴더를 찾을 수 없습니다: {idx_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    kind_filter = [k.strip() for k in kind.split(",")] if kind else None
    units = analyze_drift_units(
        src_root=src_dir,
        src_index=idx_dir,
        base=base,
        done_only=done_only,
        kind_filter=kind_filter,
        work_dir=WORK_DIR,
    )

    if output == "json":
        import json
        typer.echo(json.dumps(units, ensure_ascii=False, indent=2))
    else:
        typer.echo(render_drift_unit_table(units, all_units=all_units))


@app.command(name="drift-done")
def drift_done_cmd(
    keys: Annotated[
        list[str],
        typer.Argument(help="반영 완료할 대장 키(CH-0001 등) 또는 단위/파일명"),
    ],
    status: Annotated[
        str,
        typer.Option("--status", help="변경 상태: 반영(기본) | 해당없음 | 보류 | 넘김"),
    ] = "반영",
    check: Annotated[
        str,
        typer.Option("--check", help="확인 방법·근거 (상태가 '반영'일 때 필수; 예: compare 일치, 테스트 클래스명 등)"),
    ] = "",
    tobe: Annotated[
        str,
        typer.Option("--tobe", help="TOBE 대응 문장/메서드 (대장 'TOBE 대응' 칸)"),
    ] = "",
    note: Annotated[
        str,
        typer.Option("--note", help="비고/사유 (기본: 덮어쓰기)"),
    ] = "",
    note_append: Annotated[
        bool,
        typer.Option("--note-append", help="비고 칸을 덮어쓰지 않고 ' · <note>'로 덧붙이기"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="확인 칸 누락 등의 검증 경고를 무시하고 강제 진행"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="대장과 baseline.json에 실제 쓰지 않고 변경 전후 diff 미리보기"),
    ] = False,
    ledger: Annotated[
        Path | None,
        typer.Option("--ledger", help="반영대장 마크다운 파일 경로"),
    ] = None,
):
    """단위 또는 파일 기준선을 갱신하고 반영대장의 확인·상태·처리일·비고 기록"""
    from yunhee.tools.as_is.drift_ops import update_drift_done

    code, msg = update_drift_done(
        keys=keys,
        status=status,
        check=check,
        tobe=tobe,
        note=note,
        note_append=note_append,
        force=force,
        dry_run=dry_run,
        work_dir=WORK_DIR,
        ledger_path=ledger,
    )
    if code != 0:
        typer.secho(f"오류: {msg}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=code)
    typer.echo(msg)


@app.command(name="drift-ledger")
@app.command(name="drift-list")
def drift_ledger_cmd(
    ledger_path: Annotated[
        Path | None,
        typer.Argument(help="반영대장 마크다운 파일 경로 (기본: docs/3-변경반영/변경반영-대장.md 또는 반영대장.md)"),
    ] = None,
    base: Annotated[
        str,
        typer.Option("--base", help="비교 기준: baseline(기본) | index | <커밋>"),
    ] = "baseline",
    done_only: Annotated[
        bool,
        typer.Option("--done-only", help="완료 화면 관련 단위만 수집"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="실제 파일에 쓰지 않고 추가/갱신될 행만 출력"),
    ] = False,
    src: Annotated[
        Path | None,
        typer.Option("--src", help="AS-IS 소스 루트 (기본: YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    src_index: Annotated[
        Path | None,
        typer.Option("--src-index", help="색인 폴더 (기본: docs/as-is/src)"),
    ] = None,
):
    """drift-unit 결과를 반영대장 표 끝에 대기로 덧붙이거나 기존 대기 건 갱신"""
    from yunhee.tools.as_is.drift_ops import (
        analyze_drift_units,
        append_to_ledger,
        resolve_ledger_path,
    )

    src_dir = (src or (Path(config.ASIS_SRC_DIR).resolve() if config.ASIS_SRC_DIR else None))
    if not src_dir or not src_dir.is_dir():
        typer.secho("오류: AS-IS 소스 루트(--src 또는 YUNHEE_ASIS_SRC_DIR)가 지정되지 않았습니다.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    idx_dir = (src_index or (WORK_DIR / "docs" / "as-is" / "src")).resolve()
    if not idx_dir.is_dir():
        typer.secho(f"오류: 색인 폴더를 찾을 수 없습니다: {idx_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    l_file = resolve_ledger_path(WORK_DIR, ledger_path)
    if not l_file.is_file():
        typer.secho(f"오류: 반영대장 파일을 찾을 수 없습니다: {l_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    units = analyze_drift_units(
        src_root=src_dir,
        src_index=idx_dir,
        base=base,
        done_only=done_only,
        work_dir=WORK_DIR,
    )

    code, msg = append_to_ledger(
        ledger_path=l_file,
        units=units,
        dry_run=dry_run,
    )
    if code != 0:
        typer.secho(f"오류: {msg}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=code)
    typer.echo(msg)


@app.command(name="drift-diff")
def drift_diff_cmd(
    unit: Annotated[
        str,
        typer.Argument(help="비교할 단위 (예: apr01_appr.selectByApprIdList 또는 Apr01_Appr#update 또는 파일경로)"),
    ],
    base: Annotated[
        str,
        typer.Option("--base", help="비교 기준: baseline(기본) | index | <커밋>"),
    ] = "baseline",
    src: Annotated[
        Path | None,
        typer.Option("--src", help="AS-IS 소스 루트 (기본: YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
):
    """단일 단위의 AS-IS 전후 diff 및 현재 TOBE 대응 문장/메서드 나란히 대조"""
    from yunhee.tools.as_is.drift_ops import render_unit_diff

    src_dir = (src or (Path(config.ASIS_SRC_DIR).resolve() if config.ASIS_SRC_DIR else None))
    if not src_dir or not src_dir.is_dir():
        typer.secho("오류: AS-IS 소스 루트(--src 또는 YUNHEE_ASIS_SRC_DIR)가 지정되지 않았습니다.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    code, out = render_unit_diff(
        unit=unit,
        src_root=src_dir,
        base=base,
        work_dir=WORK_DIR,
    )
    if code != 0:
        typer.secho(f"오류: {out}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=code)
    typer.echo(out)


@app.command(name="drift-db")
def drift_db_cmd(
    from_dbml: Annotated[
        Path | None,
        typer.Option("--from", "-f", help="이전 DBML 파일 경로 (기본: .yunhee/<ENV>-dbml.prev.md)"),
    ] = None,
    to_dbml: Annotated[
        Path | None,
        typer.Option("--to", "-t", help="새 DBML 파일 경로 (기본: .yunhee/<ENV>-dbml.md)"),
    ] = None,
):
    """DBML 스냅샷 전후(테이블/컬럼/함수) 차이 및 영향 SQL/TOBE 매퍼 탐색"""
    from yunhee.tools.as_is.drift_ops import compare_dbml_snapshots

    code, out = compare_dbml_snapshots(
        from_path=from_dbml,
        to_path=to_dbml,
        work_dir=WORK_DIR,
    )
    if code != 0:
        typer.secho(f"오류: {out}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=code)
    typer.echo(out)


@app.command(name="drift-log")
def drift_log_cmd(
    since: Annotated[
        str,
        typer.Option("--since", help="시작 기준: baseline(기본) | <커밋> | <날짜>"),
    ] = "baseline",
    src: Annotated[
        Path | None,
        typer.Option("--src", help="AS-IS 소스 루트 (기본: YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
):
    """기준 이후 들어온 커밋들을 파일/종류(DB·SQL·LOGIC·MODEL·UI·ETC) 단위로 요약"""
    from yunhee.tools.as_is.drift_ops import render_drift_log

    src_dir = (src or (Path(config.ASIS_SRC_DIR).resolve() if config.ASIS_SRC_DIR else None))
    if not src_dir or not src_dir.is_dir():
        typer.secho("오류: AS-IS 소스 루트(--src 또는 YUNHEE_ASIS_SRC_DIR)가 지정되지 않았습니다.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    code, out = render_drift_log(
        src_root=src_dir,
        since=since,
        work_dir=WORK_DIR,
    )
    if code != 0:
        typer.secho(f"오류: {out}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=code)
    typer.echo(out)



@app.command(name="sql-check")
def sql_check_cmd(
    src_root: Annotated[
        Path | None,
        typer.Argument(help="AS-IS 소스 루트 (미지정 시 YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    old: Annotated[
        Path | None,
        typer.Option("--old", help="비교할 이전 AS-IS 소스 루트 (지정 시 SQL Drift 검증 모드로 동작)"),
    ] = None,
    new: Annotated[
        Path | None,
        typer.Option("--new", help="비교할 새 AS-IS 소스 루트 (미지정 시 src_root 또는 YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 매퍼 디렉터리 경로 (예: backend/src/main/resources/mapper)"),
    ] = None,
    only_tobe: Annotated[
        bool,
        typer.Option("--only-tobe", help="TOBE 매퍼가 참조하는 SQL의 변경점만 필터링"),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="출력 형식 (md, json)"),
    ] = None,
    db: Annotated[
        str,
        typer.Option("--db", help="검증 대상 PostgreSQL DB 이름"),
    ] = "asseterpdb",
    target: Annotated[
        Path | None,
        typer.Option("--target", "-t", help="출력 파일 경로 (기본: {repo_root}/docs/as-is/sql-check.md, --old 시 미지정하면 화면에만 출력)"),
    ] = None,
    src_index: Annotated[
        Path | None,
        typer.Option("--src-index", help="src-index 출력 폴더 (기본: docs/as-is/src 탐색)"),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="검증할 매퍼 이름 또는 glob 패턴 (여러 번 가능)"),
    ] = None,
    changed: Annotated[
        bool,
        typer.Option("--changed", help="git diff (+untracked) 변경된 매퍼 XML만 검증"),
    ] = False,
    summary: Annotated[
        bool,
        typer.Option("--summary", help="매퍼별 ✅ n / ❌ m 한 줄 및 ❌ statement만 상세 출력"),
    ] = False,
    new_since_index: Annotated[
        bool,
        typer.Option("--new-since-index", "--changed-asis", help="색인 기준 이후 새로 생겼거나 최근 변경된 AS-IS 매퍼 SQL만 EXPLAIN 검증"),
    ] = False,
):
    """MyBatis 매퍼 SQL EXPLAIN 정합성 및 SQL Drift 검증"""
    import json

    from yunhee.tools.as_is.sql_checker import check_sql_drift, check_tobe_sql

    if old:
        if not old.is_dir():
            typer.secho(f"[ERROR] 이전 AS-IS 디렉터리를 찾을 수 없습니다: {old}", fg=typer.colors.RED)
            raise typer.Exit(1)
        res = check_sql_drift(
            old_root=old,
            new_root=new or src_root or ASIS_SRC_DIR,
            tobe_dir=tobe,
            only_tobe=only_tobe,
            fmt=output or "md",
        )
        if not res.ok and not res.data:
            typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
            raise typer.Exit(1)
        summary_md = res.data.get("summary_text", "")
        out_content = json.dumps(res.data, ensure_ascii=False, indent=2) if output == "json" else summary_md
        typer.echo(out_content)

        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(out_content, encoding="utf-8")
            typer.secho(f"✓ 결과 저장: {target}", fg=typer.colors.GREEN)
        return

    if tobe:
        if not tobe.is_dir() and not tobe.is_file():
            cand = getattr(config, "TOBE_SRC_DIR", config.WORK_DIR) / tobe
            if cand.is_dir() or cand.is_file():
                tobe = cand
            else:
                typer.secho(f"[ERROR] TOBE 매퍼 경로를 찾을 수 없습니다: {tobe}", fg=typer.colors.RED)
                raise typer.Exit(1)
        res = check_tobe_sql(tobe, db=db, only=only, changed=changed, summary=summary)
        if not res.ok and not res.data:
            typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
            raise typer.Exit(1)
        print(res.data.get("summary", ""))
        if not res.ok:
            raise typer.Exit(1)
        return

    root = src_root if src_root is not None else ASIS_SRC_DIR
    if not root or not root.is_dir():
        typer.secho(
            f"[ERROR] AS-IS 소스 디렉터리를 찾을 수 없습니다: {root}\n"
            f"인자로 소스 경로를 넘기거나 .env.local의 YUNHEE_ASIS_SRC_DIR를 설정하세요.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    out_file = target if target is not None else find_as_is_dir() / "sql-check.md"

    src_idx = src_index
    if src_idx is None:
        cand = find_as_is_dir("src")
        if cand.is_dir():
            src_idx = cand

    typer.echo(f"[INFO] AS-IS 매퍼 SQL 정합성 검증 중 (DB: {db}) ...")
    res = check_sql(root, out_file, db=db, src_index_dir=src_idx, new_since_index=new_since_index)
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
        raise typer.Exit(1)

    d = res.data
    if new_since_index:
        if target is not None:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(d.get("report_md", ""), encoding="utf-8")
        typer.echo(d.get("report_md", "").strip())
        return
    typer.secho(f"✅ SQL 정합성 검증 완료: {d['target_file']}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  - 대상 DB: {db}, 총 SQL: {d['total_sql']}개")
    typer.echo(f"  - 통과: {d['passed_count']}개")
    typer.echo(f"  - 스키마 차이(없는 테이블/컬럼): {d['schema_diff_count']}개 (영향 화면 {d['affected_screens_count']}개)")
    typer.echo(f"  - DB 환경 차이(collation 등): {d['env_diff_count']}개")
    typer.echo(f"  - 기타/한계: {d['other_count']}개")


@app.command(name="events")
def events_cmd(
    target: Annotated[
        str,
        typer.Argument(help="Java 소스 파일 경로 또는 클래스명 (예: Sys01_Tab_Company)"),
    ],
    src: Annotated[
        Path | None,
        typer.Option("--src", "-s", help="AS-IS 소스 루트 디렉토리 (미지정 시 YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    button_types: Annotated[
        Path | None,
        typer.Option(
            "--button-types",
            "-b",
            help="버튼 타입 매핑 TSV 경로 (기본: docs/as-is/button-types.tsv → docs/button-types.tsv → data/button-types.tsv)",
        ),
    ] = None,
    ids: Annotated[
        bool,
        typer.Option("--ids", help="E-id 목록만 간단히 출력 (event-check 대조용)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="JSON 형식으로 출력"),
    ] = False,
):
    """AS-IS GXT 화면 이벤트(E0..En)·메서드·그리드·버튼 추출"""
    file_path: Path | None = None
    p = Path(target)
    if p.is_file():
        file_path = p
    else:
        target_name = target if target.endswith(".java") else f"{target}.java"
        # 1. --src 옵션 디렉터리 우선 탐색
        found = []
        if src and src.is_dir():
            found = list(src.glob(f"**/{target_name}"))
        # 2. ASIS_SRC_DIR 탐색
        if not found and ASIS_SRC_DIR and ASIS_SRC_DIR.is_dir():
            found = list(ASIS_SRC_DIR.glob(f"**/{target_name}"))
        # 3. WORK_DIR 탐색
        if not found:
            found = list(WORK_DIR.glob(f"**/{target_name}"))

        if found:
            file_path = found[0]

    if not file_path or not file_path.is_file():
        typer.secho(f"[ERROR] 대상 Java 파일을 찾을 수 없습니다: {target}", fg=typer.colors.RED)
        raise typer.Exit(1)

    text = file_path.read_text(encoding="utf-8", errors="replace")
    total_lines = text.count("\n") + 1
    file_label = get_source_label(file_path, total_lines)
    ev_list, method_list = extract_events_and_methods(text, file_path=file_path)
    grid_spec = extract_grid_spec(text, file_path=file_path)
    buttons = extract_buttons(text, events=ev_list, file_path=file_path, button_types_path=button_types)

    unknowns = [b.label for b in buttons if b.button_type == "unknown"]
    if unknowns and not json_output and not ids:
        typer.secho(
            f"💡 [INFO] 미정의 버튼 {len(unknowns)}개 발견: {', '.join(repr(u) for u in unknowns)} (type=\"unknown\")\n"
            f"   → docs/as-is/button-types.tsv 에 '<레이블>\\t<type>' 형태로 추가하면 반영됩니다.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    if json_output:
        import json
        out_obj = {
            "source": file_label,
            "events": [e.to_dict() for e in ev_list],
            "methods": [m.to_dict() for m in method_list],
            "grid_spec": grid_spec,
            "buttons": [b.to_dict() for b in buttons],
        }
        print(json.dumps(out_obj, ensure_ascii=False, indent=2))
        return

    if ids:
        # 상위 및 하위 종속 이벤트 E-id 출력
        for e in ev_list:
            if e.id == "E0":
                typer.echo(f"[{e.id}] {e.source} → {e.action}")
            elif not e.parent_id:
                cond_str = f" {e.condition}" if e.condition else ""
                typer.echo(f"[{e.id}] {e.source}.{e.event_type}{cond_str} (L{e.line}) → {e.action}")
                for sub in e.sub_events:
                    s_cond = f" {sub.condition}" if sub.condition else ""
                    typer.echo(f"       └ [{sub.id}] {sub.source}.{sub.event_type}{s_cond} (L{sub.line}) → {sub.action}")
        return

    # 기본 마크다운 출력
    md_text = render_events_markdown(file_label, ev_list, method_list, grid_spec=grid_spec, buttons=buttons)
    typer.echo(md_text)


@app.command(name="page-style")
def page_style_cmd(
    targets: Annotated[
        list[str] | None,
        typer.Argument(help="판별할 화면 파일 경로 목록 (.tsx / .java) 또는 화면명"),
    ] = None,
    all_scan: Annotated[
        bool,
        typer.Option("--all", "-a", help="모든 *_Tab_* 화면 판별 및 SID별 분포 출력"),
    ] = False,
    compare: Annotated[
        bool,
        typer.Option("--compare", "-c", help="두 화면(AS-IS와 TOBE)의 SID 일치 여부 비교"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="특징·근거까지 JSON 형식으로 출력"),
    ] = False,
    modal: Annotated[
        bool,
        typer.Option("--modal", help="--all과 함께: *_Tab_* 대신 모달(*_Edit_*·*_Lookup_*·*_Popup_*) 판별"),
    ] = False,
):
    """화면 파일(.tsx / .java)의 페이지 스타일 ID(SID) 판별 및 비교

    사용법:
      yunhee page-style Fnd01_Tab_FundSearch.tsx          # TOBE → SID만 출력 (SGVF)
      yunhee page-style Fnd01_Tab_FundSearch.java         # AS-IS → SID만 출력
      yunhee page-style --json a.tsx b.java               # 특징·근거까지 JSON 출력
      yunhee page-style --all [디렉터리]                  # 모든 *_Tab_* 판별 + SID별 분포
      yunhee page-style --all --modal [디렉터리]          # 모든 모달(*_Edit_*·*_Lookup_*·*_Popup_*) 판별 (MF·MG·MFG·MH)
      yunhee page-style --compare <asis.java> <tobe.tsx>  # 두 SID가 같은지 (종료코드 0/1)
    """
    import json

    from yunhee.tools.page_style import (
        SIDS,
        UNKNOWN,
        analyze,
        compare_pages,
        format_line,
        resolve_target_path,
        scan_modal_files,
        scan_tab_files,
    )

    args = targets or []
    scan_tab_files = scan_modal_files if modal else scan_tab_files

    # 1. --compare 모드
    if compare:
        if len(args) != 2:
            typer.secho("사용법: yunhee page-style --compare <asis.java> <tobe.tsx>", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        p1 = resolve_target_path(args[0], prefer_ext=".java")
        if not p1:
            typer.secho(f"오류: 파일을 찾을 수 없습니다: {args[0]}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        p2 = resolve_target_path(args[1], prefer_ext=".tsx")
        if not p2:
            typer.secho(f"오류: 파일을 찾을 수 없습니다: {args[1]}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

        try:
            res = compare_pages(p1, p2)
        except Exception as e:  # noqa: BLE001
            typer.secho(f"오류: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

        if json_output:
            typer.echo(json.dumps(res, ensure_ascii=False))
        else:
            typer.echo(format_line(res["a"]))
            typer.echo(format_line(res["b"]))
            typer.echo(res["message"])
        raise typer.Exit(code=0 if res["same"] else 1)

    # 2. --all 모드 또는 단일 인자가 디렉터리인 경우
    is_dir_arg = bool(args and len(args) == 1 and Path(args[0]).is_dir())
    if all_scan or is_dir_arg:
        target_dir_str = args[0] if is_dir_arg else (args[0] if (args and len(args) == 1) else None)
        if target_dir_str:
            target_dir = Path(target_dir_str)
            if not target_dir.is_dir():
                cand = config.WORK_DIR / target_dir
                if cand.is_dir():
                    target_dir = cand
                elif getattr(config, "TOBE_SRC_DIR", None) and (config.TOBE_SRC_DIR / target_dir).is_dir():
                    target_dir = config.TOBE_SRC_DIR / target_dir
                else:
                    typer.secho(f"오류: 디렉터리를 찾을 수 없습니다: {target_dir_str}", fg=typer.colors.RED, err=True)
                    raise typer.Exit(code=2)
        else:
            target_dir = config.WORK_DIR
            if (
                not scan_tab_files(target_dir)
                and getattr(config, "TOBE_SRC_DIR", None)
                and config.TOBE_SRC_DIR != config.WORK_DIR
                and scan_tab_files(config.TOBE_SRC_DIR)
            ):
                target_dir = config.TOBE_SRC_DIR

        files = scan_tab_files(target_dir)
        if not files:
            typer.secho(f"안내: {target_dir} 아래에 {"모달" if modal else "*_Tab_* 화면"} 파일이 없습니다.", fg=typer.colors.YELLOW, err=True)
            raise typer.Exit(code=0)

        results = []
        for f in files:
            try:
                results.append(analyze(f))
            except Exception as e:  # noqa: BLE001
                typer.secho(f"경고: {f.name} 분석 실패: {e}", fg=typer.colors.YELLOW, err=True)

        if json_output:
            for r in results:
                typer.echo(json.dumps(r, ensure_ascii=False))
        else:
            for r in results:
                typer.echo(format_line(r))
            dist: dict[str, int] = {}
            for r in results:
                dist[r["sid"]] = dist.get(r["sid"], 0) + 1
            typer.echo(f"\n# SID별 분포 ({len(results)}개)")
            for sid in list(SIDS) + [UNKNOWN]:
                if sid in dist:
                    typer.echo(f"{sid:<6} {dist[sid]:3d}")

        has_mismatch = any(r.get("declared") and r["declared"] != r["sid"] for r in results)
        raise typer.Exit(code=1 if has_mismatch else 0)

    # 3. 일반 파일 판별 모드
    if not args:
        typer.secho(
            "사용법: yunhee page-style <파일...> [--all [디렉터리]] [--compare <asis> <tobe>] [--json]",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    resolved_files: list[tuple[str, Path]] = []
    for t in args:
        p = resolve_target_path(t)
        if not p:
            typer.secho(f"오류: 파일을 찾을 수 없습니다: {t}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        resolved_files.append((t, p))

    bad = False
    for _, p in resolved_files:
        try:
            r = analyze(p)
        except Exception as e:  # noqa: BLE001
            typer.secho(f"오류: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)

        if json_output:
            typer.echo(json.dumps(r, ensure_ascii=False))
        elif len(args) == 1 and not r.get("declared"):
            # 단일 파일이고 선언 머리 주석이 없으면 SID만 출력
            typer.echo(r["sid"])
        else:
            typer.echo(format_line(r))

        if r.get("declared") and r["declared"] != r["sid"]:
            bad = True

    raise typer.Exit(code=1 if bad else 0)


@app.command(name="analysis")
def analysis_cmd(
    type_name: Annotated[
        str | None,
        typer.Argument(help="분석 유형 (method, sql, model, grid, screen, ui, tobe, run 등)"),
    ] = None,
    target: Annotated[
        str | None,
        typer.Argument(help="분석 대상 (클래스, 메서드, SQL ID, 화면명, 실행 ID 등)"),
    ] = None,
    extra_targets: Annotated[
        list[str] | None,
        typer.Argument(help="추가 분석 대상 (예: analysis method <클래스> <메서드1> <메서드2>)"),
    ] = None,
    list_types_flag: Annotated[
        bool,
        typer.Option("--list", help="지원하는 모든 분석 유형 목록 출력"),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="출력 형식 (md, json, code, sql). json: screen --list, ui, sql, grid, model"),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="결과 개수 또는 줄 수 제한"),
    ] = None,
    src: Annotated[
        Path | None,
        typer.Option("--src", "-s", help="AS-IS 소스 루트 경로"),
    ] = None,
    src_index: Annotated[
        Path | None,
        typer.Option("--src-index", help="AS-IS 색인 폴더 경로"),
    ] = None,
    server: Annotated[
        bool,
        typer.Option("--server", help="서버 클래스 우선 검색"),
    ] = False,
    client: Annotated[
        bool,
        typer.Option("--client", help="클라이언트 클래스 우선 검색"),
    ] = False,
    with_events: Annotated[
        bool,
        typer.Option("--with-events", help="호출 이벤트(E-id, 줄) 포함"),
    ] = False,
    param: Annotated[
        list[str] | None,
        typer.Option("--param", help="MyBatis/쿼리 파라미터 key=val (반복 가능)"),
    ] = None,
    count: Annotated[
        bool,
        typer.Option("--count", help="SQL 행 수만 카운트 실행"),
    ] = False,
    db: Annotated[
        str | None,
        typer.Option("--db", help="DB 환경변수 이름"),
    ] = None,
    sql_id: Annotated[
        str | None,
        typer.Option("--sql", help="연관 SQL ID (model 분석 등)"),
    ] = None,
    cls_name: Annotated[
        str | None,
        typer.Option("--class", help="화면 하위 클래스 필터링"),
    ] = None,
    method: Annotated[
        str | None,
        typer.Option("--method", "-m", help="특정 메서드 필터링 (grid 등)"),
    ] = None,
    section: Annotated[
        str | None,
        typer.Option("--section", help="절 필터링 (services, tables, ui, events, methods, grid, buttons, layout, source)"),
    ] = None,
    list_classes: Annotated[
        bool,
        typer.Option("--list-classes", help="화면 내 하위 클래스 목록 출력 (screen --list)"),
    ] = False,
    done: Annotated[
        str | None,
        typer.Option("--done", help="1단계 완료 클래스 목록 (콤마 구분)"),
    ] = None,
    later: Annotated[
        str | None,
        typer.Option("--later", help="2단계 등 이후 클래스 목록"),
    ] = None,
    tobe: Annotated[
        str | None,
        typer.Option("--tobe", help="대조할 TOBE 소스 경로 또는 디렉터리 (쉼표 구분 복수 지정 가능)"),
    ] = None,
    no_cte: Annotated[
        bool,
        typer.Option("--no-cte", help="CTE 블록을 생략하고 본문 SELECT/WHERE만 출력 (sql 분석)"),
    ] = False,
    stdout: Annotated[
        bool,
        typer.Option("--stdout", help="실행 로그의 STDOUT 부분만 출력"),
    ] = False,
    stderr: Annotated[
        bool,
        typer.Option("--stderr", help="실행 로그의 STDERR 부분만 출력"),
    ] = False,
    json_flag: Annotated[
        bool,
        typer.Option("--json", help="마지막 JSON 행 추출"),
    ] = False,
    keys: Annotated[
        str | None,
        typer.Option("--keys", help="JSON 추출 키 목록 (콤마 구분)"),
    ] = None,
    tests: Annotated[
        bool,
        typer.Option("--tests", help="테스트 실행 결과 통계 요약"),
    ] = False,
    no_linked: Annotated[
        bool,
        typer.Option("--no-linked", help="연결 컴포넌트를 합계 및 목록에서 제외"),
    ] = False,
    no_e0: Annotated[
        bool,
        typer.Option("--no-e0", help="E0(화면 열림/생성자)을 이벤트 집계에서 제외"),
    ] = False,
    called_from: Annotated[
        str | None,
        typer.Option("--called-from", help="호출 클래스 기준 오버로드 선택"),
    ] = None,
    check_columns: Annotated[
        bool,
        typer.Option("--check-columns/--no-check-columns", help="그리드 열의 모델·SQL·테이블 존재 검증 (기본 켬)"),
    ] = True,
    grep: Annotated[
        str | None,
        typer.Option("--grep", help="코드/본문 패턴 검색"),
    ] = None,
    context_lines: Annotated[
        int,
        typer.Option("-C", "--context", help="패턴 검색 시 전후 출력 줄 수 (기본: 2)"),
    ] = 2,
    follow: Annotated[
        bool,
        typer.Option("--follow", help="서버 메서드 단순 위임 1~2단계 추적"),
    ] = False,
    file_type: Annotated[
        str | None,
        typer.Option("--type", help="서블릿 fileType (servlet 분석 등)"),
    ] = None,
    branch: Annotated[
        list[str] | None,
        typer.Option("--branch", help="분기 조건 지정 key=val (save-script 등)"),
    ] = None,
    unreachable: Annotated[
        str,
        typer.Option("--unreachable", help="도달 불가 이벤트 처리: count(기본) | ignore"),
    ] = "count",
    raw: Annotated[
        bool,
        typer.Option("--raw", help="메서드 분석 시 요약과 함께 원문 코드 출력"),
    ] = False,
    layout_flag: Annotated[
        bool,
        typer.Option("--layout", help="ui 분석 시 폼 레이아웃 상세 함께 출력"),
    ] = False,
    all_overloads: Annotated[
        bool,
        typer.Option("--all-overloads", help="오버로드된 모든 메서드를 한 번에 출력 (method 분석)"),
    ] = False,
):
    """AS-IS·TOBE 통합 분석 (method/sql/model/grid/screen/ui/tobe/run)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  원본 소스를 직접 sed/grep/cat하지 마세요. 필요한 정보(메서드 본문 요약, 실행 가능 SQL, 그리드 컬럼 스펙 등)를
  yunhee analysis <type> <target> 으로 추출하여 컨텍스트 토큰을 절약하세요.
"""
    import inspect

    from rich.console import Console
    from rich.table import Table

    from yunhee.tools import analysis
    from yunhee.tools.analysis.common import AmbiguousTargetError

    # screen 분석에서 target과 함께 --list가 들어오면 screen의 list_classes로 처리
    if list_types_flag and type_name == "screen" and target:
        list_types_flag = False
        list_classes = True

    # 1. --list 플래그 또는 type_name 미지정 시 유형 목록 출력
    if list_types_flag or not type_name:
        types_info = analysis.list_types()
        table = Table(title="yunhee analysis 지원 유형 목록")
        table.add_column("Type", style="cyan", no_wrap=True)
        table.add_column("Target", style="yellow")
        table.add_column("Formats", style="green")
        table.add_column("Description")
        table.add_column("Example", style="dim")

        for t in types_info:
            ex = t["examples"][0] if t["examples"] else ""
            table.add_row(
                t["name"],
                t["target_help"],
                "/".join(t["formats"]),
                t["description"],
                ex,
            )

        console = Console()
        console.print(table)
        if not type_name and not list_types_flag:
            typer.echo("\n사용법: yunhee analysis <type> <대상> [옵션...]")
        return

    mod = analysis.get_type_module(type_name)
    if not mod:
        typer.secho(f"[ERROR] 알 수 없는 분석 유형입니다: {type_name}", fg=typer.colors.RED, err=True)
        typer.echo("지원하는 유형 목록을 확인하려면 'yunhee analysis --list' 를 실행하세요.", err=True)
        raise typer.Exit(code=1)

    # screen의 --list 옵션 호환
    screen_list = list_classes
    if type_name == "screen" and list_types_flag:
        screen_list = True

    # 대상이 필요하지만 주어지지 않은 경우
    if not target and type_name not in ("run",) and not (type_name == "screen" and screen_list):
        typer.secho(
            f"[ERROR] '{type_name}' 분석 대상을 지정하세요: {getattr(mod, 'TARGET_HELP', '')}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    opts = {
        "output": output,
        "limit": limit,
        "src": src,
        "src_index": src_index,
        "server": server,
        "client": client,
        "with_events": with_events,
        "param": param or [],
        "count": count,
        "db": db,
        "sql": sql_id,
        "class": cls_name,
        "method": method,
        "section": section,
        "list": screen_list,
        "done": done,
        "later": later,
        "tobe": tobe,
        "no_cte": no_cte,
        "stdout": stdout,
        "stderr": stderr,
        "json": json_flag,
        "keys": keys,
        "tests": tests,
        "no_linked": no_linked,
        "no_e0": no_e0,
        "called_from": called_from,
        "check_columns": check_columns,
        "grep": grep,
        "context_lines": context_lines,
        "follow": follow,
        "type": file_type,
        "branch": branch or [],
        "unreachable": unreachable,
        "all_overloads": all_overloads,
        "extra_targets": extra_targets or [],
        "raw": raw,
        "layout": layout_flag,
    }

    try:
        resolved_obj = mod.resolve(target or "", opts)
    except AmbiguousTargetError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"[ERROR] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    fmt = output or (getattr(mod, "FORMATS", ("md",))[0])
    try:
        sig = inspect.signature(mod.render)
        if len(sig.parameters) >= 3:
            rendered = mod.render(resolved_obj, fmt=fmt, opts=opts)
        else:
            rendered = mod.render(resolved_obj, fmt=fmt)
        typer.echo(rendered)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"[ERROR] 렌더링 실패: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


log_app = typer.Typer(
    help="서버 로그 분석 및 요청·SQL·에러 요약 (trace, req, errors, tail)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(log_app, name="log")


# --since-run 옵션의 인자 없는 호출을 'last'로 보정
if "--since-run" in sys.argv:
    for idx, a in enumerate(sys.argv):
        if a == "--since-run" and (idx + 1 >= len(sys.argv) or sys.argv[idx + 1].startswith("-")):
            sys.argv.insert(idx + 1, "last")

# --wait-deploy 옵션의 인자 없는 호출을 '60'으로 보정
if "--wait-deploy" in sys.argv:
    for idx, a in enumerate(sys.argv):
        if a == "--wait-deploy" and (idx + 1 >= len(sys.argv) or sys.argv[idx + 1].startswith("-")):
            sys.argv.insert(idx + 1, "60")


@log_app.command(name="request")
@log_app.command(name="trace")
def log_trace_cmd(
    trace_id: Annotated[str, typer.Argument(help="조회할 trace ID (16진수)")],
    sql: Annotated[bool, typer.Option("--sql", help="실행 가능한 바인딩 SQL 포함")] = False,
    raw: Annotated[bool, typer.Option("--raw", help="원문 로그 출력")] = False,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
    archived: Annotated[bool, typer.Option("--archived", help="지난 날짜의 압축 로그(archived/*.gz)까지 검색")] = False,
    file: Annotated[str | None, typer.Option("--file", "-f", help="직접 읽을 로그 파일 경로")] = None,
    source: Annotated[str | None, typer.Option("--source", help="로그 소스 (docker 또는 local)")] = None,
    docker: Annotated[str | None, typer.Option("--docker", help="Docker 컨테이너 이름 (기본: YUNHEE_LOG_DOCKER)")] = None,
    dir: Annotated[str | None, typer.Option("--dir", help="로그 디렉터리 경로")] = None,
    app_name: Annotated[str | None, typer.Option("--app", help="로그 앱 접두어")] = None,
    tz: Annotated[str | None, typer.Option("--tz", help="로그 파일에 쓰인 시각의 시간대 (docker 기본 UTC — 보통 지정하지 않음, --file과 함께 쓸 때만)")] = None,
) -> None:
    """단일 요청(trace)의 실행 요약 또는 원문 출력"""
    from yunhee.tools.log_reader import DockerExecError, get_trace_summary

    if not re.fullmatch(r"[0-9a-fA-F]{8,32}", trace_id):
        typer.secho("오류: trace ID는 16진수 (8~32자)", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    try:
        res = get_trace_summary(
            trace_id=trace_id,
            file_path=file,
            source=source,
            docker_container=docker,
            log_dir=dir,
            app=app_name,
            log_tz=tz,
            raw=raw,
            show_sql=sql,
            archived=archived,
            mask=not no_mask,
        )
    except DockerExecError as e:
        typer.secho(f"{e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res)


@log_app.command(name="req")
def log_req_cmd(
    method: Annotated[str, typer.Argument(help="HTTP 메서드 (GET, POST 등)")],
    path: Annotated[str, typer.Argument(help="API 경로 일부")],
    last: Annotated[int, typer.Option("--last", "-n", help="표시할 최근 요청 수 (기본: 5)")] = 5,
    trace: Annotated[bool, typer.Option("--trace", help="가장 최근 요청의 상세 trace 요약 이어붙이기")] = False,
    since: Annotated[str | None, typer.Option("--since", help="지금부터 거슬러 올라간 기간 (예: 30m, 1h)")] = None,
    from_time: Annotated[str | None, typer.Option("--from", help="시작 시각, 호스트 시간대(KST) — 예: 15:10, 2026-10-08 15:10")] = None,
    to_time: Annotated[str | None, typer.Option("--to", help="종료 시각, 호스트 시간대(KST) — 예: 15:20")] = None,
    since_deploy: Annotated[bool, typer.Option("--since-deploy", help="마지막 배포(앱 시작) 이후")] = False,
    since_run: Annotated[str | None, typer.Option("--since-run", help="명령어 실행 시작 이후 (run id 또는 last)")] = None,
    archived: Annotated[bool, typer.Option("--archived", help="지난 날짜의 압축 로그(archived/*.gz)까지 검색")] = False,
    file: Annotated[str | None, typer.Option("--file", "-f", help="직접 읽을 로그 파일 경로")] = None,
    source: Annotated[str | None, typer.Option("--source", help="로그 소스 (docker 또는 local)")] = None,
    docker: Annotated[str | None, typer.Option("--docker", help="Docker 컨테이너 이름 (기본: YUNHEE_LOG_DOCKER)")] = None,
    dir: Annotated[str | None, typer.Option("--dir", help="로그 디렉터리 경로")] = None,
    app_name: Annotated[str | None, typer.Option("--app", help="로그 앱 접두어")] = None,
    tz: Annotated[str | None, typer.Option("--tz", help="로그 파일에 쓰인 시각의 시간대 (docker 기본 UTC — 보통 지정하지 않음, --file과 함께 쓸 때만)")] = None,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
) -> None:
    """접근 로그에서 지정한 메서드/경로와 일치하는 최근 요청 검색"""
    from yunhee.tools.log_reader import DockerExecError, get_req_summary

    try:
        res = get_req_summary(
            method=method,
            path_pattern=path,
            last=last,
            show_trace=trace,
            file_path=file,
            source=source,
            docker_container=docker,
            log_dir=dir,
            app=app_name,
            log_tz=tz,
            since=since,
            from_time=from_time,
            to_time=to_time,
            since_deploy=since_deploy,
            since_run=since_run,
            archived=archived,
            mask=not no_mask,
        )
    except DockerExecError as e:
        typer.secho(f"{e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res)


@log_app.command(name="errors")
def log_errors_cmd(
    since: Annotated[str | None, typer.Option("--since", help="지금부터 거슬러 올라간 기간 (예: 1h)")] = None,
    from_time: Annotated[str | None, typer.Option("--from", help="시작 시각, 호스트 시간대(KST) — 예: 15:10")] = None,
    to_time: Annotated[str | None, typer.Option("--to", help="종료 시각, 호스트 시간대(KST) — 예: 15:20")] = None,
    since_deploy: Annotated[bool, typer.Option("--since-deploy", help="마지막 배포(앱 시작) 이후")] = False,
    since_run: Annotated[str | None, typer.Option("--since-run", help="명령어 실행 시작 이후 (run id 또는 last)")] = None,
    ignore: Annotated[list[str] | None, typer.Option("--ignore", help="제외할 logger 이름 일부 (반복 가능)")] = None,
    explain: Annotated[bool, typer.Option("--explain", help="Qwen 모델로 원인 요약")] = False,
    archived: Annotated[bool, typer.Option("--archived", help="지난 날짜의 압축 로그(archived/*.gz)까지 검색")] = False,
    file: Annotated[str | None, typer.Option("--file", "-f", help="직접 읽을 로그 파일 경로")] = None,
    source: Annotated[str | None, typer.Option("--source", help="로그 소스 (docker 또는 local)")] = None,
    docker: Annotated[str | None, typer.Option("--docker", help="Docker 컨테이너 이름 (기본: YUNHEE_LOG_DOCKER)")] = None,
    dir: Annotated[str | None, typer.Option("--dir", help="로그 디렉터리 경로")] = None,
    app_name: Annotated[str | None, typer.Option("--app", help="로그 앱 접두어")] = None,
    tz: Annotated[str | None, typer.Option("--tz", help="로그 파일에 쓰인 시각의 시간대 (docker 기본 UTC — 보통 지정하지 않음, --file과 함께 쓸 때만)")] = None,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
) -> None:
    """에러 로그(WARN·ERROR)를 묶어서 발생 빈도 및 스택 요약 출력"""
    from yunhee.tools.log_reader import DockerExecError, get_errors_summary

    try:
        res = get_errors_summary(
            file_path=file,
            source=source,
            docker_container=docker,
            log_dir=dir,
            app=app_name,
            log_tz=tz,
            since=since,
            from_time=from_time,
            to_time=to_time,
            since_deploy=since_deploy,
            since_run=since_run,
            ignore_loggers=ignore,
            explain=explain,
            archived=archived,
            mask=not no_mask,
        )
    except DockerExecError as e:
        typer.secho(f"{e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res)


@log_app.command(name="tail")
def log_tail_cmd(
    since: Annotated[str | None, typer.Option("--since", help="지금부터 거슬러 올라간 기간 (예: 10m)")] = None,
    from_time: Annotated[str | None, typer.Option("--from", help="시작 시각, 호스트 시간대(KST) — 예: 15:10")] = None,
    to_time: Annotated[str | None, typer.Option("--to", help="종료 시각, 호스트 시간대(KST) — 예: 15:20")] = None,
    since_deploy: Annotated[bool, typer.Option("--since-deploy", help="마지막 배포(앱 시작) 이후")] = False,
    since_run: Annotated[str | None, typer.Option("--since-run", help="명령어 실행 시작 이후")] = None,
    level: Annotated[str | None, typer.Option("--level", help="필터링할 최소 로그 레벨 (WARN, ERROR 등)")] = None,
    grep: Annotated[str | None, typer.Option("--grep", help="검색할 문자열")] = None,
    trace_only: Annotated[bool, typer.Option("--trace-only", help="요청(trace) 로그만 표시")] = False,
    all: Annotated[bool, typer.Option("--all", help="비-HTTP 요청 및 WebSocket(/ws) 포함 전체 출력")] = False,
    archived: Annotated[bool, typer.Option("--archived", help="지난 날짜의 압축 로그(archived/*.gz)까지 검색")] = False,
    file: Annotated[str | None, typer.Option("--file", "-f", help="직접 읽을 로그 파일 경로")] = None,
    source: Annotated[str | None, typer.Option("--source", help="로그 소스 (docker 또는 local)")] = None,
    docker: Annotated[str | None, typer.Option("--docker", help="Docker 컨테이너 이름 (기본: YUNHEE_LOG_DOCKER)")] = None,
    dir: Annotated[str | None, typer.Option("--dir", help="로그 디렉터리 경로")] = None,
    app_name: Annotated[str | None, typer.Option("--app", help="로그 앱 접두어")] = None,
    tz: Annotated[str | None, typer.Option("--tz", help="로그 파일에 쓰인 시각의 시간대 (docker 기본 UTC — 보통 지정하지 않음, --file과 함께 쓸 때만)")] = None,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
) -> None:
    """최근 로그를 요청(trace) 단위로 접어서 전체 흐름 요약 출력"""
    from yunhee.tools.log_reader import DockerExecError, get_tail_summary

    try:
        res = get_tail_summary(
            level=level,
            grep_pattern=grep,
            trace_only=trace_only,
            show_all=all,
            file_path=file,
            source=source,
            docker_container=docker,
            log_dir=dir,
            app=app_name,
            log_tz=tz,
            since=since,
            from_time=from_time,
            to_time=to_time,
            since_deploy=since_deploy,
            since_run=since_run,
            archived=archived,
            mask=not no_mask,
        )
    except DockerExecError as e:
        typer.secho(f"{e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res)


register_trace_commands(app)


@app.command(name="screen-capture")
@app.command(name="capture", hidden=True)
def screen_capture_cmd(
    screen_id: Annotated[
        str,
        typer.Argument(help="화면번호(예: 1018, 1318) 또는 클래스명(예: Fnd01_Tab_FundSearch)"),
    ],
    extra_args: Annotated[
        list[str] | None,
        typer.Argument(help="login=company/user/pw 형식의 로그인 인자 (예: login=kfstest/104/1111)"),
    ] = None,
    login: Annotated[
        str | None,
        typer.Option("--login", "-l", help="로그인 정보 (예: kfstest/104/1111 또는 login=kfstest/104/1111)"),
    ] = None,
    url: Annotated[
        str,
        typer.Option("--url", "-u", help="접속할 TOBE 기본 URL (기본: http://localhost:8082/AssetERP)"),
    ] = config.CAPTURE_BASE_URL,
    out: Annotated[
        str,
        typer.Option("--out", "-o", help="캡처 저장 루트 폴더 (기본: .yunhee/screen-capture)"),
    ] = config.CAPTURE_OUT_DIR,
    title: Annotated[
        str | None,
        typer.Option("--title", "-t", help="겸직선택 시 특정 부서/직책/사원ID 지정 (미지정 시 화면 권한 보유 겸직 자동 선택)"),
    ] = None,
    range_opt: Annotated[
        str | None,
        typer.Option("--range", "-r", help="조회 줄의 모든 날짜 범위(시작일~종료일) 입력값 지정 (예: 2025-01-01~2026-12-31)"),
    ] = None,
    set_opts: Annotated[
        list[str] | None,
        typer.Option("--set", "-s", help="조회 줄 특정 라벨 입력값 지정 (반복 가능, 예: --set 승인기간=2025-01-01~2025-12-31 --set 검색=삼성, 중복 라벨은 라벨#2)"),
    ] = None,
    no_popups: Annotated[
        bool,
        typer.Option("--no-popups", help="팝업/Lookup 모달 클릭 순회를 생략하고 본 화면만 캡처"),
    ] = False,
    modal_only: Annotated[
        bool,
        typer.Option("--modal-only", help="팝업/Lookup 캡처 시 전체 화면 대신 모달 영역(.ant-modal-content)만 잘라서 저장"),
    ] = False,
    boxes: Annotated[
        bool,
        typer.Option("--boxes", help="캡처 이미지에 보이는 요소의 좌표 파일(*.boxes.json) 함께 저장"),
    ] = False,
    click_all: Annotated[
        bool,
        typer.Option("--click-all", help="팝업 순회 시 기본 제외되는 일반/위험 버튼도 클릭 시도 (네트워크 CUD 차단 가드는 유지)"),
    ] = False,
    headed: Annotated[
        bool,
        typer.Option("--headed", help="디버깅용 브라우저 창 표시 (기본: Headless)"),
    ] = False,
    viewport: Annotated[
        str,
        typer.Option("--viewport", help="브라우저 뷰포트 크기 (예: 1920x1080, 1440x810, 1280x720, 720p, 810p, 1080p)"),
    ] = "1920x1080",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="캡처 결과 및 품질 신호 리포트를 JSON으로 출력"),
    ] = False,
) -> None:
    """TOBE 화면 자동 로그인·겸직선택·오픈 및 조회조건(--range/--set)·탭·팝업 순회 캡처와 품질 신호 리포트"""
    import json as json_mod

    from yunhee.tools.screen_capture import (
        capture_screen,
        parse_login_spec,
        parse_viewport_spec,
    )

    login_spec = parse_login_spec(login_arg=login, extra_args=extra_args)

    try:
        vp_w, vp_h = parse_viewport_spec(viewport)
    except ValueError as exc:
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    res = capture_screen(
        screen_id=screen_id,
        login_spec=login_spec,
        base_url=url,
        out_dir=out,
        preferred_title=title,
        include_popups=not no_popups,
        modal_only=modal_only,
        click_all=click_all,
        boxes=boxes,
        range_opt=range_opt,
        set_opts=set_opts,
        headed=headed,
        viewport_width=vp_w,
        viewport_height=vp_h,
    )

    if not res.ok:
        typer.secho(f"오류: {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    data = res.data
    if as_json:
        typer.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))
        return

    title_info = f" · 겸직={data['selected_title']}" if data.get("selected_title") else ""
    typer.secho(
        f"📸 Screen Capture: {data['screen_id']} "
        f"(company={data['company']} · user={data['user']}{title_info})",
        fg=typer.colors.CYAN,
        bold=True,
    )
    typer.echo(f"  • 오픈 방식: {data['open_method']} | 조회 행수: {data['grid_rows_after_search']}건")
    typer.echo(f"  • 저장 폴더: {data['output_dir']} (총 {len(data['captures'])}장, {data['elapsed_sec']}s)")

    # 조회 조건 (--range / --set) 요약
    sc = data.get("search_conditions") or {}
    cond_parts: list[str] = []
    if sc.get("range"):
        r_info = sc["range"]
        cond_parts.append(f"--range {r_info['requested']} ({r_info['status']})")
    for s_item in sc.get("set") or []:
        cond_parts.append(f"--set {s_item['label']}={s_item['value']} ({s_item['status']})")
    if cond_parts:
        typer.echo(f"  • 조회 조건: {' | '.join(cond_parts)}")

    # 경고 (라벨 미발견 등)
    for w in data.get("warnings") or []:
        typer.secho(f"  ⚠ {w}", fg=typer.colors.YELLOW)

    # 그리드별 품질 신호
    grids = data.get("grids") or []
    if grids:
        typer.echo(f"  • 그리드({len(grids)}):")
        for g in grids:
            empty_mark = "빈 그리드(0건)" if g.get("empty") else f"{g.get('row_count', 0)}건"
            hs_mark = "가로스크롤 O" if g.get("horizontal_scroll") else "가로스크롤 X"
            wh_list = g.get("wrapped_headers") or []
            wh_mark = f"헤더줄바꿈/잘림: {', '.join(wh_list)}" if wh_list else "헤더줄바꿈 없음"
            typer.echo(f"    - Grid #{g['index']}: {empty_mark} | {hs_mark} | {wh_mark}")
    else:
        typer.echo("  • 그리드(0): 그리드 없음")

    # 버튼 목록 및 비활성 여부
    btns = data.get("buttons") or []
    if btns:
        btn_strs = [f"{b['label']}(비활성)" if b.get("disabled") else b["label"] for b in btns]
        typer.echo(f"  • 화면 버튼: {', '.join(btn_strs)}")

    # 가로 스크롤 여부
    hs = data.get("horizontal_scroll") or {}
    typer.echo(
        f"  • 가로 스크롤: 화면={'발생' if hs.get('page') else '없음'} / 그리드={'발생' if hs.get('grids') else '없음'}"
    )

    # 팝업 순회 결과
    pt = data.get("popup_traversal") or {}
    if not no_popups and pt:
        opened_m = pt.get("opened_modals") or []
        not_opened_b = pt.get("not_opened_buttons") or []
        skipped_d = pt.get("skipped_dangerous") or []
        opened_str = (
            ", ".join(f"[{m['trigger']}]→{m['modal_title']}" for m in opened_m)
            if opened_m
            else "없음"
        )
        not_opened_str = (
            ", ".join(f"[{b['label']}]({b['reason']})" for b in not_opened_b)
            if not_opened_b
            else "없음"
        )
        typer.echo(f"  • 팝업 순회: 열림={opened_str} | 미열림={not_opened_str}")
        if skipped_d:
            typer.echo(f"    (안전 제외 버튼: {', '.join(skipped_d)})")

    # 이상 신호 요약
    anomalies = data.get("anomalies") or []
    if anomalies:
        typer.secho(f"  🔎 품질 이상 신호: {' / '.join(anomalies)}", fg=typer.colors.YELLOW, bold=True)
    else:
        typer.secho("  🔎 품질 이상 신호: 없음 (정상)", fg=typer.colors.GREEN)

    for c in data["captures"]:
        boxes_info = f" (+{c['boxes']})" if c.get("boxes") else ""
        typer.secho(f"    ✔ {c['filename']:<32} — {c['description']}{boxes_info}", fg=typer.colors.GREEN)

    if data.get("console_errors"):
        typer.secho(f"  ⚠ Console Errors ({len(data['console_errors'])}):", fg=typer.colors.YELLOW)
        for err in data["console_errors"][:5]:
            typer.echo(f"    - {err}")
    if data.get("api_failures"):
        typer.secho(f"  ✖ API Failures ({len(data['api_failures'])}):", fg=typer.colors.RED)
        for fail in data["api_failures"][:5]:
            typer.echo(f"    - {fail}")


@app.command(name="screen-desc")
@app.command(name="scree-desc", hidden=True)
def screen_desc_cmd(
    targets: Annotated[
        list[str],
        typer.Argument(
            help="조회할 화면번호 또는 화면 클래스명 (쉼표 ',', 공백 ' ' 혼합 구분 가능, 예: 1111,2222,3333, 4444)"
        ),
    ],
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="출력 포맷 지정: md(기본) 또는 json",
        ),
    ] = "md",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="JSON 포맷으로 출력 (--format=json 단축 옵션)"),
    ] = False,
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 프로젝트 루트 경로 (기본: YUNHEE_TOBE_SRC_DIR)"),
    ] = None,
    summary: Annotated[
        bool,
        typer.Option("--summary", "-s", help="각 절의 긴 목록을 상위 몇 개로 축약 표시"),
    ] = False,
    section: Annotated[
        str | None,
        typer.Option(
            "--section",
            help="특정 절만 필터링하여 출력 (tobe, popup, tabs, backend, asis, events — 쉼표 구분 가능)",
        ),
    ] = None,
) -> None:
    """화면번호(쉼표·공백 복수 지정 가능)와 관련된 모든 정보(메뉴명·파일명·팝업·하위컴포넌트·그리드·버튼·API·SQL·테이블·ASIS) 반환"""
    from yunhee.tools.trace.screen_desc import (
        describe_screens,
        parse_screen_targets,
        render_screen_desc_json,
        render_screen_desc_md,
    )

    parsed = parse_screen_targets(targets)
    if not parsed:
        typer.secho("오류: 조회할 화면번호(예: 1002, 1029)를 1개 이상 지정하세요.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    norm_fmt = "json" if as_json else fmt.strip().lower()
    if norm_fmt not in ("md", "markdown", "json"):
        typer.secho(
            f"오류: 지원하지 않는 --format 값입니다: '{fmt}' ('md' 또는 'json' 사용)",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    data = describe_screens(parsed, tobe=tobe)
    if norm_fmt == "json":
        typer.echo(render_screen_desc_json(data))
    else:
        typer.echo(render_screen_desc_md(data, summary=summary, section=section).rstrip())


@app.command(name="mark")
def mark_cmd(
    png: Annotated[
        Path,
        typer.Argument(help="마킹할 대상 원본 PNG 이미지 파일 경로"),
    ],
    draw: Annotated[
        Path,
        typer.Argument(help="그릴 요소 명세 파일 (draw.json)"),
    ],
    boxes: Annotated[
        Path | None,
        typer.Option("--boxes", "-b", help="요소 좌표 파일 (*.boxes.json, 생략 시 <png>.boxes.json 자동 탐색)"),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="마킹 결과 저장 파일 경로 (기본: <이름>-alpha.png)"),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="해석된 최종 요소 목록을 JSON으로 출력"),
    ] = False,
) -> None:
    """캡처 PNG 위에 번호 원·강조 상자·화살표·말풍선·마스킹을 그려 매뉴얼 이미지를 만든다"""
    import json as json_mod

    from yunhee.tools.marker import mark_image

    res = mark_image(
        png_path=png,
        draw_spec=draw,
        boxes_path=boxes,
        out_path=out,
    )

    if not res.ok:
        typer.secho(f"오류: {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    data = res.data
    if as_json:
        typer.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))
        return

    for w in data.get("warnings") or []:
        typer.secho(f"  ⚠ {w}", fg=typer.colors.YELLOW)

    in_size = f"{data['input_size'][0]}x{data['input_size'][1]}"
    out_size = f"{data['output_size'][0]}x{data['output_size'][1]}"
    size_str = in_size if in_size == out_size else f"{in_size} → {out_size} (crop)"

    typer.secho(
        f"🎨 Mark: {data['output_png']} ({data['item_count']}개 요소 마킹 · {size_str})",
        fg=typer.colors.CYAN,
        bold=True,
    )


@app.command(name="biz-endpoints")
def biz_endpoints(
    target: Annotated[str, typer.Argument(help="도메인명 (예: att, pay) 또는 컨트롤러 .java 파일 경로")],
    path: Annotated[str | None, typer.Option("--path", help="경로 필터링 문자열 (예: annuals)")] = None,
    output: Annotated[str, typer.Option("-o", "--output", help="출력 형식 (md, json, tsv)")] = "md",
) -> None:
    """TOBE API 엔드포인트 목록 및 파라미터·본문 DTO·서비스·권한검사 표 출력"""
    import json

    from yunhee.tools.biz.endpoints import (
        collect_endpoints,
        format_endpoints_json,
        format_endpoints_md,
        format_endpoints_tsv,
    )

    endpoints = collect_endpoints(target, path_filter=path)
    if not endpoints:
        typer.secho(f"조회된 엔드포인트가 없습니다: target={target}, path={path}", fg=typer.colors.YELLOW, err=True)
        return

    fmt = output.lower()
    if fmt == "json":
        typer.echo(json.dumps(format_endpoints_json(endpoints), ensure_ascii=False, indent=2))
    elif fmt == "tsv":
        typer.echo(format_endpoints_tsv(endpoints))
    else:
        typer.echo(format_endpoints_md(endpoints))


@app.command(name="biz-authz")
def biz_authz(
    target: Annotated[str, typer.Argument(help="도메인명 (예: att, pay) 또는 컨트롤러 .java 파일 경로")],
    as_user: Annotated[str, typer.Option("--as", "-u", help="낮은 권한 사번/계정 (예: 401)")] = "401",
    company: Annotated[str, typer.Option("--company", "-c", help="회사 코드 (예: kalpa)")] = "kalpa",
    password: Annotated[str | None, typer.Option("--password", help="계정 비밀번호")] = None,
    path: Annotated[str | None, typer.Option("--path", help="경로 필터링 문자열")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="공통 쿼리 파라미터 key=val (반복 가능)")] = None,
    probe_write: Annotated[bool, typer.Option("--probe-write", help="쓰기 API에 빈 본문으로 안전하게 인가 검사 프로빙")] = False,
    probe_delete: Annotated[bool, typer.Option("--probe-delete", help="DELETE API까지 프로빙")] = False,
    emit_rows: Annotated[bool, typer.Option("--emit-rows", help="보안 의심 마크다운 보고서용 행 목록 출력")] = False,
    output: Annotated[str, typer.Option("-o", "--output", help="출력 형식 (md, json)")] = "md",
) -> None:
    """사원 권한으로 도메인 API 권한 훑기 및 관리자 자료 노출(BOLA/IDOR) 기계적 판정"""
    import json

    from yunhee.tools.biz.authz import format_authz_md, run_authz
    from yunhee.tools.biz.endpoints import collect_endpoints

    endpoints = collect_endpoints(target, path_filter=path)
    if not endpoints:
        typer.secho(f"조회된 엔드포인트가 없습니다: target={target}, path={path}", fg=typer.colors.YELLOW, err=True)
        return

    common_params = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                common_params[k.strip()] = v.strip()

    results = run_authz(
        endpoints=endpoints,
        as_user=as_user,
        company=company,
        password=password,
        probe_write=probe_write,
        probe_delete=probe_delete,
        common_params=common_params,
    )

    if output.lower() == "json":
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_authz_md(results, as_user=as_user, emit_rows=emit_rows))


@app.command(name="biz-appr")
def biz_appr(
    link_code: Annotated[str, typer.Argument(help="전자결재 연동 코드 (예: A74, A73, D01)")],
    ref: Annotated[int, typer.Option("--ref", help="연동할 업무 데이터 행 ID (refId) 및 링크 대상")],
    as_user: Annotated[str, typer.Option("--as", "-u", help="상신자 사번/계정 (기본: 401)")] = "401",
    company: Annotated[str, typer.Option("--company", "-c", help="회사 코드 (기본: kalpa)")] = "kalpa",
    approver: Annotated[str | None, typer.Option("--approver", help="결재자 사번 목록 (쉼표 구분, 예: 301 또는 201,100)")] = None,
    password: Annotated[str | None, typer.Option("--password", help="계정 비밀번호")] = None,
    class_id: Annotated[int | None, typer.Option("--class", help="문서분류 ID (생략 시 dcr30_link에서 자동 조회)")] = None,
    confirm: Annotated[bool, typer.Option("--confirm", help="상신 후 결재자 승인(30 완료)까지 순서대로 실행")] = False,
    reject: Annotated[str | None, typer.Option("--reject", help="마지막 결재자가 반려 처리 (반려 사유 입력)")] = None,
    link_path: Annotated[str | None, typer.Option("--link-path", help="업무 행 연결 API 경로 (예: /api/v1/.../{ref}/appr)")] = None,
    link_style: Annotated[str | None, typer.Option("--link-style", help="업무 행 연결 파라미터 전달 스타일 (query 또는 body)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="실제 호출하지 않고 조립된 상신 본문 JSON만 출력")] = False,
) -> None:
    """전자결재 상신·업무 행 연결·결재자 승인(또는 반려) 원스톱 자동 실행"""
    from yunhee.tools.biz.appr import run_appr

    approvers_list = [a.strip() for a in approver.split(",") if a.strip()] if approver else []
    try:
        lines = run_appr(
            link_code=link_code,
            ref_id=ref,
            as_user=as_user,
            company=company,
            approvers=approvers_list,
            password=password,
            class_id=class_id,
            confirm=confirm,
            reject=reject,
            link_path=link_path,
            link_style=link_style,
            dry_run=dry_run,
        )
        for line in lines:
            typer.echo(line)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="biz-patch")
def biz_patch(
    path: Annotated[str, typer.Argument(help="조회 및 수정할 API 경로 (예: /api/v1/sys/companies/{id}/account)")],
    set_fields: Annotated[list[str], typer.Option("--set", help="변경할 필드 key=val (반복 가능, 예: commutePopupYn=true)")],
    where: Annotated[list[str] | None, typer.Option("--where", help="--list 목록 중 특정 행을 고르는 조건 key=val (반복 가능)")] = None,
    is_list: Annotated[bool, typer.Option("--list", help="GET 응답이 목록 형태인 경우 한 행을 골라 리스트로 감싸 저장")] = False,
    put_path: Annotated[str | None, typer.Option("--put", help="저장 경로가 GET 경로와 다를 때 지정")] = None,
    drop_suffix: Annotated[str, typer.Option("--drop-suffix", help="제거할 읽기 전용 필드 접미사 (기본: Nm, 쉼표 구분)")] = "Nm",
    keep: Annotated[str | None, typer.Option("--keep", help="보존하여 전송할 키 목록 (쉼표 구분)")] = None,
    method: Annotated[str, typer.Option("--method", help="저장 HTTP 메서드 (기본: PUT)")] = "PUT",
    as_user: Annotated[str, typer.Option("--as", "-u", help="로그인 계정/사번 (기본: admin)")] = "admin",
    company: Annotated[str, typer.Option("--company", "-c", help="회사 코드 (기본: kalpa)")] = "kalpa",
    password: Annotated[str | None, typer.Option("--password", help="계정 비밀번호")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="실제 저장하지 않고 전송할 본문 JSON만 확인")] = False,
) -> None:
    """조회(GET)한 데이터의 지정 필드만 안전하게 변경하여 저장(PUT)하고 미변경 칸 소실 검증"""
    from yunhee.tools.biz.patch import run_patch

    drop_suffixes = [s.strip() for s in drop_suffix.split(",") if s.strip()]
    keep_keys = [k.strip() for k in keep.split(",") if k.strip()] if keep else None

    try:
        lines, warnings = run_patch(
            path=path,
            sets=set_fields,
            where=where,
            is_list=is_list,
            put_path=put_path,
            drop_suffixes=drop_suffixes,
            keep_keys=keep_keys,
            method=method,
            as_user=as_user,
            company=company,
            password=password,
            dry_run=dry_run,
        )
        for line in lines:
            typer.echo(line)
        for w in warnings:
            typer.secho(f"경고: {w}", fg=typer.colors.YELLOW, err=True)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="biz-code")
def biz_code(
    kind_code: Annotated[str | None, typer.Argument(help="공통코드 종류 코드 (예: WorkTypeCode, PaymentTypeCode)")] = None,
    company: Annotated[str | None, typer.Option("--company", "-c", help="회사 코드 (예: kalpa — 지정 시 회사 행 우선 쓰임 표시)")] = None,
    like: Annotated[str | None, typer.Option("--like", help="공통코드 종류 이름 또는 코드 검색어")] = None,
    db: Annotated[str | None, typer.Option("--db", help="데이터베이스 환경변수 이름")] = None,
) -> None:
    """공통코드(sys08_code_kind, sys09_code) 조회 및 f_cdnm 규칙 기반 회사별 우선 적용 확인"""
    from yunhee.tools.biz.code import (
        format_code_table,
        get_code_rows,
        search_code_kinds,
    )

    if like:
        results = search_code_kinds(like, db_name=db)
        if not results:
            typer.echo(f"검색어 '{like}'에 해당하는 공통코드 종류가 없습니다.")
            return
        typer.echo(f"### 검색 결과: '{like}' ({len(results)}건)")
        typer.echo("| 종류 코드 | 종류 이름 | 시스템 공통 여부 |")
        typer.echo("|:---|:---|:---|")
        for r in results:
            sys_str = "공통(0)" if r["sys08_sys_yn"] == "true" else "회사별"
            typer.echo(f"| {r['sys08_kind_cd']} | {r.get('sys08_kind_nm', '')} | {sys_str} |")
        return

    if not kind_code:
        typer.secho("오류: 코드 종류(예: WorkTypeCode) 또는 --like 검색어를 지정하세요.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        kind_info, rows, similar = get_code_rows(kind_code, company_code=company, db_name=db)
        if not kind_info:
            sim_str = ", ".join(similar) if similar else "없음"
            typer.secho(f"⚠ 코드종류 '{kind_code}' 없음 — 비슷한 종류: {sim_str}", fg=typer.colors.YELLOW, err=True)
            return

        typer.echo(format_code_table(kind_info, rows))
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="biz-db-write")
def biz_db_write(
    file: Annotated[str | None, typer.Option("-f", "--file", help="실행할 SQL 파일 경로")] = None,
    expr: Annotated[str | None, typer.Option("-e", "--expr", help="직접 실행할 SQL 문장")] = None,
    db: Annotated[str | None, typer.Option("--db", help="데이터베이스 환경변수 이름")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="커밋하지 않고 전체 롤백 (--rollback)")] = False,
    no_backup: Annotated[bool, typer.Option("--no-backup", help="실행 전 자동 백업 생략")] = False,
    allow_ddl: Annotated[bool, typer.Option("--allow-ddl", help="DDL 및 WHERE 절 없는 UPDATE/DELETE 허용")] = False,
) -> None:
    """로컬 DB에 한하여 자동 백업 및 안전 가드를 거쳐 안전하게 SQL 쓰기 및 트랜잭션 실행"""
    from yunhee.tools.biz.dbwrite import execute_db_write

    if not file and not expr:
        typer.secho("오류: 실행할 SQL 파일(-f) 또는 문장(-e)을 지정하세요.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        lines, _ = execute_db_write(
            sql_text=expr,
            file_path=file,
            db_name=db,
            dry_run=dry_run,
            no_backup=no_backup,
            allow_ddl=allow_ddl,
        )
        for line in lines:
            typer.echo(line)
    except (ValueError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="biz-event-new")
def biz_event_new(
    event_id: Annotated[str, typer.Argument(help="이벤트 ID (예: PAY-BZ-0004)")],
    screens: Annotated[str, typer.Option("--screens", help="화면 번호 (쉼표로 구분, 예: 1270,1281)")],
    title: Annotated[str, typer.Option("--title", help="이벤트 제목")] = "",
    company: Annotated[str | None, typer.Option("-c", "--company", help="회사 코드 (예: kalpa)")] = None,
    force: Annotated[bool, typer.Option("--force", help="이미 존재하는 파일 덮어쓰기")] = False,
    out: Annotated[str | None, typer.Option("--out", help="출력 파일 경로")] = None,
    db: Annotated[str | None, typer.Option("--db", help="데이터베이스 환경변수 이름")] = None,
) -> None:
    """AS-IS/TOBE 화면 색인을 바탕으로 이벤트 분석 문서 틀 생성"""
    from yunhee.tools.biz.eventdoc import generate_biz_event_doc

    screen_list = [s.strip() for s in re.split(r"[,;\s]+", screens) if s.strip()]
    if not screen_list:
        typer.secho("오류: 화면 번호를 1개 이상 지정하세요 (--screens).", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        out_path, _ = generate_biz_event_doc(
            event_id=event_id,
            screens=screen_list,
            title=title,
            company=company,
            force=force,
            out=out,
            root_dir=config.WORK_DIR,
            db_name=db,
        )
        typer.secho(f"생성됨: {out_path}", fg=typer.colors.GREEN)
    except FileExistsError as exc:
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"오류: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
