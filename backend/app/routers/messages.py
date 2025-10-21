from __future__ import annotations

import json
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from app.db import execute, query_all

# 明示エクスポート（安全策）
__all__ = ["router"]

# ここが必須。無いと app.main から import できない
router = APIRouter(prefix="/api")

@router.get("/messages/me")
def api_get_my_messages(request: Request):
    # デバッグ用：ファイルに書き込み
    with open("debug.log", "a", encoding="utf-8") as f:
        f.write("\n=== api_get_my_messages called ===\n")
    
    try:
        uid = request.session.get("user_id")
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"uid = {uid}\n")
    except Exception as e:
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(f"ERROR getting uid: {e}\n")
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
    
    with open("debug.log", "a", encoding="utf-8") as f:
        f.write(f"Query returned {len(rows)} rows\n")
    
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
    
    with open("debug.log", "a", encoding="utf-8") as f:
        f.write(f"Built {len(out)} items\n")
        f.write(f"Returning: {out[:1]}\n")  # 最初の1件だけ出力
    
    return JSONResponse(out)

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

@router.get("/messages/debug/check")
def api_debug_check(request: Request):
    """デバッグ用：セッション情報とメッセージ数を確認"""
    try:
        session_uid = request.session.get("user_id")
        session_role = request.session.get("role")
    except Exception:
        session_uid = None
        session_role = None
    
    # 該当ユーザーのメッセージを取得
    if session_uid:
        rows = query_all(
            "SELECT id, text, ai_summary, created_at FROM messages WHERE user_id=? ORDER BY created_at DESC LIMIT 5",
            (session_uid,)
        )
    else:
        rows = []
    
    # 全ユーザーのメッセージ数
    all_counts = query_all("SELECT user_id, COUNT(*) FROM messages GROUP BY user_id", ())
    
    return JSONResponse({
        "session_user_id": session_uid,
        "session_role": session_role,
        "my_message_count": len(rows),
        "my_recent_messages": [{"id": r[0], "text": r[1][:50] if r[1] else "", "summary": r[2], "created_at": r[3]} for r in rows],
        "all_user_message_counts": dict(all_counts)
    })


def api_debug_message_count(request: Request):
    """デバッグ用：ログインユーザーのメッセージ数を確認"""
    try:
        uid = request.session.get("user_id")
    except Exception:
        uid = None
    
    if not uid:
        return JSONResponse({"error": "not logged in", "user_id": None, "count": 0})
    
    rows = query_all("SELECT COUNT(*) FROM messages WHERE user_id=?", (uid,))
    count = rows[0][0] if rows else 0
    
    # 全メッセージの一覧も取得
    all_rows = query_all("SELECT user_id, COUNT(*) FROM messages GROUP BY user_id", ())
    
    return JSONResponse({
        "session_user_id": uid,
        "message_count": count,
        "all_user_counts": dict(all_rows)
    })

@router.post("/messages/erase_anonymous")
def api_erase_anonymous():
    execute("DELETE FROM messages WHERE is_anonymous=1", ())
    return PlainTextResponse("anonymous messages deleted.")
