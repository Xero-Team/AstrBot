from sqlmodel import JSON, Column, Field, SQLModel, UniqueConstraint

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
