from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
APP_TITLE = "Student Support (OpenAI Only + Streaming)"
TEMPLATE_DIR = "app/templates"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
