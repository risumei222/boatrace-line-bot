import os
import re
import sys
import time
import subprocess

# ライブラリ確認と自動インストール
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.boatrace.jp/"
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


def send_line(message: str):
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
    print(f"=== ステップ1: {date_str} 払戻一覧から1-234-234決着レースを抽出中 ===")

    pay_url = f"https://www.boatrace.jp/owpc/pc/race/pay?hd={date_str}"
    res = session.get(pay_url, timeout=15)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")

    target_combos = {"1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3"}
    matched_races = []

    # 各レース場のテーブルを走査
    tables = soup.find_all("table")
    for tbl in tables:
        # テーブル内のリンクまたは前後の見出しからjcdを特定
        link = tbl.find_previous("a", href=re.compile(r"jcd=(\d+)")) or tbl.find("a", href=re.compile(r"jcd=(\d+)"))
        if not link:
            continue
        jcd = int(re.search(r"jcd=(\d+)", link["href"]).group(1))

        for tr in tbl.find_all("tr"):
            txt = tr.get_text(" ", strip=True)
            if "3連単" in txt:
                # レース番号の取得
                r_m = re.search(r"(\d+)R", txt)
                if not r_m:
                    continue
                rno = int(r_m.group(1))

                # 3連単の組番を抽出（HTMLタグ内の数字を順に取得）
                digits = []
                for num_elem in tr.find_all(class_=re.compile(r"number|is-type")):
                    d = num_elem.get_text(strip=True)
                    if d in ["1", "2", "3", "4", "5", "6"]:
                        digits.append(d)
                
                # クラス名で取れなかった場合のテキストフォールバック
                if len(digits) < 3:
                    clean_txt = txt.translate(str.maketrans("１２３４５６", "123456"))
                    after_3 = clean_txt.split("3連単")[-1]
                    digits = re.findall(r"\b([1-6])\b", after_3)

                if len(digits) >= 3:
                    combo = f"{digits[0]}-{digits[1]}-{digits[2]}"
                    if combo in target_combos:
                        # 配当金の抽出
                        pay_m = re.search(r"[¥￥]?([0-9,]+)\s*円?", txt)
                        payout = pay_m.group(1) if pay_m else "-"
                        matched_races.append({
                            "jcd": jcd,
                            "stadium": JCD_NAME_MAP.get(jcd, f"{jcd}場"),
                            "rno": rno,
                            "combo": combo,
                            "payout": payout
                        })

    # 重複除去
    unique_matches = []
    seen = set()
    for r in matched_races:
        key = (r["jcd"], r["rno"])
        if key not in seen:
            seen.add(key)
            unique_matches.append(r)

    print(f"ステップ1完了: 対象決着数 = {len(unique_matches)} 件")

    if not unique_matches:
        send_line(f"【バックテスト】{date_str} の1-234-234決着レースが検出できませんでした。")
        return

    print("=== ステップ2: 対象レースの出走表（選手の勝率）を安全に個別取得中 ===")
    detailed_data = []

    for race in unique_matches:
        jcd = race["jcd"]
        rno = race["rno"]
        list_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd:02d}&hd={date_str}"
        
        try:
            time.sleep(1.2)  # アクセス遮断を防ぐウェイト
            r_res = session.get(list_url, timeout=10)
            r_res.encoding = r_res.apparent_encoding
            r_soup = BeautifulSoup(r_res.text, "html.parser")

            tbodies = r_soup.find_all("tbody", class_=re.compile(r"is-p10-0|body"))
            if not tbodies:
                tbl = r_soup.find("table", class_="is-w748") or r_soup.find("div", class_="table1").find("table")
                tbodies = tbl.find_all("tbody")[:6] if tbl else []

            if len(tbodies) >= 6:
                racers = []
                for pit, tb in enumerate(tbodies[:6], 1):
                    t = tb.get_text(" ", strip=True)
                    rk = re.search(r"\b(A1|A2|B1|B2)\b", t)
                    rank = rk.group(1) if rk else "B1"

                    rates = re.findall(r"\b([1-9]\.\d{2})\b", t)
                    win = float(rates[0]) if rates else 0.0
                    racers.append({"rank": rank, "win": win})

                r1 = racers[0]
                r2 = racers[1]
                r5 = racers[4]
                r6 = racers[5]

                diff = round(r1["win"] - r2["win"], 2)
                max_outer = max(r5["win"], r6["win"])

                detailed_data.append({
                    "stadium": race["stadium"],
                    "rno": race["rno"],
                    "combo": race["combo"],
                    "payout": race["payout"],
                    "r1_rank": r1["rank"],
                    "r1_win": r1["win"],
                    "diff": diff,
                    "r5_rank": r5["rank"],
                    "r6_rank": r6["rank"],
                    "max_outer": max_outer
                })
        except Exception as e:
            print(f"取得スキップ: {race['stadium']}{rno}R ({e})")
            continue

    print(f"解析完了: {len(detailed_data)} 件のスペック照合に成功")

    if not detailed_data:
        send_line("出走表データの取得に失敗しました。")
        return

    # 集計
    valid_r1 = [d["r1_win"] for d in detailed_data if d["r1_win"] > 0]
    avg_r1 = sum(valid_r1) / len(valid_r1) if valid_r1 else 0.0
    avg_diff = sum(d["diff"] for d in detailed_data) / len(detailed_data)
    valid_out = [d["max_outer"] for d in detailed_data if d["max_outer"] > 0]
    avg_out = sum(valid_out) / len(valid_out) if valid_out else 0.0
    a1_num = sum(1 for d in detailed_data if d["r1_rank"] == "A1")

    # LINE送信文面
    lines = [f"📊【11/9 実決着データ検証（全{len(detailed_data)}件）】📊\n"]
    for d in detailed_data[:8]:
        lines.append(
            f"📍 {d['stadium']} {d['rno']}R [{d['combo']}] ({d['payout']}円)\n"
            f" 1号艇:{d['r1_rank']}(勝率{d['r1_win']:.2f}) | 2号艇差:{d['diff']:+.2f}\n"
            f" 外枠最高:{d['max_outer']:.2f} ({d['r5_rank']}/{d['r6_rank']})"
        )

    lines.append(
        f"\n━━━━━━━━━━━━━━━\n"
        f"【実決着から判明した生データ平均】\n"
        f"・1号艇 A1率: {a1_num}/{len(detailed_data)} ({a1_num/len(detailed_data)*100:.0f}%)\n"
        f"・1号艇 平均勝率: {avg_r1:.2f}\n"
        f"・2号艇との平均差: {avg_diff:+.2f}\n"
        f"・外枠5-6号艇 平均勝率: {avg_out:.2f}\n"
        f"━━━━━━━━━━━━━━━"
    )

    send_line("\n".join(lines))
    print("LINE送信完了")


if __name__ == "__main__":
    main()
