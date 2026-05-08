from __future__ import annotations
import sqlite3
import datetime
from typing import Tuple, Any, List, Dict

DB_PATH = "student_support.db"

# データ保持期間（日数）
DATA_RETENTION_DAYS = 30

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
    # messagesテーブルのインデックス（自動削除用）
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_anonymous_created ON messages(is_anonymous, created_at)"
        )
    except Exception:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT,
        grade TEXT,
        role TEXT NOT NULL DEFAULT 'student',
        created_at TEXT NOT NULL
    )
    """)
    # 1:1ダイレクトメッセージ用テーブル（生徒-教員チャット）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS direct_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0
    )
    """)
    # インデックス
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_dm_pair ON direct_messages(sender_id, recipient_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_dm_recipient ON direct_messages(recipient_id, is_read)"
        )
        # 自動削除用のインデックス
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_dm_created ON direct_messages(created_at)"
        )
    except Exception:
        pass

    # googleアカウント用関連テーブル(email <-> user_id)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS google_accounts (
            email TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
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
    ensure_column("users", "grade", "TEXT")

    # 匿名チャット用カラムを追加
    ensure_column("direct_messages", "is_anonymous", "INTEGER NOT NULL DEFAULT 0")

    # ユーザーごとのチャット要約（最新N件のメモ）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # インデックス（ユーザー単位の取得/削除最適化）
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_memories_user_created ON user_memories(user_id, created_at DESC)"
        )
    except Exception:
        pass

    con.commit()

    # RSSニュースキャッシュ（簡易）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            url TEXT NOT NULL UNIQUE,
            image_url TEXT,
            source TEXT,
            published_at TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_topic_time ON news_cache(topic, published_at DESC, fetched_at DESC)"
        )
    except Exception:
        pass

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
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def cleanup_old_logs(days: int = DATA_RETENTION_DAYS) -> Dict[str, int]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cutoff_date = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    ).isoformat()

    cur.execute(
        "DELETE FROM messages WHERE is_anonymous = 1 AND created_at < ?",
        (cutoff_date,)
    )
    anonymous_deleted = cur.rowcount

    cur.execute(
        "DELETE FROM messages WHERE is_anonymous = 0 AND created_at < ?",
        (cutoff_date,)
    )
    messages_deleted = cur.rowcount

    cur.execute(
        "DELETE FROM direct_messages WHERE created_at < ?",
        (cutoff_date,)
    )
    dm_deleted = cur.rowcount

    con.commit()
    con.close()

    return {
        "messages": messages_deleted,
        "direct_messages": dm_deleted,
        "anonymous_messages": anonymous_deleted
    }


def get_log_statistics() -> Dict[str, Any]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM messages")
    total_messages = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM messages WHERE is_anonymous = 1")
    anonymous_messages = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM direct_messages")
    total_dm = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM direct_messages WHERE is_anonymous = 1")
    anonymous_dm = cur.fetchone()[0]

    cur.execute("SELECT MIN(created_at) FROM messages")
    oldest_message = cur.fetchone()[0]

    cur.execute("SELECT MIN(created_at) FROM direct_messages")
    oldest_dm = cur.fetchone()[0]

    con.close()

    return {
        "total_messages": total_messages,
        "anonymous_messages": anonymous_messages,
        "total_direct_messages": total_dm,
        "anonymous_direct_messages": anonymous_dm,
        "oldest_message_date": oldest_message,
        "oldest_dm_date": oldest_dm,
        "retention_days": DATA_RETENTION_DAYS
    }
