from __future__ import annotations
import json
from typing import Dict


def sse_event(payload: Dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
