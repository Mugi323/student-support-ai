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
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/chat", include_in_schema=False)
def chat_page(request: Request):
    # Chat page for users - requires login at API level for sending messages
    return templates.TemplateResponse("chat.html", {"request": request})


@router.get("/chat_teacher", include_in_schema=False)
def chat_teacher_page(request: Request):
    # ログインしていない場合はログインページへ
    uid = request.session.get("user_id") if hasattr(request, "session") else None
    if not uid:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("chat_teacher.html", {"request": request})


@router.get("/chat_from_ai", include_in_schema=False)
def chat_from_ai_page(request: Request):
    # Chat page for users - requires login at API level for sending messages
    return templates.TemplateResponse("chat_from_ai.html", {"request": request})


@router.get("/admin", include_in_schema=False)
def admin_page(request: Request):
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
    
    # 要対応ランキング
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
    
    # 高リスク生徒一覧（いずれかの項目が8以上）
    high_risk_students = []
    all_messages = query_all("""
        SELECT user_id, ai_risk_detail, ai_summary, created_at, ai_risk_overall
        FROM messages
        WHERE ai_risk_detail IS NOT NULL
        ORDER BY created_at DESC
    """)
    
    # ユーザーごとの最新の高リスクメッセージを収集
    user_high_risk = {}
    for user_id, detail_json, summary, created_at, overall in all_messages:
        if user_id in user_high_risk:
            continue  # 既に最新メッセージを取得済み
        
        try:
            import json
            detail = json.loads(detail_json) if detail_json else {}
            scores = detail.get("scores", {})
            
            # いずれかの項目が8以上かチェック
            health = scores.get("health", 0)
            family = scores.get("family", 0)
            friends = scores.get("friends", 0)
            learning = scores.get("learning", 0)
            bullying = scores.get("bullying", 0)
            
            if health >= 8 or family >= 8 or friends >= 8 or learning >= 8 or bullying >= 8:
                # 高リスク項目を収集
                high_items = []
                if health >= 8:
                    high_items.append(f"健康: {health}")
                if family >= 8:
                    high_items.append(f"家族: {family}")
                if friends >= 8:
                    high_items.append(f"友人: {friends}")
                if learning >= 8:
                    high_items.append(f"学習: {learning}")
                if bullying >= 8:
                    high_items.append(f"いじめ: {bullying}")
                
                # 表示名を取得
                user_rows = query_all("SELECT name FROM users WHERE user_id=?", (user_id,))
                display_name = user_rows[0][0] if user_rows else user_id
                
                user_high_risk[user_id] = {
                    "user_id": user_id,
                    "display_name": display_name,
                    "high_items": ", ".join(high_items),
                    "summary": summary or "—",
                    "created_at": created_at,
                    "overall": overall or 0,
                }
        except:
            pass
    
    high_risk_students = list(user_high_risk.values())
    
    return templates.TemplateResponse(
        "dashboard.html", {
            "request": request, 
            "items": items, 
            "high_risk_students": high_risk_students,
            "q": q or ""
        }
    )
