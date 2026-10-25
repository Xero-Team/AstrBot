"""Raw Dashboard Extension Protocol v1 file-ticket route."""

from collections.abc import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from astrbot.dashboard.services.plugin_file_ticket_service import (
    FILE_TICKET_COOKIE_NAME,
    PluginFileTicketService,
    RawFileError,
    content_disposition_header,
)

from .auth import use_secure_dashboard_cookie

router = APIRouter(include_in_schema=False)


def _raw_error(status_code: int) -> Response:
    message = b"Unauthorized" if status_code == 401 else b"Not found"
    return Response(
        message,
        status_code=status_code,
        media_type="text/plain",
        headers={"Cache-Control": "no-store"},
    )


def _file_chunks(handle) -> Iterator[bytes]:
    try:
        while chunk := handle.read(128 * 1024):
            yield chunk
    finally:
        handle.close()


@router.get("/api/plugin-files/v1/{ticket_handle}")
async def get_plugin_file(ticket_handle: str, request: Request):
    if (
        request.headers.get("authorization")
        or request.headers.get("x-api-key")
        or request.query_params
    ):
        return _raw_error(401)
    if request.headers.get("range"):
        return Response(
            b"Range not supported",
            status_code=416,
            media_type="text/plain",
            headers={"Cache-Control": "no-store", "Accept-Ranges": "none"},
        )
    service: PluginFileTicketService = request.app.state.services.plugin_file_tickets
    try:
        redeemed = await service.redeem(
            ticket_handle,
            request.cookies.get(FILE_TICKET_COOKIE_NAME),
        )
    except RawFileError as exc:
        return _raw_error(exc.status_code)
    response = StreamingResponse(
        _file_chunks(redeemed.file_handle),
        media_type=redeemed.content_type,
        headers={
            "Content-Length": str(redeemed.size),
            "Content-Disposition": content_disposition_header(
                redeemed.disposition,
                redeemed.filename,
            ),
            "Cache-Control": "no-store",
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
            "Accept-Ranges": "none",
        },
    )
    if redeemed.clear_cookie:
        response.delete_cookie(
            FILE_TICKET_COOKIE_NAME,
            path=f"/api/plugin-files/v1/{ticket_handle}",
            httponly=True,
            samesite="strict",
            secure=use_secure_dashboard_cookie(request),
        )
    return response
