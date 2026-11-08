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
# 1. つーちゃん舟券ロジック 定義部
# ==========================================

@dataclass
class Racer:
    boat: int          # 艇番 (1-6)
    name: str          # 選手名
    rank: str          # 級別 ('A1', 'A2', 'B1', 'B2')
    win_rate_nat: float  # 全国勝率
    win_rate_loc: float  # 当地勝率

@dataclass
class RaceInfo:
    stadium: str       # 競艇場名 ('住之江', '鳴門', '多摩川' など)
    race_no: int       # レース番号 (1-12)
    race_type: str     # '優勝戦', '準優勝戦', 'ドリーム戦', '女子戦', '一般予選', '企画'
    is_girls: bool     # 女子戦フラグ
    weather_bad: bool  # 安定板・荒天フラグ
    racers: List[Racer]# 1〜6号艇の選手データリスト

class TsuChanEngine:
    """つーちゃん舟券ロジック再現エンジン"""

    def __init__(self, target_budget: Optional[int] = None):
        self.user_budget = target_budget

    def evaluate_race(self, race: RaceInfo) -> Tuple[bool, str, Optional[Racer], str]:
        """
        レース選定（第1フィルター〜枠番別最適化）
        返り値: (勝負可否, 理由/判定名, キーマン, 自信度ランク)
        """
        # 1. 番組の格フィルター
        valid_races = ['優勝戦', '準優勝戦', 'ドリーム戦', '企画']
        if race.race_no < 10 and race.race_type not in valid_races and not (race.is_girls and race.race_no >= 9):
            return False, "平場予選のためスキップ（不確定要素排除）", None, "SKIP"

        # 2. 1号艇（イン逃げ信頼度）フィルター
        r1 = race.racers[0]
        if r1.rank != 'A1' or r1.win_rate_nat < 6.5:
            return False, f"1号艇の逃げ信頼度不足（{r1.rank} / 全国{r1.win_rate_nat}）", None, "SKIP"

        # 3. 外枠（4〜6号艇）からキーマンを抽出
        outer_racers = race.racers[3:6]  # 4, 5, 6号艇
        candidates = [r for r in outer_racers if r.rank == 'A1' or r.win_rate_nat >= 6.5 or r.win_rate_loc >= 7.0]

        if not candidates:
            return False, "外枠に明確な格上キーマン不在", None, "SKIP"

        # 最高勝率の艇をキーマンに指名
        keyman = max(candidates, key=lambda x: (x.win_rate_nat, x.win_rate_loc))

        # 4. キーマン枠番別のスクリーニング最適化（分散・下振れ抑制ルール）
        inner_all_a1 = all(r.rank == 'A1' for r in race.racers[0:3])

        if keyman.boat in [4, 5]:
            confidence = "銀河系の端から端まで％" if (race.race_type in ['優勝戦', 'ドリーム戦'] and r1.win_rate_nat >= 7.8) else "88.6%"
            return True, f"{keyman.boat}号艇キーマン（主力アクセルゾーン）", keyman, confidence

        elif keyman.boat == 6:
            has_b_class_inner = any(r.rank in ['B1', 'B2'] for r in race.racers[1:4])
            if race.is_girls or has_b_class_inner:
                return True, "6号艇キーマン（格差・女子戦GO判定）", keyman, "86.5%"
            
            if inner_all_a1 or race.stadium in ['住之江', '大村', '徳山', '芦屋']:
                return False, f"6号艇キーマン見送り（全員A1級またはイン強水面のため3着壁リスク排除）", keyman, "SKIP"
            
            return True, "6号艇キーマン（慎重判定）", keyman, "68.0%"

        return False, "選定基準外", None, "SKIP"

    def generate_bets(self, race: RaceInfo, keyman: Racer, confidence: str) -> dict:
        """買い目生成＆傾斜配分アルゴリズム"""
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

        # 1. 本線：1 - キーマン = 全 (8点)
        for b in others:
            weight = 0.12 if b in [2, 3] else 0.05
            bet_list.append(('3連単', f"1-{k}-{b}", weight))
            weight_x = 0.18 if b in [2, 3] else 0.06
            bet_list.append(('3連単', f"1-{b}-{k}", weight_x))

        # 2. 逆転・穴：キーマン - 1 = 全 (4点)
        for b in others:
            bet_list.append(('3連単', f"{k}-1-{b}", 0.03))

        # 3. リスクヘッジ：2連単 1-キーマン
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
            "レース": f"{race.stadium}{race.race_no}R ({race.race_type})",
            "本命◎": f"1号艇 {race.racers[0].name}",
            "対抗◯": f"{k}号艇 {keyman.name}",
            "自信度": confidence,
            "合計投資額": f"{calc_total:,}円",
            "買い目内訳": final_bets
        }

# ==========================================
# 2. 公式出走表スクレイピング部
# ==========================================

STADIUM_MAP = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川",
    "06": "浜名湖", "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
}

def fetch_target_races(target_date: str) -> List[RaceInfo]:
    """指定日（YYYYMMDD）の対象レース（9〜12R）出走表を取得"""
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
        for rno in range(9, 13):
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
# 3. LINE通知部
# ==========================================

def send_line_message(text: str):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        print("エラー: LINE_CHANNEL_ACCESS_TOKEN または LINE_USER_ID が未設定です。")
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
# 4. メイン実行部
# ==========================================

if __name__ == "__main__":
    jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    target_date = jst_now.strftime("%Y%m%d")
    date_display = jst_now.strftime("%Y/%m/%d")

    print(f"=== {date_display} つーちゃんロジック自動スクリーニング開始 ===")
    
    engine = TsuChanEngine()
    races = fetch_target_races(target_date)
    print(f"取得レース数: {len(races)} 件")

    selected_bets = []
    for r in races:
        is_go, reason, keyman, confidence = engine.evaluate_race(r)
        if is_go and keyman:
            bet_data = engine.generate_bets(r, keyman, confidence)
            selected_bets.append(bet_data)

    if not selected_bets:
        msg = f"🚤【つーちゃん厳選Bot】\n📅 {date_display}\n\n本日の該当勝負レースはありませんでした。\n（見送り推奨日です）"
    else:
        msg = f"🚤【つーちゃん厳選勝負レース】\n📅 {date_display}\n厳選 {len(selected_bets)} レース選定！\n"
        for idx, item in enumerate(selected_bets, 1):
            msg += f"\n━━━━━━━━━━━━\n"
            msg += f"【{idx}】{item['レース']}\n"
            msg += f"◎ {item['本命◎']}\n"
            msg += f"◯ {item['対抗◯']}\n"
            msg += f"自信度: {item['自信度']}\n"
            msg += f"投資額: {item['合計投資額']}\n"
            msg += "─── 買い目 ───\n"
            for b in item["買い目内訳"]:
                msg += f"・{b['券種']} {b['買い目']} : {b['金額']}円\n"

    send_line_message(msg)
