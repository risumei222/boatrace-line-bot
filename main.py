import os
import re
import sys
import subprocess
import datetime
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
                         json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}, timeout=10)
        except Exception:
            pass
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                         json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
        except Exception:
            pass


def get_active_stadiums(date_str: str):
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    try:
        res = session.get(url, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        stadiums = []
        table = soup.find("table")
        if not table:
            return stadiums
        for link in table.find_all("a", href=re.compile(r"jcd=\d+")):
            m = re.search(r"jcd=(\d+)", link["href"])
            if m:
                jcd = int(m.group(1))
                if jcd not in stadiums and 1 <= jcd <= 24:
                    stadiums.append(jcd)
        return sorted(stadiums)
    except Exception:
        return []


def analyze_race(args):
    jcd, rno, date_str = args
    result_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd:02d}&hd={date_str}"
    list_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd:02d}&hd={date_str}"

    try:
        # 1. 結果取得
        res_res = session.get(result_url, timeout=8)
        res_res.encoding = res_res.apparent_encoding
        soup_res = BeautifulSoup(res_res.text, "html.parser")

        # 3連単の出目と払戻金を抽出
        trifecta = None
        payout = 0
        tables = soup_res.find_all("table")
        for tbl in tables:
            txt = tbl.get_text()
            if "3連単" in txt:
                m = re.search(r"(\d)-(\d)-(\d)", txt)
                if m:
                    trifecta = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                pm = re.search(r"¥([0-9,]+)", txt)
                if pm:
                    payout = int(pm.group(1).replace(",", ""))
                break

        if not trifecta:
            return None

        # 1-234-234（1着1号艇、2・3着が2〜4号艇）かチェック
        target_combos = ["1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3"]
        if trifecta not in target_combos:
            return None

        # 2. 該当したレースの出走表データを取得
        res_list = session.get(list_url, timeout=8)
        res_list.encoding = res_list.apparent_encoding
        soup_list = BeautifulSoup(res_list.text, "html.parser")

        tbl_list = soup_list.find("table", class_="is-w748") or soup_list.find("div", class_="table1").find("table")
        if not tbl_list:
            return None

        tbodies = tbl_list.find_all("tbody")[:6]
        racers = []
        for pit, tbody in enumerate(tbodies, 1):
            text = tbody.get_text(" ", strip=True)
            rank_m = re.search(r"\b(A1|A2|B1|B2)\b", text)
            rank = rank_m.group(1) if rank_m else "B1"
            name_tag = tbody.find("div", class_="is-fs18") or tbody.find("a", href=re.compile(r"toban="))
            name = name_tag.get_text(strip=True) if name_tag else f"{pit}号艇"

            win_rate = 0.0
            for td in tbody.find_all("td"):
                lines = [l.strip() for l in td.get_text("\n", strip=True).split("\n") if l.strip()]
                if lines and re.match(r"^[1-9]\.\d{2}$", lines[0]):
                    win_rate = float(lines[0])
                    break
            racers.append({"pit": pit, "name": name, "rank": rank, "win": win_rate})

        r1 = racers[0]
        r2 = racers[1]
        max_outer_win = max(racers[4]["win"], racers[5]["win"])
        outer_ranks = f"{racers[4]['rank']}/{racers[5]['rank']}"

        return {
            "stadium": JCD_NAME_MAP.get(jcd, f"{jcd}場"),
            "rno": rno,
            "trifecta": trifecta,
            "payout": payout,
            "r1": r1,
            "r2_diff": r1["win"] - r2["win"],
            "outer_max_win": max_outer_win,
            "outer_ranks": outer_ranks
        }
    except Exception:
        return None


def main():
    date_str = "20261109"
    print(f"=== 11月9日 1-234-234 決着レース バックテスト ===")

    stadiums = get_active_stadiums(date_str)
    tasks = [(jcd, rno, date_str) for jcd in stadiums for rno in range(1, 13)]

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = [r for r in executor.map(analyze_race, tasks) if r is not None]

    print(f"\n[集計結果] 全レース中、1-234-234 で決着したレース: {len(results)} 件\n")

    lines = [f"📊【11/9 1-234-234 決着分析（計{len(results)}件）】📊\n"]

    for r in results:
        r1 = r["r1"]
        line = (f"📍{r['stadium']}{r['rno']}R | 出目:{r['trifecta']} (配当:{r['payout']}円)\n"
                f"・1号艇: {r1['name']}({r1['rank']} / 勝率{r1['win']:.2f})\n"
                f"・2号艇との勝率差: {r['r2_diff']:+.2f}\n"
                f"・5-6号艇: 級別[{r['outer_ranks']}] / 最高勝率:{r['outer_max_win']:.2f}\n")
        lines.append(line)
        print(line)

    if results:
        # 適正値の算出
        avg_r1_win = sum(r["r1"]["win"] for r in results) / len(results)
        avg_diff = sum(r["r2_diff"] for r in results) / len(results)
        avg_outer = sum(r["outer_max_win"] for r in results) / len(results)

        summary = (f"━━━━━━━━━━━━━━━\n"
                   f"【逆算された平均値】\n"
                   f"・1号艇の平均勝率: {avg_r1_win:.2f}\n"
                   f"・2号艇との平均差: {avg_diff:+.2f}\n"
                   f"・5-6号艇の平均勝率: {avg_outer:.2f}\n"
                   f"※この数値を基準にフィルターを調整すると、取りこぼしなく最も利益が出る条件が作れます。")
        lines.append(summary)
        print(summary)

    send_notification("\n".join(lines))
    print("[完了] LINEへ分析レポートを送信しました。")


if __name__ == "__main__":
    main()
