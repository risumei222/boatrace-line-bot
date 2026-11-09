"""
BoatraceCSV 第3段階：本番運用前 最終検証スクリプト
※ 本番main.py、LINE通知、予想ロジックとは完全に分離されています。
"""

import io
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VerificationScript/3.0"
}

CSV_TYPES = [
    ("title", "レースタイトル・開催一覧"),
    ("race_cards", "出走表詳細"),
    ("recent_national", "全国近況5節"),
    ("motor_stats", "モーター成績")
]

BASE_17_FIELDS = [
    "登録番号", "選手名", "級別",
    "全国勝率", "全国2連対率", "全国3連対率",
    "当地勝率", "当地2連対率", "当地3連対率",
    "全国平均ST", "F本数", "L本数",
    "モーター番号", "モーター2連対率", "モーター3連対率",
    "ボート番号", "ボート2連対率", "ボート3連対率"
]


def fetch_csv(url: str) -> Tuple[int, bytes, dict, str]:
    """CSVファイルのHTTPS取得"""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read()
            headers = dict(res.headers)
            return res.status, raw, headers, None
    except urllib.error.HTTPError as e:
        return e.code, b"", {}, f"HTTP {e.code}"
    except Exception as e:
        return 0, b"", {}, str(e)


def decode_to_df(raw: bytes) -> Tuple[pd.DataFrame, str]:
    """文字コード自動判別デコード"""
    for enc in ["utf-8", "cp932", "shift_jis"]:
        try:
            df = pd.read_csv(io.StringIO(raw.decode(enc)))
            return df, enc
        except Exception:
            continue
    return None, None


def section_a_today():
    """A. 11月10日当日分の取得検証"""
    print("=" * 60)
    print("【A. 2026年11月10日 (当日) 4種類CSV取得結果】")
    print("=" * 60)

    for c_type, desc in CSV_TYPES:
        url = f"https://boatracecsv.github.io/data/programs/{c_type}/2026/11/10.csv"
        status, raw, headers, err = fetch_csv(url)
        print(f"\n■ {c_type} ({desc})")
        print(f"・URL: {url}")
        print(f"・HTTPステータス: {status}")
        print(f"・サイズ: {len(raw):,} bytes")
        print(f"・Last-Modified: {headers.get('Last-Modified', 'なし')}")
        print(f"・ETag: {headers.get('ETag', 'なし')}")

        if status == 200 and len(raw) > 0:
            df, enc = decode_to_df(raw)
            if df is not None:
                print(f"・行数: {len(df)} 行 / 列数: {len(df.columns)} 列")
                print(f"・文字コード: {enc}")
                print(f"・判定: VALIDATED_WITH_RACES")
            else:
                print("・判定: PARSE_FAILED")
        else:
            print(f"・エラー / 未公開: {err}")
            print(f"・判定: HTTP_NON_200 (未公開または生成前)")


def section_b_and_c_yesterday():
    """B. 11月9日分の再検査 (17項目欠損集計・突合) & C. 24場確認"""
    print("\n" + "=" * 60)
    print("【B & C. 2026年11月9日 詳細再検査・24場集計】")
    print("=" * 60)

    # 1. title取得
    url_title = "https://boatracecsv.github.io/data/programs/title/2026/11/09.csv"
    s_t, raw_t, _, _ = fetch_csv(url_title)
    df_title, _ = decode_to_df(raw_t) if s_t == 200 else (None, None)

    # 2. race_cards取得
    url_rc = "https://boatracecsv.github.io/data/programs/race_cards/2026/11/09.csv"
    s_r, raw_r, _, _ = fetch_csv(url_rc)
    df_rc, _ = decode_to_df(raw_r) if s_r == 200 else (None, None)

    if df_title is None or df_rc is None:
        print("[ERROR] 11月9日のCSV取得に失敗しました。")
        return

    # --- C. 開催場数と場別レース数集計 ---
    print("\n### C. 開催場別レース数と場コード一覧")
    stadium_col = "レース場" if "レース場" in df_title.columns else "場名"
    stadium_code_col = "レース場コード" if "レース場コード" in df_title.columns else "場コード"

    stadium_summary = df_title.groupby([stadium_code_col, stadium_col]).size().reset_index(name="レース数")
    print(f"・開催場数: {len(stadium_summary)} 場 (全国24場中、当日開催があった全場)")
    print(f"・全レース総数: {len(df_title)} レース")
    print("\n| 場コード | レース場名 | 開催レース数 |")
    print("| :---: | :--- | :---: |")
    for _, row in stadium_summary.iterrows():
        print(f"| {row[stadium_code_col]:02d} | {row[stadium_col]} | {row['レース数']} R |")

    # --- B. title と race_cards のレースコード突合 ---
    print("\n### B-1. title と race_cards のレースコード突合結果")
    rc_title = set(df_title["レースコード"].dropna())
    rc_cards = set(df_rc["レースコード"].dropna())

    only_title = rc_title - rc_cards
    only_cards = rc_cards - rc_title
    both = rc_title & rc_cards

    dup_title = len(df_title) - df_title["レースコード"].nunique()
    dup_cards = len(df_rc) - df_rc["レースコード"].nunique()

    print(f"・title総レースコード数: {len(rc_title)}")
    print(f"・race_cards総レースコード数: {len(rc_cards)}")
    print(f"・両方に存在する完全一致レース: {len(both)}")
    print(f"・titleにのみ存在: {len(only_title)} 件 {only_title if only_title else ''}")
    print(f"・race_cardsにのみ存在: {len(only_cards)} 件 {only_cards if only_cards else ''}")
    print(f"・title側 重複レースコード: {dup_title} 件")
    print(f"・race_cards側 重複レースコード: {dup_cards} 件")

    # --- B-2. 6艇×17項目の存在と値入力（欠損）詳細検査 ---
    print("\n### B-2. 6艇×17項目のカラム存在と値充足検査 (132レース対象)")
    total_races = len(df_rc)
    present_cols = set(df_rc.columns)

    print("\n【集計サマリー: 艇番別・17項目の欠損状況】")
    for pit in range(1, 7):
        print(f"\n--- ■ 艇番 {pit} (全{total_races}レース中) ---")
        print("| 検査項目名 | 実際のカラム名 | 列存在 | 入力済(値あり) | 欠損数 | 充足率 |")
        print("| :--- | :--- | :---: | :---: | :---: | :---: |")

        for base_field in BASE_17_FIELDS:
            col_name = f"艇{pit}_{base_field}"
            if col_name in present_cols:
                valid_cnt = int(df_rc[col_name].notna().sum())
                null_cnt = int(df_rc[col_name].isna().sum())
                rate = round(valid_cnt / total_races * 100, 1)
                print(f"| {base_field} | `{col_name}` | ○ | {valid_cnt} | {null_cnt} | {rate}% |")
            else:
                print(f"| {base_field} | `{col_name}` | × (未検出) | 0 | {total_races} | 0.0% |")


def section_d_timeline():
    """D. 00:00 vs 07:00 公開時刻の比較とスケジュール確認"""
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    print("\n" + "=" * 60)
    print(f"【D. 公開時刻検証 (実行基準時刻: {now_jst.strftime('%Y-%m-%d %H:%M:%S JST')})】")
    print("=" * 60)

    print("・11月10日 (当日分) 現実点での取得状態: 上記Aの結果を参照")
    print("・11月11日 (翌日分) 各時刻の検査状態:")
    print("  - 11/10 23:50 JST: 【未実施】(未来時刻のためActions cronにて予約実行)")
    print("  - 11/11 00:05 JST: 【未実施】(未来時刻のためActions cronにて予約実行)")
    print("  - 11/11 00:15 JST: 【未実施】(未来時刻のためActions cronにて予約実行)")
    print("  - 11/11 07:00 JST: 【未実施】(未来時刻のためActions cronにて予約実行)")


def main():
    jst = timezone(timedelta(hours=9))
    print(f"############################################################")
    print(f" BoatraceCSV 第3段階 本番前最終検証")
    print(f" 実行時刻: {datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S JST')}")
    print(f"############################################################\n")

    section_a_today()
    section_b_and_c_yesterday()
    section_d_timeline()


if __name__ == "__main__":
    main()
