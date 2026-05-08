from __future__ import annotations
import json
import base64
import asyncio
import os
from typing import List

from fastapi import APIRouter, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from app.core.schemas import ChatIn
from app.core.config import OPENAI_MODEL
from app.db import execute, now_iso
from app.Ollama.OllamaAdapter import OllamaAdapter
from app.services.openai_client import client
from app.db.memory import get_memories, add_memory
from app.services.risk import analyze_risk_sync
from app.utils.sse import sse_event


router = APIRouter(prefix="/api")

_SUMMARY_SYS = (
    "次のユーザー発話とAI返答を、日本語で1文(60〜120文字程度)に要約してください。"
    "継続的な関心や悩み、進捗があれば簡潔に含めてください。改行や箇条書きは禁止です。"
)


async def _save_and_memorize(uid: str, user_text: str, reply_text: str) -> dict:
    """リスク分析 → DB保存 → 1文メモ生成を共通化。finalイベント用の辞書を返す。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, analyze_risk_sync, user_text)
    ai_summary = result["summary"]
    ai_scores = result["scores"]
    ai_reason = result["reason"]
    ai_tags = result["tags"]
    ai_overall = result["overall"]

    execute(
        "INSERT INTO messages (user_id, is_anonymous, text, risk_score, sentiment, tags, created_at, ai_summary, ai_risk_detail, ai_risk_overall) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            uid,
            0,
            user_text,
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

    try:
        summary_resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": _SUMMARY_SYS},
                {"role": "user", "content": f"ユーザー: {user_text}\nAI: {reply_text}"},
            ],
        )
        one_liner = getattr(summary_resp, "output_text", "").strip() or ai_summary
    except Exception:
        one_liner = ai_summary

    try:
        add_memory(uid, one_liner, keep=10)
    except Exception:
        pass

    return {
        "user_id": uid,
        "reply": reply_text,
        "memory_summary": one_liner,
        "ai_summary": ai_summary,
        "ai_risk_overall": ai_overall,
        "ai_risk_detail": {
            "scores": ai_scores,
            "reason": ai_reason,
            "tags": ai_tags,
        },
    }


@router.post("/chat_stream")
def api_chat_stream(request: Request, payload: ChatIn):
    session_uid = None
    try:
        session_uid = request.session.get("user_id")
    except Exception:
        session_uid = None

    if session_uid:
        uid = session_uid
    else:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )

    async def generator():
        recent_memos = []
        try:
            recent_memos = get_memories(uid, limit=10) or []
        except Exception:
            recent_memos = []

        memos_text = "\n".join(f"- {m}" for m in recent_memos)

        sys = (
            "以下の方針で回答してください。\n"
            "・日本語で300文字以内の返答を出力してください。\n"
            "・会話相手は小学生もしくは中学生です。目線を合わせて話してください。\n"
            "・日常会話の場合は、相手が話しやすいように会話を発展させてください。\n"
            "・相手が悩みを抱えていると判断したときのみ、具体的な解決策を提示してください。\n"
            "・提案を行う際は、その理由も伝えてください。\n\n"
            "【参考メモ】以下はこのユーザーの最近の話題・関心の要約です。会話の文脈として自然に活用してください。\n"
            f"{memos_text}"
        )

        try:
            with client.responses.stream(
                model=OPENAI_MODEL,
                input=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": payload.text},
                ],
            ) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        yield sse_event({"type": "delta", "text": event.delta})
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

        try:
            final_data = await _save_and_memorize(uid, payload.text, reply_text)
            yield sse_event({"type": "final", "result": final_data})
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


@router.post("/chat_stream_with_images")
async def api_chat_stream_with_images(
    request: Request, text: str = Form(...), images: List[UploadFile] = File(default=[])
):
    """画像付きチャットのストリーミングエンドポイント"""
    session_uid = None
    try:
        session_uid = request.session.get("user_id")
    except Exception:
        pass

    if not session_uid:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )

    uid = session_uid

    async def generator():
        image_contents = []
        for img in images:
            content = await img.read()
            b64 = base64.b64encode(content).decode("utf-8")
            image_contents.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{img.content_type};base64,{b64}"},
                }
            )

        recent_memos = []
        try:
            recent_memos = get_memories(uid, limit=10) or []
        except Exception:
            recent_memos = []
        memos_text = "\n".join(f"- {m}" for m in recent_memos)

        sys = (
            "以下の方針で回答してください。\n"
            "・日本語で300文字以内の返答を出力してください。\n"
            "・会話相手は小学生もしくは中学生です。目線を合わせて話してください。\n"
            "・日常会話の場合は、相手が話しやすいように会話を発展させてください。\n"
            "・相手が悩みを抱えていると判断したときのみ、具体的な解決策を提示してください。\n"
            "・提案を行う際は、その理由も伝えてください。\n\n"
            "【参考メモ】以下はこのユーザーの最近の話題・関心の要約です。会話の文脈として自然に活用してください。\n"
            f"{memos_text}"
        )
        user_content = [{"type": "text", "text": text}]
        user_content.extend(image_contents)

        full_text = text
        if images:
            full_text += f"\n[画像{len(images)}枚添付]"

        try:
            stream = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user_content},
                ],
                stream=True,
            )

            reply_text = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    reply_text += content
                    yield sse_event({"type": "delta", "text": content})

        except Exception as e:
            yield sse_event(
                {
                    "type": "error",
                    "message": f"Streaming failed: {type(e).__name__}: {str(e)}",
                }
            )
            reply_text = ""

        try:
            final_data = await _save_and_memorize(uid, full_text, reply_text)
            yield sse_event({"type": "final", "result": final_data})
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


@router.post("/chat_stream_local")
async def chat_stream_local(request: Request, data: ChatIn):
    """Ollamaを使用したローカルチャットストリーミング"""
    session_uid = None
    try:
        session_uid = request.session.get("user_id")
    except Exception:
        pass

    if not session_uid:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )

    uid = session_uid
    text = data.text

    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_adapter = OllamaAdapter(model_name=OLLAMA_MODEL, host=OLLAMA_HOST)

    async def generator():
        recent_memos = []
        try:
            recent_memos = get_memories(uid, limit=10) or []
        except Exception:
            recent_memos = []
        memos_text = "\n".join(f"- {m}" for m in recent_memos)

        prompt = (
            "あなたは学校の相談支援AIです。日本語で、相手に寄り添う短い返答を出力してください。"
            "小学生にも伝わるように話してください。\n\n"
            f"相談文:\n{text}\n\n"
            "まずは短く共感してください。その後、具体的な解決策を助言してください。\n\n"
            "【参考メモ】以下はこのユーザーの最近の話題・関心の要約です。会話の文脈として自然に活用してください。\n"
            f"{memos_text}"
        )

        try:
            reply_text = ""
            for chunk in ollama_adapter.infer_stream(prompt):
                reply_text += chunk
                yield sse_event({"type": "delta", "text": chunk})
        except Exception as e:
            yield sse_event(
                {
                    "type": "error",
                    "message": f"Ollama Streaming failed: {type(e).__name__}: {str(e)}",
                }
            )
            reply_text = ""

        try:
            final_data = await _save_and_memorize(uid, text, reply_text)
            yield sse_event({"type": "final", "result": final_data})
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
