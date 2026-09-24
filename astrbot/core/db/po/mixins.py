from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class TimestampMixin(SQLModel):
    # Preserve legacy storage instead of SQLModel's inferred UTCDateTime type.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
