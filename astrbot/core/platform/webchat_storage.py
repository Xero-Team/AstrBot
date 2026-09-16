from typing import Protocol, runtime_checkable

from astrbot.core.db.protocols import AttachmentStore, MessageHistoryStore


@runtime_checkable
class WebChatStorageStore(AttachmentStore, MessageHistoryStore, Protocol):
    """Attachment and history persistence for the WebChat adapter."""
