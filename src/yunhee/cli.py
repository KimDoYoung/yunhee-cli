import os
import re
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
from yunhee.store.vectorstore import add_texts
from yunhee.store.vectorstore import search as vector_search
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
from yunhee.ui.repl import run_repl

app = typer.Typer(rich_markup_mode="rich")


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
    """[bold cyan]yunhee[/bold cyan]: 상용 AI 코딩 에이전트(Claude CLI, Antigravity CLI 등)의 토큰 절약을 위한 독립 로컬 Agent CLI.

[bold yellow]🤖 AI Coding Agent 권장 워크플로우 (Token-Saving Protocol)[/bold yellow]
  1. [bold green]TOBE 위치 파악[/bold green]: 파일 전체 읽기 금지! [cyan]yunhee outline <경로>[/cyan] 로 시그니처와 줄 번호만 확인
  2. [bold green]DB 스키마 조회[/bold green]: DDL 검색 대신 [cyan]yunhee table <TablePattern>[/cyan] 로 필요한 DBML만 추출
  3. [bold green]빌드/테스트[/bold green]: 셸 직실행 금지! [cyan]yunhee run "<Command>"[/cyan] 로 1줄 성공 / 에러 압축 리포트 수신
  4. [bold green]API 검증[/bold green]: [cyan]yunhee api GET <경로> --as admin[/cyan] 으로 자동 로그인 스모크 테스트 (행 수/키 목록)
  5. [bold green]설정 확인[/bold green]: [cyan]yunhee config[/cyan] 로 Source/Target 폴더 및 DB 설정 확인
  6. [bold green]에이전트 지침서[/bold green]: [cyan]yunhee agent-guide[/cyan] 명령으로 AI 행동 지침서 마크다운 전문 출력
  7. [bold green]변경 이력[/bold green]: [cyan]yunhee changelog --since <이전버전>[/cyan] 으로 yunhee 업데이트 내용만 확인

서브커맨드 없이 실행하면 대화형 REPL로 진입합니다.
"""
    if ctx.invoked_subcommand is None:
        run_repl(model=model)


@app.command()
def chat_cmd(model: str = OLLAMA_MODEL):
    """대화형 REPL 시작 (명시적으로)"""
    run_repl(model=model)

@app.command()
def hello():
    """스캐폴드 동작 확인용"""
    print("yunhee-cli ready")


@app.command()
def ask(prompt: str, model: str = OLLAMA_MODEL):
    """로컬 LLM(qwen2.5-coder 등)에게 질문"""
    print(chat(prompt, model=model))


@app.command()
def vec(text: str):
    """bge-m3 임베딩 확인용"""
    vector = embed(text)
    print(f"dim={len(vector)}")
    print(vector[:5], "...")


@app.command()
def index(text: str):
    """텍스트를 chromadb에 저장"""
    add_texts([text])
    print("indexed.")


@app.command()
def search(query_text: str, n: int = 3):
    """저장된 텍스트 중 유사한 것 검색"""
    results = vector_search(query_text, n_results=n)
    docs = results["documents"][0]
    dists = results["distances"][0]
    for doc, dist in zip(docs, dists):
        print(f"[{dist:.4f}] {doc}")

@app.command(name="config")
def config_cmd():
    """현재 yunhee가 바라보는 설정(Source 경로, Target 경로, DB 접속 정보 등)을 확인"""
    from rich.console import Console
    from rich.table import Table

    from yunhee import config

    table = Table(title="yunhee 설정 정보")
    table.add_column("항목", style="cyan", no_wrap=True)
    table.add_column("현재 설정값", style="green")
    table.add_column("설명 및 변경 방법", style="dim")

    cfg = config.summary()
    table.add_row("Target (Work Dir)", cfg["work-dir"], "현재 터미널 작업 디렉터리 (cd로 이동하여 변경)")
    table.add_row("Source (ASIS)", cfg["asis-src"], ".env.local의 YUNHEE_ASIS_SRC_DIR")
    table.add_row("Local DB", cfg["local-db"], ".env.local의 LOCAL_DB")
    table.add_row("Test DB", cfg["test-db"], ".env.local의 TEST_DB")
    table.add_row("Schema Snapshot", cfg["schema-env"], ".env.local의 YUNHEE_SCHEMA_ENV")
    table.add_row("Yunhee Home", cfg["yunhee-dir"], "yunhee-cli 설치 경로")
    table.add_row("Env File", cfg["env-file"], "설정 파일 (.env.local)")
    table.add_row("Ollama URL", cfg["ollama-url"], ".env.local의 YUNHEE_OLLAMA_URL")
    table.add_row("Ollama Model", cfg["ollama-model"], ".env.local의 YUNHEE_OLLAMA_MODEL")
    table.add_row("API Base URL", cfg["api-base"], ".env.local의 YUNHEE_API_BASE_URL")
    table.add_row("API Login Path", cfg["api-login-path"], ".env.local의 YUNHEE_API_LOGIN_PATH")
    table.add_row("API Admin User", cfg["test-admin-user"], ".env.local의 YUNHEE_TEST_ADMIN_USER")
    table.add_row("API Company", cfg["test-company"], ".env.local의 YUNHEE_TEST_COMPANY")
    table.add_row("API Tenant Host", cfg["api-tenant-host"], ".env.local의 YUNHEE_API_TENANT_HOST")

    console = Console()
    console.print(table)



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
    """환경변수(LOCAL_DB 등)의 PostgreSQL에 읽기 전용으로 접속해 스키마를 DBML+SQL 마크다운으로 저장 (make-dbml == dbml, 완전히 동일)"""
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

    out_file = output or WORK_DIR / f"{env_name}-dbml.md"
    out_file.write_text(render_markdown(result.data, source=env_name, source_url=redact(dsn)))
    summary = ", ".join(f"{k} {v}" for k, v in counts(result.data).items() if v)
    print(f"저장됨: {out_file} ({summary or '객체 없음'})")
    print(f"스냅샷: {save_snapshot(env_name, result.data)} ('yunhee table'/'prepare'가 사용)")


app.command(name="make-dbml")(_make_dbml)
app.command(name="dbml")(_make_dbml)


@app.command()
def table(
    names: Annotated[list[str] | None, typer.Argument(help="테이블 이름 (schema.table, glob * ? 가능)")] = None,
    page: Annotated[str | None, typer.Option("--page", help="ASIS 페이지 코드 — mapper가 참조하는 테이블 전부")] = None,
    db: Annotated[str, typer.Option("--db", help="스키마 스냅샷 (make-dbml의 환경변수 이름)")] = SCHEMA_ENV,
):
    """스키마 스냅샷에서 지정한 테이블만 DBML로 출력 (DB 접속·LLM 호출 없음)

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
    timeout: Annotated[int, typer.Option("--timeout", "-t", help="타임아웃(초)")] = 120,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="실패 시 로컬 Qwen 요약을 건너뜀")] = False,
    raw: Annotated[bool, typer.Option("--raw", help="요약 없이 원시 출력을 그대로 출력")] = False,
):
    """외부 명령어(빌드, 테스트, 스크립트 등)를 실행하고 원시 로그는 .yunhee/runs에 격리 저장하며 Qwen 에러 압축 리포트 출력 (run == exec)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  mvn, gradle, npm, pytest 등을 직접 실행하지 마세요. 수천 줄의 빌드 로그 대신 이 명령으로 Qwen의 10~20줄 핵심 에러 요약만 받아 디버깅하세요.
"""
    from yunhee.context.run_analyzer import summarize_run
    from yunhee.store import run_tracker
    from yunhee.tools.runner import execute_command

    cur_cwd = Path.cwd()
    project_root = project.find_project_root(cur_cwd)
    result = execute_command(command, cwd=cur_cwd, timeout=timeout)
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
            cwd=cur_cwd,
        )
        print(summary)

    run_tracker.save_run(
        run_id=data["run_id"],
        project=project_name,
        command=data["command"],
        exit_code=data["exit_code"],
        duration_ms=data["duration_ms"],
        log_path=data["log_path"],
        summary=summary,
        cwd=data.get("cwd"),
    )

    if data["exit_code"] != 0:
        raise typer.Exit(code=data["exit_code"] if 0 <= data["exit_code"] <= 255 else 1)


app.command(name="run")(_run_exec)
app.command(name="exec")(_run_exec)


@app.command(name="last-run")
def last_run():
    """가장 최근에 실행한 외부 명령어 결과와 요약을 확인"""
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


@app.command(name="runs")
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
    table.add_column("CWD", style="yellow")
    table.add_column("Created At", style="dim")
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

    console = Console()
    console.print(table)


@app.command()
def outline(
    paths: Annotated[list[str], typer.Argument(help="분석할 파일 또는 디렉터리 경로 (하나 이상)")],
    limit: Annotated[int, typer.Option("--limit", help="최대 글자 수 제한")] = 30000,
):
    """소스 파일(Java, XML, TS/TSX, Python) 또는 디렉터리의 클래스·메서드·시그니처와 줄 번호를 추출 (LLM 호출 없음)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  TOBE 기존 코드(Service, Controller, Mapper XML 등) 전체를 읽지 마세요. 이 명령으로 메서드 위치와 줄 번호를 파악한 뒤 필요한 줄만 핀포인트로 읽으세요.
"""
    from yunhee.tools.outliner import outline_path

    combined_outputs = []
    remaining_limit = limit

    for p in paths:
        if remaining_limit <= 0:
            combined_outputs.append("// ... [글자 수 예산 초과로 이하 생략]")
            break
        res = outline_path(p, char_limit=remaining_limit)
        if not res.ok:
            typer.echo(f"오류: {res.error}", err=True)
            raise typer.Exit(code=1)
        out_text = res.data or ""
        combined_outputs.append(out_text)
        remaining_limit -= len(out_text)

    print("\n\n".join(combined_outputs))


TENANT_REQUIRED_MSG = (
    "오류: 회사 선택 로그인(-c)은 admin 테넌트에서만 됩니다: -t admin "
    "(또는 .yunhee.toml [api] tenant / .env.local YUNHEE_API_DEFAULT_TENANT)"
)


@app.command()
def api(
    method: Annotated[str, typer.Argument(help="HTTP 메서드 (GET, POST, PUT, DELETE)")],
    path: Annotated[str, typer.Argument(help="호출할 API 경로 (예: /api/v1/sys/roles)")],
    as_role: Annotated[str, typer.Option("--as", help="로그인 역할 (admin 또는 user)")] = "admin",
    base: Annotated[str | None, typer.Option("--base", help="기본 URL")] = None,
    login_path: Annotated[str | None, typer.Option("--login-path", help="로그인 엔드포인트 경로 (기본: .env.local의 YUNHEE_API_LOGIN_PATH 또는 /api/auth/login)")] = None,
    company: Annotated[str | None, typer.Option("--company", "-c", help="로그인 시 전달할 회사 코드 (companyCode)")] = None,
    tenant: Annotated[str | None, typer.Option("--tenant", "-t", help="테넌트 식별자 (세션 분리 및 X-Tenant-Id 헤더)")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="쿼리 파라미터 key=val (반복 가능)")] = None,
    body: Annotated[str | None, typer.Option("--body", "-b", help="JSON 요청 본문")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="압축 요약 대신 원본 JSON 본문 출력")] = False,
    timeout: Annotated[float | None, typer.Option("--timeout", help="요청 타임아웃(초) (기본: .env.local의 YUNHEE_API_TIMEOUT 또는 15)")] = None,
):
    """테스트 계정으로 자동 로그인하여 API를 호출하고 응답 요약(상태코드, 행수, 필드목록)을 확인 (LLM 호출 없음)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  수천 줄의 원시 응답 JSON 대신 이 명령으로 행 수(rows=N)와 키 목록만 2~3줄로 확인하여 토큰을 절약하세요.
"""
    import json

    from yunhee import config
    from yunhee.tools import api_client

    params_dict = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                params_dict[k] = v

    json_body = None
    if body:
        try:
            json_body = json.loads(body)
        except Exception as e:  # noqa: BLE001
            typer.echo(f"오류: JSON 본문 파싱 실패: {e}", err=True)
            raise typer.Exit(code=1)

    target_base = base or config.API_BASE_URL
    target_tenant = config.resolve_api_tenant(tenant)

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
        timeout=timeout,
        **kw,
    )

    if not res.ok and not res.data:
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=1)

    if raw:
        print(res.data.get("text", ""))
    else:
        print(res.data.get("summary", ""))

    if not res.ok:
        raise typer.Exit(code=1)


@app.command(name="sql")
def sql_cmd(
    query: Annotated[str | None, typer.Argument(help="실행할 SQL 쿼리")] = None,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="실행할 SQL 파일 경로")] = None,
    rollback: Annotated[bool, typer.Option("--rollback", help="쓰기를 허용하되 반드시 트랜잭션 종료 시 ROLLBACK")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="출력할 최대 행 수 (기본: 5)")] = 5,
    timeout: Annotated[float, typer.Option("--timeout", help="statement_timeout 타임아웃(초) (기본: 10)")] = 10.0,
    var: Annotated[list[str] | None, typer.Option("--var", help="변수 설정 key=val 또는 key=\"select ...\" (반복 가능)")] = None,
    db: Annotated[str | None, typer.Option("--db", help="대상 데이터베이스 환경변수 이름 또는 연결 URL (기본: LOCAL_DB)")] = None,
):
    """PostgreSQL 읽기 전용 쿼리 실행 또는 롤백 시험 (LLM 호출 없음)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  psql 대신 이 명령으로 중복 검사나 행 수를 확인하고, 저장 SQL 시험 시 --rollback 옵션을 사용하세요.
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
        rollback=rollback,
        limit=limit,
        timeout=timeout,
        vars_dict=vars_dict or None,
        db_name=db,
    )
    if not res.ok:
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=1)

    print(res.data.get("summary", ""))


@app.command(name="port-sql")
def port_sql_cmd(
    sql_id: Annotated[str, typer.Argument(help="AS-IS SQL ID (예: sys04_role.selectByName)")],
    cols: Annotated[str | None, typer.Option("--cols", help="추출할 컬럼 목록 (쉼표 구분)")] = None,
    getter_defaults: Annotated[bool, typer.Option("--getter-defaults", help="AS-IS 모델 getter null 기본값을 COALESCE로 적용")] = False,
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
    db: Annotated[str, typer.Option("--db", help="스키마 환경 (기본 LOCAL_DB)")] = SCHEMA_ENV,
    package: Annotated[str | None, typer.Option("--package", help="DTO 패키지 (예: kr.co.kfs.asseterp.biz.sys.dto) — resultType FQN에 사용")] = None,
) -> None:
    """AS-IS SQL을 TOBE 매퍼 조각과 레코드 DTO로 변환 (--cols 순서 = 출력 순서)"""
    from yunhee.tools.as_is.sql_porter import port_sql

    col_list = [c.strip() for c in cols.split(",") if c.strip()] if cols else None
    res = port_sql(
        sql_id=sql_id,
        cols=col_list,
        getter_defaults=getter_defaults,
        src_root=src,
        db_env=db,
        dto_package=package,
    )
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(res.data["output"])


@app.command(name="port-save")
def port_save_cmd(
    table: Annotated[str, typer.Argument(help="대상 테이블명 (예: sys04_role)")],
    cols: Annotated[str, typer.Option("--cols", help="INSERT/UPDATE 대상 컬럼 목록 (쉼표 구분)")],
    company_col: Annotated[str | None, typer.Option("--company-col", help="회사 ID 컬럼명")] = None,
    id_col: Annotated[str | None, typer.Option("--id-col", help="PK ID 컬럼명")] = None,
    company_via: Annotated[str | None, typer.Option("--company-via", help="회사 조건 서브쿼리 경로 (예: emp01_person.emp01_person_id=emp03_person_id)")] = None,
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
) -> None:
    """UpdateDataModel 대신 사용할 명시 INSERT, UPDATE, DELETE 및 부수 효과 SQL 생성"""
    from yunhee.tools.as_is.sql_porter import port_save

    col_list = [c.strip() for c in cols.split(",") if c.strip()]
    res = port_save(
        table=table,
        cols=col_list,
        company_col=company_col,
        id_col=id_col,
        company_via=company_via,
        src_root=src,
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
    api_param: Annotated[list[str] | None, typer.Option("-p", "--param-api", help="API 요청 파라미터 (key=value, 반복 가능)")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", help="SQL 파라미터 (key=value, 반복 가능)")] = None,
    base: Annotated[str | None, typer.Option("--base", "-b", help="API 기본 URL")] = None,
    tenant: Annotated[str | None, typer.Option("--tenant", "-t", help="테넌트 식별자")] = None,
    company: Annotated[str | None, typer.Option("--company", "-c", help="회사 코드")] = None,
    db: Annotated[str, typer.Option("--db", help="대상 DB명 (기본: asseterpdb)")] = "asseterpdb",
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
    grid: Annotated[str | None, typer.Option("--grid", help="대조할 화면/그리드 클래스 (예: Sys05_Page_UserRole)")] = None,
) -> None:
    """조회 API와 AS-IS SQL 행 수 및 그리드 컬럼 커버리지 비교"""
    from yunhee.tools.comparator import compare_api_sql

    api_params_dict = {}
    if api_param:
        for p in api_param:
            if "=" in p:
                k, v = p.split("=", 1)
                api_params_dict[k.strip()] = v.strip()

    sql_params_dict = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                sql_params_dict[k.strip()] = v.strip()

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
        grid=grid,
    )
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    from yunhee.tools.api_client import header_tag

    tag = header_tag(effective_base, effective_tenant, company)
    if tag:
        typer.echo(tag)
    typer.echo(res.data["summary"])


@app.command(name="changelog")
def changelog_cmd(
    version: Annotated[str | None, typer.Argument(help="볼 버전 (예: 0.1.3). 생략 시 현재 설치된 버전")] = None,
    since: Annotated[str | None, typer.Option("--since", help="이 버전 이후(미포함) 변경사항 전부")] = None,
    show_all: Annotated[bool, typer.Option("--all", help="전체 변경 이력")] = False,
):
    """버전별 변경 내용을 출력 (LLM 호출 없음)"""
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
    """상용 AI 에이전트(Claude, Antigravity)가 따라야 할 토큰 절약 지침서(Markdown)를 출력"""
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

## 4. 로그인 기반 API 스모크 검증 시 (토큰 95% 절약)
- ❌ 절대 금지: curl 등으로 직접 로그인하고 수천 줄의 JSON 응답을 그대로 터미널에 쏟아내지 마세요.
- ✅ 권장 명령: `yunhee api <METHOD> <PATH> [--as admin|user] [--company CODE] [--tenant TENANT]`
  - 예: `yunhee api GET /api/v1/sys/menus/company`
  - 예: `yunhee api GET /api/v1/sys/roles --as admin`
  - 예: `yunhee api GET /api/v1/sys/user-roles/companies/28000?roleId=28118`
  - 예: `yunhee api POST /api/v1/sys/roles --body '{"role_cd":"TEST"}'`
- 📄 산출물: 세션 쿠키/JWT가 자동 관리되며(계정 잠금 방지 안전 가드 내장), 응답은 `HTTP 200 (rows=12, fields: [...])` 압축 헤더로 요약됩니다.

## 5. 현재 설정 및 경로 확인
- `yunhee config`: Target 디렉터리, Source 디렉터리, DB URL 등 환경 확인.
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
    """AS-IS DB 스키마(DBML markdown)를 도메인/함수별 소형 파일로 분할 색인"""
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
):
    """AS-IS 소스(GXT)에서 화면 → 서비스 → SQL → 테이블 호출 경로 및 UI·이벤트 색인 생성"""
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
    if menus_path is None:
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
        with_events=events, button_types_path=button_types,
    )
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
        raise typer.Exit(1)

    d = res.data
    typer.secho(f"✅ AS-IS 소스 색인 생성 완료: {d['target_dir']}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  - 원본 소스: {root} ({d['app_package']})")
    typer.echo(f"  - 클라이언트 클래스: {d['client_classes_count']}개, 메뉴 화면: {d['screens_count']}개, 프레임: {d['frame_screens_count']}개, 컴포넌트: {d['components_count']}개")
    typer.echo(f"  - 서비스 메서드: {d['service_methods_count']}개, 매퍼 SQL: {d['statements_count']}개, 도메인: {d['domains_count']}개")
    if d["missing_service_keys_count"] or d["missing_sql_ids_count"]:
        typer.echo(f"  - 미해결 호출: 서비스 키 {d['missing_service_keys_count']}개, 매퍼 SQL ID {d['missing_sql_ids_count']}개 → unresolved.md")
    if events:
        typer.echo(f"  - events: 클래스 {d['events_classes_count']}개 분석 (화면 파일 UI 절에 포함)")
        for name, err in d["events_errors"]:
            typer.secho(f"    ⚠ {name}: {err}", fg=typer.colors.YELLOW, err=True)


@app.command(name="sql-check")
def sql_check_cmd(
    src_root: Annotated[
        Path | None,
        typer.Argument(help="AS-IS 소스 루트 (미지정 시 YUNHEE_ASIS_SRC_DIR)"),
    ] = None,
    tobe: Annotated[
        Path | None,
        typer.Option("--tobe", help="TOBE 매퍼 디렉터리 경로 (예: backend/src/main/resources/mapper)"),
    ] = None,
    db: Annotated[
        str,
        typer.Option("--db", help="검증 대상 PostgreSQL DB 이름"),
    ] = "asseterpdb",
    target: Annotated[
        Path | None,
        typer.Option("--target", "-t", help="출력 파일 경로 (기본: {repo_root}/docs/as-is/sql-check.md)"),
    ] = None,
    src_index: Annotated[
        Path | None,
        typer.Option("--src-index", help="src-index 출력 폴더 (기본: docs/as-is/src 탐색)"),
    ] = None,
):
    """MyBatis 매퍼 SQL을 대상 DB에서 EXPLAIN으로 정합성(스키마/환경 차이) 검증"""
    from yunhee.tools.as_is.sql_checker import check_tobe_sql

    if tobe:
        if not tobe.is_dir():
            typer.secho(f"[ERROR] TOBE 매퍼 디렉터리를 찾을 수 없습니다: {tobe}", fg=typer.colors.RED)
            raise typer.Exit(1)
        res = check_tobe_sql(tobe, db=db)
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
    res = check_sql(root, out_file, db=db, src_index_dir=src_idx)
    if not res.ok:
        typer.secho(f"[ERROR] {res.error}", fg=typer.colors.RED)
        raise typer.Exit(1)

    d = res.data
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
    """AS-IS GXT 화면의 위젯 이벤트(E0..En)와 메서드 호출/하는 일을 정밀 추출"""
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
    list_types_flag: Annotated[
        bool,
        typer.Option("--list", help="지원하는 모든 분석 유형 목록 출력"),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="출력 형식 (md, json, code, sql)"),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="결과 개수 또는 글자 수 제한"),
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
    section: Annotated[
        str | None,
        typer.Option("--section", help="절 필터링 (services, tables, ui, events, methods, grid, buttons)"),
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
        Path | None,
        typer.Option("--tobe", help="대조할 TOBE 소스 경로 또는 디렉터리"),
    ] = None,
    stdout: Annotated[
        bool,
        typer.Option("--stdout", help="실행 로그의 STDOUT 부분만 출력"),
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
):
    """AS-IS 및 TOBE 통합 정적 분석 도구 (method, sql, model, grid, screen, ui, tobe, run)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  원본 소스를 직접 sed/grep/cat하지 마세요. 필요한 정보(메서드 본문 요약, 실행 가능 SQL, 그리드 컬럼 스펙 등)를
  yunhee analysis <type> <target> 으로 추출하여 컨텍스트 토큰을 절약하세요.
"""
    import inspect

    from rich.console import Console
    from rich.table import Table

    from yunhee.tools import analysis
    from yunhee.tools.analysis.common import AmbiguousTargetError

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
        "section": section,
        "list": screen_list,
        "done": done,
        "later": later,
        "tobe": tobe,
        "stdout": stdout,
        "json": json_flag,
        "keys": keys,
        "tests": tests,
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


if __name__ == "__main__":
    app()