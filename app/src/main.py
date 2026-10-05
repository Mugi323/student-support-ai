"""
使用方法:
uvicorn src.main:app --reload --port 8000
"""

from __future__ import annotations
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from src.core.config import APP_TITLE, TEMPLATE_DIR, SECRET_KEY
from src.db import init_db
from src.db.teacher import init_teacher_db
from src.pages.views import router as pages_router
from src.routers.chat import router as chat_router
from src.routers.messages import router as messages_router
from src.routers import auth as auth_router
from src.routers.direct_chat import router as direct_chat_router
from src.routers.admin import router as admin_router
from src.routers.chat_from_ai import router as chat_from_ai_router
from src.routers.recommendations_api import router as recommendations_router

from fastapi.staticfiles import StaticFiles


app = FastAPI(title=APP_TITLE)

app.mount("/static", StaticFiles(directory="src/static"), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
init_db()
init_teacher_db()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=3600,
    same_site="lax",
    https_only=False,
)

app.include_router(pages_router)
app.include_router(chat_router)
app.include_router(messages_router)
app.include_router(auth_router.router)
app.include_router(direct_chat_router)
app.include_router(admin_router)
app.include_router(chat_from_ai_router)
app.include_router(recommendations_router)
