from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from app.db import execute, query_all, now_iso

router = APIRouter(prefix="/api/direct")

# ユーティリティ


def _require_login(request: Request) -> str:
    try:
        uid = request.session.get("user_id")
    except Exception:
        uid = None
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )
    return uid


def _require_role(request: Request) -> str:
    try:
        role = request.session.get("role")
    except Exception:
        role = None
    return role or ""


@router.get("/participants")
def list_participants(request: Request):
    """
    ログインユーザーがやり取り可能な相手一覧を返す。
    - 生徒: すべての教員
    - 教員: すべての生徒
    返却: [{user_id, name, role}]
    """
    _require_login(request)
    role = _require_role(request)
    if role == "teacher":
        rows = query_all(
            "SELECT user_id, name, role FROM users WHERE role='student' ORDER BY created_at DESC"
        )
    else:
        rows = query_all(
            "SELECT user_id, name, role FROM users WHERE role='teacher' ORDER BY created_at DESC"
        )
    out = [{"user_id": r[0], "name": r[1] or r[0], "role": r[2]} for r in rows]
    return JSONResponse(out)


@router.get("/messages/{other_id}")
def get_direct_messages(request: Request, other_id: str):
    """
    相手との過去メッセージを時系列で取得。
    セキュリティ: ログイン本人のみ。
    """
    uid = _require_login(request)
    # 自/相手のどちらがsenderでも含める
    rows = query_all(
        """
        SELECT id, sender_id, recipient_id, text, created_at, is_read
        FROM direct_messages
        WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)
        ORDER BY id ASC
        LIMIT 500
        """,
        (uid, other_id, other_id, uid),
    )
    out = [
        {
            "id": r[0],
            "sender_id": r[1],
            "recipient_id": r[2],
            "text": r[3],
            "created_at": r[4],
            "is_read": bool(r[5]),
        }
        for r in rows
    ]
    return JSONResponse(out)


@router.post("/messages/{other_id}")
def send_direct_message(request: Request, other_id: str, body: dict):
    """
    1対1メッセージ送信。
    body: {"text": str}
    - 生徒→教員、教員→生徒 のみ許可（roleチェック）
    """
    uid = _require_login(request)
    role = _require_role(request)

    text = (body or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    # 相手の役割を確認
    other_rows = query_all("SELECT role FROM users WHERE user_id=?", (other_id,))
    if not other_rows:
        raise HTTPException(status_code=404, detail="recipient not found")
    other_role = other_rows[0][0]

    # 生徒-教員間のみ許可
    allowed = {"student", "teacher"}
    if role not in allowed or other_role not in allowed or role == other_role:
        raise HTTPException(status_code=403, detail="forbidden pair")

    mid = execute(
        "INSERT INTO direct_messages (sender_id, recipient_id, text, created_at, is_read) VALUES (?,?,?,?,0)",
        (uid, other_id, text, now_iso()),
    )

    return JSONResponse({"id": mid, "ok": True})


@router.post("/messages/{other_id}/read")
def mark_as_read(request: Request, other_id: str):
    """
    相手から自分宛の未読を既読化。
    """
    uid = _require_login(request)
    execute(
        "UPDATE direct_messages SET is_read=1 WHERE sender_id=? AND recipient_id=? AND is_read=0",
        (other_id, uid),
    )
    return JSONResponse({"ok": True})


@router.get("/unread_count")
def unread_count(request: Request):
    """
    自分宛て未読件数の合計を返す。
    """
    uid = _require_login(request)
    rows = query_all(
        "SELECT COUNT(*) FROM direct_messages WHERE recipient_id=? AND is_read=0",
        (uid,),
    )
    return JSONResponse({"count": rows[0][0] if rows else 0})
