from sqlmodel import JSON, Field, SQLModel

from astrbot.core.db.po.mixins import TimestampMixin


class KnowledgeBaseTask(TimestampMixin, SQLModel, table=True):
    """Persisted state for one Dashboard knowledge-base ingestion task."""

    __tablename__ = "knowledge_base_tasks"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    task_id: str = Field(max_length=64, nullable=False, unique=True, index=True)
    operation_kind: str = Field(max_length=32, nullable=False, index=True)
    kb_id: str = Field(max_length=64, nullable=False, index=True)
    status: str = Field(default="pending", max_length=32, nullable=False, index=True)
    progress: dict = Field(default_factory=dict, sa_type=JSON)
    result: dict | None = Field(default=None, sa_type=JSON)
    error: str | None = Field(default=None, max_length=512)
