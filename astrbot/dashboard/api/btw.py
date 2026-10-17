"""BTW work-session visibility routes."""

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ok
from astrbot.dashboard.services.btw_service import BtwService

from .auth import AuthContext, require_scope

router = APIRouter(tags=["BTW"])


async def require_btw_scope(request: Request) -> AuthContext:
    """Work sessions are chat data; reading them needs the session scope."""
    return await require_scope(request, "chat")


def get_service(request: Request) -> BtwService:
    return request.app.state.services.btw


@router.get("/btw/work-sessions")
async def list_work_sessions(
    _auth: AuthContext = Depends(require_btw_scope),
    service: BtwService = Depends(get_service),
):
    """List active and retained BTW work sessions with delegation progress."""
    return ok({"sessions": await service.list_work_sessions()})
