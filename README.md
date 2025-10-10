# ChatGPT Web Service (FastAPI)

## Setup
```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 3000
