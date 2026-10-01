import os
import re
from pathlib import Path
from typing import Annotated

import typer

from yunhee import project
from yunhee.config import OLLAMA_MODEL, SCHEMA_ENV, WORK_DIR, redact
from yunhee.context.analyzer import summarize_page
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
  1. [bold green]화면 분석[/bold green]: ASIS Java/XML 소스를 직접 열람하지 말고 [cyan]yunhee prepare <PageCode>[/cyan] 실행 (토큰 95% 절감)
  2. [bold green]스키마 조회[/bold green]: DDL 검색 대신 [cyan]yunhee table <TablePattern>[/cyan] 또는 [cyan]--page <PageCode>[/cyan] 사용
  3. [bold green]빌드/테스트[/bold green]: 셸에서 직접 돌리지 말고 [cyan]yunhee run "<Command>"[/cyan] 로 감싸서 실행 (원시 로그 격리, Qwen 에러 요약 수신)
  4. [bold green]에이전트 지침서[/bold green]: [cyan]yunhee agent-guide[/cyan] 명령으로 AI 행동 지침서 마크다운 전문 출력

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

def _prepare(
    page_code: str,
    model: str = OLLAMA_MODEL,
    force: bool = False,
    show: bool = False,
    delete: bool = False,
    two_stage: bool = typer.Option(False, "--two-stage", help="파일별 mini-summary 후 합산 (느리지만 전체 파일 반영)"),
    no_grounding: bool = typer.Option(False, "--no-grounding", help="mapper_index 환각 검증 패스 건너뜀"),
    no_schema: bool = typer.Option(False, "--no-schema", help="연관 테이블 DBML 섹션을 붙이지 않음"),
    db: str = typer.Option(SCHEMA_ENV, "--db", help="연관 테이블을 조회할 스키마 스냅샷 (make-dbml의 환경변수 이름)"),
):
    """ASIS 페이지 소스를 Qwen 14B로 요약해 캐시하고 연관 DBML을 부착 (prepare == prep)

[bold yellow]🤖 AI Agent 권장사항:[/bold yellow]
  ASIS 소스(Java/GXT/XML)를 직접 대량 열람하지 마세요. 이 명령의 결과 마크다운만 소비하면 토큰의 95%가 절약됩니다.
"""
    from yunhee.tools.legacy_page import validate_page_code

    err = validate_page_code(page_code)
    if err:
        print(f"오류: {err}")
        raise typer.Exit(code=1)

    cache_dir = project.PROJECT_DIR / "prep"
    cache_file = cache_dir / f"{page_code}.md"

    if delete:
        if cache_file.exists():
            cache_file.unlink()
            print(f"삭제됨: {cache_file}")
        else:
            print(f"캐시가 없습니다: {cache_file}")
        return

    if show:
        if not cache_file.exists():
            print(f"캐시가 없습니다: {cache_file} (먼저 'yunhee prepare {page_code}' 실행하세요)")
            raise typer.Exit(code=1)
        print(cache_file.read_text())
        return

    if cache_file.exists() and not force:
        print(cache_file.read_text())
        return

    try:
        summary = summarize_page(
            page_code,
            model=model,
            two_stage=two_stage,
            grounding=not no_grounding,
        )
    except ValueError as e:
        print(f"오류: {e}")
        raise typer.Exit(code=1) from e

    if not no_schema:
        from yunhee.context.schema_context import page_schema_section

        summary = f"{summary.rstrip()}\n\n{page_schema_section(page_code, db)}"

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(summary)
    print(summary)


app.command(name="prepare")(_prepare)
app.command(name="prep")(_prepare)


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


@app.command(name="agent-guide")
def agent_guide():
    """상용 AI 에이전트(Claude, Antigravity)가 따라야 할 토큰 절약 지침서(Markdown)를 출력"""
    guide = """# YUNHEE AI AGENT PROTOCOL (토큰 절약 행동 수칙)

당신은 이 프로젝트를 작업하는 상용 AI 코딩 어시스턴트(Claude, Antigravity, Gemini 등)입니다.
이 환경에는 토큰 소모를 극적으로 줄이기 위한 독립 로컬 CLI인 `yunhee`가 설치되어 있습니다.
작업 시 아래 규칙을 반드시 준수하여 불필요한 토큰 낭비를 원천 차단하세요.

---

## 1. ASIS 레거시 화면 분석 시 (토큰 95% 절약)
- ❌ 절대 금지: ASIS 소스 디렉터리의 Java/GXT/XML 파일들을 직접 view_file이나 cat으로 대량 열람하지 마세요.
- ✅ 권장 명령: `yunhee prepare <화면코드>` (예: `yunhee prepare Sys04`, `yunhee prepare Emp00 --two-stage`)
- 📄 산출물: GXT 보일러플레이트가 제거된 화면 레이아웃, 그리드 컬럼, 폼 필드, 이벤트, 검증된 SQL ID, 연관 테이블 DBML만 약 2,000토큰으로 압축 제공됩니다.

## 2. DB 스키마 확인 시 (토큰 90% 절약)
- ❌ 절대 금지: 전체 DB DDL이나 거대한 스키마 파일을 검색하거나, PostgreSQL 카탈로그를 직접 조회하지 마세요.
- ✅ 권장 명령:
  - 특정 테이블: `yunhee table <테이블명>` (예: `yunhee table sys04_role`)
  - 패턴 검색: `yunhee table '<패턴>'` (예: `yunhee table 'emp00_*'`)
  - 화면 연관 테이블: `yunhee table --page <화면코드>` (예: `yunhee table --page Org01`)
- 📄 산출물: 컬럼, 타입, 코멘트, PK/FK, Enum만 정제된 순수 DBML 블록으로 제공됩니다.

## 3. 컴파일, 빌드, 린트, 테스트 실행 시 (토큰 95% 절약)
- ❌ 절대 금지: `mvn compile`, `./gradlew build`, `npm run build`, `pytest` 등을 셸에서 직접 실행하지 마세요. (수천 줄의 빌드 로그로 컨텍스트가 오염됩니다)
- ✅ 권장 명령: `yunhee run "<실행명령어>"` (예: `yunhee run "mvn compile"`, `yunhee run "npx tsc -b --noEmit"`)
- 📄 산출물:
  - 원시 전체 로그는 `.yunhee/runs/<run_id>.log` 파일에 영구 격리 저장됩니다.
  - 성공 시: `✅ Execution Succeeded (소요시간)` 1줄만 반환됩니다.
  - 실패 시: 로컬 Qwen 14B가 1) 실패 원인, 2) 관련 파일:라인, 3) 핵심 에러 메시지만 10~20줄로 요약해 반환합니다.
- 직전 실행 결과 재확인: `yunhee last-run`
- 최근 실행 이력 표: `yunhee runs`
"""
    print(guide.strip())


if __name__ == "__main__":
    app()