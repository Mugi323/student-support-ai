from __future__ import annotations
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from app.core.config import TEMPLATE_DIR
from app.utils.user import (
    get_user_by_name,
    create_user,
    set_password_for_user,
    verify_user_password,
    get_user_by_id,
    set_user_role,
)

config = Config()

oauth = OAuth(config)
oauth.register(
    name='google',
    # configオブジェクトから環境変数名(GOOGLE_CLIENT_ID)を使って値を取得します
    client_id=config('GOOGLE_CLIENT_ID'), 
    client_secret=config('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    },
    # 🚨 CSRF/セッション問題を回避するため、ローカル開発環境(http)向けにスキームを明示
    redirect_uri_params={'_external': True, '_scheme': 'http'}
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
    # update role if form selected role differs
    if full[3] != role:
        set_user_role(uid, role)
        full = get_user_by_id(uid)

    request.session["user_id"] = full[0]
    request.session["role"] = full[3]
    # store display name in session for header
    request.session["name"] = full[1]

    return RedirectResponse(url="/dashboard", status_code=302)

@router.get("/login/google", include_in_schema=False)
async def login_google(request: Request):
    redirect_uri = request.url_for('authorize_google')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/authorize/google", include_in_schema=False)
async def authorize_google(request: Request):
    """Googleからのコールバックを処理"""
    print("Google認証コールバック受信")
    try:
        print("Google認証コールバック処理開始")
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        print(f"Googleユーザー情報: {user_info}")
        if not user_info:
            return templates.TemplateResponse(
                "login.html", 
                {"request": request, "error": "Google認証に失敗しました。"}
            )
        print("Google認証成功")
        print("ユーザー情報取得中...")
        # メールアドレスからユーザー名を取得(またはメールアドレスをそのまま使用)
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        
        # ユーザーが存在しない場合は作成
        user = get_user_by_name(name)
        if not user:
            # Google認証ユーザーはデフォルトで学生として登録 
            #あとで選択可能にする機能を実装する
            uid = create_user(name=name, role="student")
        else:
            uid = user[0]
        
        # セッションに情報を保存
        full = get_user_by_id(uid)
        request.session["user_id"] = full[0]
        request.session["role"] = full[3]
        request.session["name"] = full[1]
        request.session["google_email"] = email
        request.session["google_picture"] = user_info.get('picture', '')
        
        return RedirectResponse(url="/dashboard", status_code=302)
        
    except Exception as e:
        print(f"Google認証エラー: {e}")
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Google認証中にエラーが発生しました。"}
        )

@router.post("/logout", include_in_schema=False)
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
