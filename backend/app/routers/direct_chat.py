from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from app.db import execute, query_all, now_iso

router = APIRouter(prefix="/api/direct")

# ユーティリティ


def _require_login(request: Request) -> str:
    try:
        uid = request.session.get("user_id")
    except Exception:
        uid = None
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )
    return uid


def _require_role(request: Request) -> str:
    try:
        role = request.session.get("role")
    except Exception:
        role = None
    return role or ""


@router.get("/participants")
def list_participants(request: Request):
    """
    ログインユーザーがやり取り可能な相手一覧を返す。
    - 生徒: すべての教員
    - 教員: すべての生徒 + 匿名チャット中の生徒を「匿名生徒」として表示
    返却: [{user_id, name, role, is_anonymous}]
    """
    uid = _require_login(request)
    role = _require_role(request)
    
    if role == "teacher":
        # 通常の生徒一覧
        rows = query_all(
            "SELECT user_id, name, role FROM users WHERE role='student' ORDER BY created_at DESC"
        )
        out = []
        
        # 各生徒について、匿名・通常の両方のチャットをチェック
        for r in rows:
            student_id = r[0]
            student_name = r[1] or r[0]
            student_role = r[2]
            
            # 通常チャット(is_anonymous=0)のメッセージがあるかチェック
            normal_msg = query_all(
                """
                SELECT COUNT(*) FROM direct_messages 
                WHERE sender_id = ? AND recipient_id = ? AND (is_anonymous = 0 OR is_anonymous IS NULL)
                """,
                (student_id, uid)
            )
            has_normal = normal_msg and normal_msg[0][0] > 0
            
            # 匿名チャット(is_anonymous=1)のメッセージがあるかチェック
            anon_msg = query_all(
                """
                SELECT COUNT(*) FROM direct_messages 
                WHERE sender_id = ? AND recipient_id = ? AND is_anonymous = 1
                """,
                (student_id, uid)
            )
            has_anonymous = anon_msg and anon_msg[0][0] > 0
            
            # 通常チャットがある場合は通常エントリを追加
            if has_normal:
                out.append({
                    "user_id": student_id,
                    "name": student_name,
                    "role": student_role,
                    "is_anonymous": False
                })
            
            # 匿名チャットがある場合は匿名エントリを追加
            if has_anonymous:
                out.append({
                    "user_id": f"{student_id}:anonymous",  # 仮想ID
                    "real_user_id": student_id,  # 実際のユーザーID
                    "name": f"匿名生徒 (ID: {student_id[:8]}...)",
                    "role": student_role,
                    "is_anonymous": True
                })
    else:
        # 生徒の場合: すべての教員（通常エントリのみ）
        rows = query_all(
            """
            SELECT t.user_id, t.name, u.role, t.teacher_type
            FROM teachers t
            INNER JOIN users u ON t.user_id = u.user_id
            ORDER BY t.teacher_type, t.name
            """
        )
        out = [{"user_id": r[0], "name": r[1] or r[0], "role": r[2], "is_anonymous": False, "teacher_type": r[3]} for r in rows]
    
    return JSONResponse(out)


@router.get("/messages/{other_id}")
def get_direct_messages(request: Request, other_id: str, anonymous: str = None):
    """
    相手との過去メッセージを時系列で取得。
    セキュリティ: ログイン本人のみ。
    is_anonymousフラグも含めて返す。
    匿名チャット(?anonymous=true)と通常チャットを分離。
    """
    uid = _require_login(request)
    
    # 匿名モードかどうかを判定（クエリパラメータまたはURL内の:anonymous）
    is_anonymous_mode = anonymous == "true" or ":anonymous" in other_id
    real_other_id = other_id.replace(":anonymous", "")
    
    if is_anonymous_mode:
        # 匿名チャット: is_anonymous=1 のメッセージのみ取得
        rows = query_all(
            """
            SELECT id, sender_id, recipient_id, text, created_at, is_read, is_anonymous
            FROM direct_messages
            WHERE ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?))
              AND is_anonymous = 1
            ORDER BY id ASC
            LIMIT 500
            """,
            (uid, real_other_id, real_other_id, uid),
        )
    else:
        # 通常チャット: is_anonymous=0 または NULL のメッセージのみ取得
        rows = query_all(
            """
            SELECT id, sender_id, recipient_id, text, created_at, is_read, is_anonymous
            FROM direct_messages
            WHERE ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?))
              AND (is_anonymous = 0 OR is_anonymous IS NULL)
            ORDER BY id ASC
            LIMIT 500
            """,
            (uid, real_other_id, real_other_id, uid),
        )
    
    out = [
        {
            "id": r[0],
            "sender_id": r[1],
            "recipient_id": r[2],
            "text": r[3],
            "created_at": r[4],
            "is_read": bool(r[5]),
            "is_anonymous": bool(r[6]) if len(r) > 6 else False,
        }
        for r in rows
    ]
    return JSONResponse(out)


@router.post("/messages/{other_id}")
def send_direct_message(request: Request, other_id: str, body: dict):
    """
    1対1メッセージ送信。
    body: {"text": str, "is_anonymous": bool (optional)}
    - 生徒→教員、教員→生徒 のみ許可（roleチェック）
    - is_anonymous=trueの場合、先生側に送信者名を表示しない
    - other_idに:anonymousが含まれている場合は匿名チャットとして扱う
    """
    uid = _require_login(request)
    role = _require_role(request)

    text = (body or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    
    # 匿名フラグを取得（デフォルトはFalse）
    is_anonymous = (body or {}).get("is_anonymous", False)
    
    # 匿名チャットの場合、other_idから:anonymousを削除
    real_other_id = other_id.replace(":anonymous", "")
    if ":anonymous" in other_id:
        is_anonymous = True  # 匿名チャットなら強制的にTrue

    # 相手の役割を確認
    other_rows = query_all("SELECT role FROM users WHERE user_id=?", (real_other_id,))
    if not other_rows:
        raise HTTPException(status_code=404, detail="recipient not found")
    other_role = other_rows[0][0]

    # 生徒-教員間のみ許可
    # ただし、相手が教員の場合は、teachersテーブルに登録されているかチェック
    if other_role == "teacher":
        teacher_check = query_all(
            "SELECT user_id FROM teachers WHERE user_id=?",
            (real_other_id,)
        )
        if not teacher_check:
            raise HTTPException(
                status_code=403,
                detail="recipient is not a registered teacher"
            )
            
    allowed = {"student", "teacher"}
    if role not in allowed or other_role not in allowed or role == other_role:
        raise HTTPException(status_code=403, detail="forbidden pair")

    # is_anonymousカラムを含めて保存（real_other_idを使用）
    mid = execute(
        "INSERT INTO direct_messages (sender_id, recipient_id, text, is_anonymous, created_at, is_read) VALUES (?,?,?,?,?,0)",
        (uid, real_other_id, text, 1 if is_anonymous else 0, now_iso()),
    )

    return JSONResponse({"id": mid, "ok": True})


@router.post("/messages/{other_id}/read")
def mark_as_read(request: Request, other_id: str):
    """
    相手から自分宛の未読を既読化。
    匿名チャットと通常チャットを分離して既読化。
    """
    uid = _require_login(request)
    
    # 匿名チャットかどうかを判定
    is_anonymous_chat = ":anonymous" in other_id
    real_other_id = other_id.replace(":anonymous", "")
    
    if is_anonymous_chat:
        # 匿名チャット: is_anonymous=1 のメッセージのみ既読化
        execute(
            "UPDATE direct_messages SET is_read=1 WHERE sender_id=? AND recipient_id=? AND is_read=0 AND is_anonymous=1",
            (real_other_id, uid),
        )
    else:
        # 通常チャット: is_anonymous=0 または NULL のメッセージのみ既読化
        execute(
            "UPDATE direct_messages SET is_read=1 WHERE sender_id=? AND recipient_id=? AND is_read=0 AND (is_anonymous=0 OR is_anonymous IS NULL)",
            (real_other_id, uid),
        )
    
    return JSONResponse({"ok": True})


@router.get("/unread_count")
def unread_count(request: Request):
    """
    自分宛て未読件数の合計を返す。
    """
    uid = _require_login(request)
    rows = query_all(
        "SELECT COUNT(*) FROM direct_messages WHERE recipient_id=? AND is_read=0",
        (uid,),
    )
    return JSONResponse({"count": rows[0][0] if rows else 0})


@router.get("/unread_by_sender")
def unread_by_sender(request: Request):
    """
    送信者ごとの未読件数を返す。
    匿名チャットと通常チャットを分離してカウント。
    返却: {sender_id: count, "sender_id:anonymous": count, ...}
    """
    uid = _require_login(request)
    
    # 通常チャット（is_anonymous = 0 または NULL）の未読件数
    normal_rows = query_all(
        """
        SELECT sender_id, COUNT(*) as unread_count
        FROM direct_messages
        WHERE recipient_id=? AND is_read=0 AND (is_anonymous = 0 OR is_anonymous IS NULL)
        GROUP BY sender_id
        """,
        (uid,),
    )
    
    # 匿名チャット（is_anonymous = 1）の未読件数
    anon_rows = query_all(
        """
        SELECT sender_id, COUNT(*) as unread_count
        FROM direct_messages
        WHERE recipient_id=? AND is_read=0 AND is_anonymous = 1
        GROUP BY sender_id
        """,
        (uid,),
    )
    
    result = {}
    
    # 通常チャットの未読件数を追加
    for r in normal_rows:
        result[r[0]] = r[1]
    
    # 匿名チャットの未読件数を追加（:anonymous 付き）
    for r in anon_rows:
        result[f"{r[0]}:anonymous"] = r[1]
    
    return JSONResponse(result)
