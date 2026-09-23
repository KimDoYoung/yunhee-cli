from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console

from yunhee.config import OLLAMA_MODEL
from yunhee.ollama_client import chat_stream

HISTORY_FILE = Path.home() / ".yunhee_history"
console = Console()

COMMANDS = ["/help", "/exit", "/quit", "/clear"]

HELP_TEXT = """\
[bold]사용 가능한 명령어[/bold]
  /help            이 도움말
  /exit, /quit     종료
  /clear           대화 맥락 초기화
  /model <name>    사용 모델 변경 (예: /model qwen2.5-coder:14b)
"""


def run_repl(model: str = OLLAMA_MODEL) -> None:
    completer = WordCompleter(COMMANDS, ignore_case=True, sentence=True)
    session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=completer,
        complete_while_typing=True,
    )
    messages: list[dict] = []
    current_model = model

    console.print(f"[bold cyan]yunhee-cli[/bold cyan] [dim]({current_model})[/dim] — /help 로 명령어 확인\n")

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
                console.print(HELP_TEXT)
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