import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class PlatformSession(SQLModel, table=True):
    """Platform session table for managing user sessions across different platforms.

    A session represents a chat window for a specific user on a specific platform.
    Each session can have multiple conversations (对话) associated with it.
    """

    __tablename__ = "platform_sessions"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    session_id: str = Field(
        max_length=100,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    platform_id: str = Field(default="webchat", nullable=False)
    """Platform identifier (e.g., 'webchat', 'qq', 'discord')"""
    creator: str = Field(nullable=False)
    """Username of the session creator"""
    display_name: str | None = Field(default=None, max_length=255)
    """Display name for the session"""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": datetime.now(UTC)},
    )


class UmoAlias(SQLModel, table=True):
    """User-facing names for unified message origins."""

    __tablename__ = "umo_aliases"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    umo: str = Field(nullable=False, max_length=512, unique=True, index=True)
    creator_sender_id: str = Field(nullable=False, max_length=255)
    auto_name: str | None = Field(default=None, max_length=255)
    user_alias: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": datetime.now(UTC)},
    )
