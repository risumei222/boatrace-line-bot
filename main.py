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
        res.encoding = res.apparent_encoding
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
        # 1. 結果取得（着順テーブルから1〜3着を直接抽出）
        res = session.get(result_url, timeout=8)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        ranks = {}
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                r_txt = tds[0].get_text(strip=True).translate(str.maketrans("１２３４５６", "123456"))
                b_txt = tds[1].get_text(strip=True).translate(str.maketrans("１２３４５６", "123456"))
                if r_txt in ["1", "2", "3"] and b_txt in ["1", "2", "3", "4", "5", "6"]:
                    ranks[int(r_txt)] = int(b_txt)

        if not (1 in ranks and 2 in ranks and 3 in ranks):
            return None

        first, second, third = ranks[1], ranks[2], ranks[3]
        combo = f"{first}-{second}-{third}"

        # 1-234-234 の判定
        if not (first == 1 and second in [2, 3, 4] and third in [2, 3, 4] and second != third):
            return None

        # 2. 出走表からスペック（勝率）を取得
        res_l = session.get(list_url, timeout=8)
        res_l.encoding = res_l.apparent_encoding
        soup_l = BeautifulSoup(res_l.text, "html.parser")

        table = soup_l.find("table", class_="is-w748") or soup_l.find("div", class_="table1").find("table")
        if not table:
            return None

        tbodies = table.find_all("tbody")
        if len(tbodies) < 6:
            return None

        racers = []
        for pit, tb in enumerate(tbodies[:6], 1):
            txt = tb.get_text(" ", strip=True)
            rm = re.search(r"\b(A1|A2|B1|B2)\b", txt)
            rank = rm.group(1) if rm else "B1"

            # 全国勝率の取得
            win_rates = re.findall(r"\b([1-9]\.\d{2})\b", txt)
            win_val = float(win_rates[0]) if win_rates else 0.0

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

    avg_r1_win = sum(r["r1_win"] for r in results if r["r1_win"] > 0) / max(len(results), 1)
    avg_diff = sum(r["diff"] for r in results) / max(len(results), 1)
    avg_outer = sum(r["max_outer"] for r in results if r["max_outer"] > 0) / max(len(results), 1)
    a1_count = sum(1 for r in results if r["r1_rank"] == "A1")

    lines = [f"📊【11/9 生データ実測（計{len(results)}件）】📊\n"]
    for r in results[:8]:
        lines.append(
            f"📍 {r['stadium']} {r['rno']}R [{r['combo']}]\n"
            f"・1号艇: {r['r1_rank']} (勝率{r['r1_win']:.2f}) | 2号艇差:{r['diff']:+.2f}\n"
            f"・5-6号艇: 最高勝率 {r['max_outer']:.2f} ({r['r5_rank']}/{r['r6_rank']})"
        )

    lines.append(
        f"\n━━━━━━━━━━━━━━━\n"
        f"【実測から逆算した平均値】\n"
        f"・1号艇 A1率: {a1_count}/{len(results)} ({a1_count/len(results)*100:.0f}%)\n"
        f"・1号艇 平均勝率: {avg_r1_win:.2f}\n"
        f"・2号艇との平均差: {avg_diff:+.2f}\n"
        f"・5-6号艇の平均勝率: {avg_outer:.2f}"
    )

    send_notification("\n".join(lines))
    print("LINE送信完了")


if __name__ == "__main__":
    main()
