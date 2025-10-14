"""
Ollama版 Student Support AI

使用方法:
1. Ollamaをインストール: https://ollama.ai/
2. モデルをダウンロード: ollama pull qwen2.5:7b
3. backend/app/Ollama/.env ファイルを作成して設定
4. 起動: uvicorn app.Ollama.main_ollama:app --reload --port 8000
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Generator
import os, json, re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 相対インポートを使用
from ..db import init_db, execute, query_all, now_iso
from .OllamaAdapter import OllamaAdapter

# == 初期化 ==
# .envファイルを参照（プロジェクトルートまたはOllamaディレクトリ）
load_dotenv(dotenv_path=Path(__file__).parent / ".env")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_adapter = OllamaAdapter(model_name=OLLAMA_MODEL, host=OLLAMA_HOST)

app = FastAPI(title="Student Support (Ollama + Streaming)")
templates = Jinja2Templates(directory="app/templates")
init_db()


class ChatIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    is_anonymous: bool = True
    name: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, q: Optional[str] = None):
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
            items.append(
                {
                    "user_id": user_id,
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


# ====== ヘルパー関数 ======


def stable_user_id(name: Optional[str], is_anonymous: bool) -> str:
    """ユーザーIDを生成"""
    import hashlib, datetime

    if is_anonymous or not name:
        today = datetime.date.today().isoformat()
        return "anon_" + hashlib.sha256(today.encode()).hexdigest()[:10]
    return "user_" + hashlib.sha256(name.encode()).hexdigest()[:10]


def sse_event(payload: Dict) -> bytes:
    """Server-Sent Eventsのフォーマット"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def compute_overall(scores: Dict[str, float]) -> float:
    """総合リスクスコアを計算"""
    return float(max(scores.values())) if scores else 0.0


# ====== ストリーミングエンドポイント ======


@app.post("/api/chat_stream")
def api_chat_stream(payload: ChatIn):
    """
    SSEで2段ストリーム:
      1) {"type":"delta","text":"..."} を逐次送る（AIの短い返答）
      2) 完了後、{"type":"final", "result":{ai_summary, ai_risk_detail, ai_risk_overall, user_id}} を1回送る
    """
    uid = stable_user_id(payload.name, payload.is_anonymous)

    async def generator():
        try:
            # ---- 第1段: 応答テキストをストリーム出力 ----
            prompt1 = (
                "あなたは学校の相談支援AIです。日本語で、相手に寄り添う短い返答を出力してください。"
                "小学生にも伝わるように話してください。\n\n"
                f"相談文:\n{payload.text}\n\n"
                "まずは短く共感してください。その後、具体的な解決策を助言してください。"
            )

            # Ollamaストリーミング応答
            reply_parts = []
            for chunk in ollama_adapter.infer_stream(prompt1):
                reply_parts.append(chunk)
                yield sse_event({"type": "delta", "text": chunk})
            reply_text = "".join(reply_parts)

            # ---- 第2段: 構造化リスク分析（JSON） → DB保存 → 最終イベント ----
            prompt2 = (
                "あなたは学校の相談支援AI。日本語で、短く正確に要約し、"
                "健康・家族・友人・学習・いじめ の5カテゴリのリスクを0〜10で数値化します。"
                "会話文のみから判断し、医療的診断は行いません。\n\n"
                f"相談文:\n{payload.text}\n\n"
                "以下のJSON形式で出力してください（他の説明や```json等のマークダウンは不要です）:\n"
                "{\n"
                '  "summary": "180文字以内の要約",\n'
                '  "risk_scores": {\n'
                '    "health": 0-10の数値,\n'
                '    "family": 0-10の数値,\n'
                '    "friends": 0-10の数値,\n'
                '    "learning": 0-10の数値,\n'
                '    "bullying": 0-10の数値\n'
                '  },\n'
                '  "risk_reason": "240文字以内のリスク判断理由",\n'
                '  "tags": ["タグ1", "タグ2", ...] (最大8個)\n'
                "}"
            )

            analysis_text = ollama_adapter.infer(prompt2)
            
            # JSON部分を抽出（マークダウンのコードブロックなどを除去）
            json_match = re.search(r'\{[\s\S]*\}', analysis_text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(analysis_text)

            # listで返る場合は先頭
            if isinstance(data, list) and data:
                data = data[0]
            if not isinstance(data, dict):
                raise TypeError("Model returned non-dict JSON")

            ai_summary = (data.get("summary") or "").strip()
            ai_scores_src = data.get("risk_scores") or {}
            ai_scores = {k: float(v) for k, v in ai_scores_src.items() if v is not None}
            ai_reason = data.get("risk_reason", "") or ""
            ai_tags = data.get("tags", []) or []
            ai_overall = compute_overall(ai_scores)

            # DB保存
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

            # 最終結果を送信
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
                    "message": f"AI処理に失敗しました: {type(e).__name__}: {str(e)}",
                }
            )

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(generator(), headers=headers)


# ====== ユーザ別ログ取得エンドポイント ======


@app.get("/api/messages/{user_id}")
def api_get_user_messages(user_id: str):
    """
    指定 user_id のメッセージ最新100件を返す。
    フロント側は ai_risk_detail.scores.* を参照するので、JSONを復元して返却。
    """
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


# ====== 匿名メッセージ削除エンドポイント ======


@app.post("/api/messages/erase_anonymous")
def api_erase_anonymous():
    """匿名メッセージを全て削除"""
    execute("DELETE FROM messages WHERE is_anonymous=1", ())
    return PlainTextResponse("anonymous messages deleted.")
