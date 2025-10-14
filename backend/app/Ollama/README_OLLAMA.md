# Student Support AI - Ollama版


## セットアップ手順

### 1. Ollamaのインストール

1. [Ollama公式サイト](https://ollama.ai/)からダウンロードしてインストール
2. インストール後、自動的にOllamaサービスが起動



### 2. モデルのダウンロード

ターミナルで以下のコマンドを実行(GUIでも可)：

```bash
# 推奨モデル（日本語対応が良好）
ollama pull qwen3:8b
```

利用可能なモデルを確認：
```bash
ollama list
```

### 3. Python環境のセットアップ

```bash
# backend/app/Ollama ディレクトリに移動
cd backend/app/Ollama

# 必要なパッケージをインストール
pip install -r requirements_ollama.txt
```

### 4. 環境変数の設定

`backend/app/Ollama/.env` ファイルに以下を設定します:

```bash
OLLAMA_MODEL=qwen3:8b
OLLAMA_HOST=http://localhost:11434
PORT=8000
```

**注意:** `.env_ollama.example` はサンプルファイルです。実際の設定は `.env` ファイルに記述してください。

### 5. アプリケーションの起動

```bash
# backendディレクトリから起動（重要！）
cd ../../..  # backend ディレクトリに戻る
uvicorn app.Ollama.main_ollama:app --reload --port 8000
```

ブラウザで http://localhost:8000 にアクセス

## ファイル構成

```
Ollama/
├── OllamaAdapter.py          # Ollama APIラッパー
├── main_ollama.py            # Ollama版メインアプリケーション
├── requirements_ollama.txt   # 必要なPythonパッケージ
├── .env                      # 環境変数設定ファイル（要作成）
├── .env_ollama.example       # 環境変数のサンプル
└── README_OLLAMA.md          # このファイル
```

## 推奨モデルと必要スペック

### qwen2.5:7b (推奨)
- **メモリ**: 8GB以上
- **特徴**: 日本語対応が良好、JSON出力が安定
- **速度**: 中程度

### qwen3:8b
- **メモリ**: 12GB以上
- **特徴**: より高性能、複雑な推論が可能
- **速度**: やや遅い

### llama3:8b
- **メモリ**: 8GB以上
- **特徴**: 英語が得意、汎用性が高い
- **速度**: 速い

## トラブルシューティング

### Ollamaに接続できない

```bash
# Ollamaサービスが起動しているか確認
ollama serve
```

### モデルが見つからない

```bash
# インストール済みモデルを確認
ollama list

# モデルをダウンロード
ollama pull qwen2.5:7b
```

### JSONパースエラーが発生する

1. より高性能なモデル（qwen2.5:7b以上）を使用
2. モデルを再起動: `ollama restart`
3. プロンプトが適切に設定されているか確認

### メモリ不足エラー

1. より小さいモデルを使用（例: qwen2:3b）
2. 他のアプリケーションを終了してメモリを解放
3. Ollamaの設定でコンテキストサイズを調整

### 起動時のパスエラー

起動は必ず `backend` ディレクトリから行ってください：

```bash
# 正しい起動方法
cd backend
uvicorn app.Ollama.main_ollama:app --reload --port 8000

# 間違った起動方法
cd backend/app/Ollama
uvicorn main_ollama:app --reload --port 8000  # エラーになる
```

## OpenAI版との違い

| 項目 | OpenAI版 | Ollama版 |
|------|----------|----------|
| コスト | 従量課金 | 無料 |
| インターネット | 必要 | 不要 |
| 応答品質 | 非常に高い | 高い（モデルに依存） |
| 応答速度 | 高速 | 中〜高速（ハードウェアに依存） |
| プライバシー | クラウド処理 | 完全ローカル |
| セットアップ | 簡単 | やや複雑 |
| メモリ必要量 | 少ない | 8GB以上 |

## 注意事項

1. **初回起動時**: モデルのダウンロードに時間がかかる場合があります
2. **メモリ**: 十分なRAMがないと動作が不安定になります
3. **JSON出力**: モデルによってはJSON形式が不安定な場合があります
4. **データベース**: OpenAI版と同じデータベースを共有します

## サポート

問題が発生した場合は、以下を確認してください：

1. Ollamaが正しくインストールされているか
2. モデルがダウンロードされているか (`ollama list`)
3. 十分なメモリがあるか
4. 正しいディレクトリから起動しているか

それでも解決しない場合は、GitHubのIssueで報告してください。
