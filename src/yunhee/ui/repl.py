from __future__ import annotations

import _thread
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown

from yunhee import changelog, config, project
from yunhee.agent import (
    AgentLoop,
    list_rules_text,
    save_rule,
    search_knowledge,
)
from yunhee.agent.tools.core_exec import run_command
from yunhee.agent.tools.ext_gotenberg import (
    convert_markdown_to_pdf,
    export_pdf_from_file,
)
from yunhee.agent.tools.screen_scout import build_screen_spec_markdown
from yunhee.config import OLLAMA_MODEL
from yunhee.ui.components import (
    format_tool_call_status,
    format_tool_result_preview,
    listen_esc_cancel,
    render_tools_table,
)

HISTORY_FILE = Path.home() / ".yunhee_history"
console = Console()

BUILTIN_COMMANDS = [
    "/help",
    "/exit",
    "/quit",
    "/clear",
    "/config",
    "/init",
    "/tools",
    "/session",
    "/memory",
    "/knowledge",
    "/자기소개",
    "/intro",
    "/changelog",
    "/out",
    "/out:pdf",
    "/out:markdown",
    "/out:md",
]

HYBRID_COMMANDS = [
    "/table",
    "/outline",
    "/sql",
    "/log",
    "/run",
    "/api",
    "/events",
    "/analysis",
]

ALL_AUTOCOMPLETE_COMMANDS = BUILTIN_COMMANDS + HYBRID_COMMANDS


def _help_text() -> str:
    return f"""\
[bold cyan]yunhee-cli[/bold cyan] [dim]v{project.current_version()} (Agentic Harness)[/dim]

[bold]사용 가능한 슬래시 명령어[/bold]
  [green]/help[/green]            이 도움말
  [green]/자기소개[/green]        yunhee 에이전트 자기소개 ('자기소개?' 도 가능)
  [green]/exit, /quit[/green]     종료
  [green]/clear[/green]           대화 맥락 초기화
  [green]/config[/green]          현재 설정값 보기 (work-dir, yunhee-dir, .env.local 등)
  [green]/changelog[/green]       버전별 변경 이력 조회
  [green]/init[/green]            현재 폴더를 yunhee 프로젝트로 등록/갱신 (.yunhee/project.json)
  [green]/tools[/green]           현재 에이전트가 호출 가능한 도구 목록 확인
  [green]/session[/green]         현재 세션 기록(마크다운/JSONL) 파일 경로 확인
  [green]/memory[/green]          프로젝트 핵심 규칙(.yunhee/memory.md) 조회 (추가: /memory add <규칙>)
  [green]/knowledge <검색어>[/green] ChromaDB 지식 베이스(bge-m3) 즉시 검색
  [green]/out <화면|파일>[/green]    마이그레이션 종합 마크다운 명세서 작성 (== /out:markdown, /out:md)
  [green]/out:pdf <화면|파일>[/green] Gotenberg 스타일링 공식 PDF 명세서 원클릭 발간
  [green]/out:pdf session[/green]        현재까지의 전체 대화 기록을 예쁜 PDF 대화록으로 발간

[bold]하이브리드 CLI 명령어 (실행 결과를 현재 대화 맥락에 자동 주입)[/bold]
  [cyan]/table <테이블명>[/cyan]   특정 테이블 스키마 DBML 즉시 조회
  [cyan]/outline <경로>[/cyan]     소스 파일 구조 및 메서드 목록 즉시 조회
  [cyan]/log errors[/cyan]          최근 서버 에러 로그 즉시 조회
  [cyan]/run "<명령어>"[/cyan]       외부 명령어 실행 및 요약 확인

[bold]단축키[/bold]
  [yellow]Ctrl+C[/yellow]           입력 중인 내용 취소 (프로그램 유지)
  [yellow]ESC 2회 (더블탭)[/yellow]  모델 추론 및 도구 실행 즉시 중단/취소
  [yellow]Ctrl+D[/yellow]           REPL 종료
"""


def _check_project() -> None:
    state = project.status()
    if state == "missing":
        console.print(
            "[yellow]이 폴더는 아직 yunhee 프로젝트로 등록되지 않았습니다.[/yellow] "
            "[dim]/init[/dim] 을 실행하여 프로젝트 설정 및 필요한 폴더를 생성하세요.\n"
        )
    elif state == "outdated":
        data = project.load() or {}
        console.print(
            f"[yellow].yunhee 설정이 이전 yunhee 버전({data.get('yunhee_version')})으로 만들어졌습니다.[/yellow] "
            f"현재 버전({project.current_version()})으로 갱신하려면 [dim]/init[/dim] 을 실행하세요.\n"
        )


def _print_changes_since(old_version: str | None) -> None:
    if not old_version:
        return
    entries = changelog.changes_since(old_version, project.current_version())
    if not entries:
        return
    console.print(f"[bold]{old_version} 이후 변경사항[/bold]")
    for e in entries:
        console.print(e.render(), markup=False)
    console.print()


def _handle_hybrid_command(
    cmd_line: str,
    messages_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    /table, /outline, /log 등 CLI 명령어를 대화창에서 바로 실행하고
    그 결과를 대화 컨텍스트에 주입합니다.
    """
    raw = cmd_line.lstrip("/").strip()
    full_cmd = f"yunhee {raw}"
    console.print(f"[dim yellow]⚡ 하이브리드 명령어 실행 중: {full_cmd}[/dim yellow]")

    result = run_command(full_cmd, timeout_seconds=30)
    lines = result.strip().splitlines()

    # 터미널에 요약 미리보기 출력
    if len(lines) <= 10:
        console.print(f"[dim]{result}[/dim]")
    else:
        top = "\n".join(lines[:8])
        console.print(f"[dim]{top}\n... (외 {len(lines) - 8}줄 생략, 대화 컨텍스트에 전체 주입됨)[/dim]")

    # 대화 맥락에 시스템/사용자 피드백 형태로 첨부
    feedback = (
        f"[사용자 슬래시 명령어 /{raw} 실행 결과]:\n```\n{result}\n```\n"
        "위 실행 결과를 참고하여 사용자의 추가 질문에 답변하세요."
    )
    messages_history.append({"role": "user", "content": feedback})
    console.print("[green]✔ 실행 결과가 현재 대화 컨텍스트에 첨부되었습니다.[/green]\n")
    return messages_history


def run_repl(model: str = OLLAMA_MODEL) -> None:
    """Claude CLI / Gemini CLI 스타일 자율 대화형 에이전트 REPL 진입점."""
    completer = WordCompleter(ALL_AUTOCOMPLETE_COMMANDS, ignore_case=True, sentence=True)
    session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=completer,
        complete_while_typing=True,
    )

    loop = AgentLoop(model=model)
    messages_history: list[dict[str, Any]] | None = None

    console.print(
        f"[bold cyan]yunhee-cli[/bold cyan] [dim]v{project.current_version()} ({loop.model})[/dim] "
        "— [green]Agentic Harness[/green] (/help 로 명령어 확인)\n"
    )
    if loop.session_logger:
        console.print(f"• [bold]세션 기록[/bold]: [dim]{loop.session_logger.md_path}[/dim]")

    _check_project()

    while True:
        # 1. 사용자 입력 받기 (Ctrl+C는 입력창만 취소)
        try:
            user_input = session.prompt("you> ").strip()
        except KeyboardInterrupt:
            console.print("[dim](입력 취소)[/dim]")
            continue
        except EOFError:
            console.print("\n[dim]bye[/dim]")
            break

        if not user_input:
            continue

        # 2. 자기소개 직통 처리 (물음표 및 슬래시 유무 무관)
        norm_input = user_input.rstrip("? ").strip().lower()
        if norm_input in ("자기소개", "/자기소개", "intro", "/intro", "about", "/about", "whoami", "/whoami"):
            from yunhee.intro import get_intro_text

            console.print(Markdown(get_intro_text()))
            console.print()
            continue

        # 3. 슬래시 커맨드 분기 처리
        if user_input.startswith("/"):
            parts = user_input[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("exit", "quit"):
                console.print("[dim]bye[/dim]")
                break

            if cmd == "clear":
                messages_history = None
                console.print("[dim]대화 맥락을 초기화했습니다.[/dim]\n")
                continue

            if cmd == "help":
                console.print(_help_text())
                continue

            if cmd == "tools":
                schemas = loop.registry.get_schemas()
                console.print(render_tools_table(schemas))
                console.print()
                continue

            if cmd == "session":
                if loop.session_logger:
                    console.print(
                        f"[cyan]현재 세션 로그 파일:[/cyan]\n"
                        f"  - Markdown: {loop.session_logger.md_path}\n"
                        f"  - JSONL:    {loop.session_logger.jsonl_path}\n"
                    )
                else:
                    console.print("[dim]세션 로거가 비활성화되어 있습니다.[/dim]\n")
                continue

            if cmd == "config":
                console.print(f"[bold]현재 설정[/bold] [dim]v{project.current_version()}[/dim]")
                for key, value in config.summary().items():
                    console.print(f"  {key:<12} {value}")
                proj = project.load()
                proj_display = (
                    f"{proj['name']} (v{proj['yunhee_version']})"
                    if proj
                    else "(미등록 - /init 필요)"
                )
                console.print(f"  {'project':<12} {proj_display}\n")
                continue

            if cmd == "init":
                data = project.init()
                console.print(
                    f"[green]등록 완료[/green] {project.PROJECT_FILE}\n"
                    f"  name           {data['name']}\n"
                    f"  yunhee_version {data['yunhee_version']}"
                )
                pdir = Path(config.WORK_DIR) / ".yunhee"
                if data.get("mcp_created"):
                    console.print(f"  [cyan]mcp.json 생성[/cyan]     {pdir / 'mcp.json'} (기본: time, fetch)")
                if data.get("memory_created"):
                    console.print(f"  [cyan]memory.md 생성[/cyan]    {pdir / 'memory.md'} (프로젝트 영구 기억)")
                console.print(f"  [cyan]sessions/ 생성[/cyan]    {pdir / 'sessions'} (대화록 보관)")
                console.print(f"  [cyan]runs/ 생성[/cyan]        {pdir / 'runs'} (실행 로그 보관)")
                if data.get("gitignore_created"):
                    console.print(f"  [cyan].gitignore 생성[/cyan]   {pdir / '.gitignore'}")
                console.print()
                continue

            if cmd == "changelog":
                data = project.load() or {}
                old_ver = data.get("yunhee_version")
                if old_ver and old_ver != project.current_version():
                    _print_changes_since(old_ver)
                else:
                    entries = changelog.changes_since(None, project.current_version())
                    for e in entries:
                        console.print(e.render(), markup=False)
                continue

            if cmd == "memory":
                if arg.startswith("add "):
                    new_rule = arg[4:].strip()
                    msg = save_rule(new_rule)
                    console.print(f"{msg}\n")
                else:
                    console.print(list_rules_text() + "\n")
                continue

            if cmd == "knowledge":
                query = arg.strip()
                if not query:
                    console.print("[dim]사용법: /knowledge <검색어>[/dim]\n")
                else:
                    console.print(f"[dim]ChromaDB 지식 검색 중: '{query}'...[/dim]")
                    res = search_knowledge(query, limit=3)
                    console.print(f"{res}\n")
                continue

            if cmd in ("out", "out:pdf", "out:markdown", "out:md"):
                format_type = "pdf" if cmd == "out:pdf" else "markdown"
                target = arg.strip()

                if not target:
                    console.print(
                        "[yellow]사용법:[/yellow]\n"
                        "  [green]/out <화면코드>[/green]          - 화면 마크다운 명세서 작성 (== /out:markdown, /out:md)\n"
                        "  [green]/out:pdf <화면코드>[/green]      - 화면 마크다운 작성 및 Gotenberg 공식 PDF 발간\n"
                        "  [green]/out:pdf <파일.md>[/green]       - 기존 마크다운 문서를 PDF로 변환 발간\n"
                        "  [green]/out:pdf session[/green]        - 현재 대화 세션 전체를 PDF 대화록으로 발간\n"
                    )
                    continue

                # Case 1: 세션 대화록 출력 (target == "session")
                if target.lower() == "session":
                    if not loop.session_logger:
                        console.print("[dim]세션 로거가 비활성화되어 있습니다.[/dim]\n")
                        continue
                    sess_md = loop.session_logger.md_path
                    if not sess_md.is_file():
                        console.print("[dim]기록된 세션 대화가 아직 없습니다.[/dim]\n")
                        continue

                    if format_type == "markdown":
                        console.print(f"✔ 현재 세션 마크다운 파일: [cyan]{sess_md}[/cyan]\n")
                    else:
                        pdf_out = Path(config.WORK_DIR) / "docs" / "pdf" / f"session_{loop.session_logger.session_id}.pdf"
                        console.print(f"[dim yellow]⚡ Gotenberg PDF 발간 중: {sess_md.name} -> {pdf_out.name}...[/dim yellow]")
                        ok, msg = convert_markdown_to_pdf(
                            sess_md.read_text(encoding="utf-8"),
                            pdf_out,
                            title=f"yunhee 대화 세션 기록 ({loop.session_logger.session_id})",
                        )
                        if ok:
                            console.print(f"[bold green]{msg}[/bold green]\n")
                        else:
                            console.print(f"[bold red]{msg}[/bold red]\n")
                    continue

                # Case 2: 기존 마크다운 파일인 경우
                target_path = Path(target).resolve()
                if target_path.is_file() and target_path.suffix.lower() == ".md":
                    if format_type == "markdown":
                        console.print(f"✔ 지정한 마크다운 파일: [cyan]{target_path}[/cyan]\n")
                    else:
                        pdf_out = Path(config.WORK_DIR) / "docs" / "pdf" / f"{target_path.stem}.pdf"
                        console.print(f"[dim yellow]⚡ Gotenberg PDF 변환 중: {target_path.name}...[/dim yellow]")
                        ok, msg = export_pdf_from_file(target_path, pdf_out)
                        if ok:
                            console.print(f"[bold green]{msg}[/bold green]\n")
                        else:
                            console.print(f"[bold red]{msg}[/bold red]\n")
                    continue

                # Case 3: 화면 코드인 경우 (정적 분석 ➜ 명세서 생성 ➜ [PDF 발간])
                console.print(f"[dim yellow]⚡ 화면 분석 및 마이그레이션 명세서 작성 중: '{target}'...[/dim yellow]")
                try:
                    md_content, spec_path = build_screen_spec_markdown(target)
                    console.print(f"✔ 마크다운 명세서 작성 완료: [cyan]{spec_path}[/cyan]")

                    if format_type == "pdf":
                        pdf_out = Path(config.WORK_DIR) / "docs" / "pdf" / f"{spec_path.stem}.pdf"
                        console.print(f"[dim yellow]⚡ Gotenberg PDF 발간 중: {pdf_out.name}...[/dim yellow]")
                        ok, msg = convert_markdown_to_pdf(
                            md_content,
                            pdf_out,
                            title=f"마이그레이션 기술 명세서: {spec_path.stem}",
                        )
                        if ok:
                            console.print(f"[bold green]{msg}[/bold green]\n")
                        else:
                            console.print(f"[bold red]{msg}[/bold red]\n")
                    else:
                        console.print()
                except Exception as e:  # noqa: BLE001
                    console.print(f"[bold red]명세서 작성 중 오류 발생:[/bold red] {e}\n")
                continue

            # 하이브리드 CLI 커맨드 처리 (예: /table, /outline, /log 등)
            if f"/{cmd}" in HYBRID_COMMANDS:
                if messages_history is None:
                    messages_history = [{"role": "system", "content": loop.system_prompt}]
                messages_history = _handle_hybrid_command(user_input, messages_history)
                continue

            console.print(f"[red]알 수 없는 명령어: /{cmd}[/red] ([dim]/help[/dim] 참고)\n")
            continue

        # 3. 에이전트 자율 루프 실행 (스피너, 도구 상태 카드, ESC 2회 인터럽트)
        def trigger_cancel() -> None:
            _thread.interrupt_main()

        try:
            with (
                listen_esc_cancel(trigger_cancel),
                console.status(
                    "[bold cyan]yunhee가 생각 중입니다...[/bold cyan] [dim](취소: ESC 2회)[/dim]",
                    spinner="dots",
                ) as status,
            ):

                def on_tool_call(name: str, args: dict[str, Any]) -> None:
                    status.update(format_tool_call_status(name, args))

                def on_tool_result(name: str, result: str) -> None:
                    status.update("[bold cyan]도구 결과 분석 및 다음 답변 정리 중...[/bold cyan]")
                    console.print(format_tool_result_preview(name, result))

                response, messages_history = loop.run(
                    user_input,
                    messages_history=messages_history,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                )

            # 4. 최종 에이전트 응답 출력 (Markdown 지원)
            console.print("\n[bold green]yunhee>[/bold green]")
            console.print(Markdown(response))
            console.print()

        except KeyboardInterrupt:
            # ESC 2회 연타 또는 터미널 인터럽트 발생 시
            console.print(
                "\n[bold yellow]⚠ 실행이 취소되었습니다 (ESC 2회). 새로운 요청을 입력하세요.[/bold yellow]\n"
            )
            continue
        except Exception as e:  # noqa: BLE001
            console.print(f"\n[bold red]오류 발생:[/bold red] {e}\n")
