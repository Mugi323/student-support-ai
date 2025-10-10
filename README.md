# Student Support AI

ChatGPT API を **FastAPI** でラップした最小 Web サービスのテンプレートです。  
ローカルは **conda 環境**で開発し、CI は **GitHub Actions (micromamba)** で同一環境を再現します。  
GUI クライアント **SourceTree** を使った GitHub Flow（ブランチ→PR→レビュー→マージ）で共同開発できます。

---

## 特長
- FastAPI（`/api/chat`）で OpenAI API をサーバ側から呼び出し
- conda / micromamba で依存を固定（`environment.yml`）
- 最小の自動テスト（`pytest`）と CI（`.github/workflows/ci.yml`）
- `.env` による秘密情報のローカル管理（**コミット禁止**）
- SourceTree で回しやすい GitHub Flow

---

## デモ API
- `GET /health` — 稼働チェック  
- `POST /api/chat` — ChatGPT へのプロキシ
  ```json
  {
    "messages": [
      { "role": "user", "content": "こんにちは" }
    ]
  }

# 1) クローン
```
git clone git@github.com:Mugi3233/student-support-ai.git
cd student-support-ai
```
# 2) conda 環境作成＆有効化
```
conda env create -f environment.yml
conda activate student-support-ai
```
# 3) .env を作成（コミットしない）
```
cp .env.example .env
# エディタで OPENAI_API_KEY=... を設定
```

# 4) 起動
```
uvicorn app.main:app --reload --port 3000
```
# 5) 動作確認（別ターミナル）
```
curl -s http://localhost:3000/health
curl -s http://localhost:3000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"こんにちは"}]}'
```
