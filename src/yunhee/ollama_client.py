import json
from collections.abc import Iterator

import httpx

from yunhee.config import EMBED_MODEL, OLLAMA_HOST, OLLAMA_MODEL

DEFAULT_TIMEOUT = 300.0  # 콜드 스타트 대비 넉넉하게


def chat(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Ollama에 단발성 질의를 보내고 응답 텍스트를 반환"""
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


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
        json={"model": model, "messages": messages, "stream": True},
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
                break