@echo off
REM Ollama版 Student Support AI 起動スクリプト (Windows)

echo ========================================
echo Student Support AI - Ollama版
echo ========================================
echo.

REM 現在のディレクトリをチェック
if not exist "app\Ollama\main_ollama.py" (
    echo エラー: このスクリプトは backend ディレクトリから実行してください
    echo.
    echo 正しい実行方法:
    echo   cd backend
    echo   start_ollama.bat
    echo.
    pause
    exit /b 1
)

REM Ollamaが起動しているかチェック
echo Ollamaの接続を確認中...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo.
    echo 警告: Ollamaに接続できません
    echo Ollamaサービスを起動してください: ollama serve
    echo.
    pause
)

REM .env_ollamaファイルの存在チェック
if not exist "app\Ollama\.env_ollama" (
    echo.
    echo 警告: .env_ollama ファイルが見つかりません
    echo app\Ollama\.env_ollama.example をコピーして .env_ollama を作成してください
    echo.
    echo   copy app\Ollama\.env_ollama.example app\Ollama\.env_ollama
    echo.
    pause
)

echo.
echo アプリケーションを起動します...
echo ブラウザで http://localhost:8000 にアクセスしてください
echo 終了するには Ctrl+C を押してください
echo.
echo 注意: backendディレクトリから起動していることを確認してください
echo 現在のディレクトリ: %CD%
echo.

uvicorn app.Ollama.main_ollama:app --reload --port 8000
