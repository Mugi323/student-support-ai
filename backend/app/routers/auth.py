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
    link_google_account,
    get_user_id_by_google_email,
    update_user_name,
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


def _save_session(request: Request, user_row) -> None:
    request.session["user_id"] = user_row[0]
    request.session["role"]    = user_row[3]
    request.session["name"]    = user_row[1]


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
        set_password_for_user(uid, password)
        user = get_user_by_name(name)

    # verify password
    uid = user[0]
    if not verify_user_password(uid, password):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "認証に失敗しました。"}
        )

    # セッションに user_id / role を保存
    full = get_user_by_id(uid)
    # update role if form selected role differs
    if full[3] != role:
        set_user_role(uid, role)
        full = get_user_by_id(uid)

    _save_session(request, full)

    # 🔥 教師の場合、メールアドレスが未登録ならsetup-profileへ
    if role == "teacher":
        from app.utils.user import get_email_by_user_id  # この関数を追加する必要があります
        email = get_email_by_user_id(uid)
        if not email:
            request.session["needs_email"] = True  # メール登録が必要なフラグ
            return RedirectResponse(url="/setup-profile", status_code=302)

    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/login/google", include_in_schema=False)
async def login_google(request: Request):
    redirect_uri = request.url_for('authorize_google')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/authorize/google", include_in_schema=False)
async def authorize_google(request: Request):
    """Googleからのコールバックを処理"""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            return templates.TemplateResponse(
                "login.html", 
                {"request": request, "error": "Google認証に失敗しました。"}
            )
        # メールアドレスからユーザー名を取得(またはメールアドレスをそのまま使用)
        email = user_info.get('email')
        initial_name = user_info.get('name') or (email.split('@')[0] if email and '@' in email else 'user')
        
        uid = get_user_id_by_google_email(email)
        is_new_user = False

        if not uid:
            # ユーザーIDが見つからない場合（新規登録）
            
            # 1. Googleの表示名を検索キーとして既存ユーザーが存在するかをチェック (二重登録防止のための簡易チェック)
            #    ただし、このnameは変更される可能性があるので、メインの認証キーにはしない
            existing_user_by_name = get_user_by_name(initial_name)
            if existing_user_by_name:
                # 既存ユーザーが見つかった場合、そのユーザーIDを使用
                uid = existing_user_by_name[0]
            else:
                # 完全に新規の場合、メールアドレスを使って新しいユーザーを作成
                # user_idは安定したもの (stable_user_id) が生成される
                uid = create_user(name=initial_name, role="student")
                is_new_user = True
            
            # 2. Googleアカウントのメールアドレスをユーザーidにリンク
            link_google_account(uid, email)

            # 3. 新規ユーザーの場合、プロファイル設定へリダイレクト
            if is_new_user:
                # DBには既にinitial_nameが入っている
                # setup-profileページへリダイレクト
                pass # 次のセッション保存後にリダイレクト
        else:
            print(f"既存のGoogle連携ユーザー: {uid}")
        
        # セッションに情報を保存
        full = get_user_by_id(uid)
        _save_session(request, full)
        request.session["google_email"] = email
        request.session["google_picture"] = user_info.get('picture', '')
        
        if is_new_user:
            # 新規ユーザーの場合、パスワード設定ページへリダイレクト
            return RedirectResponse(url="/setup-profile", status_code=302)
        
        return RedirectResponse(url="/dashboard", status_code=302)
        
    except Exception as e:
        print(f"Google認証エラー: {e}")
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Google認証中にエラーが発生しました。"}
        )

@router.get("/api/me")
def get_me(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return {"user_id": uid, "role": request.session.get("role", "student")}


@router.post("/logout", include_in_schema=False)
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)

@router.get("/setup-profile", include_in_schema=False)
def setup_profile_page(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    user = get_user_by_id(user_id)
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    initial_name = user[1] 
    initial_role = user[3]
    
    # 🔥 通常ログインの教師かGoogleログインの新規ユーザーかを判定
    needs_email = request.session.get("needs_email", False)
    is_google_user = "google_email" in request.session

    return templates.TemplateResponse(
        "setup_profile.html", 
        {
            "request": request,
            "initial_name": initial_name,
            "initial_role": initial_role,
            "needs_email": needs_email,  # メール入力が必要か
            "is_google_user": is_google_user,  # Google経由か
        }
    )

@router.post("/setup-profile", include_in_schema=False)
def setup_profile_action(
    request: Request,
    name: str = Form(None),
    role: str = Form(None),
    email: str = Form(None),  # 🔥 メールアドレスを追加
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    # 🔥 Google経由の場合は名前と役割を更新
    if "google_email" in request.session:
        if name:
            update_user_name(user_id, name)
        if role:
            set_user_role(user_id, role)
            request.session["role"] = role
        if name:
            request.session["name"] = name
    
    # 🔥 通常ログインの教師の場合はメールアドレスを登録
    elif email and request.session.get("needs_email"):
        link_google_account(user_id, email)  # 既存の関数を再利用
        request.session.pop("needs_email", None)  # フラグをクリア
    
    return RedirectResponse(url="/dashboard", status_code=302)
