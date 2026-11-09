import os
import sys
import subprocess
import requests

LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


def send_notification(message: str):
    if LINE_NOTIFY_TOKEN:
        try:
            requests.post("https://notify-api.line.me/api/notify",
                          headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"},
                          data={"message": f"\n{message}"}, timeout=10)
        except Exception:
            pass
    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        try:
            requests.post("https://api.line.me/v2/bot/message/push",
                          headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
                          json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message[:4500]}]}, timeout=10)
        except Exception:
            pass


def main():
    lines = ["📡【公式データファイル 通信テスト結果】"]

    # テスト対象1: 公式結果テキストアーカイブ（mbrace サーバー）
    # 2026年11月9日の結果ファイル: k261109.lzh
    url_mbrace = "http://www1.mbrace.or.jp/od2/K/202611/k261109.lzh"
    try:
        r1 = requests.get(url_mbrace, headers=HEADERS, timeout=10)
        lines.append(f"\n① データ配信サーバー (mbrace):")
        lines.append(f"・HTTPステータス: {r1.status_code}")
        lines.append(f"・取得サイズ: {len(r1.content)} バイト")
        if r1.status_code == 200:
            lines.append("➔ 【成功】ブロックされずに取得可能！")
        else:
            lines.append(f"➔ 【失敗】アクセス制限または存在せず")
    except Exception as e:
        lines.append(f"\n① データ配信サーバー エラー:\n{e}")

    # テスト対象2: BOAT RACE公式ダウンロード窓口
    url_official = "https://www.boatrace.jp/owpc/pc/extra/data/download.html"
    try:
        r2 = requests.get(url_official, headers=HEADERS, timeout=10)
        lines.append(f"\n② 公式ダウンロード窓口:")
        lines.append(f"・HTTPステータス: {r2.status_code}")
    except Exception as e:
        lines.append(f"\n② 公式窓口 エラー:\n{e}")

    report = "\n".join(lines)
    print(report)
    send_notification(report)


if __name__ == "__main__":
    main()
