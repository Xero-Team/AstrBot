import shutil
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete

from astrbot.core import logger

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
                except Exception as exc:
                    logger.warning("清空知识库表 %s 失败: %s", table_name, exc)

    for kb_id, kb_helper in list(kb_manager.kb_insts.items()):
        try:
            await kb_helper.terminate()
            if kb_helper.kb_dir.exists():
                shutil.rmtree(kb_helper.kb_dir)
        except Exception as exc:
            logger.warning("清理知识库 %s 失败: %s", kb_id, exc)

    kb_manager.kb_insts.clear()


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
                        session.add(model_class(**normalized_row))
                        count += 1
                    except Exception as exc:
                        logger.warning(
                            "导入知识库记录到 %s 失败: %s",
                            table_name,
                            exc,
                        )

                imported_tables[f"kb_{table_name}"] = count
