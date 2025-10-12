from __future__ import annotations
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.core.schemas import ChatIn
from app.core.config import OPENAI_MODEL
from app.db import execute, now_iso
from app.services.openai_client import client
from app.services.risk import analyze_risk_sync
from app.utils.sse import sse_event
from app.utils.user import stable_user_id

router = APIRouter(prefix="/api")


@router.post("/chat_stream")
def api_chat_stream(request: Request, payload: ChatIn):
    # Prefer logged-in session user when available
    session_uid = None
    session_name = None
    try:
        session_uid = request.session.get("user_id")
        session_name = request.session.get("name")
    except Exception:
        session_uid = None
        session_name = None

    if session_uid and not payload.is_anonymous:
        uid = session_uid
        display_name = session_name
    else:
        uid = stable_user_id(payload.name, payload.is_anonymous)
        display_name = payload.name

    async def generator():
        # ---- 第1段: 応答テキストをストリーム出力 ----
        sys = "あなたは学校の相談支援AIです。日本語で、相手に寄り添う短い返答を出力してください。小学生にも伝わるように話してください。"
        user = f"相談文:\n{payload.text}\n\nまずは短く共感してください。その後、具体的な解決策を助言してください。"

        try:
            with client.responses.stream(
                model=OPENAI_MODEL,
                input=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user},
                ],
            ) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        delta = event.delta
                        yield sse_event({"type": "delta", "text": delta})
                    elif event.type == "response.error":
                        yield sse_event({"type": "error", "message": str(event.error)})
                reply_text = stream.get_final_response().output_text or ""
        except Exception as e:
            yield sse_event(
                {
                    "type": "error",
                    "message": f"Streaming failed: {type(e).__name__}: {str(e)}",
                }
            )
            reply_text = ""

        # ---- 第2段: 構造化リスク分析 → DB保存 → 最終イベント ----
        try:
            result = analyze_risk_sync(payload.text)
            ai_summary = result["summary"]
            ai_scores = result["scores"]
            ai_reason = result["reason"]
            ai_tags = result["tags"]
            ai_overall = result["overall"]

            # use session uid if available; text owner should be session user id when logged in
            execute(
                "INSERT INTO messages (user_id, is_anonymous, text, risk_score, sentiment, tags, created_at, ai_summary, ai_risk_detail, ai_risk_overall) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    1 if payload.is_anonymous else 0,
                    payload.text,
                    0.0,
                    0.0,
                    '["general"]',
                    now_iso(),
                    ai_summary,
                    json.dumps(
                        {"scores": ai_scores, "reason": ai_reason, "tags": ai_tags},
                        ensure_ascii=False,
                    ),
                    ai_overall,
                ),
            )

            yield sse_event(
                {
                    "type": "final",
                    "result": {
                        "user_id": uid,
                        "reply": reply_text,
                        "ai_summary": ai_summary,
                        "ai_risk_overall": ai_overall,
                        "ai_risk_detail": {
                            "scores": ai_scores,
                            "reason": ai_reason,
                            "tags": ai_tags,
                        },
                    },
                }
            )
        except Exception as e:
            yield sse_event(
                {
                    "type": "error",
                    "message": f"AI解析に失敗しました: {type(e).__name__}: {str(e)}",
                }
            )

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(generator(), headers=headers)
