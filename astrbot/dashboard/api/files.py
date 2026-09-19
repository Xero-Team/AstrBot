from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from astrbot.core.auth.models import Resource
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import ChatUploadInitRequest, ChatUploadSessionRequest
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError
from astrbot.dashboard.services.file_service import FileService, FileServiceError
from astrbot.dashboard.upload_utils import UploadFileAdapter

from .auth import AuthContext, object_resource, require_resource_action, require_scope

router = APIRouter(tags=["Files"])
_BINARY_FILE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "File bytes or an error envelope",
        "content": {
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            }
        },
    }
}


def get_service(request: Request) -> FileService:
    return request.app.state.services.files


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.services.chat


async def require_file_scope(request: Request) -> AuthContext:
    auth = await require_scope(request, "file")
    attachment_id = request.path_params.get("attachment_id")
    resource = (
        object_resource("file", attachment_id)
        if attachment_id
        else Resource.named("file", "collection")
    )
    await require_resource_action(
        request,
        auth,
        action="data.manage",
        resource=resource,
    )
    return auth


async def _serve_token_file(file_token: str, service: FileService):
    try:
        file_path, owned = await service.claim_token_file(file_token)
        background = (
            BackgroundTask(service.file_token_service.release_token, file_token)
            if owned
            else None
        )
        return FileResponse(file_path, background=background)
    except FileServiceError as exc:
        raise HTTPException(status_code=404) from exc


def _file_response(file_path: str, mimetype: str | None = None) -> FileResponse:
    if mimetype:
        return FileResponse(file_path, media_type=mimetype)
    return FileResponse(file_path)


async def _run_file(operation, *, error_message: str = "File access error"):
    try:
        result = await run_maybe_async(operation)
        return result
    except ChatServiceError as exc:
        return error(str(exc))
    except FileNotFoundError, OSError:
        return error(error_message)


async def _run_chat_upload(operation):
    result = await _run_file(operation)
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    return ok(result)


async def _upload_file(file: UploadFile, service: ChatService):
    return await _run_chat_upload(
        lambda: service.save_uploaded_file(UploadFileAdapter(file))
    )


@router.get("/files/tokens/{file_token}", responses=_BINARY_FILE_RESPONSE)
async def get_token_file(
    file_token: str,
    service: FileService = Depends(get_service),
):
    return await _serve_token_file(file_token, service)


@router.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _upload_file(file, service)


@router.post("/files/upload/init")
async def init_file_upload(
    payload: ChatUploadInitRequest,
    auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _run_chat_upload(
        lambda: service.upload_init(
            payload.model_dump(exclude_none=True), owner=auth.username
        )
    )


@router.post("/files/upload/chunk")
async def upload_file_chunk(
    upload_id: str = Form(...),
    chunk_index: str = Form(...),
    chunk: UploadFile = File(...),
    auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _run_chat_upload(
        lambda: service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str=chunk_index,
            chunk_file=UploadFileAdapter(chunk),
            owner=auth.username,
        )
    )


@router.post("/files/upload/complete")
async def complete_file_upload(
    payload: ChatUploadSessionRequest,
    auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _run_chat_upload(
        lambda: service.upload_complete(
            payload.model_dump(exclude_none=True), owner=auth.username
        )
    )


@router.post("/files/upload/abort")
async def abort_file_upload(
    payload: ChatUploadSessionRequest,
    auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _run_chat_upload(
        lambda: service.upload_abort(
            payload.model_dump(exclude_none=True), owner=auth.username
        )
    )


@router.post("/files/upload/status")
async def status_file_upload(
    payload: ChatUploadSessionRequest,
    auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    return await _run_chat_upload(
        lambda: service.upload_status(
            payload.model_dump(exclude_none=True), owner=auth.username
        )
    )


@router.get("/files/content", responses=_BINARY_FILE_RESPONSE)
async def get_file_by_name(
    filename: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    result = await _run_file(lambda: service.resolve_webchat_file(filename))
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    file_path, mimetype = result
    return _file_response(file_path, mimetype)


@router.get("/files/{attachment_id}", responses=_BINARY_FILE_RESPONSE)
@router.get("/files/{attachment_id}/content", responses=_BINARY_FILE_RESPONSE)
async def get_file(
    attachment_id: str,
    _auth: AuthContext = Depends(require_file_scope),
    service: ChatService = Depends(get_chat_service),
):
    result = await _run_file(lambda: service.resolve_attachment_file(attachment_id))
    if isinstance(result, dict) and result.get("status") == "error":
        return result
    file_path, mimetype = result
    return _file_response(file_path, mimetype)


@router.delete("/files/{attachment_id}")
async def delete_file(
    attachment_id: str,
    _auth: AuthContext = Depends(require_file_scope),
):
    return ok({"attachment_id": attachment_id})
