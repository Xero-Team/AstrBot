from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    PromptFolderRequest,
    PromptMoveRequest,
    PromptReorderRequest,
    PromptRequest,
    model_patch_dict,
)
from astrbot.dashboard.services.prompt_service import (
    PromptService,
    PromptServiceError,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Prompts"])


def get_service(request: Request) -> PromptService:
    return request.app.state.services.prompts


async def require_prompt_scope(request: Request) -> AuthContext:
    return await require_scope(request, "prompt")


def _raise_prompt_error(exc: PromptServiceError | ValueError) -> None:
    raise ApiError(str(exc)) from exc


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except (PromptServiceError, ValueError) as exc:
        _raise_prompt_error(exc)


@router.get("/prompts/tree")
async def prompt_tree(
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(service.get_folder_tree)


@router.get("/prompts")
async def list_prompts(
    request: Request,
    folder_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(
        lambda: service.list_prompts(folder_id, "folder_id" in request.query_params)
    )


@router.post("/prompts")
async def create_prompt(
    payload: PromptRequest,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.create_prompt(model_patch_dict(payload)))


@router.post("/prompts/move")
async def move_prompt(
    payload: PromptMoveRequest,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.move_prompt(model_patch_dict(payload)))


@router.post("/prompts/reorder")
async def reorder_prompts(
    payload: PromptReorderRequest,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.reorder_items(model_patch_dict(payload)))


@router.get("/prompt-folders")
async def list_prompt_folders(
    parent_id: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.list_folders(parent_id))


@router.post("/prompt-folders")
async def create_prompt_folder(
    payload: PromptFolderRequest,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.create_folder(model_patch_dict(payload)))


@router.put("/prompt-folders/{folder_id:path}")
async def update_prompt_folder(
    folder_id: str,
    payload: PromptFolderRequest,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(
        lambda: service.update_folder(
            {"folder_id": folder_id, **model_patch_dict(payload)}
        )
    )


@router.delete("/prompt-folders/{folder_id:path}")
async def delete_prompt_folder(
    folder_id: str,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.delete_folder({"folder_id": folder_id}))


@router.get("/prompts/{prompt_id:path}")
async def get_prompt(
    prompt_id: str,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.get_prompt_detail({"prompt_id": prompt_id}))


@router.put("/prompts/{prompt_id:path}")
async def update_prompt(
    prompt_id: str,
    payload: PromptRequest,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(
        lambda: service.update_prompt(
            {"prompt_id": prompt_id, **model_patch_dict(payload)}
        )
    )


@router.delete("/prompts/{prompt_id:path}")
async def delete_prompt(
    prompt_id: str,
    _auth: AuthContext = Depends(require_prompt_scope),
    service: PromptService = Depends(get_service),
):
    return await _run(lambda: service.delete_prompt({"prompt_id": prompt_id}))
