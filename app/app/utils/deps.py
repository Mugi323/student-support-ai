from __future__ import annotations
from fastapi import HTTPException, Request, status


def require_login(request: Request) -> str:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )
    return uid


def require_teacher(request: Request) -> None:
    if request.session.get("role") != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="教師ログインが必要です"
        )
