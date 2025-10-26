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

## 任意設定（おすすめ拡張: Web記事/SNS）
- 一般Web記事（Bing Web Search）
	- BING_SEARCH_API_KEY=あなたのキー
	- BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com （既定のままでOK）
- SNS（Mastodon）
	- MASTODON_BASE_URL=https://mastodon.social（使用するインスタンス）
	- MASTODON_ACCESS_TOKEN=発行したトークン

これらを設定すると、トップページ「あなたへのおすすめ」にニュースに加えて「記事」「SNS」も混在表示されます（未設定時は従来どおりニュース/イベント/豆知識のみ）。
# 4) OpneAI APIをテスト
```
cd backend
uvicorn app.main:app --reload --port 8000
```
# 5) Webページにアクセス
```
http://127.0.0.1:8000
