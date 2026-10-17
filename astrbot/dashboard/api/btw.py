"""BTW work-session visibility routes."""

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.services.btw_service import BtwService

from .auth import AuthContext, require_scope

router = APIRouter(tags=["BTW"])


async def require_btw_scope(request: Request) -> AuthContext:
    """Require a Dashboard session with chat scope for internal run data.

    Work sessions span profiles and message origins, so a developer API key
    cannot be scoped to the rows they contain.  Keep this surface on the same
    authenticated control plane as the Dashboard page instead of widening the
    ``chat`` API-key capability to every retained task.
    """
    auth = await require_scope(request, "chat")
    if auth.via == "api_key":
        raise ApiError("Dashboard session required", status_code=403)
    return auth


def get_service(request: Request) -> BtwService:
    return request.app.state.services.btw


@router.get("/btw/work-sessions")
async def list_work_sessions(
    _auth: AuthContext = Depends(require_btw_scope),
    service: BtwService = Depends(get_service),
):
    """List active and retained BTW work sessions with delegation progress."""
    return ok({"sessions": await service.list_work_sessions()})
