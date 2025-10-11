from __future__ import annotations
from typing import Optional, Dict, Any, Iterable
import os, json, asyncio

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
from openai import OpenAI

from .db import init_db, execute, query_all, now_iso

# == 既存初期化 ==
load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
openai_client = OpenAI()

app = FastAPI(title="Student Support (OpenAI Only + Streaming)")
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


# ====== ここから ストリーミング実装 ======


def stable_user_id(name: Optional[str], is_anonymous: bool) -> str:
    # 安定IDの簡易版（必要なら risk.py の実装に差し替え可）
    import hashlib, datetime

    if is_anonymous or not name:
        today = datetime.date.today().isoformat()
        return "anon_" + hashlib.sha256(today.encode()).hexdigest()[:10]
    return "user_" + hashlib.sha256(name.encode()).hexdigest()[:10]


def sse_event(payload: Dict) -> bytes:
    # SSE: data: <json>\n\n
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def ai_risk_schema():
    return {
        "name": "StudentSupportRiskSummary",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "maxLength": 180},
                "risk_scores": {
                    "type": "object",
                    "properties": {
                        "self_harm": {"type": "number", "minimum": 0, "maximum": 10},
                        "bullying": {"type": "number", "minimum": 0, "maximum": 10},
                        "truancy": {"type": "number", "minimum": 0, "maximum": 10},
                        "health": {"type": "number", "minimum": 0, "maximum": 10},
                    },
                    "required": ["self_harm", "bullying", "truancy", "health"],
                    "additionalProperties": False,
                },
                "risk_reason": {"type": "string", "maxLength": 240},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            },
            # ← 'tags' を追加
            "required": ["summary", "risk_scores", "risk_reason", "tags"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def compute_overall(scores: Dict[str, float]) -> float:
    return float(max(scores.values())) if scores else 0.0


# ==== 追加: Responses APIの出力から堅牢にJSONを取り出すヘルパ ====


def _iter_contents(resp: Any) -> Iterable[Any]:
    """response.output[*].content[*] をイテレート（SDKの型/辞書両対応）"""
    out = getattr(resp, "output", None)
    if not out and isinstance(resp, dict):
        out = resp.get("output")
    if not out:
        return []
    for block in out:
        content = getattr(block, "content", None)
        if content is None and isinstance(block, dict):
            content = block.get("content")
        if not content:
            continue
        for c in content:
            yield c


def extract_json_from_response(resp: Any) -> Dict[str, Any]:
    """
    優先度:
      1) content[*].json（dict/list）
      2) content[*].text（JSON文字列なら loads）
      3) response.output_text（JSON文字列なら loads）
    いずれも見つからなければ ValueError
    """
    # 1) 直接jsonフィールド
    for c in _iter_contents(resp):
        cj = getattr(c, "json", None)
        if cj is None and isinstance(c, dict):
            cj = c.get("json")
        if isinstance(cj, (dict, list)):
            return cj  # 既に構造化

    # 2) textフィールドをJSONとして読む
    for c in _iter_contents(resp):
        ctype = getattr(c, "type", None) or (isinstance(c, dict) and c.get("type"))
        if ctype in ("json_schema", "output_text", "text"):
            txt = getattr(c, "text", None) or (isinstance(c, dict) and c.get("text"))
            if isinstance(txt, str) and txt.strip().startswith(("{", "[")):
                return json.loads(txt)

    # 3) output_text
    ot = getattr(resp, "output_text", None)
    if isinstance(ot, str) and ot.strip().startswith(("{", "[")):
        return json.loads(ot)

    raise ValueError("No JSON content found in model response")


@app.post("/api/chat_stream")
def api_chat_stream(payload: ChatIn):
    """
    SSEで2段ストリーム:
      1) {"type":"delta","text":"..."} を逐次送る（AIの短い返答）
      2) 完了後、{"type":"final", "result":{ai_summary, ai_risk_detail, ai_risk_overall, user_id}} を1回送る
    """
    uid = stable_user_id(payload.name, payload.is_anonymous)

    async def generator():
        # ---- 第1段: 応答テキストをストリーム出力 ----
        sys = "あなたは学校の相談支援AIです。日本語で、相手に寄り添う短い返答を出力してください。助言は穏やかに、過度な断定を避けてください。"
        user = f"相談文:\n{payload.text}\n\nまずは短く共感してください。その後、現実的な解決策や今からすべきことを助言してください。"

        # OpenAI Responses API の同期ストリーム
        with openai_client.responses.stream(
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

        # ---- 第2段: 構造化リスク分析（JSON） → DB保存 → 最終イベント ----
        schema = ai_risk_schema()
        sys2 = (
            "あなたは学校の相談支援AI。日本語で、短く正確に要約し、"
            "いじめ/不登校/希死念慮/健康の4カテゴリのリスクを0〜10で数値化します。"
            "会話文のみから判断し、医療的診断は行いません。"
        )
        user2 = f"相談文:\n{payload.text}\n\n出力は付与のJSONスキーマに完全準拠で。"

        try:
            # 1) 新SDK系（対応環境ならこれで成功）
            try:
                analysis = openai_client.responses.create(
                    model=OPENAI_MODEL,
                    input=[
                        {"role": "system", "content": sys2},
                        {"role": "user", "content": user2},
                    ],
                    response_format={"type": "json_schema", "json_schema": schema},
                )
                # ---- JSON抽出（構造化/テキスト両対応）----
                data = None
                # content[*].json 優先
                for block in getattr(analysis, "output", []) or []:
                    for c in getattr(block, "content", []) or []:
                        cj = getattr(c, "json", None)
                        if isinstance(cj, (dict, list)):
                            data = cj
                            break
                    if data is not None:
                        break
                # なければ text か output_text を読む
                if data is None:
                    text_json = getattr(analysis, "output_text", None) or ""
                    if not text_json:
                        for block in getattr(analysis, "output", []) or []:
                            for c in getattr(block, "content", []) or []:
                                if getattr(c, "type", None) in (
                                    "json_schema",
                                    "output_text",
                                    "text",
                                ):
                                    tt = getattr(c, "text", None)
                                    if isinstance(tt, str):
                                        text_json += tt
                    data = json.loads(text_json)

            except TypeError:
                # 2) 旧SDK互換: Chat Completions にフォールバック
                comp = openai_client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": sys2},
                        {"role": "user", "content": user2},
                    ],
                    response_format={"type": "json_schema", "json_schema": schema},
                )
                content = comp.choices[0].message.content or ""
                data = json.loads(content)

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
            # 型名だけでなく本文も返す
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


# ====== 非ストリーミング版 (/api/chat) はそのまま使えます ======


@app.post("/api/messages/erase_anonymous")
def api_erase_anonymous():
    execute("DELETE FROM messages WHERE is_anonymous=1", ())
    return PlainTextResponse("anonymous messages deleted.")
