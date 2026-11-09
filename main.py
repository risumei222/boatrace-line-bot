import os
import re
import sys
import subprocess
import requests
from bs4 import BeautifulSoup

# 外部ライブラリ自動インストール
for pkg in ["requests", "beautifulsoup4"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

JCD_NAME_MAP = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
    6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
    11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
    16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
    21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
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
                          json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}, timeout=10)
        except Exception:
            pass
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
        except Exception:
            pass


def main():
    date_str = "20261109"
    url = f"https://www.boatrace.jp/owpc/pc/race/pay?hd={date_str}"
    print(f"=== 払戻金一覧から全件取得中: {url} ===")

    res = requests.get(url, headers=HEADERS, timeout=15)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")

    target_combos = {"1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3"}
    results = []

    tables = soup.find_all("table")
    for tbl in tables:
        link = tbl.find("a", href=re.compile(r"jcd=(\d+)"))
        if not link:
            continue
        jcd = int(re.search(r"jcd=(\d+)", link["href"]).group(1))
        stadium_name = JCD_NAME_MAP.get(jcd, f"{jcd}場")

        rows = tbl.find_all("tr")
        for tr in rows:
            text = tr.get_text(" ", strip=True)
            if "3連単" in text:
                rno_match = re.search(r"(\d+)R", text)
                rno = int(rno_match.group(1)) if rno_match else 0
                
                digits = re.findall(r"\b([1-6])\b", text)
                pay_match = re.search(r"[¥￥]?([0-9,]+)\s*円?", text)
                payout = pay_match.group(1) if pay_match else "-"

                if len(digits) >= 3:
                    trifecta = f"{digits[0]}-{digits[1]}-{digits[2]}"
                    if trifecta in target_combos:
                        results.append({
                            "stadium": stadium_name,
                            "rno": rno,
                            "trifecta": trifecta,
                            "payout": payout
                        })

    print(f"検出件数: {len(results)}件")

    lines = [f"📊【11/9 1-234-234 決着一覧（計{len(results)}件）】📊\n"]
    for r in results:
        lines.append(f"📍 {r['stadium']} {r['rno']}R : {r['trifecta']} ({r['payout']}円)")

    lines.append("\n━━━━━━━━━━━━━━━")
    lines.append("※この中から『1号艇勝率』や『2号艇との差』をどの水準に置くかで、狙い目レースを最適化できます。")

    send_notification("\n".join(lines))
    print("LINE送信完了")


if __name__ == "__main__":
    main()
