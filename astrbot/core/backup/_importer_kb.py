import asyncio
import shutil
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete

from astrbot import logger
from astrbot.core.knowledge_base.models import KBDocument
from astrbot.core.utils.error_redaction import safe_error

from .constants import KB_METADATA_MODELS

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager


async def clear_kb_data(kb_manager: KnowledgeBaseManager | None) -> None:
    """Clear knowledge base metadata and on-disk KB content.

    Args:
        kb_manager: Knowledge base manager instance.
    """

    if kb_manager is None:
        return

    async with kb_manager.kb_db.get_db() as session:
        async with session.begin():
            for table_name, model_class in KB_METADATA_MODELS.items():
                try:
                    await session.execute(delete(model_class))
                    logger.debug("已清空知识库表 %s", table_name)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("清空知识库表失败: %s", safe_error("", exc))

    for _kb_id, kb_helper in list(kb_manager.kb_insts.items()):
        try:
            await kb_helper.terminate()
            if kb_helper.kb_dir.exists():
                shutil.rmtree(kb_helper.kb_dir)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("清理知识库失败: %s", safe_error("", exc))

    kb_manager.kb_insts.clear()


def _normalize_kb_document_row(row: dict[str, Any]) -> dict[str, Any]:
    """Fill identity columns so pre-identity backups import with unique keys."""
    normalized = dict(row)
    doc_id = str(normalized.get("doc_id") or "")
    if not normalized.get("identity_key"):
        normalized["identity_key"] = f"legacy:{doc_id}" if doc_id else ""
    normalized.setdefault("content_hash", "")
    normalized.setdefault("source_kind", "file")
    normalized.setdefault("source_url", None)
    return normalized


async def import_kb_metadata_tables(
    kb_manager: KnowledgeBaseManager | None,
    kb_meta_data: dict[str, list[dict[str, Any]]],
    imported_tables: dict[str, int],
    convert_datetime_fields: Any,
) -> None:
    """Import knowledge base metadata tables into the KB database.

    Args:
        kb_manager: Knowledge base manager instance.
        kb_meta_data: Raw metadata table payload from the backup.
        imported_tables: Mutable import statistics map to update in place.
        convert_datetime_fields: Row normalization callback.
    """

    if kb_manager is None:
        return

    async with kb_manager.kb_db.get_db() as session:
        async with session.begin():
            for table_name, rows in kb_meta_data.items():
                model_class = KB_METADATA_MODELS.get(table_name)
                if model_class is None:
                    continue

                count = 0
                for row in rows:
                    try:
                        normalized_row = convert_datetime_fields(row, model_class)
                        if model_class is KBDocument:
                            normalized_row = _normalize_kb_document_row(normalized_row)
                        allowed = set(model_class.model_fields)
                        normalized_row = {
                            key: value
                            for key, value in normalized_row.items()
                            if key in allowed
                        }
                        session.add(model_class(**normalized_row))
                        count += 1
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("导入知识库记录失败: %s", safe_error("", exc))

                imported_tables[f"kb_{table_name}"] = count
