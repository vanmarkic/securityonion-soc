"""Stream API routes — ported from Go server/streamhandler.go.

Handles binary upload/download of job output streams (e.g. PCAP files).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from src.services.stream_service import StreamService

router = APIRouter()

_EXTENSION_RE = re.compile(r"^[a-zA-Z0-9]+$")


async def get_stream_service() -> StreamService:
    """Dependency that provides the StreamService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests.
    """
    raise NotImplementedError("StreamService dependency not configured")


@router.get("/stream/")
@router.get("/stream/{job_id}")
async def get_stream(
    request: Request,
    job_id: str | None = None,
    jobId: str = Query(default=""),
    ext: str = Query(default=""),
    unwrap: bool = Query(default=False),
    service: StreamService = Depends(get_stream_service),
) -> Response:
    """Download job output as a binary stream."""
    raw_id = job_id if job_id else jobId
    if not raw_id:
        raise HTTPException(status_code=400, detail="Missing job ID")

    try:
        parsed_id = int(raw_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid job ID") from None

    content, filename, length, mime_type = await service.get_job_stream(parsed_id, unwrap)

    if content is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Handle extension parameter
    if ext:
        if not _EXTENSION_RE.match(ext):
            raise HTTPException(status_code=400, detail="Invalid extension")
        dot_ext = f".{ext}"
        if not filename.endswith(dot_ext):
            if filename.endswith(".bin"):
                filename = filename[: -len(".bin")] + dot_ext
            else:
                filename = filename + dot_ext

    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Length": str(length),
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Transfer-Encoding": "binary",
        },
    )


@router.post("/stream/")
@router.post("/stream/{job_id}")
async def post_stream(
    request: Request,
    job_id: str | None = None,
    jobId: str = Query(default=""),
    service: StreamService = Depends(get_stream_service),
) -> Response:
    """Upload job output as a binary stream."""
    raw_id = job_id if job_id else jobId
    if not raw_id:
        raise HTTPException(status_code=400, detail="Missing job ID")

    try:
        parsed_id = int(raw_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid job ID") from None

    body = await request.body()

    try:
        await service.save_job_stream(parsed_id, body)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from None
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None

    return Response(status_code=200)
