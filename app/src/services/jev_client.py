from __future__ import annotations
import httpx
from typing import Dict
from src.core.config import TYPESAFE_API_KEY, JEV_MODEL

_JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"

_CRITERIA = ["No risk", "Slightly concerning", "Needs attention", "Urgent action required"]
_MAX_IDX = len(_CRITERIA) - 1  # 3

_QUESTIONS: Dict[str, object] = {
    "health": {
        "type": "score",
        "instructions": "Evaluate physical and health risks.",
        "criteria": _CRITERIA,
    },
    "family": {
        "type": "score",
        "instructions": "Evaluate family relationship risks.",
        "criteria": _CRITERIA,
    },
    "friends": {
        "type": "score",
        "instructions": "Evaluate friendship and social relationship risks.",
        "criteria": _CRITERIA,
    },
    "study": {
        "type": "score",
        "instructions": "Evaluate academic performance and career risks.",
        "criteria": _CRITERIA,
    },
    "bully": {
        "type": "score",
        "instructions": "Evaluate bullying, violence, and harassment risks.",
        "criteria": _CRITERIA,
    },
}

_KEY_MAP = {
    "health": "health",
    "family": "family",
    "friends": "friends",
    "study": "learning",
    "bully": "bullying",
}


def _score_to_ten(score: float) -> float:
    """criteria スケール（0–3）を 0–10 スケールに変換する。"""
    return round(max(0.0, min(float(score), _MAX_IDX)) / _MAX_IDX * 10, 2)


def call_jev(text: str) -> Dict[str, float]:
    """Jev API を呼び出し、5カテゴリのリスクスコア（0–10）を返す。

    Returns:
        {"health": float, "family": float, "friends": float,
         "learning": float, "bullying": float}
    """
    headers = {
        "Authorization": f"Bearer {TYPESAFE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": JEV_MODEL,
        "state": text,
        "questions": _QUESTIONS,
    }
    response = httpx.post(_JEV_ENDPOINT, json=payload, headers=headers, timeout=30.0)
    response.raise_for_status()
    data = response.json()

    answers = data.get("answers") or {}
    scores: Dict[str, float] = {}
    for jev_key, out_key in _KEY_MAP.items():
        entry = answers.get(jev_key) or {}
        raw_score = entry.get("score", 0.0) if isinstance(entry, dict) else 0.0
        scores[out_key] = _score_to_ten(raw_score)
    return scores
