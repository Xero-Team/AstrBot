import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel, Text


class WebChatThread(SQLModel, table=True):
    """A side thread created from a selected WebChat assistant response."""

    __tablename__ = "webchat_threads"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    thread_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    creator: str = Field(nullable=False, index=True)
    parent_session_id: str = Field(
        nullable=False,
        index=True,
        foreign_key="platform_sessions.session_id",
        ondelete="CASCADE",
    )
    parent_message_id: int = Field(nullable=False, index=True)
    base_checkpoint_id: str = Field(nullable=False, index=True)
    selected_text: str = Field(sa_type=Text, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
