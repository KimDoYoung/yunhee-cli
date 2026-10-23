from __future__ import annotations

import uuid
from datetime import UTC, datetime

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from yunhee.config import CHROMA_HOST, CHROMA_PORT
from yunhee.ollama_client import embed

DEFAULT_KEY_PREFIX = "YUNHEE"


class OllamaEmbeddingFunction(EmbeddingFunction):
    """chromadb가 문서를 저장/검색할 때 bge-m3로 임베딩하도록 연결"""

    def __init__(self) -> None:
        pass

    def name(self) -> str:
        return "ollama_bge_m3"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> OllamaEmbeddingFunction:
        return OllamaEmbeddingFunction()

    def __call__(self, input: Documents) -> Embeddings:
        return [embed(text) for text in input]


def generate_doc_id(prefix: str = DEFAULT_KEY_PREFIX) -> str:
    """YUNHEE_YYYYMMDD_HHMMSS_xxxxxx 규격의 고유 문서 ID 생성."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    rand_suffix = uuid.uuid4().hex[:6]
    return f"{prefix}_{timestamp}_{rand_suffix}"


def get_collection(name: str = "yunhee"):
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return client.get_or_create_collection(
        name=name,
        embedding_function=OllamaEmbeddingFunction(),
    )


def add_texts(
    texts: list[str],
    ids: list[str] | None = None,
    metadatas: list[dict] | None = None,
    prefix: str = DEFAULT_KEY_PREFIX,
) -> list[str]:
    """
    문서 목록을 ChromaDB에 적재합니다.
    ids가 주어지지 않으면 YUNHEE_ 접두사를 가진 고유 ID를 자동 발급합니다.
    """
    collection = get_collection()
    if ids is None:
        ids = [generate_doc_id(prefix=prefix) for _ in range(len(texts))]
    else:
        # 사용자가 넘겨준 id라도 YUNHEE 접두사가 없으면 붙여주거나 보존
        ids = [
            i if i.startswith((f"{prefix}_", f"{prefix}-")) else f"{prefix}_{i}"
            for i in ids
        ]

    kwargs = {"documents": texts, "ids": ids}
    if metadatas is not None:
        kwargs["metadatas"] = metadatas

    collection.add(**kwargs)
    return ids


def search(query_text: str, n_results: int = 3):
    collection = get_collection()
    return collection.query(query_texts=[query_text], n_results=n_results)
