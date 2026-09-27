from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import JSON, Field, SQLModel, UniqueConstraint


class Preference(SQLModel, table=True):
    """This class represents preferences for bots."""

    __tablename__ = "preferences"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    scope: str = Field(nullable=False)
    """Scope of the preference, such as 'global', 'umo', 'plugin'."""
    scope_id: str = Field(nullable=False)
    """ID of the scope, such as 'global', 'umo', 'plugin_name'."""
    key: str = Field(nullable=False)
    value: dict = Field(sa_type=JSON, nullable=False)
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
            "scope",
            "scope_id",
            "key",
            name="uix_preference_scope_scope_id_key",
        ),
    )
