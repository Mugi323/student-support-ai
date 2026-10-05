from __future__ import annotations
from typing import Optional, List

from fastapi import APIRouter, Request

from app.services.recommendations import get_recommendations_async


router = APIRouter(prefix="/api")


@router.get("/recommendations")
async def api_get_recommendations(
    request: Request,
    limit: Optional[int] = 6,
    fresh: Optional[bool] = False,
    shuffle: Optional[bool] = False,
    audience: Optional[str] = None,
    exclude: Optional[str] = None,
):
    try:
        uid = request.session.get("user_id") if hasattr(request, "session") else None
    except Exception:
        uid = None
    # audience は 'kids' のみを有効値として受け付け（その他は None 扱い）
    aud = audience if (audience == "kids") else None
    # exclude はカンマ区切りのURL文字列として受け取り、最大50件までに制限
    ex_list: List[str] = []
    if exclude:
        try:
            ex_list = [x for x in (exclude.split(",") if exclude else []) if x]
            ex_list = ex_list[-50:]
        except Exception:
            ex_list = []
    items = await get_recommendations_async(
        uid,
        limit=limit or 6,
        force_refresh=bool(fresh),
        shuffle=bool(shuffle),
        audience=aud,
        exclude_urls=ex_list,
    )
    return {"items": items}
