import os
import json
import urllib.request

def send_line_message(text):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        print("エラー: トークンまたはユーザーIDが設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            print(f"送信成功 (HTTP {res.status})")
    except Exception as e:
        print(f"送信失敗: {e}")

if __name__ == "__main__":
    message = "🚤【ボートレースbot通知】\n定期実行の稼働テストです。無事にLINEへメッセージが届きました！"
    send_line_message(message)
