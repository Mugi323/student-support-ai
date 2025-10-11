"""
使用方法:
uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from app.core.config import APP_TITLE, TEMPLATE_DIR
from app.db import init_db
from app.pages.views import router as pages_router
from app.routers.chat import router as chat_router
from app.routers.messages import router as messages_router

app = FastAPI(title=APP_TITLE)
templates = Jinja2Templates(directory=TEMPLATE_DIR)
init_db()

# ルータ登録（既存のパスを維持）
app.include_router(pages_router)
app.include_router(chat_router)
app.include_router(messages_router)
