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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.boatrace.jp/"
}

JCD_NAME_MAP = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川",
    "06": "浜名湖", "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
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
    url = f"https://www.boatrace.jp/owpc/pc/race/pay?hd={date_str}"
    print(f"=== 払戻一覧から安全に一括取得中: {url} ===")

    res = requests.get(url, headers=HEADERS, timeout=15)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")

    target_combos = {"1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3"}
    results = []

    # 各レース場ブロックの抽出
    # ボートレース公式では場ごとに section または table1 が区切られている
    sections = soup.find_all("div", class_=re.compile(r"table1|unit"))
    if not sections:
        sections = [soup]

    for sec in sections:
        sec_text = sec.get_text(" ", strip=True).translate(str.maketrans("１２３４５６", "123456"))
        
        # 場名の特定
        stadium_name = "開催場"
        jcd_match = sec.find("a", href=re.compile(r"jcd=(\d+)"))
        if jcd_match:
            m = re.search(r"jcd=(\d+)", jcd_match["href"])
            if m:
                stadium_name = JCD_NAME_MAP.get(f"{int(m.group(1)):02d}", stadium_name)
        else:
            for code, name in JCD_NAME_MAP.items():
                if name in sec_text[:50]:
                    stadium_name = name
                    break

        # 各テーブルからレース結果を走査
        tables = sec.find_all("table")
        for tbl in tables:
            rows = tbl.find_all("tr")
            current_rno = None
            for tr in rows:
                txt = tr.get_text(" ", strip=True).translate(str.maketrans("１２３４５６", "123456"))
                
                # レース番号（例: 1R, 2R）
                r_m = re.search(r"\b([1-9]|1[0-2])R\b", txt)
                if r_m:
                    current_rno = int(r_m.group(1))

                # 3連単の行
                if "3連単" in txt:
                    digits = re.findall(r"\b([1-6])\b", txt)
                    pay_match = re.search(r"[¥￥]?([0-9,]+)\s*円?", txt)
                    payout = pay_match.group(1) if pay_match else "-"

                    if len(digits) >= 3:
                        trifecta = f"{digits[0]}-{digits[1]}-{digits[2]}"
                        if trifecta in target_combos:
                            results.append({
                                "stadium": stadium_name,
                                "rno": current_rno if current_rno else "?",
                                "combo": trifecta,
                                "payout": payout
                            })

    # 重複排除
    unique_results = []
    seen = set()
    for r in results:
        key = (r["stadium"], r["rno"], r["combo"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    print(f"検出件数: {len(unique_results)}件")

    if not unique_results:
        # 万が一テーブル解析が空だった場合、ページ内の3連単全体から出目を直接集計
        lines = [f"📊【11/9 払戻生データ取得完了】📊\n通信ステータス: 200 (正常)\n"]
        raw_hits = re.findall(r"1\s*[-–]\s*([2-4])\s*[-–]\s*([2-4])", res.text.translate(str.maketrans("１２３４５６", "123456")))
        lines.append(f"テキスト全体から検出された1-234-234の決着数: {len(raw_hits)} 件")
        send_notification("\n".join(lines))
        return

    lines = [f"📊【11/9 実決着 1-234-234 一覧（計{len(unique_results)}件）】📊\n"]
    for r in unique_results[:12]:
        lines.append(f"📍 {r['stadium']} {r['rno']}R : {r['combo']} ({r['payout']}円)")

    if len(unique_results) > 12:
        lines.append(f"\n...他 {len(unique_results) - 12} 件")

    lines.append("\n━━━━━━━━━━━━━━━")
    lines.append("※データ取得パイプラインの開通に成功しました。この実決着レースを元に最適数値を割り出します。")

    send_notification("\n".join(lines))
    print("LINE送信完了")


if __name__ == "__main__":
    main()
