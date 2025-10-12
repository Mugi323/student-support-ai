from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.config import TEMPLATE_DIR
from app.utils.user import (
    get_user_by_name,
    create_user,
    set_password_for_user,
    verify_user_password,
    get_user_by_id,
)

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATE_DIR)


@router.get("/login", include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", include_in_schema=False)
def login_action(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    role: str = Form("student"),
):
    # If user doesn't exist -> create and set password
    user = get_user_by_name(name)
    if not user:
        uid = create_user(name=name, role=role)
        # set password
        set_password_for_user(uid, password)
        user = get_user_by_name(name)

    # verify password
    uid = user[0]
    if not verify_user_password(uid, password):
        # invalid credentials -> redirect back to login (simple behavior)
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "認証に失敗しました。"}
        )

    # セッションに user_id / role を保存
    full = get_user_by_id(uid)
    request.session["user_id"] = full[0]
    request.session["role"] = full[3]

    return RedirectResponse(url="/dashboard", status_code=302)


@router.post("/logout", include_in_schema=False)
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
