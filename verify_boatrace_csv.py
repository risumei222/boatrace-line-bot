"""
BoatraceCSV 第2段階 独立検証スクリプト
対象: 2026年11月09日 (過去日) / 2026年11月10日 (当日)
※ 本番Bot・LINE通知・予想ロジックとは完全に分離されています。
"""

import io
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
import pandas as pd

TARGET_DATES = [
    {"label": "過去日", "year": "2026", "month": "11", "day": "09", "date_str": "2026/11/09", "yymmdd": "261109"},
    {"label": "当日",   "year": "2026", "month": "11", "day": "10", "date_str": "2026/11/10", "yymmdd": "261110"}
]

CSV_TYPES = [
    ("title", "レースタイトル・開催一覧"),
    ("race_cards", "出走表詳細"),
    ("recent_national", "全国近況5節"),
    ("motor_stats", "モーター成績")
]

REQUIRED_17_FIELDS = [
    "登録番号", "選手名", "級別",
    "全国勝率", "全国2連対率", "全国3連対率",
    "当地勝率", "当地2連対率", "当地3連対率",
    "全国平均ST", "F本数", "L本数",
    "モーター番号", "モーター2連対率", "モーター3連対率",
    "ボート番号", "ボート2連対率", "ボート3連対率"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VerificationScript/2.0"
}


def test_mbrace_patterns(yymmdd: str, date_str: str):
    """mbraceのURL命名パターンを複数検査"""
    print(f"\n==================================================")
    print(f"【mbrace Bファイル 命名規則・接続検査: {date_str}】")
    print(f"==================================================")

    yymm = yymmdd[:4]
    patterns = [
        f"http://www1.mbrace.or.jp/od2/B/20{yymm}/b{yymmdd}.lzh",
        f"http://www1.mbrace.or.jp/od2/B/20{yymm}/B{yymmdd}.lzh",
        f"http://www1.mbrace.or.jp/od2/B/{yymm}/b{yymmdd}.lzh",
        f"http://www1.mbrace.or.jp/od2/B/20{yymm}/b20{yymmdd}.lzh",
        f"https://www.boatrace.jp/owpc/pc/extra/data/download.html"
    ]

    for url in patterns:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as res:
                size = len(res.read())
                print(f"・[200 OK] {url} (取得サイズ: {size:,} B)")
        except urllib.error.HTTPError as e:
            print(f"・[HTTP {e.code}] {url}")
        except Exception as e:
            print(f"・[接続遮断/エラー] {url} -> {e}")


def inspect_csv_content(csv_type: str, df: pd.DataFrame):
    """取得成功したCSVの構造・項目を詳細解析"""
    print(f"\n--- 詳細解析: {csv_type} ---")
    print(f"・全データ行数: {len(df)} 行")
    print(f"・全列数: {len(df.columns)} 列")
    print(f"・カラム一覧: {list(df.columns)}")

    # レース場数・レースコード検出
    rc_col = next((c for c in ["レースコード", "race_code", "race_id", "RACE_CODE"] if c in df.columns), None)
    stadium_col = next((c for c in ["場コード", "場名", "stadium", "place", "場"] if c in df.columns), None)
    boat_col = next((c for c in ["艇番", "boat_number", "pit_number", "枠番", "艇"] if c in df.columns), None)

    if stadium_col:
        print(f"・検出レース場数: {df[stadium_col].nunique()} 場")
    if rc_col:
        total_races = df[rc_col].nunique()
        print(f"・ユニークレース数: {total_races} レース")
        print(f"・レースコード重複行数: {len(df) - total_races} 行")

        # 6艇の整合性
        if boat_col:
            groups = df.groupby(rc_col)
            complete_6 = sum(1 for _, g in groups if len(g) == 6)
            print(f"・6艇揃っているレース数: {complete_6} / {total_races} レース")

    # 先頭2行サンプル
    print(f"・先頭1行データサンプル:\n{df.head(1).to_dict(orient='records')}")

    # 出走表(race_cards)の場合、17項目の照合
    if csv_type == "race_cards":
        print(f"\n【出走表 必須17項目の照合結果】")
        present = set(df.columns)
        missing = [f for f in REQUIRED_17_FIELDS if f not in present]
        print(f"・不足カラム: {missing if missing else 'なし（17項目すべて一致）'}")

        print("\n| カラム名 | 存在 | 値あり件数 | 欠損件数 | 充足率 |")
        print("| :--- | :---: | :---: | :---: | :---: |")
        for f in REQUIRED_17_FIELDS:
            if f in present:
                valid = int(df[f].notna().sum())
                nulls = int(df[f].isna().sum())
                rate = round(valid / len(df) * 100, 1) if len(df) > 0 else 0.0
                print(f"| {f} | ○ | {valid} | {nulls} | {rate}% |")
            else:
                print(f"| {f} | × (カラム欠損) | 0 | {len(df)} | 0.0% |")


def test_boatrace_csv_date(target: dict):
    """特定日付のBoatraceCSV 4種類を取得・検証"""
    d_str = target["date_str"]
    lbl = target["label"]
    print(f"\n==================================================")
    print(f"【BoatraceCSV 取得検証: {lbl} ({d_str})】")
    print(f"==================================================")

    for c_type, c_desc in CSV_TYPES:
        url = f"https://boatracecsv.github.io/data/programs/{c_type}/{d_str}.csv"
        print(f"\n■ [{c_type}] {c_desc}")
        print(f"URL: {url}")

        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as res:
                raw = res.read()
                print(f"・HTTPステータス: {res.status}")
                print(f"・実取得バイト数: {len(raw):,} bytes")
                print(f"・Last-Modified: {res.headers.get('Last-Modified')}")
                print(f"・ETag: {res.headers.get('ETag')}")

                if len(raw) == 0:
                    print("・判定: EMPTY_FILE")
                    continue

                df = None
                for enc in ["utf-8", "cp932", "shift_jis"]:
                    try:
                        df = pd.read_csv(io.StringIO(raw.decode(enc)))
                        print(f"・文字コード: {enc}")
                        break
                    except Exception:
                        continue

                if df is None:
                    print("・判定: PARSE_FAILED")
                    continue

                print(f"・判定: VALIDATED_WITH_RACES (取得成功)")
                inspect_csv_content(c_type, df)

        except urllib.error.HTTPError as e:
            print(f"・HTTPステータス: {e.code} (未公開/404)")
            print(f"・判定: HTTP_NON_200 (コード: {e.code})")
        except Exception as e:
            print(f"・通信エラー: {e}")
            print(f"・判定: FETCH_FAILED")


def main():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST")
    print(f"##################################################")
    print(f" BoatraceCSV 第2段階検証実行ログ: {now_jst}")
    print(f"##################################################")

    # 1. 2026/11/09 (過去日) および 2026/11/10 (当日) の検査
    for target in TARGET_DATES:
        test_boatrace_csv_date(target)
        test_mbrace_patterns(target["yymmdd"], target["date_str"])


if __name__ == "__main__":
    main()
