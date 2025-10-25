from __future__ import annotations
from typing import List, Tuple
from app.db.sqlite import execute, query_all, now_iso


KEEP_DEFAULT = 10


def add_memory(user_id: str, summary: str, keep: int = KEEP_DEFAULT) -> int:
    """ユーザーごとのメモ（1文要約）を追加し、古いものを削除して keep 件に保つ。

    Returns: 新規レコードのID
    """
    if not summary:
        return -1
    last_id = execute(
        "INSERT INTO user_memories (user_id, summary, created_at) VALUES (?,?,?)",
        (user_id, summary, now_iso()),
    )
    # prune: 最新 keep 件を残してそれ以外を削除
    query = (
        "DELETE FROM user_memories WHERE id IN ("
        "  SELECT id FROM user_memories WHERE user_id = ? ORDER BY created_at DESC LIMIT -1 OFFSET ?"
        ")"
    )
    try:
        execute(query, (user_id, keep))
    except Exception:
        # 削除に失敗しても致命的ではないので握りつぶす
        pass
    return last_id


def get_memories(user_id: str, limit: int = KEEP_DEFAULT) -> List[Tuple[str]]:
    """ユーザーの最近の要約メモを新しい順で取得"""
    rows = query_all(
        "SELECT summary FROM user_memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [r[0] for r in rows]
