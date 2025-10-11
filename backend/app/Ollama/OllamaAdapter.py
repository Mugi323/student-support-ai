"""
ollamaライブラリを使用
モデル名とホストを設定

"""

import ollama
import re

class OllamaAdapter:
    def __init__(self, model_name='qwen3:8b', host='http://localhost:11434'):
        # モデル名とホストを設定
        self.model_name = model_name
        self.client = ollama.Client(host=host)

    def infer(self, prompt):
        """返答を生成する

        Args:
            prompt (str): ユーザーの入力

        Returns:
            str: ボットの返答
        """
        response = self.client.chat(
            model=self.model_name,
            messages=[{'role': 'user', 'content': prompt}]
        )
        # <think>タグを除去
        content = response['message']['content']
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        return content.strip()
    
    def infer_stream(self, prompt):
        """ストリーミングで返答を生成する

        Args:
            prompt (str): ユーザーの入力

        Yields:
            str: ボットの返答（チャンク単位）
        """
        stream = self.client.chat(
            model=self.model_name,
            messages=[{'role': 'user', 'content': prompt}],
            stream=True
        )
        
        in_think_tag = False
        buffer = ""
        
        for chunk in stream:
            if 'message' in chunk and 'content' in chunk['message']:
                content = chunk['message']['content']
                
                for char in content:
                    buffer += char
                    
                    # <think>の開始を検出
                    if buffer.endswith('<think>'):
                        in_think_tag = True
                        buffer = buffer[:-7]  # <think>を削除
                        if buffer:
                            yield buffer
                            buffer = ""
                    # </think>の終了を検出
                    elif buffer.endswith('</think>'):
                        in_think_tag = False
                        buffer = ""
                    # <think>タグ内でない場合のみ出力
                    elif not in_think_tag and len(buffer) > 8:  # バッファリング
                        # タグの途中でない部分を出力
                        safe_length = len(buffer) - 8
                        if safe_length > 0:
                            yield buffer[:safe_length]
                            buffer = buffer[safe_length:]
        
        # 残りのバッファを出力（<think>タグ内でない場合のみ）
        if buffer and not in_think_tag:
            yield buffer