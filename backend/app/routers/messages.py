from __future__ import annotations

import json
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from app.db import execute, query_all

# 明示エクスポート（安全策）
__all__ = ["router"]

# ここが必須。無いと app.main から import できない
router = APIRouter(prefix="/api")


@router.get("/messages/{user_id}")
def api_get_user_messages(request: Request, user_id: str):
    # allow access only if the requester is the same user or a teacher
    session_uid = None
    session_role = None
    try:
        session_uid = request.session.get("user_id")
        session_role = request.session.get("role")
    except Exception:
        session_uid = None
        session_role = None

    if session_uid != user_id and session_role != "teacher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    rows = query_all(
        """
        SELECT id, user_id, text, ai_summary, ai_risk_overall, ai_risk_detail, created_at
        FROM messages
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 100
        """,
        (user_id,),
    )
    out = []
    for mid, uid, text, ai_summary, ai_overall, ai_detail, created_at in rows:
        detail_obj = {}
        try:
            detail_obj = json.loads(ai_detail) if ai_detail else {}
        except Exception:
            detail_obj = {}
        out.append(
            {
                "id": mid,
                "user_id": uid,
                "text": text,
                "ai_summary": ai_summary,
                "ai_risk_overall": ai_overall,
                "ai_risk_detail": detail_obj,
                "created_at": created_at,
            }
        )
    return JSONResponse(out)


@router.post("/messages/erase_anonymous")
def api_erase_anonymous():
    execute("DELETE FROM messages WHERE is_anonymous=1", ())
    return PlainTextResponse("anonymous messages deleted.")
