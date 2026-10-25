from fastapi import APIRouter, WebSocket

from astrbot.dashboard.services.webchat_service import WebChatService

router = APIRouter(tags=["Chat"])


def get_service(websocket: WebSocket) -> WebChatService:
    return websocket.app.state.services.webchat


def websocket_auth_from_protocols(
    protocols: str | None,
) -> tuple[str | None, str | None]:
    """Return the bearer token and the accepted subprotocol.

    Browsers send ``Sec-WebSocket-Protocol`` as a comma-separated list. The
    first non-marker entry is the Dashboard JWT; ``astrbot`` is echoed back as
    the accepted protocol so the token never enters the URL.
    """
    if not protocols:
        return None, None
    offered = [item.strip() for item in protocols.split(",") if item.strip()]
    token = next((item for item in offered if item != "astrbot"), None)
    return token, ("astrbot" if "astrbot" in offered else None)


async def _run_unified_chat_ws(
    websocket: WebSocket,
) -> None:
    token, subprotocol = websocket_auth_from_protocols(
        websocket.headers.get("sec-websocket-protocol")
    )
    await websocket.accept(subprotocol=subprotocol)
    service = get_service(websocket)
    await service.run_websocket_session(
        token=token,
        receive_json=websocket.receive_json,
        send_json=websocket.send_json,
        close=websocket.close,
    )


@router.websocket("/unified-chat/ws")
async def unified_chat_ws(websocket: WebSocket) -> None:
    await _run_unified_chat_ws(websocket)
