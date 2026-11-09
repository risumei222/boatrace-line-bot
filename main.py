import os
import re
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor

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

JCD_NAME_MAP = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川",
    6: "浜名湖", 7: "蒲郡", 8: "常滑", 9: "津", 10: "三国",
    11: "びわこ", 12: "住之江", 13: "尼崎", 14: "鳴門", 15: "丸亀",
    16: "児島", 17: "宮島", 18: "徳山", 19: "下関", 20: "若松",
    21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村"
}

session = requests.Session()
session.headers.update(HEADERS)


def send_notification(message: str):
    if LINE_NOTIFY_TOKEN:
        try:
            session.post("https://notify-api.line.me/api/notify",
                         headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"},
                         data={"message": f"\n{message}"}, timeout=10)
        except Exception:
            pass
    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        try:
            session.post("https://api.line.me/v2/bot/message/push",
                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
                         json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message[:4500]}]}, timeout=10)
        except Exception:
            pass


def get_active_stadiums(date_str: str):
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        stadiums = []
        for a in soup.find_all("a", href=re.compile(r"jcd=\d+")):
            m = re.search(r"jcd=(\d+)", a["href"])
            if m:
                jcd = int(m.group(1))
                if jcd not in stadiums and 1 <= jcd <= 24:
                    stadiums.append(jcd)
        return sorted(stadiums)
    except Exception:
        return []


def analyze_single_race(args):
    jcd, rno, date_str = args
    result_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd:02d}&hd={date_str}"
    list_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd:02d}&hd={date_str}"

    try:
        # 1. 結果取得（タグ構造に依存せず、テキスト全体から3連単の着順を抽出）
        res = session.get(result_url, timeout=8)
        text_clean = res.text.translate(str.maketrans("１２３４５６", "123456"))
        
        # 「3連単」の文字以降から数字3つを抽出
        m_section = re.search(r"3連単.*?(?=3連複|2連単|2連複|拡連複|単勝|複勝|$)", text_clean, re.DOTALL)
        if not m_section:
            return None
        
        digits = re.findall(r"\b([1-6])\b", m_section.group(0))
        if len(digits) < 3:
            return None

        first, second, third = int(digits[0]), int(digits[1]), int(digits[2])
        combo = f"{first}-{second}-{third}"

        # 1-234-234 判定
        if not (first == 1 and second in [2, 3, 4] and third in [2, 3, 4] and second != third):
            return None

        # 払戻金の抽出
        m_pay = re.search(r"[¥￥]([0-9,]+)", m_section.group(0))
        payout = m_pay.group(1) if m_pay else "-"

        # 2. 出走表からスペックを取得
        res_l = session.get(list_url, timeout=8)
        soup_l = BeautifulSoup(res_l.text, "html.parser")
        table = soup_l.find("table", class_="is-w748") or soup_l.find("div", class_="table1").find("table")
        if not table:
            return None

        tbodies = table.find_all("tbody")[:6]
        if len(tbodies) < 6:
            return None

        racers = []
        for pit, tb in enumerate(tbodies, 1):
            txt = tb.get_text(" ", strip=True)
            rm = re.search(r"\b(A1|A2|B1|B2)\b", txt)
            rank = rm.group(1) if rm else "B1"

            # 勝率の抽出
            rates = re.findall(r"\b([1-9]\.\d{2})\b", txt)
            win_val = float(rates[0]) if rates else 0.0
            racers.append({"pit": pit, "rank": rank, "win": win_val})

        r1 = racers[0]
        r2 = racers[1]
        r5 = racers[4]
        r6 = racers[5]

        diff = round(r1["win"] - r2["win"], 2)
        max_outer = max(r5["win"], r6["win"])

        return {
            "stadium": JCD_NAME_MAP.get(jcd, f"{jcd}場"),
            "rno": rno,
            "combo": combo,
            "payout": payout,
            "r1_rank": r1["rank"],
            "r1_win": r1["win"],
            "diff": diff,
            "r5_rank": r5["rank"],
            "r6_rank": r6["rank"],
            "max_outer": max_outer
        }
    except Exception:
        return None


def main():
    date_str = "20261109"
    print(f"=== {date_str} 生データ解析 ===")

    stadiums = get_active_stadiums(date_str)
    tasks = [(jcd, rno, date_str) for jcd in stadiums for rno in range(1, 13)]

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = [r for r in executor.map(analyze_single_race, tasks) if r is not None]

    print(f"検出件数: {len(results)}件")

    if not results:
        send_notification(f"【生データ解析】{date_str} の1-234-234該当なし")
        return

    # 実測データの集計
    valid_r1 = [r["r1_win"] for r in results if r["r1_win"] > 0]
    avg_r1_win = sum(valid_r1) / len(valid_r1) if valid_r1 else 0.0
    avg_diff = sum(r["diff"] for r in results) / len(results)
    valid_outer = [r["max_outer"] for r in results if r["max_outer"] > 0]
    avg_outer = sum(valid_outer) / len(valid_outer) if valid_outer else 0.0
    a1_count = sum(1 for r in results if r["r1_rank"] == "A1")

    lines = [f"📊【11/9 生データ実測（実決着: {len(results)}件）】📊\n"]
    for r in results[:8]:
        lines.append(
            f"📍 {r['stadium']}{r['rno']}R [{r['combo']}] ({r['payout']}円)\n"
            f"・1号艇: {r['r1_rank']} (勝率{r['r1_win']:.2f}) | 2号艇差:{r['diff']:+.2f}\n"
            f"・外枠: {r['r5_rank']}/{r['r6_rank']} (最高勝率{r['max_outer']:.2f})"
        )

    lines.append(
        f"\n━━━━━━━━━━━━━━━\n"
        f"【実測から逆算した平均値】\n"
        f"・1号艇 A1率: {a1_count}/{len(results)} ({a1_count/len(results)*100:.0f}%)\n"
        f"・1号艇 平均勝率: {avg_r1_win:.2f}\n"
        f"・2号艇との平均差: {avg_diff:+.2f}\n"
        f"・外枠の平均勝率: {avg_outer:.2f}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"※この実データをもとに、最も的中率と回収率が高くなるフィルターの数値を固めます。"
    )

    send_notification("\n".join(lines))
    print("LINE送信完了")


if __name__ == "__main__":
    main()
