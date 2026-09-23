import uuid

from sqlmodel import JSON, Field, SQLModel, Text, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class PersonaFolder(TimestampMixin, SQLModel, table=True):
    """Persona 文件夹，支持递归层级结构。

    用于组织和管理多个 Persona，类似于文件系统的目录结构。
    """

    __tablename__ = "persona_folders"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    folder_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    name: str = Field(max_length=255, nullable=False)
    parent_id: str | None = Field(default=None, max_length=36)
    """父文件夹ID，NULL表示根目录"""
    description: str | None = Field(default=None, sa_type=Text)
    sort_order: int = Field(default=0)

    __table_args__ = (
        UniqueConstraint(
            "folder_id",
            name="uix_persona_folder_id",
        ),
    )


class Persona(TimestampMixin, SQLModel, table=True):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__ = "personas"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: list | None = Field(default=None, sa_type=JSON)
    """a list of strings, each representing a dialog to start with"""
    tools: list | None = Field(default=None, sa_type=JSON)
    """None means use ALL tools for default, empty list means no tools, otherwise a list of tool names."""
    skills: list | None = Field(default=None, sa_type=JSON)
    """None means use ALL skills for default, empty list means no skills, otherwise a list of skill names."""
    custom_error_message: str | None = Field(default=None, sa_type=Text)
    """Optional custom error message sent to end users when the agent request fails."""
    folder_id: str | None = Field(default=None, max_length=36)
    """所属文件夹ID，NULL 表示在根目录"""
    sort_order: int = Field(default=0)
    """排序顺序"""

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            name="uix_persona_id",
        ),
    )
