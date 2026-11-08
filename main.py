import os
import sys
import json
import re
import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple

# 必要な外部ライブラリを自動インストール
for pkg in ["requests", "beautifulsoup4"]:
    try:
        __import__(pkg)
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import requests
from bs4 import BeautifulSoup

# ==========================================
# データ構造モデル
# ==========================================

@dataclass
class Racer:
    boat: int            # 艇番 (1-6)
    name: str            # 選手名
    rank: str            # 級別 ('A1', 'A2', 'B1', 'B2')
    win_rate_nat: float  # 全国勝率
    win_rate_loc: float  # 当地勝率

@dataclass
class RaceInfo:
    stadium: str         # 競艇場名
    race_no: int         # レース番号 (1-12)
    race_type: str       # '優勝戦', '準優勝戦', 'ドリーム戦', '女子戦', '一般予選', '企画'
    is_girls: bool       # 女子戦フラグ
    weather_bad: bool    # 荒天フラグ
    racers: List[Racer]  # 1〜6号艇の選手データリスト

# ==========================================
# ロジック1：つーちゃん舟券ロジック
# ==========================================

class TsuChanEngine:
    def __init__(self, target_budget: Optional[int] = None):
        self.user_budget = target_budget

    def evaluate_race(self, race: RaceInfo) -> Tuple[bool, str, Optional[Racer], str]:
        valid_races = ['優勝戦', '準優勝戦', 'ドリーム戦', '企画']
        if race.race_no < 10 and race.race_type not in valid_races and not (race.is_girls and race.race_no >= 9):
            return False, "平場予選スキップ", None, "SKIP"

        r1 = race.racers[0]
        if r1.rank != 'A1' or r1.win_rate_nat < 6.5:
            return False, "1号艇信頼度不足", None, "SKIP"

        outer_racers = race.racers[3:6]
        candidates = [r for r in outer_racers if r.rank == 'A1' or r.win_rate_nat >= 6.5 or r.win_rate_loc >= 7.0]

        if not candidates:
            return False, "外枠格上キーマン不在", None, "SKIP"

        keyman = max(candidates, key=lambda x: (x.win_rate_nat, x.win_rate_loc))
        inner_all_a1 = all(r.rank == 'A1' for r in race.racers[0:3])

        if keyman.boat in [4, 5]:
            confidence = "銀河系の端から端まで％" if (race.race_type in ['優勝戦', 'ドリーム戦'] and r1.win_rate_nat >= 7.8) else "88.6%"
            return True, f"{keyman.boat}号艇キーマン", keyman, confidence

        elif keyman.boat == 6:
            has_b_class_inner = any(r.rank in ['B1', 'B2'] for r in race.racers[1:4])
            if race.is_girls or has_b_class_inner:
                return True, "6号艇キーマン（女子・格差）", keyman, "86.5%"
            if inner_all_a1 or race.stadium in ['住之江', '大村', '徳山', '芦屋']:
                return False, "6号艇キーマン見送り（壁リスク）", keyman, "SKIP"
            return True, "6号艇キーマン（慎重）", keyman, "68.0%"

        return False, "選定外", None, "SKIP"

    def generate_bets(self, race: RaceInfo, keyman: Racer, confidence: str) -> dict:
        k = keyman.boat
        all_boats = [1, 2, 3, 4, 5, 6]
        others = [b for b in all_boats if b not in [1, k]]

        if "銀河系" in confidence or "現在まで" in confidence:
            total_budget = 6000
        elif "88" in confidence or "86" in confidence:
            total_budget = 4000
        else:
            total_budget = 2500

        if self.user_budget:
            total_budget = self.user_budget

        bet_list = []
        for b in others:
            w1 = 0.12 if b in [2, 3] else 0.05
            bet_list.append(('3連単', f"1-{k}-{b}", w1))
            w2 = 0.18 if b in [2, 3] else 0.06
            bet_list.append(('3連単', f"1-{b}-{k}", w2))

        for b in others:
            bet_list.append(('3連単', f"{k}-1-{b}", 0.03))

        bet_list.append(('2連単', f"1-{k}", 0.10))

        total_weight = sum(w for _, _, w in bet_list)
        final_bets = []
        calc_total = 0

        for b_type, comb, weight in bet_list:
            raw_amt = (weight / total_weight) * total_budget
            amt = max(100, int(round(raw_amt / 100.0) * 100))
            final_bets.append({"券種": b_type, "買い目": comb, "金額": amt})
            calc_total += amt

        return {
            "ロジック": "つーちゃん式",
            "レース": f"{race.stadium}{race.race_no}R ({race.race_type})",
            "本命◎": f"1号艇 {race.racers[0].name}",
            "対抗◯": f"{k}号艇 {keyman.name}",
            "自信度": confidence,
            "合計投資額": f"{calc_total:,}円",
            "買い目内訳": final_bets
        }

# ==========================================
# ロジック2：堅実イン逃げ式（全国+当地フィルター版）
# ==========================================

class SolidEscapeEngine:
    """1-234-234 厳選6点 堅実投資エンジン（1Rあたり最大1,000円配分）"""

    STRONG_IN_STADIUMS = ['大村', '徳山', '芦屋', '下関', '丸亀', '尼崎']

    def evaluate_race(self, race: RaceInfo) -> Tuple[bool, str, str]:
        # 1. 1号艇：A1級 かつ 全国勝率 6.30以上
        r1 = race.racers[0]
        if r1.rank != 'A1' or r1.win_rate_nat < 6.30:
            return False, "1号艇の逃げ信頼度不足", "SKIP"

        # 2. 5・6号艇（消去条件）：
        #    A1級不在 かつ 全国勝率5.30未満 かつ 当地勝率5.30未満（当地巧者も排除）
        r5 = race.racers[4]
        r6 = race.racers[5]
        if r5.rank == 'A1' or r5.win_rate_nat >= 5.30 or r5.win_rate_loc >= 5.30:
            return False, "5号艇の連絡みリスクあり（全国/当地勝率）", "SKIP"
        if r6.rank == 'A1' or r6.win_rate_nat >= 5.30 or r6.win_rate_loc >= 5.30:
            return False, "6号艇の連絡みリスクあり（全国/当地勝率）", "SKIP"

        # 3. 2〜4号艇：壁となる勝率（全員4.50以上で大外の差し筋をブロック）
        for r in race.racers[1:4]:
            if r.win_rate_nat < 4.50:
                return False, f"{r.boat}号艇の壁信頼度不足", "SKIP"

        confidence = "鉄板（Sランク）" if race.stadium in self.STRONG_IN_STADIUMS else "堅実（Aランク）"
        return True, "1-234-234 成立条件合致", confidence

    def generate_bets(self, race: RaceInfo, confidence: str) -> dict:
        # 傾斜配分（合計1,000円以内）
        allocation = [
            ("1-2-3", 300),
            ("1-2-4", 200),
            ("1-3-2", 200),
            ("1-3-4", 100),
            ("1-4-2", 100),
            ("1-4-3", 100),
        ]

        final_bets = [{"券種": "3連単", "買い目": comb, "金額": amt} for comb, amt in allocation]
        calc_total = sum(amt for _, amt in allocation)

        return {
            "ロジック": "堅実イン逃げ式 (1-234-234)",
            "レース": f"{race.stadium}{race.race_no}R ({race.race_type})",
            "本命◎": f"1号艇 {race.racers[0].name}",
            "切×": f"5号艇 {race.racers[4].name} / 6号艇 {race.racers[5].name}",
            "自信度": confidence,
            "合計投資額": f"{calc_total:,}円",
            "買い目内訳": final_bets
        }

# ==========================================
# 出走表スクレイピング部
# ==========================================

STADIUM_MAP = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川",
    "06": "浜名湖", "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def fetch_target_races(target_date: str) -> List[RaceInfo]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    index_url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={target_date}"
    
    try:
        res = requests.get(index_url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"開催一覧取得エラー: {e}")
        return []

    jcds = set()
    for a in soup.select("a[href*='jcd=']"):
        m = re.search(r"jcd=(\d{2})", a["href"])
        if m:
            jcds.add(m.group(1))

    race_info_list = []

    for jcd in sorted(list(jcds)):
        stadium_name = STADIUM_MAP.get(jcd, f"場{jcd}")
        for rno in range(1, 13):
            race_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd}&hd={target_date}"
            try:
                r_res = requests.get(race_url, headers=headers, timeout=10)
                r_soup = BeautifulSoup(r_res.text, "html.parser")
                
                race_title_el = r_soup.select_one(".heading2_titleDetail")
                title_text = race_title_el.get_text(strip=True) if race_title_el else ""
                
                race_type = "一般予選"
                if "優勝戦" in title_text:
                    race_type = "優勝戦"
                elif "準優勝戦" in title_text:
                    race_type = "準優勝戦"
                elif "ドリーム" in title_text:
                    race_type = "ドリーム戦"
                elif "企画" in title_text or "特選" in title_text:
                    race_type = "企画"

                is_girls = "女子" in title_text or "ヴィーナス" in title_text or "オールレディース" in title_text

                racers = []
                tbody_list = r_soup.select("div.table1 table tbody")
                if len(tbody_list) < 6:
                    continue

                for boat_no, tbody in enumerate(tbody_list[:6], start=1):
                    name_el = tbody.select_one("span.is-fs18 a, div.is-fs18 a")
                    name = name_el.get_text(strip=True) if name_el else f"{boat_no}号艇"

                    rank_el = tbody.select_one(".is-lineH2")
                    rank_match = re.search(r"(A1|A2|B1|B2)", rank_el.get_text() if rank_el else "")
                    rank = rank_match.group(1) if rank_match else "B1"

                    rates = re.findall(r"\d+\.\d{2}", tbody.get_text())
                    win_nat = float(rates[0]) if len(rates) >= 1 else 0.0
                    win_loc = float(rates[1]) if len(rates) >= 2 else 0.0

                    racers.append(Racer(
                        boat=boat_no,
                        name=name,
                        rank=rank,
                        win_rate_nat=win_nat,
                        win_rate_loc=win_loc
                    ))

                if len(racers) == 6:
                    race_info_list.append(RaceInfo(
                        stadium=stadium_name,
                        race_no=rno,
                        race_type=race_type,
                        is_girls=is_girls,
                        weather_bad=False,
                        racers=racers
                    ))
            except Exception:
                continue

    return race_info_list

# ==========================================
# LINE通知部
# ==========================================

def send_line_message(text: str):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        print("エラー: LINEトークン未設定")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }
    
    res = requests.post(url, headers=headers, json=payload, timeout=15)
    print(f"LINE送信結果: {res.status_code}")

# ==========================================
# メイン実行部
# ==========================================

if __name__ == "__main__":
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    target_date = jst_now.strftime("%Y%m%d")
    date_display = jst_now.strftime("%Y/%m/%d")

    print(f"=== {date_display} デュアルスクリーニング開始 ===")
    
    tsuchan_engine = TsuChanEngine()
    solid_engine = SolidEscapeEngine()

    races = fetch_target_races(target_date)
    print(f"取得レース数: {len(races)} 件")

    tsuchan_bets = []
    solid_bets = []

    for r in races:
        # つーちゃん式 (9〜12R)
        if r.race_no >= 9:
            is_go, _, keyman, conf = tsuchan_engine.evaluate_race(r)
            if is_go and keyman:
                tsuchan_bets.append(tsuchan_engine.generate_bets(r, keyman, conf))

        # 堅実イン逃げ式 (全レース対象)
        is_go_s, _, conf_s = solid_engine.evaluate_race(r)
        if is_go_s:
            solid_bets.append(solid_engine.generate_bets(r, conf_s))

    # LINE通知メッセージ組み立て
    msg = f"🚤【ボートレース厳選配信】\n📅 {date_display}\n"

    # つーちゃん式
    msg += f"\n━━━━━━━━━━━━\n◆ つーちゃん式（{len(tsuchan_bets)}件）\n━━━━━━━━━━━━\n"
    if not tsuchan_bets:
        msg += "本日の該当レースなし（見送り推奨）\n"
    else:
        for idx, item in enumerate(tsuchan_bets, 1):
            msg += f"\n【{idx}】{item['レース']}\n"
            msg += f"◎ {item['本命◎']} / ◯ {item['対抗◯']}\n"
            msg += f"自信度: {item['自信度']} / 投資: {item['合計投資額']}\n"
            for b in item["買い目内訳"]:
                msg += f"・{b['券種']} {b['買い目']} : {b['金額']}円\n"

    # 堅実イン逃げ式
    msg += f"\n━━━━━━━━━━━━\n◆ 堅実イン逃げ式(1-234-234)（{len(solid_bets)}件）\n━━━━━━━━━━━━\n"
    if not solid_bets:
        msg += "本日の該当レースなし（見送り推奨）\n"
    else:
        for idx, item in enumerate(solid_bets, 1):
            msg += f"\n【{idx}】{item['レース']}\n"
            msg += f"◎ {item['本命◎']}\n"
            msg += f"切 {item['切×']}\n"
            msg += f"自信度: {item['自信度']} / 投資: {item['合計投資額']}\n"
            for b in item["買い目内訳"]:
                msg += f"・{b['買い目']} : {b['金額']}円\n"

    send_line_message(msg)
