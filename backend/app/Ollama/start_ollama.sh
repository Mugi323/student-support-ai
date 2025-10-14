#!/bin/bash
# Ollama版 Student Support AI 起動スクリプト (Linux/Mac)

echo "========================================"
echo "Student Support AI - Ollama版"
echo "========================================"
echo ""

# 現在のディレクトリをチェック
if [ ! -f "app/Ollama/main_ollama.py" ]; then
    echo "エラー: このスクリプトは backend ディレクトリから実行してください"
    echo ""
    echo "正しい実行方法:"
    echo "  cd backend"
    echo "  bash app/Ollama/start_ollama.sh"
    echo ""
    exit 1
fi

# Ollamaが起動しているかチェック
echo "Ollamaの接続を確認中..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo ""
    echo "警告: Ollamaに接続できません"
    echo "Ollamaサービスを起動してください: ollama serve"
    echo ""
    read -p "続行しますか? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# .envファイルの存在チェック
if [ ! -f ".env" ]; then
    echo ""
    echo "警告: .env ファイルが見つかりません"
    echo "backend/.env ファイルを作成してください"
    echo ""
    echo "例: app/Ollama/.env_ollama.example を参考に作成"
    echo ""
    read -p "続行しますか? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "アプリケーションを起動します..."
echo "ブラウザで http://localhost:8000 にアクセスしてください"
echo "終了するには Ctrl+C を押してください"
echo ""
echo "注意: backendディレクトリから起動していることを確認してください"
echo "現在のディレクトリ: $(pwd)"
echo ""

uvicorn app.Ollama.main_ollama:app --reload --port 8000
