"""Detection API routes -- ported from Go detectionhandler.go."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from src.domain.detection import Detection, DetectionComment
from src.ports.auth import Unauthorized
from src.services.detection_service import (
    BulkCommunityError,
    CommunityDeleteError,
    DetectionService,
    InvalidRequest,
    MissingPublicId,
    ObjectNotFound,
    PublicIdConflict,
    SyncBlocked,
    SyncError,
)
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


# ------------------------------------------------------------------
# Dependencies (overrideable via app.dependency_overrides)
# ------------------------------------------------------------------


async def get_detection_service() -> DetectionService:
    raise NotImplementedError("DetectionService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    return ctx


# ------------------------------------------------------------------
# Request/Response models
# ------------------------------------------------------------------


class BulkOpRequest(BaseModel):
    ids: list[str] | None = None
    query: str | None = None


class BulkResponse(BaseModel):
    count: int


class ConvertContentResponse(BaseModel):
    query: str


class GenPublicIdResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    public_id: str = Field(alias="publicId", serialization_alias="publicId")


class OverrideNoteRequest(BaseModel):
    note: str


# ------------------------------------------------------------------
# GET /detection/{id}
# ------------------------------------------------------------------


@router.get("/detection/{detection_id}")
async def get_detection(
    detection_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        det = await service.get_detection(detection_id)
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return det.model_dump(by_alias=True)


# ------------------------------------------------------------------
# GET /detection/public/{public_id}
# ------------------------------------------------------------------


@router.get("/detection/public/{public_id}")
async def get_detection_by_public_id(
    public_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        det = await service.get_detection_by_public_id(public_id)
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return det.model_dump(by_alias=True)


# ------------------------------------------------------------------
# POST /detection/
# ------------------------------------------------------------------


@router.post("/detection/")
async def create_detection(
    detection: Detection,
    response: Response,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        det, status = await service.create_detection(
            detection,
            user_id=ctx.requestor_id,
            author_name=ctx.username,
        )
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except MissingPublicId:
        raise HTTPException(status_code=400, detail="missingPublicIdErr") from None
    except PublicIdConflict:
        raise HTTPException(status_code=409, detail="publicIdConflictErr") from None
    except SyncBlocked:
        raise HTTPException(status_code=423) from None
    except SyncError:
        raise HTTPException(status_code=500) from None
    except Exception:
        raise HTTPException(status_code=500) from None

    response.status_code = status
    return det.model_dump(by_alias=True)


# ------------------------------------------------------------------
# PUT /detection/
# ------------------------------------------------------------------


@router.put("/detection/")
async def update_detection(
    detection: Detection,
    response: Response,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        det, status = await service.update_detection(
            detection, user_id=ctx.requestor_id
        )
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except MissingPublicId:
        raise HTTPException(status_code=400, detail="missingPublicIdErr") from None
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except PublicIdConflict:
        raise HTTPException(status_code=409) from None
    except SyncBlocked:
        raise HTTPException(status_code=423) from None
    except SyncError:
        raise HTTPException(status_code=500) from None
    except Exception:
        raise HTTPException(status_code=500) from None

    response.status_code = status
    return det.model_dump(by_alias=True)


# ------------------------------------------------------------------
# PUT /detection/{id}/override/{override_index}/note
# ------------------------------------------------------------------


@router.put("/detection/{detection_id}/override/{override_index}/note")
async def update_override_note(
    detection_id: str,
    override_index: int,
    body: OverrideNoteRequest,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.update_override_note(detection_id, override_index, body.note)
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# DELETE /detection/{id}
# ------------------------------------------------------------------


@router.delete("/detection/{detection_id}")
async def delete_detection(
    detection_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        err_map = await service.delete_detection(detection_id, user_id=ctx.requestor_id)
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except CommunityDeleteError:
        raise HTTPException(status_code=400, detail="ERROR_DELETE_COMMUNITY") from None
    except Unauthorized:
        raise HTTPException(status_code=403, detail="ERROR_PERMISSION_DENIED") from None
    except SyncBlocked:
        raise HTTPException(status_code=423) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return err_map


# ------------------------------------------------------------------
# POST /detection/{id}/duplicate
# ------------------------------------------------------------------


@router.post("/detection/{detection_id}/duplicate")
async def duplicate_detection(
    detection_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        det = await service.duplicate_detection(detection_id)
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return det.model_dump(by_alias=True)


# ------------------------------------------------------------------
# POST /detection/{id}/comment
# ------------------------------------------------------------------


@router.post("/detection/{detection_id}/comment")
async def create_comment(
    detection_id: str,
    comment: DetectionComment,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        c = await service.create_comment(detection_id, comment)
    except Exception:
        raise HTTPException(status_code=500) from None
    return c.model_dump(by_alias=True)


# ------------------------------------------------------------------
# GET /detection/comment/{id}
# ------------------------------------------------------------------


@router.get("/detection/comment/{comment_id}")
async def get_comment(
    comment_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        c = await service.get_comment(comment_id)
    except Exception:
        raise HTTPException(status_code=404) from None
    return c.model_dump(by_alias=True)


# ------------------------------------------------------------------
# PUT /detection/comment/{id}
# ------------------------------------------------------------------


@router.put("/detection/comment/{comment_id}")
async def update_comment(
    comment_id: str,
    comment: DetectionComment,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        c = await service.update_comment(comment_id, comment)
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return c.model_dump(by_alias=True)


# ------------------------------------------------------------------
# DELETE /detection/comment/{id}
# ------------------------------------------------------------------


@router.delete("/detection/comment/{comment_id}")
async def delete_comment(
    comment_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_comment(comment_id)
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# GET /detection/{id}/comment
# ------------------------------------------------------------------


@router.get("/detection/{detection_id}/comment")
async def get_detection_comments(
    detection_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        comments = await service.get_comments(detection_id)
    except ObjectNotFound:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return [c.model_dump(by_alias=True) for c in comments]


# ------------------------------------------------------------------
# GET /detection/{id}/history
# ------------------------------------------------------------------


@router.get("/detection/{detection_id}/history")
async def get_detection_history(
    detection_id: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        history = await service.get_detection_history(detection_id)
    except Exception:
        raise HTTPException(status_code=404) from None
    return history


# ------------------------------------------------------------------
# POST /detection/convert
# ------------------------------------------------------------------


@router.post("/detection/convert")
async def convert_content(
    detection: Detection,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> ConvertContentResponse:
    try:
        query = await service.convert_content(detection)
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return ConvertContentResponse(query=query)


# ------------------------------------------------------------------
# POST /detection/bulk/{new_status}
# ------------------------------------------------------------------


@router.post("/detection/bulk/{new_status}")
async def bulk_update(
    new_status: str,
    body: BulkOpRequest,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> BulkResponse:
    try:
        count = await service.bulk_update(
            new_status, body.ids, body.query, user_id=ctx.requestor_id
        )
    except Unauthorized:
        raise HTTPException(status_code=403, detail="ERROR_PERMISSION_DENIED") from None
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except BulkCommunityError:
        raise HTTPException(status_code=400, detail="ERROR_BULK_COMMUNITY") from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return BulkResponse(count=count)


# ------------------------------------------------------------------
# POST /detection/sync/{engine}/{sync_type}
# ------------------------------------------------------------------


@router.post("/detection/sync/{engine}/{sync_type}")
async def sync_engine(
    engine: str,
    sync_type: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.sync_engine(engine, sync_type, user_id=ctx.requestor_id)
    except Unauthorized:
        raise HTTPException(status_code=403, detail="ERROR_PERMISSION_DENIED") from None
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# GET /detection/{engine}/genpublicid
# ------------------------------------------------------------------


@router.get("/detection/{engine}/genpublicid")
async def gen_public_id(
    engine: str,
    service: DetectionService = Depends(get_detection_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> GenPublicIdResponse:
    try:
        pid = await service.gen_public_id(engine)
    except InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except NotImplementedError:
        raise HTTPException(status_code=501) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return GenPublicIdResponse(publicId=pid)
