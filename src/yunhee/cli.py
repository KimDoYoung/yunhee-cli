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

app = typer.Typer(rich_markup_mode="rich", add_completion=False)


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
  4. [bold green]API/로그[/bold green]: [cyan]yunhee api GET <경로> [--log][/cyan] · [cyan]yunhee log trace|req|errors|tail[/cyan]
  5. [bold green]AS-IS 분석[/bold green]: [cyan]yunhee analysis screen|ui|method|sql|grid <대상>[/cyan]
  6. [bold green]원본 변경[/bold green]: [cyan]yunhee drift --all --base baseline[/cyan] · [cyan]drift --record <화면>[/cyan]
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


@app.command()
def ask(prompt: str, model: str = OLLAMA_MODEL):
    """로컬 LLM(qwen2.5-coder) 단발 질의"""
    print(chat(prompt, model=model))


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
    table.add_row("Source (ASIS)", cfg["asis-src"], ".env.local의 YUNHEE_ASIS_SRC_DIR")
    table.add_row("소스 브랜치", cfg["asis-branch"], "원격 추적 브랜치(origin/<branch>) 대비 상태 (읽기 전용)")
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

    console = Console(width=200)
    console.print(table)
    typer.echo(f"소스 브랜치: {cfg['asis-branch']}")


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

    out_file = output or WORK_DIR / f"{env_name}-dbml.md"
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
):
    """소스 파일·디렉터리의 클래스·메서드 시그니처와 줄 번호 추출

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
        res = outline_path(p, char_limit=remaining_limit, members=members, symbol=symbol)
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
    as_role: Annotated[str, typer.Option("--as", "-u", help="로그인 계정/역할 (사원 ID, 로그인 ID, admin)")] = "admin",
    base: Annotated[str | None, typer.Option("--base", help="기본 URL")] = None,
    login_path: Annotated[str | None, typer.Option("--login-path", help="로그인 엔드포인트 경로 (기본: .env.local의 YUNHEE_API_LOGIN_PATH 또는 /api/auth/login)")] = None,
    company: Annotated[str | None, typer.Option("--company", "-c", help="로그인 시 전달할 회사 코드 (companyCode)")] = None,
    tenant: Annotated[str | None, typer.Option("--tenant", "-t", help="테넌트 식별자 (세션 분리 및 X-Tenant-Id 헤더)")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="쿼리 파라미터 key=val (반복 가능)")] = None,
    body: Annotated[str | None, typer.Option("--body", "-b", help="JSON 요청 본문")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="압축 요약 대신 원본 JSON 본문 출력")] = False,
    timeout: Annotated[float | None, typer.Option("--timeout", help="요청 타임아웃(초) (기본: .env.local의 YUNHEE_API_TIMEOUT 또는 15)")] = None,
    log: Annotated[bool, typer.Option("--log", help="호출 후 서버 로그(trace) 요약 출력")] = False,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
    wait_deploy: Annotated[float | None, typer.Option("--wait-deploy", help="배포 후 앱 기동 완료까지 대기(초, 기본 60초)")] = None,
):
    """자동 로그인 기반 API 호출 및 응답(상태·행수·필드) 요약

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
        mask=not no_mask,
        wait_deploy=wait_deploy,
        **kw,
    )

    if not res.ok and not res.data:
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=1)

    if raw:
        print(res.data.get("text", ""))
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
    db: Annotated[str | None, typer.Option("--db", help="대상 데이터베이스 환경변수 이름 또는 연결 URL (기본: LOCAL_DB)")] = None,
    output: Annotated[str, typer.Option("--output", "-o", help="출력 형식: table(기본) | tsv | csv | json")] = "table",
    no_header: Annotated[bool, typer.Option("--no-header", help="tsv·csv 출력 시 헤더 줄 생략")] = False,
    null: Annotated[str, typer.Option("--null", help="tsv·csv에서 NULL 값을 표기할 문자열 (기본: 빈 칸)")] = "",
    out: Annotated[Path | None, typer.Option("--out", help="결과를 파일에 저장하고 화면에는 요약 한 줄만 출력")] = None,
):
    """PostgreSQL 읽기 전용 쿼리 실행 또는 --rollback 시험

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
    """테이블 스키마 기반 명시적 INSERT/UPDATE/DELETE 및 부수효과 생성"""
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
    as_user: Annotated[str, typer.Option("--as", "-u", help="로그인 계정/역할 (사원 ID, 로그인 ID, admin)")] = "admin",
    sql_total: Annotated[str | None, typer.Option("--sql-total", help="페이징 총건수 검증용 AS-IS SQL ID (예: apr40_download_history.selectByTextPagingTotal)")] = None,
    from_log: Annotated[bool, typer.Option("--from-log", help="최근 로그 trace에서 매퍼 파라미터를 읽어 기본값으로 사용")] = False,
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
        as_user=as_user,
        sql_total_ref=sql_total,
        from_log=from_log,
    )
    if not res.ok:
        err_msg = res.error or "비교 실패"
        if err_msg.startswith("API 호출 실패: "):
            err_msg = err_msg.replace("API 호출 실패: ", "")
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
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="쿼리 파라미터 (key=value, 반복 가능)")] = None,
    compare: Annotated[str | None, typer.Option("--compare", help="비교할 AS-IS SQL ID (예: fbx03_file.selectByBoxId)")] = None,
    count: Annotated[bool, typer.Option("--count", help="행 수만 출력")] = False,
    rows: Annotated[int | None, typer.Option("--rows", "-n", help="출력할 최대 행 수")] = None,
    rollback: Annotated[bool, typer.Option("--rollback", help="트랜잭션 실행 후 롤백 (쓰기 문장 필수)")] = False,
    db: Annotated[str, typer.Option("--db", "-c", help="대상 DB명 (기본: asseterpdb)")] = "asseterpdb",
    src: Annotated[Path | None, typer.Option("--src", "-s", help="AS-IS 소스 루트 경로")] = None,
) -> None:
    """TOBE 매퍼 statement 실행 및 AS-IS SQL 비교"""
    from yunhee.tools.as_is.mapper_runner import run_mapper_statement

    params_dict = {}
    if param:
        for p in param:
            if "=" in p:
                k, v = p.split("=", 1)
                params_dict[k.strip()] = v.strip()

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
- ❌ 절대 금지: curl 등으로 직접 로그인하고 수천 줄의 JSON 응답을 그대로 터미널에 쏟아내지 마세요.
- ✅ 권장 명령: `yunhee api <METHOD> <PATH> [--as admin|user] [--company CODE] [--tenant TENANT]`
  - 예: `yunhee api GET /api/v1/sys/menus/company`
  - 예: `yunhee api GET /api/v1/sys/roles --as admin`
  - 예: `yunhee api GET /api/v1/sys/user-roles/companies/28000?roleId=28118`
  - 예: `yunhee api POST /api/v1/sys/roles --body '{"role_cd":"TEST"}'`
- 📄 산출물: 세션 쿠키/JWT가 자동 관리되며(계정 잠금 방지 안전 가드 내장), 응답은 `HTTP 200 (rows=12, fields: [...])` 압축 헤더로 요약됩니다.

## 5. AS-IS 정적 분석 및 폼 레이아웃 파악 (토큰 90% 절약)
- ❌ 절대 금지: 복잡한 GXT 폼 탭의 컴포넌트 크기, 라벨, 배치, 읽기 전용 속성을 파악하려고 수백 줄의 자바 소스를 직접 열지 마세요.
- ✅ 권장 명령:
    - `yunhee analysis screen <화면> --list`: 클래스 목록 및 줄/버튼/이벤트/그리드 통계 (연결 컴포넌트 포함(`(연결)` 표시), `--no-linked` 지원)
    - `yunhee analysis screen <화면> --section layout`: 폼 탭은 원본 Java를 열기 전에 이것부터 확인하세요.
    - `yunhee analysis screen <화면> --section source`: 색인 시점의 소스 커밋과 의존 파일 개수 요약 확인.
    - `yunhee analysis ui <화면>`: TOBE 이벤트 구현율 및 `(생략 N)` (TOBE에서 생략하기로 결정된 이벤트 수) 확인 (연결 컴포넌트 포함(`(연결)` 표시)).

## 6. 서버 로그 및 실제 실행 SQL 확인 시 (grep 금지)
- ❌ 절대 금지: docker logs나 서버 로그 파일을 직접 grep하지 마세요. (호스트 같은 경로는 로컬 테스트 로그이며, 배포본은 docker 컨테이너 t3600-tomcat 안에 있습니다)
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
    if menus_path is None:
        cand = out_dir.parent / "menus.tsv"
        if cand.is_file():
            menus_path = cand
        elif menus_from_db:
            from yunhee.tools import sql_runner

            gen_res = sql_runner.run_sql(
                builtin="menus",
                db_name=menus_from_db,
                output_fmt="tsv",
                no_header=True,
                out_file=cand,
            )
            if not gen_res.ok:
                typer.secho(f"[ERROR] --menus-from-db 실행 실패: {gen_res.error}", fg=typer.colors.RED)
                raise typer.Exit(1)
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
        if not tobe.is_dir():
            typer.secho(f"[ERROR] TOBE 매퍼 디렉터리를 찾을 수 없습니다: {tobe}", fg=typer.colors.RED)
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
        Path | None,
        typer.Option("--tobe", help="대조할 TOBE 소스 경로 또는 디렉터리"),
    ] = None,
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


@log_app.command(name="trace")
def log_trace_cmd(
    trace_id: Annotated[str, typer.Argument(help="조회할 trace ID (16진수)")],
    sql: Annotated[bool, typer.Option("--sql", help="실행 가능한 바인딩 SQL 포함")] = False,
    raw: Annotated[bool, typer.Option("--raw", help="원문 로그 출력")] = False,
    no_mask: Annotated[bool, typer.Option("--no-mask", help="개인정보 마스킹 해제")] = False,
    archived: Annotated[bool, typer.Option("--archived", help="지난 날짜의 압축 로그(archived/*.gz)까지 검색")] = False,
    file: Annotated[str | None, typer.Option("--file", "-f", help="직접 읽을 로그 파일 경로")] = None,
    source: Annotated[str | None, typer.Option("--source", help="로그 소스 (docker 또는 local)")] = None,
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


if __name__ == "__main__":
    app()