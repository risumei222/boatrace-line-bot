import os
import re
import sys
import glob
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

for pkg in ["pandas"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import pandas as pd

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
}

TARGET_COMBOS = {"1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3"}


def install_system_dependencies():
    """LZH解凍用コマンド(unar)の確認とインストール"""
    if shutil.which("unar") is None and shutil.which("lha") is None:
        try:
            print("[INFO] unar をインストール中...")
            subprocess.run(["sudo", "apt-get", "update", "-y"], check=False)
            subprocess.run(["sudo", "apt-get", "install", "-y", "unar"], check=False)
        except Exception as e:
            print(f"[WARN] apt-get 実行スキップ: {e}")


def send_line_message(text: str):
    """LINE Messaging API による結果送信"""
    if not (LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID):
        print("[INFO] LINE認証情報が未設定のため送信スキップ")
        return

    import json
    url = "https://api.line.me/v2/bot/message/push"
    payload = json.dumps({
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text[:4000]}]
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            print(f"[INFO] LINE送信成功 (Status: {res.status})")
    except Exception as e:
        print(f"[ERROR] LINE送信失敗: {e}")


def download_file(url: str, save_path: str) -> bool:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as res:
            if res.status == 200:
                with open(save_path, "wb") as f:
                    f.write(res.read())
                return True
    except Exception as e:
        print(f"[DOWNLOAD FAIL] {url} -> {e}")
    return False


def extract_lzh(archive_path: str, extract_dir: str) -> bool:
    cmd = None
    if shutil.which("unar"):
        cmd = ["unar", "-o", extract_dir, archive_path]
    elif shutil.which("lha"):
        cmd = ["lha", "x", f"-w={extract_dir}", archive_path]

    if not cmd:
        return False

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def parse_b_file(filepath: str) -> Dict[str, Dict]:
    races = {}
    current_jcd = None
    current_rno = None

    encodings = ["cp932", "shift_jis", "euc-jp", "utf-8"]
    lines = []
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                lines = f.readlines()
            break
        except Exception:
            continue

    if not lines:
        return {}

    for line in lines:
        m_race = re.search(r"(\d{2})#\s*(\d{1,2})R", line)
        if m_race:
            current_jcd = int(m_race.group(1))
            current_rno = int(m_race.group(2))
            continue

        m_racer = re.match(r"^\s*([1-6])\s+(\d{4})\s*(\S+)\s+(A1|A2|B1|B2)\s+([0-9\.]+)", line)
        if m_racer and current_jcd and current_rno:
            pit = int(m_racer.group(1))
            rank = m_racer.group(4)
            win_rate = float(m_racer.group(5))

            race_key = f"{current_jcd:02d}_{current_rno:02d}"
            if race_key not in races:
                races[race_key] = {"jcd": current_jcd, "rno": current_rno, "racers": {}}

            races[race_key]["racers"][pit] = {
                "rank": rank,
                "win": win_rate
            }

    return races


def parse_k_file(filepath: str) -> Dict[str, Dict]:
    results = {}
    current_jcd = None
    current_rno = None

    encodings = ["cp932", "shift_jis", "euc-jp", "utf-8"]
    lines = []
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                lines = f.readlines()
            break
        except Exception:
            continue

    if not lines:
        return {}

    for line in lines:
        m_race = re.search(r"(\d{2})#\s*(\d{1,2})R", line)
        if m_race:
            current_jcd = int(m_race.group(1))
            current_rno = int(m_race.group(2))
            continue

        if "3連単" in line or "３連単" in line:
            m_tri = re.search(r"([1-6])\s*[-–=]\s*([1-6])\s*[-–=]\s*([1-6])\s+([0-9,]+)", line)
            if m_tri and current_jcd and current_rno:
                combo = f"{m_tri.group(1)}-{m_tri.group(2)}-{m_tri.group(3)}"
                payout = int(m_tri.group(4).replace(",", ""))
                race_key = f"{current_jcd:02d}_{current_rno:02d}"
                results[race_key] = {
                    "combo": combo,
                    "payout": payout
                }

    return results


def run_pipeline(target_date: str):
    install_system_dependencies()

    yy = target_date[2:4]
    mmdd = target_date[4:8]
    yy_mmdd = f"{yy}{mmdd}"
    yyyymm = target_date[0:6]

    report_lines = [f"📋【データ取得検証・バックテストレポート: {target_date}】\n"]

    with tempfile.TemporaryDirectory() as tmpdir:
        b_lzh = os.path.join(tmpdir, f"b{yy_mmdd}.lzh")
        k_lzh = os.path.join(tmpdir, f"k{yy_mmdd}.lzh")

        url_b = f"http://www1.mbrace.or.jp/od2/B/{yyyymm}/b{yy_mmdd}.lzh"
        url_k = f"http://www1.mbrace.or.jp/od2/K/{yyyymm}/k{yy_mmdd}.lzh"

        print(f"[INFO] ダウンロード試行: {url_b}")
        success_b = download_file(url_b, b_lzh)

        print(f"[INFO] ダウンロード試行: {url_k}")
        success_k = download_file(url_k, k_lzh)

        report_lines.append(f"1. ファイル取得ステータス:")
        report_lines.append(f"・出走表 (Bファイル): {'取得成功' if success_b else '取得失敗 (UNKNOWN)'}")
        report_lines.append(f"・結果表 (Kファイル): {'取得成功' if success_k else '取得失敗 (UNKNOWN)'}\n")

        if not (success_b and success_k):
            report_lines.append("❌ 公式LZHファイルの直接取得に失敗しました。")
            report_lines.append("海外IP遮断のため、別ルート（BoatraceCSVリポジトリ等）への切り替えが必要です。")
            final_report = "\n".join(report_lines)
            print(final_report)
            send_line_message(final_report)
            return

        extract_dir_b = os.path.join(tmpdir, "extract_b")
        extract_dir_k = os.path.join(tmpdir, "extract_k")
        os.makedirs(extract_dir_b, exist_ok=True)
        os.makedirs(extract_dir_k, exist_ok=True)

        ext_b = extract_lzh(b_lzh, extract_dir_b)
        ext_k = extract_lzh(k_lzh, extract_dir_k)

        if not (ext_b and ext_k):
            report_lines.append("❌ アーカイブ解凍に失敗しました (UNKNOWN)。")
            send_line_message("\n".join(report_lines))
            return

        b_files = glob.glob(os.path.join(extract_dir_b, "**", "*.TXT"), recursive=True) + glob.glob(os.path.join(extract_dir_b, "**", "*.txt"), recursive=True)
        k_files = glob.glob(os.path.join(extract_dir_k, "**", "*.TXT"), recursive=True) + glob.glob(os.path.join(extract_dir_k, "**", "*.txt"), recursive=True)

        if not b_files or not k_files:
            report_lines.append("❌ 解凍後にテキストが見つかりませんでした。")
            send_line_message("\n".join(report_lines))
            return

        b_data = parse_b_file(b_files[0])
        k_data = parse_k_file(k_files[0])

        records = []
        unknown_count = 0

        for r_key, b_info in b_data.items():
            k_info = k_data.get(r_key)
            racers = b_info.get("racers", {})

            if len(racers) < 6 or not k_info:
                unknown_count += 1
                records.append({
                    "race_key": r_key,
                    "status": "UNKNOWN",
                    "r1_win": None,
                    "diff_r2": None,
                    "max_outer": None,
                    "combo": k_info["combo"] if k_info else None,
                    "payout": k_info["payout"] if k_info else 0
                })
                continue

            r1_win = racers[1]["win"]
            r2_win = racers[2]["win"]
            r5_win = racers[5]["win"]
            r6_win = racers[6]["win"]

            diff = round(r1_win - r2_win, 2)
            max_outer = max(r5_win, r6_win)

            # 検証フィルター（1号艇勝率6.50以上、2号艇差+1.00以上、外枠5.50以下）
            pass_condition = (r1_win >= 6.50 and diff >= 1.00 and max_outer <= 5.50)
            status = "PASS" if pass_condition else "STOP"

            records.append({
                "race_key": r_key,
                "status": status,
                "r1_win": r1_win,
                "diff_r2": diff,
                "max_outer": max_outer,
                "combo": k_info["combo"],
                "payout": k_info["payout"]
            })

        df = pd.DataFrame(records)

        total_pop = len(df)
        pass_df = df[df["status"] == "PASS"]
        stop_df = df[df["status"] == "STOP"]
        unk_df = df[df["status"] == "UNKNOWN"]

        invest_per_race = 600
        total_bets = len(pass_df)
        total_invest = total_bets * invest_per_race

        hits = 0
        total_return = 0

        for _, row in pass_df.iterrows():
            if row["combo"] in TARGET_COMBOS:
                hits += 1
                total_return += row["payout"]

        hit_rate = (hits / total_bets * 100) if total_bets > 0 else 0.0
        recovery_rate = (total_return / total_invest * 100) if total_invest > 0 else 0.0
        profit = total_return - total_invest

        report_lines.append(f"2. データ突合結果:")
        report_lines.append(f"・母集団全レース数: {total_pop} レース")
        report_lines.append(f"・正常突合: {len(pass_df) + len(stop_df)} レース")
        report_lines.append(f"・欠損 (UNKNOWN): {len(unk_df)} レース\n")

        report_lines.append(f"3. バックテスト集計 (母集団全レース対象):")
        report_lines.append(f"・購入対象 (PASS): {total_bets} 件")
        report_lines.append(f"・見送り (STOP): {len(stop_df)} 件")
        report_lines.append(f"・的中数: {hits} 件")
        report_lines.append(f"・的中率: {hit_rate:.1f}%")
        report_lines.append(f"・総投資額: {total_invest:,} 円")
        report_lines.append(f"・総払戻額: {total_return:,} 円")
        report_lines.append(f"・純収支: {profit:+,} 円")
        report_lines.append(f"・回収率: {recovery_rate:.1f}%\n")

        all_hits = df[df["combo"].isin(TARGET_COMBOS)]
        report_lines.append(f"4. 1-234-234 決着の全体出現:")
        report_lines.append(f"・当日の全出現件数: {len(all_hits)} / {total_pop} ({len(all_hits)/max(total_pop, 1)*100:.1f}%)")

        final_report = "\n".join(report_lines)
        print(final_report)
        send_line_message(final_report)


if __name__ == "__main__":
    run_pipeline("20261109")
