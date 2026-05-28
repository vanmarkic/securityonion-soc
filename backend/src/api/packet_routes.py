"""Packet API routes — PCAP packet retrieval."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.services.packet_service import PacketService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_packet_service() -> PacketService:
    """Dependency that provides the PacketService.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("PacketService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


def _parse_packets_params(
    raw_id: str, request: Request, max_count: int,
) -> tuple[int, int, int, bool, str | None]:
    """Parse and validate common packet query parameters.

    Returns (job_id, offset, count, unwrap, error).
    """
    try:
        job_id = int(raw_id)
    except (ValueError, TypeError):
        return 0, 0, 0, False, "Invalid job ID"

    # unwrap
    unwrap_str = request.query_params.get("unwrap", "false")
    unwrap = unwrap_str.lower() == "true"

    # offset
    try:
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        offset = 0
    if offset < 0:
        offset = 0

    # count
    count = max_count
    count_str = request.query_params.get("count", "")
    if count_str:
        try:
            req_count = int(count_str)
            if 0 < req_count < max_count:
                count = req_count
        except ValueError:
            pass

    return job_id, offset, count, unwrap, None


@router.get("/packets/")
async def get_packets_by_query(
    request: Request,
    service: PacketService = Depends(get_packet_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    raw_id = request.query_params.get("jobId", "")
    job_id, offset, count, unwrap, err = _parse_packets_params(
        raw_id, request, service.max_packet_count,
    )
    if err is not None:
        return JSONResponse(content={"detail": err}, status_code=400)

    try:
        packets = await service.get_packets(job_id, offset, count, unwrap)
    except Exception:
        return JSONResponse(content={"detail": "Not found"}, status_code=404)

    return packets


@router.get("/packets/{jobId}")
async def get_packets_by_path(
    jobId: str,
    request: Request,
    service: PacketService = Depends(get_packet_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    job_id, offset, count, unwrap, err = _parse_packets_params(
        jobId, request, service.max_packet_count,
    )
    if err is not None:
        return JSONResponse(content={"detail": err}, status_code=400)

    try:
        packets = await service.get_packets(job_id, offset, count, unwrap)
    except Exception:
        return JSONResponse(content={"detail": "Not found"}, status_code=404)

    return packets
