"""NapCat runtime exceptions."""

from __future__ import annotations


class NapCatError(Exception):
    """Base exception for NapCat runtime failures."""


class NapCatTransportError(NapCatError):
    """Raised when the NapCat transport fails before a valid API payload exists."""

    def __init__(self, operation: str, detail: str) -> None:
        super().__init__(f"NapCat transport error during {operation}: {detail}")
        self.operation = operation
        self.detail = detail


class NapCatApiError(NapCatError):
    """Raised when NapCat returns a business-level failure payload."""

    def __init__(
        self,
        operation: str,
        *,
        status: str | None,
        retcode: int | None,
        message: str | None,
        wording: str | None,
    ) -> None:
        summary = message or wording or "NapCat API returned a failed response"
        super().__init__(
            f"NapCat API error during {operation}: "
            f"status={status!r} retcode={retcode!r} detail={summary}"
        )
        self.operation = operation
        self.status = status
        self.retcode = retcode
        self.message = message
        self.wording = wording
