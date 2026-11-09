import os
import re
import sys
import subprocess
import datetime
from concurrent.futures import ThreadPoolExecutor

# 外部ライブラリを自動インストール
for pkg in ["requests", "beautifulsoup4"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import requests
from bs4 import BeautifulSoup

# ==========================================
# 1. 設定・環境変数
# ==========================================
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

EXCLUDED_STADIUMS_SOLID = [2, 3, 4]  # 戸田, 江戸川, 平和島

session = requests.Session()
session.headers.update(HEADERS)


# ==========================================
# 2. 通知関数
# ==========================================
def send_notification(message: str):
    """LINEまたはTelegramへ一括送信"""
    if LINE_NOTIFY_TOKEN:
        try:
            session.post(
                "https://notify-api.line.me/api/notify",
                headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"},
                data={"message": f"\n{message}"},
                timeout=10
            )
        except Exception as e:
            print(f"[ERROR] LINE Notify送信失敗: {e}")

    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        try:
            session.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
                },
                json={
                    "to": LINE_USER_ID,
                    "messages": [{"type": "text", "text": message}]
                },
                timeout=10
            )
        except Exception as e:
            print(f"[ERROR] LINE Push送信失敗: {e}")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            session.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
        except Exception as e:
            print(f"[ERROR] Telegram送信失敗: {e}")


# ==========================================
# 3. 公式Webサイト 高速スクレイピング
# ==========================================
def get_active_stadiums(date_str: str):
    """当日の開催場一覧を取得"""
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    print(f"\n[接続] 開催場一覧を取得中: {url}")
    try:
        res = session.get(url, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        
        stadiums = []
        table = soup.find("table")
        if not table:
            return stadiums
            
        links = table.find_all("a", href=re.compile(r"jcd=\d+"))
        for link in links:
            m = re.search(r"jcd=(\d+)", link["href"])
            if m:
                jcd = int(m.group(1))
                if jcd not in stadiums and 1 <= jcd <= 24:
                    stadiums.append(jcd)
        return sorted(stadiums)
    except Exception as e:
        print(f"[ERROR] 開催場一覧取得エラー: {e}")
        return []


def parse_racelist(args):
    """指定レースの出走表をパース（並列実行用）"""
    jcd, rno, date_str = args
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd:02d}&hd={date_str}"
    try:
        res = session.get(url, timeout=8)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        race_title = ""
        title_tag = soup.find("h3", class_="title16__title")
        if title_tag:
            race_title = title_tag.get_text(strip=True)

        is_special_race = any(k in race_title for k in ["企画", "ドリーム", "準優勝", "優勝", "女子", "ヴィーナス"])

        table = soup.find("table", class_="is-w748") or soup.find("div", class_="table1").find("table")
        if not table:
            return None

        tbodies = table.find_all("tbody")
        if len(tbodies) < 6:
            return None

        racers = []
        for pit, tbody in enumerate(tbodies[:6], start=1):
            text = tbody.get_text(" ", strip=True)
            
            rank_match = re.search(r"\b(A1|A2|B1|B2)\b", text)
            rank = rank_match.group(1) if rank_match else "B1"

            name_tag = tbody.find("div", class_="is-fs18") or tbody.find("a", href=re.compile(r"toban="))
            name = name_tag.get_text(strip=True) if name_tag else f"{pit}号艇"

            tds = tbody.find_all("td")
            win_rate_nat = 0.0
            win_rate_loc = 0.0
            avg_st = 0.20

            for td in tds:
                td_txt = td.get_text("\n", strip=True)
                lines = [l.strip() for l in td_txt.split("\n") if l.strip()]
                for line in lines:
                    st_m = re.search(r"^0\.(\d{2})$", line)
                    if st_m and avg_st == 0.20:
                        avg_st = float(line)
                if lines and re.match(r"^[1-9]\.\d{2}$", lines[0]):
                    val = float(lines[0])
                    if win_rate_nat == 0.0:
                        win_rate_nat = val
                    elif win_rate_loc == 0.0:
                        win_rate_loc = val

            racers.append({
                "pit": pit,
                "name": name,
                "rank": rank,
                "win_nat": win_rate_nat,
                "win_loc": win_rate_loc,
                "avg_st": avg_st
            })

        return {
            "jcd": jcd,
            "stadium": JCD_NAME_MAP.get(jcd, f"{jcd}場"),
            "rno": rno,
            "title": race_title,
            "is_special": is_special_race,
            "racers": racers
        }
    except Exception:
        return None


# ==========================================
# 4. ロジック判定エンジン
# ==========================================
def evaluate_solid_escape(race_data):
    """ロジック2：堅実イン逃げ式（1-234-234）"""
    if race_data["jcd"] in EXCLUDED_STADIUMS_SOLID:
        return None, "イン受難水面"

    racers = race_data["racers"]
    r1, r2, r5, r6 = racers[0], racers[1], racers[4], racers[5]

    if r1["rank"] != "A1" or r1["win_nat"] < 6.20:
        return None, f"1号艇条件外({r1['rank']}/{r1['win_nat']:.2f})"

    if (r1["win_nat"] - r2["win_nat"]) < 0.80:
        return None, f"2号艇と勝率差小({r1['win_nat']:.2f} vs {r2['win_nat']:.2f})"

    if r5["rank"] in ["A1", "A2"] or r6["rank"] in ["A1", "A2"]:
        return None, "外枠にA級存在"
    if r5["win_nat"] >= 5.20 or r6["win_nat"] >= 5.20:
        return None, "5・6号艇の勝率超過"

    candidates = []
    st_list = [racers[1]["avg_st"], racers[2]["avg_st"], racers[3]["avg_st"]]
    min_st = min(st_list)

    for r in racers[1:4]:
        base_course = 3.0 if r["pit"] == 2 else (2.0 if r["pit"] == 3 else 1.0)
        st_bonus = 1.5 if r["avg_st"] == min_st else 0.0
        score = base_course + r["win_nat"] + st_bonus
        candidates.append({"pit": r["pit"], "score": score})

    candidates.sort(key=lambda x: x["score"], reverse=True)
    p_strong, p_mid, p_weak = candidates[0]["pit"], candidates[1]["pit"], candidates[2]["pit"]

    bets = [
        (f"1-{p_strong}-{p_mid}", 300),
        (f"1-{p_strong}-{p_weak}", 200),
        (f"1-{p_mid}-{p_strong}", 200),
        (f"1-{p_mid}-{p_weak}", 100),
        (f"1-{p_weak}-{p_strong}", 100),
        (f"1-{p_weak}-{p_mid}", 100)
    ]

    return {
        "logic": "堅実イン逃げ式",
        "bets": bets,
        "total_cost": 1000,
        "reason": f"展開評価: 強={p_strong}号艇, 中={p_mid}号艇, 並={p_weak}号艇"
    }, "合格"


def evaluate_leisumei(race_data):
    """ロジック1：リースメイ式（厳選ホームラン枠）"""
    rno = race_data["rno"]
    if rno < 9 and not race_data["is_special"]:
        return None, "前半一般戦"

    racers = race_data["racers"]
    r1 = racers[0]

    if r1["rank"] != "A1" or r1["win_nat"] < 6.80:
        return None, f"1号艇信頼度不足({r1['rank']}/{r1['win_nat']:.2f})"

    outer_candidates = []
    for r in racers[3:6]:
        score = r["win_nat"] + (r["win_loc"] * 0.5) + ((0.20 - r["avg_st"]) * 10)
        outer_candidates.append({"pit": r["pit"], "score": score, "r": r})

    outer_candidates.sort(key=lambda x: x["score"], reverse=True)
    keyman = outer_candidates[0]["r"]

    if not (keyman["rank"] == "A1" or keyman["win_nat"] >= 6.50 or keyman["win_loc"] >= 7.00):
        return None, f"外枠キーマン実力不足({keyman['pit']}号艇:{keyman['win_nat']:.2f})"

    k_pit = keyman["pit"]
    other_pits = [p for p in [2, 3, 4, 5, 6] if p != k_pit]

    bets = []
    for p in other_pits:
        amount = 300 if p in [2, 3] else 200
        bets.append((f"1-{k_pit}-{p}", amount))
        bets.append((f"1-{p}-{k_pit}", amount))

    inner_racers = sorted(racers[1:4], key=lambda x: x["win_nat"], reverse=True)
    best_inner = inner_racers[0]["pit"]
    bets.append((f"{best_inner}-1-{k_pit}", 200))
    bets.append((f"{best_inner}-{k_pit}-1", 200))

    total = sum(b[1] for b in bets)

    return {
        "logic": "リースメイ式",
        "keyman": f"{keyman['pit']}号艇 {keyman['name']}",
        "bets": bets,
        "total_cost": total,
        "reason": f"軸={k_pit}号艇(全国{keyman['win_nat']:.2f}/当地{keyman['win_loc']:.2f}), 逆転保険={best_inner}号艇"
    }, "合格"


# ==========================================
# 5. 高速メイン処理
# ==========================================
def main():
    # ※深夜テスト用に前日(20261109)のデータで判定を実行します
    date_str = "20261109"
    print(f"=== 高速ボートレース分析エンジン起動: {date_str} ===")

    stadiums = get_active_stadiums(date_str)
    if not stadiums:
        print("[警告] 当日開催場が取得できませんでした。")
        return

    print(f"[開催場] 全国 {len(stadiums)} 場を巡回します: {[JCD_NAME_MAP.get(j, j) for j in stadiums]}")

    # 全場・全レースのタスクを作成
    tasks = [(jcd, rno, date_str) for jcd in stadiums for rno in range(1, 13)]

    # 10並列で超高速に取得（20分 -> 約30秒へ短縮）
    print(f"[取得中] 全 {len(tasks)} レースを並列スクレイピング中...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        all_races = list(executor.map(parse_racelist, tasks))

    valid_races = [r for r in all_races if r is not None]
    print(f"[取得完了] {len(valid_races)} レースの出走表取得に成功しました。判定を開始します。\n")

    solid_hits = []
    leisumei_hits = []

    for race_data in valid_races:
        r1 = race_data["racers"][0]
        s_name = race_data["stadium"]
        rno = race_data["rno"]

        # 堅実イン逃げ式
        res_solid, msg_s = evaluate_solid_escape(race_data)
        if res_solid:
            print(f"[{s_name} {rno}R] -> 【堅実 HIT!】 1号艇:{r1['name']}({r1['rank']}/{r1['win_nat']:.2f})")
            solid_hits.append((race_data, res_solid))
            continue

        # リースメイ式
        res_lei, msg_l = evaluate_leisumei(race_data)
        if res_lei:
            print(f"[{s_name} {rno}R] -> 【リースメイ HIT! 軸:{res_lei['keyman']}】")
            leisumei_hits.append((race_data, res_lei))
            continue

        print(f"[{s_name} {rno}R] 1号艇:{r1['name']}({r1['rank']}/{r1['win_nat']:.2f}) -> SKIP: 堅実({msg_s}) | リースメイ({msg_l})")

    # ==========================================
    # 6. 通知送信
    # ==========================================
    total_hits = len(solid_hits) + len(leisumei_hits)
    print(f"\n=== 全判定完了: 検出件数 {total_hits} 件 ===")

    if total_hits == 0:
        msg = f"【ボートレース厳選配信（テスト）】\n対象日（{date_str}）は条件合致レースなし（見送り推奨）"
        send_notification(msg)
        return

    lines = [f"🚤【本日の厳選勝負レース（{total_hits}件）】🚤\n"]
    if solid_hits:
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("【ロジック2：堅実イン逃げ式（1-234-234）】")
        for rdata, plan in solid_hits:
            lines.append(f"\n📍 {rdata['stadium']} {rdata['rno']}R")
            lines.append(f"1号艇: {rdata['racers'][0]['name']} (A1 / 勝率{rdata['racers'][0]['win_nat']:.2f})")
            lines.append(f"根拠: {plan['reason']}")
            lines.append("▼ 買い目 & 配分 (計1,000円):")
            for bet, amt in plan["bets"]:
                lines.append(f"・{bet} : {amt}円")

    if leisumei_hits:
        lines.append("\n━━━━━━━━━━━━━━━")
        lines.append("【ロジック1：リースメイ式】")
        for rdata, plan in leisumei_hits:
            lines.append(f"\n📍 {rdata['stadium']} {rdata['rno']}R")
            lines.append(f"1号艇: {rdata['racers'][0]['name']} (勝率{rdata['racers'][0]['win_nat']:.2f})")
            lines.append(f"対抗◯: {plan['keyman']}")
            lines.append(f"根拠: {plan['reason']}")
            lines.append(f"▼ 買い目 (計{len(plan['bets'])}点 / {plan['total_cost']}円):")
            for bet, amt in plan["bets"]:
                lines.append(f"・{bet} : {amt}円")

    final_message = "\n".join(lines)
    send_notification(final_message)
    print("[送信完了] LINE通知を送信しました。")


if __name__ == "__main__":
    main()
