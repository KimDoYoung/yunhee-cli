from pathlib import Path
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from yunhee.ollama_client import embed

# store/vectorstore.py 기준 4단계 위 = 프로젝트 루트 (src/yunhee/store -> src/yunhee -> src -> root)
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "chroma"


class OllamaEmbeddingFunction(EmbeddingFunction):
    """chromadb가 문서를 저장/검색할 때 bge-m3로 임베딩하도록 연결"""

    def __call__(self, input: Documents) -> Embeddings:
        return [embed(text) for text in input]


def get_collection(name: str = "yunhee"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(DATA_DIR))
    return client.get_or_create_collection(
        name=name,
        embedding_function=OllamaEmbeddingFunction(),
    )


def add_texts(texts: list[str], ids: list[str] | None = None) -> None:
    collection = get_collection()
    if ids is None:
        existing = collection.count()
        ids = [f"doc-{existing + i}" for i in range(len(texts))]
    collection.add(documents=texts, ids=ids)


def search(query_text: str, n_results: int = 3):
    collection = get_collection()
    return collection.query(query_texts=[query_text], n_results=n_results)