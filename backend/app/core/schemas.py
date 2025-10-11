from __future__ import annotations
from typing import Optional, Dict, Any, Iterable
from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    is_anonymous: bool = True
    name: Optional[str] = None


def ai_risk_schema() -> Dict[str, Any]:
    return {
        "name": "StudentSupportRiskSummary",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "maxLength": 180},
                "risk_scores": {
                    "type": "object",
                    "properties": {
                        "health": {"type": "number", "minimum": 0, "maximum": 10},
                        "family": {"type": "number", "minimum": 0, "maximum": 10},
                        "friends": {"type": "number", "minimum": 0, "maximum": 10},
                        "learning": {"type": "number", "minimum": 0, "maximum": 10},
                        "bullying": {"type": "number", "minimum": 0, "maximum": 10},
                    },
                    "required": ["health", "family", "friends", "learning", "bullying"],
                    "additionalProperties": False,
                },
                "risk_reason": {"type": "string", "maxLength": 240},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            },
            "required": ["summary", "risk_scores", "risk_reason", "tags"],
            "additionalProperties": False,
        },
        "strict": True,
    }
