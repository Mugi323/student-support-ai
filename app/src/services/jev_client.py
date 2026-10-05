from __future__ import annotations
import httpx
from typing import Dict
from src.core.config import TYPESAFE_API_KEY, JEV_MODEL

_JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"

_CRITERIA = ["リスクなし", "気になる程度", "要注意", "緊急対応が必要"]
_MAX_IDX = len(_CRITERIA) - 1  # 3

_QUESTIONS: Dict[str, object] = {
    "health": {
        "type": "score",
        "instructions": "身体・健康リスクを評価してください",
        "criteria": _CRITERIA,
    },
    "family": {
        "type": "score",
        "instructions": "家庭・家族関係のリスクを評価してください",
        "criteria": _CRITERIA,
    },
    "friends": {
        "type": "score",
        "instructions": "友人・人間関係のリスクを評価してください",
        "criteria": _CRITERIA,
    },
    "study": {
        "type": "score",
        "instructions": "学習・進路に関するリスクを評価してください",
        "criteria": _CRITERIA,
    },
    "bully": {
        "type": "score",
        "instructions": "いじめ・暴力・ハラスメントリスクを評価してください",
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
