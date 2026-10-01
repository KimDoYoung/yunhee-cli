import os
import re
from pathlib import Path
from typing import Annotated

import typer

from yunhee import project
from yunhee.config import OLLAMA_MODEL, SCHEMA_ENV, WORK_DIR, redact
from yunhee.ollama_client import chat, embed
from yunhee.store.vectorstore import add_texts
from yunhee.store.vectorstore import search as vector_search
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


def _get_project_name() -> str:
    proj_data = project.load()
    if proj_data and proj_data.get("name"):
        return proj_data["name"]
    return WORK_DIR.name


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

    result = execute_command(command, timeout=timeout)
    data = result.data
    project_name = _get_project_name()

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
    )

    if data["exit_code"] != 0:
        raise typer.Exit(code=data["exit_code"] if 0 <= data["exit_code"] <= 255 else 1)


app.command(name="run")(_run_exec)
app.command(name="exec")(_run_exec)


@app.command(name="last-run")
def last_run():
    """가장 최근에 실행한 외부 명령어 결과와 요약을 확인"""
    from yunhee.store import run_tracker

    project_name = _get_project_name()
    last = run_tracker.get_last_run(project_name)
    if not last:
        print(f"프로젝트 '{project_name}'의 실행 이력이 없습니다.")
        return

    if last.get("summary"):
        print(last["summary"])
    else:
        status_icon = "✅" if last["exit_code"] == 0 else "❌"
        duration_sec = f"{last['duration_ms'] / 1000:.2f}s"
        print(f"{status_icon} Exit Code: {last['exit_code']} ({duration_sec})")
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

    project_name = _get_project_name()
    records = run_tracker.list_runs(project_name, limit=limit)
    if not records:
        print(f"프로젝트 '{project_name}'의 실행 이력이 없습니다.")
        return

    table = Table(title=f"실행 이력 (Project: {project_name})")
    table.add_column("Run ID", style="dim", no_wrap=True)
    table.add_column("Command", style="cyan")
    table.add_column("Exit", justify="right")
    table.add_column("Duration", justify="right")
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
            r["created_at"][:19].replace("T", " "),
            r["log_path"],
        )

    console = Console()
    console.print(table)


@app.command()
def outline(
    path: Annotated[str, typer.Argument(help="분석할 파일 또는 디렉터리 경로")],
    limit: Annotated[int, typer.Option("--limit", help="최대 글자 수 제한")] = 30000,
):
    """소스 파일(Java, XML, TS/TSX, Python) 또는 디렉터리의 클래스·메서드·시그니처와 줄 번호를 추출 (LLM 호출 없음)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  TOBE 기존 코드(Service, Controller, Mapper XML 등) 전체를 읽지 마세요. 이 명령으로 메서드 위치와 줄 번호를 파악한 뒤 필요한 줄만 핀포인트로 읽으세요.
"""
    from yunhee.tools.outliner import outline_path

    res = outline_path(path, char_limit=limit)
    if not res.ok:
        typer.echo(f"오류: {res.error}", err=True)
        raise typer.Exit(code=1)
    print(res.data)


@app.command()
def api(
    method: Annotated[str, typer.Argument(help="HTTP 메서드 (GET, POST, PUT, DELETE)")],
    path: Annotated[str, typer.Argument(help="호출할 API 경로 (예: /api/v1/sys/roles)")],
    as_role: Annotated[str, typer.Option("--as", help="로그인 역할 (admin 또는 user)")] = "admin",
    base: Annotated[str | None, typer.Option("--base", help="기본 URL")] = None,
    param: Annotated[list[str] | None, typer.Option("--param", "-p", help="쿼리 파라미터 key=val (반복 가능)")] = None,
    body: Annotated[str | None, typer.Option("--body", "-b", help="JSON 요청 본문")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="압축 요약 대신 원본 JSON 본문 출력")] = False,
):
    """테스트 계정으로 자동 로그인하여 API를 호출하고 응답 요약(상태코드, 행수, 필드목록)을 확인 (LLM 호출 없음)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  수천 줄의 원시 응답 JSON 대신 이 명령으로 행 수(rows=N)와 키 목록만 2~3줄로 확인하여 토큰을 절약하세요.
"""
    import json

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

    kw = {}
    if base:
        kw["base_url"] = base

    res = api_client.request_api(
        method=method,
        path=path,
        as_role=as_role,
        params=params_dict or None,
        json_body=json_body,
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
- ✅ 권장 명령: `yunhee api <METHOD> <PATH> [--as admin|user]`
  - 예: `yunhee api GET /api/v1/sys/roles --as admin`
  - 예: `yunhee api POST /api/v1/sys/roles --body '{"role_cd":"TEST"}'`
- 📄 산출물: 세션 쿠키/JWT가 자동 관리되며, 응답은 `HTTP 200 (rows=12, fields: [...])` 압축 헤더로 요약됩니다.

## 5. 현재 설정 및 경로 확인
- `yunhee config`: Target 디렉터리, Source 디렉터리, DB URL 등 환경 확인.
"""
    print(guide.strip())


if __name__ == "__main__":
    app()