from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.config import TEMPLATE_DIR
from app.db import query_all

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATE_DIR)


@router.get("/", include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/chat", include_in_schema=False)
def chat_page(request: Request):
    # Chat page for users - requires login at API level for sending messages
    return templates.TemplateResponse("chat.html", {"request": request})


@router.get("/chat_from_ai", include_in_schema=False)
def chat_from_ai_page(request: Request):
    # Chat page for users - requires login at API level for sending messages
    return templates.TemplateResponse("chat_from_ai.html", {"request": request})


@router.get("/admin", include_in_schema=False)
def admin(request: Request):
    # Admin page - requires login at API level for sending messages
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/messages", include_in_schema=False)
def my_messages_page(request: Request):
    # Page that displays the current user's logs by calling /api/messages/me
    # expose current session user/role into template for debugging/UI
    sess_uid = None
    sess_role = None
    try:
        sess_uid = request.session.get("user_id")
        sess_role = request.session.get("role")
    except Exception:
        sess_uid = None
        sess_role = None

    return templates.TemplateResponse(
        "messages.html",
        {"request": request, "session_user": sess_uid, "session_role": sess_role},
    )


@router.get("/dashboard", include_in_schema=False)
def dashboard(request: Request, q: Optional[str] = None):
    # 教員のみ閲覧可能
    role = request.session.get("role") if hasattr(request, "session") else None
    if role != "teacher":
        return RedirectResponse(url="/", status_code=302)
    rows = query_all("""
        SELECT user_id, AVG(COALESCE(ai_risk_overall, 0)) as avg_ai, MAX(created_at) as last_at, COUNT(*) as cnt
        FROM messages
        GROUP BY user_id
        ORDER BY avg_ai DESC, last_at DESC
        LIMIT 200
    """)
    items = []
    for user_id, avg_ai, last_at, cnt in rows:
        last = query_all(
            "SELECT text, ai_summary, ai_risk_overall, created_at FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        if last:
            text, ai_summary, ai_overall, ts = last[0]
            preview = ai_summary or ((text[:50] + "…") if len(text) > 50 else text)
            # get display name from users table when available
            user_rows = query_all("SELECT name FROM users WHERE user_id=?", (user_id,))
            display_name = user_rows[0][0] if user_rows else user_id
            items.append(
                {
                    "user_id": user_id,
                    "display_name": display_name,
                    "avg_ai_risk": round(avg_ai or 0.0, 2),
                    "cnt": cnt,
                    "last_summary": preview,
                    "last_at": ts,
                    "last_ai_risk": ai_overall or 0.0,
                }
            )
    if q:
        ql = q.lower()
        items = [
            x
            for x in items
            if ql in x["user_id"].lower() or ql in (x["last_summary"] or "").lower()
        ]
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "items": items, "q": q or ""}
    )
