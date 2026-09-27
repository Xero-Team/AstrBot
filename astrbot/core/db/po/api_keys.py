import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import JSON, Field, SQLModel


class ApiKey(SQLModel, table=True):
    """API keys used by external developers to access Open APIs."""

    __tablename__ = "api_keys"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    key_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    name: str = Field(max_length=255, nullable=False)
    key_hash: str = Field(max_length=128, nullable=False, unique=True)
    key_prefix: str = Field(max_length=24, nullable=False)
    scopes: list | None = Field(default=None, sa_type=JSON)
    created_by: str = Field(max_length=255, nullable=False)
    last_used_at: datetime | None = Field(default=None, sa_type=DateTime)
    expires_at: datetime | None = Field(default=None, sa_type=DateTime)
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": datetime.now(UTC)},
    )
