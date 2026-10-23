"""
yunhee-cli L2 Semantic Knowledge Memory
ChromaDB + bge-m3 기반 재사용 가능한 경험/노하우/비즈니스 룰/코드 패턴을
벡터 저장하고 질문 시점에 가장 유사한 상위 지식(Top-3)만 소환하는 RAG 엔진.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from yunhee.store.vectorstore import (
    generate_doc_id,
    get_collection,
)

logger = logging.getLogger(__name__)

KNOWLEDGE_COLLECTION_NAME = "yunhee_knowledge"
KNOWLEDGE_KEY_PREFIX = "YUNHEE_KB"


def get_knowledge_collection():
    """ChromaDB의 yunhee_knowledge 컬렉션 반환."""
    return get_collection(name=KNOWLEDGE_COLLECTION_NAME)


def save_knowledge(
    title: str,
    content: str,
    category: str = "general",
    screen_id: str = "",
) -> str:
    """
    에러 해결 노하우, 비즈니스 특이사항, 코드 포팅 팁 등 재사용 가능한 지식을
    ChromaDB 벡터 스토어에 영구 저장합니다. (bge-m3 임베딩)
    """
    clean_title = title.strip()
    clean_content = content.strip()

    if not clean_title or not clean_content:
        return "error: 제목(title)과 내용(content)은 필수 항목입니다."

    doc_id = generate_doc_id(prefix=KNOWLEDGE_KEY_PREFIX)
    full_document = f"[{clean_title}] {clean_content}"

    metadata: dict[str, Any] = {
        "title": clean_title,
        "category": category.strip() or "general",
        "screen_id": screen_id.strip(),
        "created_at": datetime.now(UTC).isoformat(),
    }

    try:
        col = get_knowledge_collection()
        col.add(
            documents=[full_document],
            ids=[doc_id],
            metadatas=[metadata],
        )
        return (
            f"✔ 지식이 성공적으로 저장되었습니다.\n"
            f"  - ID:       {doc_id}\n"
            f"  - 제목:     {clean_title}\n"
            f"  - 카테고리: {category}"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("save_knowledge 실패: %s", e)
        return f"error: 지식 저장 중 오류가 발생했습니다 ({e})"


def search_knowledge(query: str, limit: int = 3) -> str:
    """
    과거에 축적된 지식 베이스(ChromaDB)에서 현재 작업과 유사한 노하우 및 해결 사례를 검색합니다.
    """
    clean_query = query.strip()
    if not clean_query:
        return "error: 검색할 쿼리가 비어 있습니다."

    try:
        col = get_knowledge_collection()
        count = col.count()
        if count == 0:
            return "안내: 등록된 지식 베이스 문서가 없습니다."

        n_results = min(limit, count)
        results = col.query(query_texts=[clean_query], n_results=n_results)

        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return "일치하는 지식이 없습니다."

        output_lines = [f"[검색 결과: '{clean_query}' (총 {len(documents)}건)]"]
        for idx, (doc, dist, meta) in enumerate(zip(documents, distances, metadatas), 1):
            title = meta.get("title", "제목 없음") if meta else "제목 없음"
            cat = meta.get("category", "") if meta else ""
            cat_str = f" [{cat}]" if cat else ""
            dist_str = f" (거리: {dist:.4f})" if dist is not None else ""
            output_lines.append(f"{idx}. {title}{cat_str}{dist_str}")
            output_lines.append(f"   {doc}")

        return "\n".join(output_lines)

    except Exception as e:  # noqa: BLE001
        logger.warning("search_knowledge 실패: %s", e)
        return f"error: 지식 검색 중 오류가 발생했습니다 ({e})"


def prefetch_relevant_knowledge(
    query: str,
    limit: int = 3,
    max_distance: float = 0.6,
) -> str:
    """
    에이전트 루프가 프롬프트를 전송하기 전, 사용자의 질문과 가장 밀접한
    과거 지식 상위 n개를 ChromaDB에서 능동 검색하여 프롬프트에 주입할 섹션 문자열을 반환합니다.
    연관 지식이 없거나 거리가 멀면 0 토큰(빈 문자열)을 반환합니다.
    """
    clean_query = query.strip()
    if not clean_query or len(clean_query) < 3:
        return ""

    try:
        col = get_knowledge_collection()
        if col.count() == 0:
            return ""

        results = col.query(query_texts=[clean_query], n_results=min(limit, col.count()))
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        relevant_docs: list[str] = []
        for doc, dist, meta in zip(documents, distances, metadatas):
            # 거리 임계값 이내의 지식만 선별
            if dist is not None and dist > max_distance:
                continue
            title = meta.get("title", "") if meta else ""
            cat = meta.get("category", "") if meta else ""
            cat_info = f"({cat}) " if cat else ""
            relevant_docs.append(f"- [{title}] {cat_info}{doc}")

        if not relevant_docs:
            return ""

        return (
            "[참고 가능한 과거 지식 및 해결 사례 (Semantic Knowledge)]\n"
            + "\n".join(relevant_docs)
            + "\n\n"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("prefetch_relevant_knowledge 무시: %s", e)
        return ""
