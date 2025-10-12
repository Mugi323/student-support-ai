from __future__ import annotations
import hashlib
import datetime
from app.db import execute, query_all, now_iso


def stable_user_id(name: str | None, is_anonymous: bool) -> str:
    if is_anonymous or not name:
        today = datetime.date.today().isoformat()
        return "anon_" + hashlib.sha256(today.encode()).hexdigest()[:10]
    return "user_" + hashlib.sha256(name.encode()).hexdigest()[:10]


def create_user(name: str, role: str = "student") -> str:
    # generate stable id from name
    uid = stable_user_id(name, is_anonymous=False)
    try:
        execute(
            "INSERT OR IGNORE INTO users (user_id, name, role, created_at) VALUES (?,?,?,?)",
            (uid, name, role, now_iso()),
        )
    except Exception:
        pass
    return uid


def get_user_by_name(name: str):
    rows = query_all(
        "SELECT user_id, name, grade, role, created_at FROM users WHERE name=?", (name,)
    )
    if not rows:
        return None
    return rows[0]


def set_password_for_user(user_id: str, password: str):
    # store pbkdf2 hash: iterations$salt$hex
    import os
    import hashlib

    salt = os.urandom(16)
    iterations = 100_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    token = f"{iterations}${salt.hex()}${dk.hex()}"
    try:
        execute("UPDATE users SET password_hash=? WHERE user_id=?", (token, user_id))
    except Exception:
        pass


def verify_user_password(user_id: str, password: str) -> bool:
    rows = query_all("SELECT password_hash FROM users WHERE user_id=?", (user_id,))
    if not rows:
        return False
    ph = rows[0][0]
    if not ph:
        return False
    try:
        iterations, salt_hex, dk_hex = ph.split("$")
        iterations = int(iterations)
        salt = bytes.fromhex(salt_hex)
        import hashlib

        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return check.hex() == dk_hex
    except Exception:
        return False


def get_user_by_id(user_id: str):
    rows = query_all(
        "SELECT user_id, name, grade, role, created_at FROM users WHERE user_id=?",
        (user_id,),
    )
    if not rows:
        return None
    return rows[0]
