import typer

from yunhee import project
from yunhee.config import OLLAMA_MODEL
from yunhee.context.analyzer import summarize_page
from yunhee.ollama_client import chat, embed
from yunhee.store.vectorstore import add_texts
from yunhee.store.vectorstore import search as vector_search
from yunhee.ui.repl import run_repl

app = typer.Typer()


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
    """서브커맨드 없이 실행하면 바로 REPL 진입"""
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
):
    """ASIS 페이지 소스를 qwen으로 요약해 .yunhee/prep/<page_code>.md에 캐시 (prepare == prep, 완전히 동일)"""
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

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(summary)
    print(summary)


app.command(name="prepare")(_prepare)
app.command(name="prep")(_prepare)


if __name__ == "__main__":
    app()