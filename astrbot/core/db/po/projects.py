import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel, UniqueConstraint


class ChatUIProject(SQLModel, table=True):
    """This class represents projects for organizing ChatUI conversations.

    Projects allow users to group related conversations together.
    """

    __tablename__ = "chatui_projects"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    project_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    creator: str = Field(nullable=False)
    """Username of the project creator"""
    emoji: str | None = Field(default="📁", max_length=10)
    """Emoji icon for the project"""
    title: str = Field(nullable=False, max_length=255)
    """Title of the project"""
    description: str | None = Field(default=None, max_length=1000)
    """Description of the project"""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": datetime.now(UTC)},
    )


class SessionProjectRelation(SQLModel, table=True):
    """This class represents the relationship between platform sessions and ChatUI projects."""

    __tablename__ = "session_project_relations"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    session_id: str = Field(nullable=False, max_length=100)
    """Session ID from PlatformSession"""
    project_id: str = Field(nullable=False, max_length=36)
    """Project ID from ChatUIProject"""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": datetime.now(UTC)},
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uix_session_project_relation",
        ),
    )
