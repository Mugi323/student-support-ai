from __future__ import annotations
import hashlib, datetime


def stable_user_id(name: str | None, is_anonymous: bool) -> str:
    if is_anonymous or not name:
        today = datetime.date.today().isoformat()
        return "anon_" + hashlib.sha256(today.encode()).hexdigest()[:10]
    return "user_" + hashlib.sha256(name.encode()).hexdigest()[:10]
