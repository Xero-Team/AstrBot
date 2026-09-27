import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class Attachment(SQLModel, table=True):
    """This class represents attachments for messages in AstrBot.

    Attachments can be images, files, or other media types.
    """

    __tablename__ = "attachments"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    attachment_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    path: str = Field(nullable=False)  # Path to the file on disk
    type: str = Field(nullable=False)  # Type of the file (e.g., 'image', 'file')
    mime_type: str = Field(nullable=False)  # MIME type of the file
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
