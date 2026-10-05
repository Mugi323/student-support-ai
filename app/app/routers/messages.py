from __future__ import annotations

import json
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from app.db import execute, query_all
from typing import List, Dict

# 明示エクスポート（安全策）
__all__ = ["router"]

# ここが必須。無いと app.main から import できない
router = APIRouter(prefix="/api")


@router.get("/messages/me")
def api_get_my_messages(request: Request):
    """ログインユーザー自身のメッセージを取得"""
    try:
        uid = request.session.get("user_id")
    except Exception:
        uid = None

    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )

    rows = query_all(
        """
        SELECT id, user_id, text, ai_summary, ai_risk_overall, ai_risk_detail, created_at
        FROM messages
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (uid,),
    )

    out = []
    for mid, user_id_val, text, ai_summary, ai_overall, ai_detail, created_at in rows:
        detail_obj = {}
        try:
            detail_obj = json.loads(ai_detail) if ai_detail else {}
        except Exception:
            detail_obj = {}
        out.append(
            {
                "id": mid,
                "user_id": user_id_val,
                "text": text,
                "ai_summary": ai_summary or "",
                "ai_risk_overall": ai_overall or 0.0,
                "ai_risk_detail": detail_obj,
                "created_at": created_at,
            }
        )

    return JSONResponse(out)


@router.get("/memories/me")
def api_get_my_memories(request: Request):
    """ログインユーザーの最近の会話要約（最大10件）を取得"""
    try:
        uid = request.session.get("user_id")
    except Exception:
        uid = None

    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )

    rows = query_all(
        """
        SELECT summary, created_at
        FROM user_memories
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (uid,),
    )

    data: List[Dict] = [{"summary": r[0], "created_at": r[1]} for r in rows]
    return JSONResponse(data)


@router.get("/messages/{user_id}")
def api_get_user_messages(request: Request, user_id: str):
    """特定ユーザーのメッセージを取得（本人または教師のみアクセス可能）"""
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
        # Allow anonymous ids (generated for non-logged-in users) to be read without session.
        # This keeps previous UX where anonymous users who stored anon id in localStorage
        # can retrieve their own logs. Note: anon ids are not strongly unique.
        if not user_id.startswith("anon_"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )
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
def api_erase_anonymous(request: Request):
    """匿名メッセージを削除"""
    if request.session.get("role") != "teacher":
        raise HTTPException(status_code=401, detail="教師ログインが必要です")
    execute("DELETE FROM messages WHERE is_anonymous=1", ())
    return PlainTextResponse("anonymous messages deleted.")
