from __future__ import annotations
import json
from typing import Dict, Any, Iterable
from .openai_client import client
from app.core.config import OPENAI_MODEL
from app.core.schemas import ai_risk_schema


def compute_overall(scores: Dict[str, float]) -> float:
    return float(max(scores.values())) if scores else 0.0


def _iter_contents(resp: Any):
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
    for c in _iter_contents(resp):
        cj = getattr(c, "json", None)
        if cj is None and isinstance(c, dict):
            cj = c.get("json")
        if isinstance(cj, (dict, list)):
            return cj
    for c in _iter_contents(resp):
        ctype = getattr(c, "type", None) or (isinstance(c, dict) and c.get("type"))
        if ctype in ("json_schema", "output_text", "text"):
            txt = getattr(c, "text", None) or (isinstance(c, dict) and c.get("text"))
            if isinstance(txt, str) and txt.strip().startswith(("{", "[")):
                return json.loads(txt)
    ot = getattr(resp, "output_text", None)
    if isinstance(ot, str) and ot.strip().startswith(("{", "[")):
        return json.loads(ot)
    raise ValueError("No JSON content found in model response")


def analyze_risk_sync(text: str) -> Dict[str, Any]:
    sys2 = (
        "あなたは学校の相談支援AI。日本語で、短く正確に要約し、"
        "健康・家族・友人・学習・いじめ の5カテゴリのリスクを0〜10で数値化します。"
        "会話文のみから判断し、医療的診断は行いません。"
    )
    user2 = f"相談文:\n{text}\n\n出力は付与のJSONスキーマに完全準拠で。"
    schema = ai_risk_schema()
    try:
        analysis = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": sys2},
                {"role": "user", "content": user2},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
        )
        data = None
        for block in getattr(analysis, "output", []) or []:
            for c in getattr(block, "content", []) or []:
                cj = getattr(c, "json", None)
                if isinstance(cj, (dict, list)):
                    data = cj
                    break
            if data is not None:
                break
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
        comp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": sys2},
                {"role": "user", "content": user2},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
        )
        content = comp.choices[0].message.content or ""
        data = json.loads(content)

    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise TypeError("Model returned non-dict JSON")

    summary = (data.get("summary") or "").strip()
    scores_src = data.get("risk_scores") or {}
    scores = {k: float(v) for k, v in scores_src.items() if v is not None}
    reason = data.get("risk_reason", "") or ""
    tags = data.get("tags", []) or []
    overall = compute_overall(scores)
    return {
        "summary": summary,
        "scores": scores,
        "reason": reason,
        "tags": tags,
        "overall": overall,
    }
