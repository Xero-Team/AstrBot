from datetime import UTC, datetime

from sqlmodel import (
    JSON,
    Column,
    Field,
    Index,
    SQLModel,
    UniqueConstraint,
)

from astrbot.core.db.po.mixins import TimestampMixin


class SessionBridgeRule(TimestampMixin, SQLModel, table=True):
    """Persisted directed edge for a session-bridge watch, connect, or pair."""

    __tablename__ = "session_bridge_rules"  # type: ignore

    rule_id: str = Field(primary_key=True, max_length=12, nullable=False)
    subject_id: str = Field(nullable=False, max_length=512, index=True)
    source_umo: str = Field(nullable=False, max_length=512)
    target_umo: str = Field(nullable=False, max_length=512)
    source_config_id: str = Field(nullable=False, max_length=128, index=True)
    target_config_id: str = Field(nullable=False, max_length=128, index=True)
    kind: str = Field(nullable=False, max_length=32, index=True)
    expires_at: int | None = Field(default=None)
    header: bool = Field(default=True, nullable=False)
    pair_id: str | None = Field(default=None, max_length=12)
    match: dict = Field(default_factory=dict, sa_type=JSON, nullable=False)
    except_: dict = Field(
        default_factory=dict,
        sa_column=Column("except", JSON, nullable=False),
    )

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "source_umo",
            "target_umo",
            name="uix_session_bridge_direction",
        ),
    )


class SessionBridgeDelivery(SQLModel, table=True):
    """Durable record of one successful session-bridge delivery.

    One row serves two purposes: it proves that ``source_message_id`` was
    forwarded from ``origin_umo`` into ``dest_umo`` (restart-surviving dedup)
    and carries the destination-side message id so a later cross-platform
    quote/reply can be resolved back to the original message.
    """

    __tablename__ = "session_bridge_deliveries"  # type: ignore

    id: int = Field(primary_key=True, default=None)
    dest_umo: str = Field(nullable=False, max_length=512)
    origin_umo: str = Field(nullable=False, max_length=512)
    source_message_id: str = Field(nullable=False, max_length=512)
    dest_message_id: str | None = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint(
            "dest_umo",
            "origin_umo",
            "source_message_id",
            name="uix_session_bridge_delivery",
        ),
        Index("ix_session_bridge_dest_msg", "dest_umo", "dest_message_id"),
        Index("ix_session_bridge_created_at", "created_at"),
    )
