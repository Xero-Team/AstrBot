"""Test knowledge base lookup by name."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.knowledge_base.models import KnowledgeBase


def _manager_with(helpers: dict) -> KnowledgeBaseManager:
    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.kb_insts = helpers
    return kb_mgr


def _helper(kb_id: str, kb_name: str) -> MagicMock:
    helper = MagicMock()
    helper.kb = KnowledgeBase(
        kb_id=kb_id,
        kb_name=kb_name,
        description="Test KB",
        emoji="📚",
        doc_count=1,
        chunk_count=2,
    )
    return helper


class TestKBNameLookup:
    @pytest.mark.asyncio
    async def test_get_kb_by_name_with_name(self):
        helper = _helper("bb47bf6f-3315-49bd-9c9a-7cc4aa9abbac", "测试")
        kb_mgr = _manager_with({helper.kb.kb_id: helper})

        result = await kb_mgr.get_kb_by_name("测试")

        assert result is helper

    @pytest.mark.asyncio
    async def test_get_kb_by_name_does_not_match_id(self):
        helper = _helper("bb47bf6f-3315-49bd-9c9a-7cc4aa9abbac", "测试")
        kb_mgr = _manager_with({helper.kb.kb_id: helper})

        result = await kb_mgr.get_kb_by_name(helper.kb.kb_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_kb_by_name_not_found(self):
        helper = _helper("bb47bf6f-3315-49bd-9c9a-7cc4aa9abbac", "测试")
        kb_mgr = _manager_with({helper.kb.kb_id: helper})

        result = await kb_mgr.get_kb_by_name("non-existent-kb")

        assert result is None


class TestCheckAllKB:
    """Test check_all_kb distinguishes None from empty KB"""

    def test_check_all_kb_with_valid_non_empty_kb(self):
        """Should return False when KB has documents"""
        from unittest.mock import MagicMock

        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        mock_kb = KnowledgeBase(
            kb_id="kb-1",
            kb_name="Non-empty KB",
            description="",
            emoji="📚",
            doc_count=1,
            chunk_count=2,
        )
        mock_helper = MagicMock()
        mock_helper.kb = mock_kb

        kb_list = [mock_helper]
        result = check_all_kb(kb_list)

        assert result is False

    def test_check_all_kb_with_valid_empty_kb(self):
        """Should return True when KB is empty"""
        from unittest.mock import MagicMock

        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        mock_kb = KnowledgeBase(
            kb_id="kb-2",
            kb_name="Empty KB",
            description="",
            emoji="📚",
            doc_count=0,
            chunk_count=0,
        )
        mock_helper = MagicMock()
        mock_helper.kb = mock_kb

        kb_list = [mock_helper]
        result = check_all_kb(kb_list)

        assert result is True

    def test_check_all_kb_with_none(self):
        """Should return True and log warning when KB is None"""
        from unittest.mock import patch

        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        with patch("astrbot.core.tools.knowledge_base_tools.logger") as mock_logger:
            kb_list = [None]
            result = check_all_kb(kb_list)

            assert result is True
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "1/1" in call_args
            assert "未找到或未加载" in call_args

    def test_check_all_kb_mixed(self):
        """Should return False when at least one KB has documents"""
        from unittest.mock import MagicMock, patch

        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        mock_kb_empty = KnowledgeBase(
            kb_id="kb-2",
            kb_name="Empty KB",
            description="",
            emoji="📚",
            doc_count=0,
            chunk_count=0,
        )
        mock_helper_empty = MagicMock()
        mock_helper_empty.kb = mock_kb_empty

        mock_kb_non_empty = KnowledgeBase(
            kb_id="kb-1",
            kb_name="Non-empty KB",
            description="",
            emoji="📚",
            doc_count=1,
            chunk_count=2,
        )
        mock_helper_non_empty = MagicMock()
        mock_helper_non_empty.kb = mock_kb_non_empty

        with patch("astrbot.core.tools.knowledge_base_tools.logger") as mock_logger:
            kb_list = [None, mock_helper_empty, mock_helper_non_empty]
            result = check_all_kb(kb_list)

            assert result is False
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "1/3" in call_args

    def test_check_all_kb_all_none(self):
        """Should return True and log warning when all KBs are None"""
        from unittest.mock import patch

        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        with patch("astrbot.core.tools.knowledge_base_tools.logger") as mock_logger:
            kb_list = [None, None, None]
            result = check_all_kb(kb_list)

            assert result is True
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "3/3" in call_args
