from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console

from yunhee import config, project
from yunhee.config import OLLAMA_MODEL
from yunhee.ollama_client import chat_stream

HISTORY_FILE = Path.home() / ".yunhee_history"
console = Console()

COMMANDS = ["/help", "/exit", "/quit", "/clear", "/config", "/init"]

def _help_text() -> str:
    return f"""\
[bold]yunhee-cli[/bold] [dim]v{project.current_version()}[/dim]

[bold]사용 가능한 명령어[/bold]
  /help            이 도움말
  /exit, /quit     종료
  /clear           대화 맥락 초기화
  /config          현재 설정값 보기 (work-dir, yunhee-dir, .env.local 등)
  /init            현재 폴더를 yunhee 프로젝트로 등록/갱신 (.yunhee/project.json)
  /model <name>    사용 모델 변경 (예: /model qwen2.5-coder:14b)
"""


def _check_project() -> None:
    state = project.status()
    if state == "missing":
        console.print(
            "[yellow]이 폴더는 아직 yunhee 프로젝트로 등록되지 않았습니다.[/yellow] "
            "[dim]/init[/dim] 을 실행하세요.\n"
        )
    elif state == "outdated":
        data = project.load() or {}
        console.print(
            f"[yellow].yunhee 설정이 이전 yunhee 버전({data.get('yunhee_version')})으로 만들어졌습니다.[/yellow] "
            f"현재 버전({project.current_version()})으로 갱신하려면 [dim]/init[/dim] 을 실행하세요.\n"
        )


def run_repl(model: str = OLLAMA_MODEL) -> None:
    completer = WordCompleter(COMMANDS, ignore_case=True, sentence=True)
    session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=completer,
        complete_while_typing=True,
    )
    messages: list[dict] = []
    current_model = model

    console.print(
        f"[bold cyan]yunhee-cli[/bold cyan] [dim]v{project.current_version()} ({current_model})[/dim] "
        "— /help 로 명령어 확인\n"
    )
    _check_project()

    while True:
        try:
            user_input = session.prompt("you> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            parts = user_input[1:].split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd in ("exit", "quit"):
                console.print("[dim]bye[/dim]")
                break
            elif cmd == "clear":
                messages.clear()
                console.print("[dim]대화 맥락을 초기화했습니다.[/dim]\n")
            elif cmd == "help":
                console.print(_help_text())
            elif cmd == "config":
                console.print(f"[bold]현재 설정[/bold] [dim]v{project.current_version()}[/dim]")
                for key, value in config.summary().items():
                    console.print(f"  {key:<12} {value}")
                proj = project.load()
                proj_display = f"{proj['name']} (v{proj['yunhee_version']})" if proj else "(미등록 - /init 필요)"
                console.print(f"  {'project':<12} {proj_display}")
                console.print()
            elif cmd == "init":
                data = project.init()
                console.print(
                    f"[green]등록 완료[/green] {project.PROJECT_FILE}\n"
                    f"  name           {data['name']}\n"
                    f"  yunhee_version {data['yunhee_version']}\n"
                )
            else:
                console.print(f"[red]알 수 없는 명령어: /{cmd}[/red] ([dim]/help[/dim] 참고)\n")
            continue

        messages.append({"role": "user", "content": user_input})

        console.print("[bold green]yunhee>[/bold green] ", end="")
        full_response = ""
        for chunk in chat_stream(messages, model=current_model):
            console.print(chunk, end="", style="green")
            full_response += chunk
        console.print("\n")

        messages.append({"role": "assistant", "content": full_response})