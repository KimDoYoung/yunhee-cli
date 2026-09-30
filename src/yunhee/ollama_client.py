import json
import sys
from collections.abc import Iterator

import httpx

from yunhee.config import EMBED_MODEL, NUM_CTX, OLLAMA_HOST, OLLAMA_MODEL

DEFAULT_TIMEOUT = 300.0  # 콜드 스타트 대비 넉넉하게


def _warn_if_truncated(data: dict) -> None:
    """Ollama는 num_ctx를 넘는 프롬프트의 앞부분을 조용히 버린다.

    실제로 평가한 프롬프트 토큰 수(prompt_eval_count)가 num_ctx에 닿았으면 잘린 것으로 보고 stderr에 경고한다.
    (프롬프트 캐시가 적중하면 prompt_eval_count가 작게 나올 수 있어 잘림을 놓칠 수는 있지만, 오탐은 없다.)
    """
    evaluated = data.get("prompt_eval_count") or 0
    if evaluated >= NUM_CTX:
        print(
            f"\n[yunhee] 경고: 프롬프트가 num_ctx({NUM_CTX} 토큰)를 넘어 앞부분이 잘렸습니다. "
            "입력을 줄이거나(/clear 등) YUNHEE_NUM_CTX를 늘리세요.",
            file=sys.stderr,
        )


def chat(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Ollama에 단발성 질의를 보내고 응답 텍스트를 반환"""
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_ctx": NUM_CTX},
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    _warn_if_truncated(data)
    return data["message"]["content"]


def embed(text: str, model: str = EMBED_MODEL) -> list[float]:
    """텍스트를 bge-m3로 임베딩해서 float 벡터로 반환"""
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/embed",
        json={
            "model": model,
            "input": text,
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    # /api/embed는 embeddings: [[...]] 형태로 반환 (배치 입력 대비 리스트의 리스트)
    return resp.json()["embeddings"][0]


def chat_stream(messages: list[dict], model: str = OLLAMA_MODEL) -> Iterator[str]:
    """Ollama에 멀티턴 대화를 보내고, 응답을 토큰(청크) 단위로 yield"""
    with httpx.stream(
        "POST",
        f"{OLLAMA_HOST}/api/chat",
        json={"model": model, "messages": messages, "stream": True, "options": {"num_ctx": NUM_CTX}},
        timeout=DEFAULT_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            content = data.get("message", {}).get("content", "")
            if content:
                yield content
            if data.get("done"):
                _warn_if_truncated(data)
                break