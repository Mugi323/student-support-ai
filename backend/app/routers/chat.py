from __future__ import annotations
import json
import base64
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


@router.post("/chat_stream")
def api_chat_stream(request: Request, payload: ChatIn):
    # Prefer logged-in session user when available
    session_uid = None
    try:
        session_uid = request.session.get("user_id")
    except Exception:
        session_uid = None
        pass

    # require login: must have session user_id
    if session_uid:
        uid = session_uid
    else:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )

    async def generator():
        # ---- 第1段: 応答テキストをストリーム出力 ----
        # 直近のユーザーメモ（1文要約）を取得して、コンテキストとして渡す
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
        user = f"{payload.text}"

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

        # ---- 第2段: 構造化リスク分析 → DB保存 → メモ生成・保存 → 最終イベント ----
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
                    0,
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

            # 1文要約（ユーザー発話＋AI返答）を生成してメモ化（最新10件を保持）
            try:
                summary_sys = (
                    "次のユーザー発話とAI返答を、日本語で1文(60〜120文字程度)に要約してください。"
                    "継続的な関心や悩み、進捗があれば簡潔に含めてください。改行や箇条書きは禁止です。"
                )
                summary_resp = client.responses.create(
                    model=OPENAI_MODEL,
                    input=[
                        {"role": "system", "content": summary_sys},
                        {
                            "role": "user",
                            "content": f"ユーザー: {payload.text}\nAI: {reply_text}",
                        },
                    ],
                )
                one_liner = (
                    getattr(summary_resp, "output_text", "").strip() or ai_summary
                )
            except Exception:
                one_liner = ai_summary  # フォールバック

            try:
                add_memory(uid, one_liner, keep=10)
            except Exception:
                pass

            yield sse_event(
                {
                    "type": "final",
                    "result": {
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


@router.post("/chat_stream_with_images")
async def api_chat_stream_with_images(
    request: Request, text: str = Form(...), images: List[UploadFile] = File(default=[])
):
    """画像付きチャットのストリーミングエンドポイント"""

    # セッションからユーザーIDを取得
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
        # 画像をBase64エンコード
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

        # 直近のユーザーメモ（1文要約）を取得して、コンテキストとして渡す
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
        # メッセージコンテンツを構築
        user_content = [
            {
                "type": "text",
                "text": f"{text}",
            }
        ]
        user_content.extend(image_contents)

        try:
            # 画像がある場合はchat.completions APIを使用
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

        # ---- 第2段: リスク分析 → DB保存 → メモ生成・保存 ----
        try:
            # テキストと画像の枚数情報を記録
            full_text = text
            if images:
                full_text += f"\n[画像{len(images)}枚添付]"

            result = analyze_risk_sync(full_text)
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
                    full_text,
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

            # 1文要約（ユーザー発話＋AI返答）を生成してメモ化（最新10件を保持）
            try:
                summary_sys = (
                    "次のユーザー発話とAI返答を、日本語で1文(60〜120文字程度)に要約してください。"
                    "継続的な関心や悩み、進捗があれば簡潔に含めてください。改行や箇条書きは禁止です。"
                )
                summary_resp = client.responses.create(
                    model=OPENAI_MODEL,
                    input=[
                        {"role": "system", "content": summary_sys},
                        {
                            "role": "user",
                            "content": f"ユーザー: {full_text}\nAI: {reply_text}",
                        },
                    ],
                )
                one_liner = (
                    getattr(summary_resp, "output_text", "").strip() or ai_summary
                )
            except Exception:
                one_liner = ai_summary

            try:
                add_memory(uid, one_liner, keep=10)
            except Exception:
                pass

            yield sse_event(
                {
                    "type": "final",
                    "result": {
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


@router.post("/chat_stream_local")
async def chat_stream_local(request: Request, data: ChatIn):
    """Ollamaを使用したローカルチャットストリーミング"""

    # セッションからユーザーIDを取得
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

    # Ollamaの設定を取得
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:8b")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # OllamaAdapterを初期化
    ollama_adapter = OllamaAdapter(model_name=OLLAMA_MODEL, host=OLLAMA_HOST)

    def sse_event(data_dict):
        return f"data: {json.dumps(data_dict, ensure_ascii=False)}\n\n"

    async def generator():
        # プロンプトを作成
        # 直近のユーザーメモ（1文要約）を取得して、コンテキストとして渡す
        recent_memos = []
        try:
            recent_memos = get_memories(uid, limit=10) or []
        except Exception:
            recent_memos = []
        memos_text = "\n".join(f"- {m}" for m in recent_memos)

        prompt = f"""あなたは学校の相談支援AIです。日本語で、相手に寄り添う短い返答を出力してください。小学生にも伝わるように話してください。

相談文:
{text}

まずは短く共感してください。その後、具体的な解決策を助言してください。

【参考メモ】以下はこのユーザーの最近の話題・関心の要約です。会話の文脈として自然に活用してください。
{memos_text}
"""

        try:
            # Ollamaでストリーミング応答を生成
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

        # リスク分析
        try:
            result = analyze_risk_sync(text)
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
                    text,
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

            # 1文要約（ユーザー発話＋AI返答）を生成してメモ化（最新10件を保持）
            try:
                summary_sys = (
                    "次のユーザー発話とAI返答を、日本語で1文(60〜120文字程度)に要約してください。"
                    "継続的な関心や悩み、進捗があれば簡潔に含めてください。改行や箇条書きは禁止です。"
                )
                summary_resp = client.responses.create(
                    model=OPENAI_MODEL,
                    input=[
                        {"role": "system", "content": summary_sys},
                        {
                            "role": "user",
                            "content": f"ユーザー: {text}\nAI: {reply_text}",
                        },
                    ],
                )
                one_liner = (
                    getattr(summary_resp, "output_text", "").strip() or ai_summary
                )
            except Exception:
                one_liner = ai_summary

            try:
                add_memory(uid, one_liner, keep=10)
            except Exception:
                pass

            yield sse_event(
                {
                    "type": "final",
                    "result": {
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

@router.post("/chat_stream_local_with_images")
async def chat_stream_local_with_images(
    request: Request, text: str = Form(...), images: List[UploadFile] = File(default=[])
):
    """Ollama(Qwen3-VL)を使用した画像付きチャットのストリーミングエンドポイント"""

    # セッションからユーザーIDを取得
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

    # Ollamaの設定を取得
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:8b")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # OllamaAdapterを初期化
    ollama_adapter = OllamaAdapter(model_name=OLLAMA_MODEL, host=OLLAMA_HOST)

    async def generator():
        # 画像をBase64エンコード
        image_data_list = []
        for img in images:
            content = await img.read()
            b64 = base64.b64encode(content).decode("utf-8")
            image_data_list.append(b64)

        # 直近のユーザーメモ（1文要約）を取得して、コンテキストとして渡す
        recent_memos = []
        try:
            recent_memos = get_memories(uid, limit=10) or []
        except Exception:
            recent_memos = []
        memos_text = "\n".join(f"- {m}" for m in recent_memos)

        prompt = f"""あなたは学校の相談支援AIです。日本語で、相手に寄り添う短い返答を出力してください。小学生にも伝わるように話してください。

相談文:
{text}

{"[画像が添付されています。画像の内容も考慮して回答してください。]" if images else ""}

まずは短く共感してください。その後、具体的な解決策を助言してください。

【参考メモ】以下はこのユーザーの最近の話題・関心の要約です。会話の文脈として自然に活用してください。
{memos_text}
"""

        try:
            # Ollamaでストリーミング応答を生成（画像付き）
            reply_text = ""
            for chunk in ollama_adapter.infer_stream_with_images(prompt, image_data_list):
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

        # ---- 第2段: リスク分析 → DB保存 → メモ生成・保存 ----
        try:
            # テキストと画像の枚数情報を記録
            full_text = text
            if images:
                full_text += f"\n[画像{len(images)}枚添付]"

            result = analyze_risk_sync(full_text)
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
                    full_text,
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

            # 1文要約（ユーザー発話＋AI返答）を生成してメモ化（最新10件を保持）
            try:
                summary_sys = (
                    "次のユーザー発話とAI返答を、日本語で1文(60〜120文字程度)に要約してください。"
                    "継続的な関心や悩み、進捗があれば簡潔に含めてください。改行や箇条書きは禁止です。"
                )
                summary_resp = client.responses.create(
                    model=OPENAI_MODEL,
                    input=[
                        {"role": "system", "content": summary_sys},
                        {
                            "role": "user",
                            "content": f"ユーザー: {full_text}\nAI: {reply_text}",
                        },
                    ],
                )
                one_liner = (
                    getattr(summary_resp, "output_text", "").strip() or ai_summary
                )
            except Exception:
                one_liner = ai_summary

            try:
                add_memory(uid, one_liner, keep=10)
            except Exception:
                pass

            yield sse_event(
                {
                    "type": "final",
                    "result": {
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