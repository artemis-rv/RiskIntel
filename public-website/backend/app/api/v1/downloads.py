"""
app/api/v1/downloads.py
────────────────────────
Download tracking API routes.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_verified
from app.db.session import get_db
from app.middleware.rate_limit import _get_client_ip
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.download import CreateDownloadRequest, DownloadResponse
from app.services.download_service import DownloadService

router = APIRouter(prefix="/downloads", tags=["Downloads"])


def _get_ip(request: Request) -> Optional[str]:
    """
    The address recorded against a download.

    This deliberately reuses the rate limiter's derivation rather than reading
    X-Forwarded-For directly. Taking the leftmost entry of that header, as this
    function used to, records whatever the client put there: anyone can send
    `X-Forwarded-For: 10.0.0.1` and have it written into the audit trail as the
    address that downloaded the agent. For a record whose purpose is to answer
    "who was given this build", an attacker-chosen value is worse than none.

    The shared helper honours the header only when the immediate peer is a
    configured trusted proxy, and then takes the rightmost address that is not
    one of ours.
    """
    return _get_client_ip(request)


@router.post(
    "",
    response_model=DownloadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a software download",
    description="Requires authenticated, email-verified user. Max 5 downloads per release per hour.",
)
async def create_download(
    request: Request,
    body: CreateDownloadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> DownloadResponse:
    service = DownloadService(db)
    return await service.create_download(
        body,
        user_id=current_user.user_id,
        ip_address=_get_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:512],
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/me",
    response_model=PaginatedResponse[DownloadResponse],
    status_code=status.HTTP_200_OK,
    summary="List my download history",
)
async def list_my_downloads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> PaginatedResponse[DownloadResponse]:
    service = DownloadService(db)
    return await service.list_my_downloads(
        current_user.user_id, page=page, page_size=page_size
    )


@router.get(
    "/{release_id}/file",
    status_code=status.HTTP_200_OK,
    response_class=FileResponse,
    summary="Download the release artefact",
    description=(
        "Authenticates and authorises the caller, confirms the release is "
        "published and the artefact is present, records the download, then "
        "streams the file. Requires a verified email address."
    ),
    responses={
        200: {"content": {"application/octet-stream": {}}},
        403: {"description": "Email not verified, or account inactive"},
        404: {"description": "Release not published, or artefact unavailable"},
        429: {"description": "Hourly download limit reached for this release"},
    },
)
async def download_release_file(
    request: Request,
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> FileResponse:
    """
    Deliver a release artefact.

    The client never learns where the file lives. `release_id` is the only thing
    it names, the storage layer maps that to a path inside a single trusted
    root, and the response carries a filename derived from the release version
    rather than from anything stored in the database.
    """
    service = DownloadService(db)
    resolved, filename, media_type = await service.prepare_delivery(
        release_id,
        user_id=current_user.user_id,
        ip_address=_get_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:512],
        request_id=getattr(request.state, "request_id", None),
    )

    return FileResponse(
        path=resolved,
        media_type=media_type,
        filename=filename,
        headers={
            # `filename=` above sets Content-Disposition; this makes the intent
            # explicit and stops any proxy sniffing the body into something
            # renderable.
            #
            # Cache-Control is deliberately NOT set here: SecurityHeadersMiddleware
            # already applies "no-store, no-cache, must-revalidate" to every
            # response, which is stricter than anything worth adding. Setting it
            # again here would look authoritative while being silently overridden.
            "X-Content-Type-Options": "nosniff",
        },
    )
