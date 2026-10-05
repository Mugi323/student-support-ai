from __future__ import annotations
import json
import base64
import asyncio
import os
import uuid
from typing import List

from fastapi import APIRouter, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse
from src.core.schemas import ChatIn
from src.core.config import OPENAI_MODEL
from src.db import execute, query_all, now_iso
from src.Ollama.OllamaAdapter import OllamaAdapter
from src.services.openai_client import client
from src.db.memory import get_memories, add_memory
from src.services.risk import analyze_risk_sync
from src.utils.sse import sse_event
from src.utils.deps import require_login


router = APIRouter(prefix="/api")


@router.post("/conversations")
async def create_conversation(request: Request):
    uid = require_login(request)
    conv_id = str(uuid.uuid4())
    execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?,?,?,?)",
        (conv_id, uid, "新しいチャット", now_iso()),
    )
    return JSONResponse({"id": conv_id, "title": "新しいチャット"})


@router.get("/conversations")
async def list_conversations(request: Request):
    uid = require_login(request)
    rows = query_all(
        """
        SELECT c.id, c.title, c.created_at FROM conversations c
        WHERE c.user_id=?
          AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND m.user_id=c.user_id)
        ORDER BY c.created_at DESC LIMIT 60
        """,
        (uid,),
    )
    return JSONResponse([{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows])


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request):
    uid = require_login(request)
    execute("DELETE FROM messages WHERE conversation_id=? AND user_id=?", (conv_id, uid))
    execute("DELETE FROM conversations WHERE id=? AND user_id=?", (conv_id, uid))
    return JSONResponse({"ok": True})


@router.patch("/conversations/{conv_id}/title")
async def update_conversation_title(conv_id: str, request: Request):
    uid = require_login(request)
    body = await request.json()
    title = (body.get("title") or "")[:50] or "新しいチャット"
    execute(
        "UPDATE conversations SET title=? WHERE id=? AND user_id=?",
        (title, conv_id, uid),
    )
    return JSONResponse({"ok": True})

_SUMMARY_SYS = (
    "次のユーザー発話とAI返答を、日本語で1文(60〜120文字程度)に要約してください。"
    "継続的な関心や悩み、進捗があれば簡潔に含めてください。改行や箇条書きは禁止です。"
)

_CHAT_SYS_PROMPT = (
    "以下の方針で回答してください。\n"
    "・日本語で300文字以内の返答を出力してください。\n"
    "・会話相手は小学生もしくは中学生です。目線を合わせて話してください。\n"
    "・日常会話の場合は、相手が話しやすいように会話を発展させてください。\n"
    "・相手が悩みを抱えていると判断したときのみ、具体的な解決策を提示してください。\n"
    "・提案を行う際は、その理由も伝えてください。\n\n"
    "【参考メモ】以下はこのユーザーの最近の話題・関心の要約です。会話の文脈として自然に活用してください。\n"
)


async def _save_and_memorize(
    uid: str, user_text: str, reply_text: str, conv_id: str | None = None
) -> dict:
    """リスク分析 → DB保存 → 1文メモ生成を共通化。finalイベント用の辞書を返す。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, analyze_risk_sync, user_text)
    ai_summary = result["summary"]
    ai_scores = result["scores"]
    ai_reason = result["reason"]
    ai_tags = result["tags"]
    ai_overall = result["overall"]

    execute(
        "INSERT INTO messages (user_id, is_anonymous, text, risk_score, sentiment, tags, created_at, ai_summary, ai_reply, ai_risk_detail, ai_risk_overall, conversation_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            uid,
            0,
            user_text,
            0.0,
            0.0,
            '["general"]',
            now_iso(),
            ai_summary,
            reply_text,
            json.dumps(
                {"scores": ai_scores, "reason": ai_reason, "tags": ai_tags},
                ensure_ascii=False,
            ),
            ai_overall,
            conv_id,
        ),
    )

    # 会話タイトルが未設定なら最初のメッセージから自動設定
    if conv_id:
        rows = query_all(
            "SELECT title FROM conversations WHERE id=? AND user_id=?", (conv_id, uid)
        )
        if rows and rows[0][0] == "新しいチャット":
            auto_title = user_text[:30] + ("…" if len(user_text) > 30 else "")
            execute(
                "UPDATE conversations SET title=? WHERE id=? AND user_id=?",
                (auto_title, conv_id, uid),
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


def _build_sys_prompt(uid: str) -> str:
    recent_memos = []
    try:
        recent_memos = get_memories(uid, limit=10) or []
    except Exception:
        pass
    memos_text = "\n".join(f"- {m}" for m in recent_memos)
    return _CHAT_SYS_PROMPT + memos_text


@router.post("/chat_stream")
async def api_chat_stream(request: Request, payload: ChatIn):
    uid = require_login(request)

    async def generator():
        sys = _build_sys_prompt(uid)

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
            final_data = await _save_and_memorize(uid, payload.text, reply_text, payload.conv_id)
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
    uid = require_login(request)

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

        sys = _build_sys_prompt(uid)
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
    uid = require_login(request)
    text = data.text

    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_adapter = OllamaAdapter(model_name=OLLAMA_MODEL, host=OLLAMA_HOST)

    async def generator():
        recent_memos = []
        try:
            recent_memos = get_memories(uid, limit=10) or []
        except Exception:
            pass
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
