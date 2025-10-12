from __future__ import annotations
import sqlite3
import datetime
from typing import Tuple, Any, List

DB_PATH = "student_support.db"


def init_db() -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # 既存テーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        is_anonymous INTEGER NOT NULL DEFAULT 1,
        text TEXT NOT NULL,
        risk_score REAL NOT NULL,
        sentiment REAL NOT NULL,
        tags TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT,
        grade TEXT,
        role TEXT NOT NULL DEFAULT 'student',
        created_at TEXT NOT NULL
    )
    """)
    con.commit()

    # 追加カラム（AI用）
    def ensure_column(table: str, col: str, decl: str):
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    ensure_column("messages", "ai_summary", "TEXT")
    ensure_column("messages", "ai_risk_detail", "TEXT")
    ensure_column("messages", "ai_risk_overall", "REAL")
    # ensure users.role exists for existing DBs
    ensure_column("users", "role", "TEXT NOT NULL DEFAULT 'student'")
    ensure_column("users", "password_hash", "TEXT")

    con.commit()
    con.close()


def execute(query: str, params: Tuple[Any, ...] = ()) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(query, params)
    con.commit()
    last_id = cur.lastrowid
    con.close()
    return last_id


def query_all(query: str, params: Tuple[Any, ...] = ()) -> List[Tuple]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    con.close()
    return rows


def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()
