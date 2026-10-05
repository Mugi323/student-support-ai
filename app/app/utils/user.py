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


def set_user_role(user_id: str, role: str):
    try:
        execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
    except Exception:
        pass

def update_user_name(user_id: str, new_name: str):
    try:
        execute("UPDATE users SET name=? WHERE user_id=?", (new_name, user_id))
        return True
    except Exception as e:
        print(f"ユーザー名更新エラー: {e}")
        return False
    
def update_user_grade(user_id: str, new_grade: str) -> bool:
    """ユーザーIDを指定して学年(grade)を更新します。"""
    try:
        execute("UPDATE users SET grade=? WHERE user_id=?", (new_grade, user_id))
        return True
    except Exception as e:
        print(f"学年更新エラー: {e}")
        return False

# get user id from Google Account (email<->user_id)
def link_google_account(user_id: str, google_email: str) -> None:
    try:
        execute(
            "INSERT OR IGNORE INTO google_accounts (email, user_id) VALUES (?,?)",
            (google_email, user_id),
        )
    except Exception as e:
        print(f"Googleアカウント連携エラー: {e}")
        pass

def get_user_id_by_google_email(google_email: str) -> str | None:
    rows = query_all(
        "SELECT user_id FROM google_accounts WHERE email=?", (google_email,)
    )
    if not rows:
        return None
    return rows[0][0]

def get_email_by_user_id(user_id: str) -> str | None:
    """ユーザーIDに紐づくメールアドレスを取得"""
    rows = query_all(
        "SELECT email FROM google_accounts WHERE user_id = ?", 
        (user_id,)
    )
    return rows[0][0] if rows else None