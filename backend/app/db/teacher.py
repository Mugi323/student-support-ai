from __future__ import annotations
import sqlite3
import datetime
from typing import List, Dict, Any

DB_PATH = "student_support.db"


def init_teacher_db() -> None:
    """教師管理用テーブルの初期化"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # 教師テーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        teacher_type TEXT NOT NULL CHECK(teacher_type IN ('teacher', 'school_nurse', 'counselor')),
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    """)
    
    # インデックス
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_user_id ON teachers(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_type ON teachers(teacher_type)")
    except Exception:
        pass
    
    con.commit()
    con.close()


def get_all_teachers() -> List[Dict[str, Any]]:
    """登録済み教師の全取得"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    
    cur.execute("""
        SELECT t.id, t.user_id, t.name, t.email, t.teacher_type, t.created_at
        FROM teachers t
        ORDER BY t.teacher_type, t.name
    """)
    
    rows = cur.fetchall()
    con.close()
    
    return [dict(row) for row in rows]


def get_pending_teachers() -> List[Dict[str, Any]]:
    """
    usersテーブルでrole='teacher'だが、teachersテーブルに未登録のユーザーを取得
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    
    cur.execute("""
        SELECT u.user_id, u.name, g.email
        FROM users u
        LEFT JOIN google_accounts g ON u.user_id = g.user_id
        WHERE u.role = 'teacher'
        AND u.user_id NOT IN (SELECT user_id FROM teachers)
        ORDER BY u.name
    """)
    
    rows = cur.fetchall()
    con.close()
    
    return [dict(row) for row in rows]


def add_teachers(teachers_data: List[Dict[str, str]]) -> int:
    """
    教師を一括登録
    teachers_data: [{"user_id": "...", "name": "...", "email": "...", "teacher_type": "..."}, ...]
    """
    if not teachers_data:
        return 0
    
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    now = datetime.datetime.utcnow().isoformat()
    count = 0
    
    for teacher in teachers_data:
        try:
            cur.execute("""
                INSERT INTO teachers (user_id, name, email, teacher_type, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                teacher["user_id"],
                teacher["name"],
                teacher["email"],
                teacher["teacher_type"],
                now
            ))
            count += 1
        except sqlite3.IntegrityError:
            # 既に登録済みの場合はスキップ
            continue
    
    con.commit()
    con.close()
    
    return count


def update_teacher_type(user_id: str, teacher_type: str) -> bool:
    """教師タイプの更新"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    cur.execute("""
        UPDATE teachers
        SET teacher_type = ?
        WHERE user_id = ?
    """, (teacher_type, user_id))
    
    con.commit()
    updated = cur.rowcount > 0
    con.close()
    
    return updated


def delete_teacher(user_id: str) -> bool:
    """教師の削除（teachersテーブルから削除、usersテーブルは残る）"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    cur.execute("DELETE FROM teachers WHERE user_id = ?", (user_id,))
    
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    
    return deleted