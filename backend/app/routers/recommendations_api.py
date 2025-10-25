from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Request

from app.services.recommendations import get_recommendations_async


router = APIRouter(prefix="/api")


@router.get("/recommendations")
async def api_get_recommendations(
    request: Request,
    limit: Optional[int] = 6,
    fresh: Optional[bool] = False,
    shuffle: Optional[bool] = False,
):
    try:
        uid = request.session.get("user_id") if hasattr(request, "session") else None
    except Exception:
        uid = None
    items = await get_recommendations_async(
        uid,
        limit=limit or 6,
        force_refresh=bool(fresh),
        shuffle=bool(shuffle),
    )
    return {"items": items}
