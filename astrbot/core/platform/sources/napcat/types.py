"""Normalized NapCat runtime types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NapCatLoginInfo:
    user_id: int
    nickname: str
    qid: str | None = None
    remark: str | None = None
    sex: str | None = None
    age: int | None = None
    level: int | None = None
    login_days: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NapCatStatus:
    online: bool
    good: bool
    stats: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NapCatVersionInfo:
    app_name: str
    app_version: str
    protocol_version: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NapCatSendMessageResult:
    message_id: int
    res_id: str | None = None
    forward_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NapCatFetchedMessage:
    message_id: int
    sender_id: int | None = None
    sender_nickname: str | None = None
    time: int | None = None
    message_str: str = ""
    raw_message: str = ""
    message_payload: object | None = None
    extra: dict[str, Any] = field(default_factory=dict)
