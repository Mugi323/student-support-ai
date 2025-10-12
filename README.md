# Student Support AI

# 1) クローン
```
git clone git@github.com:Mugi3233/student-support-ai.git
cd student-support-ai/backend
```
# 2) conda 環境作成＆有効化
```
conda env create -f environment.yml -n stu_sup
conda activate stu-sup
pip install -r requirements.txt
```
# 3) .env を作成（コミットしない）
```
cp .env.example .env
# エディタで OPENAI_API_KEY=... を設定
```
# 4) OpneAI APIをテスト
```
cd backend
uvicorn app.main:app --reload --port 8000
```
# 5) Webページにアクセス
```
http://127.0.0.1:8000
```
