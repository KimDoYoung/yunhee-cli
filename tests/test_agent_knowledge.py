"""
Tests for L2 Semantic Knowledge Memory (knowledge.py)
"""

from unittest.mock import MagicMock, patch

from yunhee.agent.knowledge import (
    prefetch_relevant_knowledge,
    save_knowledge,
    search_knowledge,
)


def test_save_knowledge():
    mock_col = MagicMock()
    with patch("yunhee.agent.knowledge.get_knowledge_collection", return_value=mock_col):
        res = save_knowledge(
            title="SysRoleMapper 삭제 주의사항",
            content="sys04_user_role을 서비스에서 먼저 삭제해야 함",
            category="mybatis",
            screen_id="sys04",
        )

    assert "성공적으로 저장되었습니다" in res
    assert "YUNHEE_KB_" in res
    assert "SysRoleMapper 삭제 주의사항" in res

    mock_col.add.assert_called_once()
    kwargs = mock_col.add.call_args.kwargs
    assert kwargs["documents"][0] == "[SysRoleMapper 삭제 주의사항] sys04_user_role을 서비스에서 먼저 삭제해야 함"
    assert kwargs["metadatas"][0]["category"] == "mybatis"
    assert kwargs["metadatas"][0]["screen_id"] == "sys04"


def test_search_knowledge():
    mock_col = MagicMock()
    mock_col.count.return_value = 1
    mock_col.query.return_value = {
        "documents": [["[SysRoleMapper 주의사항] 내용"]],
        "distances": [[0.25]],
        "metadatas": [[{"title": "SysRoleMapper 주의사항", "category": "mybatis"}]],
    }

    with patch("yunhee.agent.knowledge.get_knowledge_collection", return_value=mock_col):
        res = search_knowledge("SysRoleMapper")

    assert "SysRoleMapper 주의사항" in res
    assert "0.2500" in res
    assert "[SysRoleMapper 주의사항] 내용" in res


def test_prefetch_relevant_knowledge():
    mock_col = MagicMock()
    mock_col.count.return_value = 2
    # 하나는 가까운 거리(0.3), 하나는 먼 거리(0.85)
    mock_col.query.return_value = {
        "documents": [["[문서1] 유효한 팁", "[문서2] 너무 먼 지식"]],
        "distances": [[0.3, 0.85]],
        "metadatas": [[{"title": "문서1", "category": "tips"}, {"title": "문서2", "category": "other"}]],
    }

    with patch("yunhee.agent.knowledge.get_knowledge_collection", return_value=mock_col):
        context = prefetch_relevant_knowledge("팁 검색", max_distance=0.6)

    # 0.3인 문서1만 포함되고 0.85인 문서2는 제외되어야 함
    assert "문서1" in context
    assert "문서2" not in context
    assert "[참고 가능한 과거 지식 및 해결 사례" in context
