"""
Tests for vectorstore and YUNHEE key prefix generation
"""

from unittest.mock import MagicMock, patch

from yunhee.store.vectorstore import (
    DEFAULT_KEY_PREFIX,
    add_texts,
    generate_doc_id,
)


def test_generate_doc_id():
    doc_id = generate_doc_id()
    assert doc_id.startswith("YUNHEE_")
    parts = doc_id.split("_")
    # YUNHEE, YYYYMMDD, HHMMSS, rand_suffix
    assert len(parts) >= 4
    assert parts[0] == DEFAULT_KEY_PREFIX


def test_generate_doc_id_custom_prefix():
    doc_id = generate_doc_id(prefix="YUNHEE_KB")
    assert doc_id.startswith("YUNHEE_KB_")


def test_add_texts_generates_yunhee_prefixed_ids():
    mock_collection = MagicMock()
    with patch("yunhee.store.vectorstore.get_collection", return_value=mock_collection):
        ids = add_texts(["첫 번째 문서", "두 번째 문서"])

    assert len(ids) == 2
    for doc_id in ids:
        assert doc_id.startswith("YUNHEE_")

    mock_collection.add.assert_called_once()
    kwargs = mock_collection.add.call_args.kwargs
    assert kwargs["documents"] == ["첫 번째 문서", "두 번째 문서"]
    assert kwargs["ids"] == ids


def test_add_texts_enforces_prefix_on_custom_ids():
    mock_collection = MagicMock()
    with patch("yunhee.store.vectorstore.get_collection", return_value=mock_collection):
        ids = add_texts(["문서 내용"], ids=["custom-id-1"])

    assert len(ids) == 1
    assert ids[0] == "YUNHEE_custom-id-1"

    # 이미 접두사가 있는 경우는 중복 추가 방지
    with patch("yunhee.store.vectorstore.get_collection", return_value=mock_collection):
        ids2 = add_texts(["문서 내용"], ids=["YUNHEE_existing-id"])
    assert ids2[0] == "YUNHEE_existing-id"
