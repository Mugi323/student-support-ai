# Ollama版 クイックスタートガイド

## 🚀 最短5ステップで起動！

### 1️⃣ Ollamaをインストール
https://ollama.ai/ からダウンロードしてインストール

### 2️⃣ モデルをダウンロード
```bash
ollama pull qwen2.5:7b
```

### 3️⃣ 依存パッケージをインストール
```bash
cd backend/app/Ollama
pip install -r requirements_ollama.txt
```

### 4️⃣ 設定ファイルをコピー
```bash
# Windows
copy .env_ollama.example .env_ollama

# Linux/Mac
cp .env_ollama.example .env_ollama
```

### 5️⃣ 起動！
```bash
cd ../../..  # backend ディレクトリに戻る

# Windows
app\Ollama\start_ollama.bat

# Linux/Mac
bash app/Ollama/start_ollama.sh

# または直接
uvicorn app.Ollama.main_ollama:app --reload --port 8000
```

ブラウザで **http://localhost:8000** にアクセス！

---

## ⚙️ 動作要件

- **Python**: 3.8以上
- **メモリ**: 8GB以上推奨
- **ストレージ**: モデルサイズ分（4-8GB）

---

## 🔧 よくあるエラーと解決方法

### "Ollamaに接続できません"
```bash
ollama serve
```

### "モジュールが見つかりません"
```bash
pip install -r requirements_ollama.txt
```

### "パスが見つかりません"
**必ず `backend` ディレクトリから起動してください！**

---

## 📚 詳細ドキュメント

詳しい使い方は [README_OLLAMA.md](README_OLLAMA.md) を参照してください。
