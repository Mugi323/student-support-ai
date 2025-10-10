import os
from openai import OpenAI
from dotenv import load_dotenv


# 事前に環境変数 OPENAI_API_KEY を設定してください
# Linux/Mac: export OPENAI_API_KEY=sk-xxxx
# Windows(PowerShell): $env:OPENAI_API_KEY="sk-xxxx"

def main():
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # 例：高速・安価な汎用モデル
        messages=[
            {"role": "system", "content": "あなたは新設な日本語カウンセラーです。"},
            {"role": "user", "content": "加藤先生が、生徒が少ないことで拗ねてしまいました。どうしたらいいでしょうか？"}
        ],
        temperature=0.3,
        max_tokens=200,
    )
    print(resp.choices[0].message.content)

if __name__ == "__main__":
    load_dotenv()                 # .env をロード（無ければ無視）
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("環境変数 OPENAI_API_KEY が未設定です。")
    main()
