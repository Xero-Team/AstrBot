import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import JSON, Field, SQLModel


class ConversationV2(SQLModel, table=True):
    __tablename__ = "conversations"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    conversation_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    platform_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    content: list | None = Field(default=None, sa_type=JSON)
    """content is a list of OpenAI-formated messages in list[dict] format."""
    title: str | None = Field(default=None, max_length=255)
    prompt_id: str | None = Field(default=None)
    """Persona or prompt id resolved at run time; not a ``prompts`` row key."""
    token_usage: int = Field(default=0, nullable=False)
    """token_usage is the total token value of the messages.

    when 0, will use estimated token counter.
    """
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": datetime.now(UTC)},
    )
