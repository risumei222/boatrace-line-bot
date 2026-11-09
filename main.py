import os
import re
import sys
import subprocess

# 外部ライブラリ自動インストール
for pkg in ["requests", "beautifulsoup4"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import requests
from bs4 import BeautifulSoup

LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
    date_str = "20261109"
    lines = ["🔍【ボートレース公式 通信診断レポート】"]

    # 1. 一覧ページの診断
    idx_url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    try:
        res_idx = requests.get(idx_url, headers=HEADERS, timeout=10)
        lines.append(f"\n① 一覧ページ ({date_str}):")
        lines.append(f"・HTTPステータス: {res_idx.status_code}")
        lines.append(f"・最終URL: {res_idx.url}")

        soup_idx = BeautifulSoup(res_idx.text, "html.parser")
        title_idx = soup_idx.title.string.strip() if soup_idx.title and soup_idx.title.string else "タイトルなし"
        lines.append(f"・ページ名: {title_idx}")

        stadiums = []
        for a in soup_idx.find_all("a", href=re.compile(r"jcd=\d+")):
            m = re.search(r"jcd=(\d+)", a["href"])
            if m:
                j = int(m.group(1))
                if j not in stadiums and 1 <= j <= 24:
                    stadiums.append(j)
        lines.append(f"・検出開催場数: {len(stadiums)} 場 {stadiums[:5]}")
    except Exception as e:
        lines.append(f"① 一覧接続エラー: {e}")
        stadiums = []

    # 2. 代表レース（桐生1R）のレース結果ページの診断
    test_jcd = stadiums[0] if stadiums else 1
    res_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd={test_jcd:02d}&hd={date_str}"
    try:
        res_res = requests.get(res_url, headers=HEADERS, timeout=10)
        lines.append(f"\n② 結果ページ (場:{test_jcd:02d} / 1R):")
        lines.append(f"・HTTPステータス: {res_res.status_code}")
        
        soup_res = BeautifulSoup(res_res.text, "html.parser")
        title_res = soup_res.title.string.strip() if soup_res.title and soup_res.title.string else "タイトルなし"
        lines.append(f"・ページ名: {title_res}")
        lines.append(f"・文字数: {len(res_res.text)} 字")

        # ページ内に「3連単」やレース結果の文言があるか
        has_trifecta = "3連単" in res_res.text
        lines.append(f"・『3連単』の文字: {'あり' if has_trifecta else 'なし'}")

        # エラー文言の有無
        if "アクセス" in res_res.text or "エラー" in res_res.text or "中止" in res_res.text:
            lines.append("・注意: ページ内に『エラー/中止/アクセス制限』系の単語を検出")
    except Exception as e:
        lines.append(f"② 結果接続エラー: {e}")

    report = "\n".join(lines)
    print(report)
    send_notification(report)


if __name__ == "__main__":
    main()
