from __future__ import annotations
from typing import Optional, Dict
import os, json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

from .db import init_db, execute, query_all, now_iso

# .env 読み込み（backend/.env を起動ディレクトリに置く想定）
load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
openai_client = OpenAI()  # OPENAI_API_KEY を自動参照

app = FastAPI(title="Student Support (OpenAI Only)")
templates = Jinja2Templates(directory="app/templates")

# DB初期化（AI用カラムのマイグレーション含む）
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
    # 平均 ai_risk_overall ベースで並べ替え（ローカル指標は撤廃）
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
            preview = ai_summary or (text[:50] + "…") if len(text) > 50 else text
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


def ai_analyze(text: str) -> Dict:
    """
    OpenAI Responses API で構造化出力:
    {
      "summary": "短い要約",
      "risk_scores": {"self_harm":0-10, "bullying":0-10, "truancy":0-10, "health":0-10},
      "risk_reason": "主要根拠(短文)",
      "tags": ["..."]
    }
    """
    schema = {
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
            "required": ["summary", "risk_scores"],
        },
        "strict": True,
    }

    sys = (
        "あなたは学校の相談支援AI。日本語で、短く正確に要約し、"
        "いじめ/不登校/希死念慮/健康の4カテゴリのリスクを0〜10で数値化します。"
        "会話文のみから判断し、医療的診断は行いません。過剰な断定は避けてください。"
    )
    user = f"相談文:\n{text}\n\n出力は付与のJSONスキーマに完全準拠で。"

    resp = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    return json.loads(resp.output_text)


def compute_overall(risk_scores: Dict[str, float]) -> float:
    vals = list(risk_scores.values()) if risk_scores else []
    return float(max(vals)) if vals else 0.0


@app.post("/api/chat")
def api_chat(payload: ChatIn):
    # 匿名/実名のID生成は従来仕様（ただしローカル分析は不使用）
    # ※ 旧仕様は main.py/risk.py にありました【:contentReference[oaicite:3]{index=3}】【:contentReference[oaicite:4]{index=4}】
    uid = (
        "anon_" if payload.is_anonymous or not payload.name else "user_"
    ) + "hash"  # プレースホルダ
    # 元実装の安定ID生成を踏襲したい場合は risk.py の user_id_from_name_or_anon を移植してください【:contentReference[oaicite:5]{index=5}】

    try:
        ai = ai_analyze(payload.text)
        ai_summary = (ai.get("summary") or "").strip()
        ai_scores = {k: float(v) for k, v in (ai.get("risk_scores") or {}).items()}
        ai_reason = ai.get("risk_reason", "")
        ai_tags = ai.get("tags", []) or []
        ai_overall = compute_overall(ai_scores)

        # 旧ローカル列は NOT NULL のためダミー値で保存（実運用は ai_* を参照）
        execute(
            "INSERT INTO messages (user_id, is_anonymous, text, risk_score, sentiment, tags, created_at, ai_summary, ai_risk_detail, ai_risk_overall) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                1 if payload.is_anonymous else 0,
                payload.text,
                0.0,  # risk_score（ダミー）
                0.0,  # sentiment（ダミー）
                '["general"]',  # tags（ダミー）
                now_iso(),
                ai_summary,
                json.dumps(
                    {"scores": ai_scores, "reason": ai_reason, "tags": ai_tags},
                    ensure_ascii=False,
                ),
                ai_overall,
            ),
        )

        return JSONResponse(
            {
                "user_id": uid,
                "ai_summary": ai_summary,
                "ai_risk_overall": ai_overall,
                "ai_risk_detail": {
                    "scores": ai_scores,
                    "reason": ai_reason,
                    "tags": ai_tags,
                },
                "reply": "話してくれてありがとう。必要なら専門の先生につなげるよ。もう少し詳しく教えてくれる？",
            }
        )
    except Exception as e:
        # 失敗時も最低限ログ保存（AI列はNone）
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
                None,
                None,
                None,
            ),
        )
        return JSONResponse(
            {"user_id": uid, "error": f"AI解析に失敗しました: {type(e).__name__}"},
            status_code=200,
        )


@app.get("/api/messages/{user_id}")
def api_messages(user_id: str):
    rows = query_all(
        """
        SELECT text, created_at, ai_summary, ai_risk_detail, ai_risk_overall
        FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 200
    """,
        (user_id,),
    )
    data = []
    for t, ts, ai_sum, ai_det, ai_ov in rows:
        data.append(
            {
                "text": t,
                "created_at": ts,
                "ai_summary": ai_sum,
                "ai_risk_detail": json.loads(ai_det) if ai_det else None,
                "ai_risk_overall": ai_ov,
            }
        )
    return JSONResponse(data)


@app.post("/api/erase_anonymous")
def api_erase_anonymous():
    execute("DELETE FROM messages WHERE is_anonymous=1", ())
    return PlainTextResponse("anonymous messages deleted.")
