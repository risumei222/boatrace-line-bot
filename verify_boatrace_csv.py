"""
BoatraceCSV 第5段階：当日データ公開時刻の実測 & 公式突合スクリプト
対象日: 2026年11月11日
※ 本番Bot・LINE通知・予想エンジンには一切干渉しません。
"""

import io
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VerificationScript/5.0"
}

TARGET_DATE = "2026/11/11"

CSV_TYPES = [
    ("title", "レースタイトル・開催一覧"),
    ("race_cards", "出走表詳細"),
    ("recent_national", "全国近況5節"),
    ("motor_stats", "モーター成績")
]

REQUIRED_17 = [
    "登録番号", "選手名", "級別",
    "全国勝率", "全国2連対率", "全国3連対率",
    "当地勝率", "当地2連対率", "当地3連対率",
    "全国平均ST", "F本数", "L本数",
    "モーター番号", "モーター2連対率", "モーター3連対率",
    "ボート番号", "ボート2連対率", "ボート3連対率"
]


def test_20261111():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    now_utc = datetime.now(timezone.utc)

    print("=" * 65)
    print(f"【BoatraceCSV 11/11公開実測】")
    print(f"・JST実行日時: {now_jst.strftime('%Y-%m-%d %H:%M:%S JST')}")
    print(f"・UTC実行日時: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 65)

    data_store = {}

    for c_type, desc in CSV_TYPES:
        url = f"https://boatracecsv.github.io/data/programs/{c_type}/{TARGET_DATE}.csv"
        print(f"\n■ {c_type} ({desc})")
        print(f"・URL: {url}")

        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as res:
                raw = res.read()
                status = res.status
                lm = res.headers.get("Last-Modified")
                etag = res.headers.get("ETag")
                size = len(raw)

                print(f"・HTTPステータス: {status}")
                print(f"・ファイルサイズ: {size:,} bytes")
                print(f"・Last-Modified: {lm}")
                print(f"・ETag: {etag}")

                if size == 0:
                    print("・判定: EMPTY_FILE (空ファイル)")
                    continue

                df = None
                for enc in ["utf-8", "cp932", "shift_jis"]:
                    try:
                        df = pd.read_csv(io.StringIO(raw.decode(enc)))
                        break
                    except Exception:
                        continue

                if df is None:
                    print("・判定: PARSE_FAILED (パース失敗)")
                    continue

                row_cnt = len(df)
                col_cnt = len(df.columns)
                print(f"・CSV行数: {row_cnt} 行 / 列数: {col_cnt} 列")

                # レース場数・コード数
                stadium_col = next((c for c in ["レース場コード", "場コード", "場名"] if c in df.columns), None)
                rc_col = next((c for c in ["レースコード", "race_code"] if c in df.columns), None)

                st_cnt = df[stadium_col].nunique() if stadium_col else 0
                rc_cnt = df[rc_col].nunique() if rc_col else 0

                print(f"・レース場数: {st_cnt} 場")
                print(f"・レースコード数: {rc_cnt} レース")
                print("・判定: HTTP 200 (取得成功)")

                data_store[c_type] = df

        except urllib.error.HTTPError as e:
            print(f"・HTTPステータス: {e.code}")
            print(f"・判定: HTTP {e.code} (未公開候補)")
        except Exception as e:
            print(f"・通信エラー: {e}")
            print("・判定: FETCH_FAILED")

    # 取得成功判定 (title と race_cards の突き合わせ)
    print("\n--------------------------------------------------")
    print("【11/11 取得成功判定】")
    if "title" in data_store and "race_cards" in data_store:
        df_t = data_store["title"]
        df_r = data_store["race_cards"]
        rc_t = set(df_t["レースコード"])
        rc_r = set(df_r["レースコード"])

        if rc_t == rc_r and len(rc_t) > 0:
            print(f"・titleとrace_cardsのレースコード: 完全一致 ({len(rc_t)} レース)")
            # 6艇×17項目チェック
            cols = set(df_r.columns)
            missing = []
            for p in range(1, 7):
                for f in REQUIRED_17:
                    if f"艇{p}_{f}" not in cols:
                        missing.append(f"艇{p}_{f}")

            if not missing:
                print("・6艇分の必須17項目: すべて完全一致で存在")
                print("★【総合判定】: 11/11データ 完全取得成功 (VALIDATED_WITH_RACES)")
            else:
                print(f"・必須列不足: {missing[:5]}...")
        else:
            print(f"・レースコード不一致: title {len(rc_t)} 件 / race_cards {len(rc_r)} 件")
    else:
        print("★【総合判定】: まだ全データが公開されていません (未公開)")


def inspect_toda_1r():
    """11/9 戸田1Rの出走表データを抽出して公式照合用に表示"""
    print("\n" + "=" * 65)
    print("【公式照合用: 2026年11月9日 戸田1R 実データ抽出】")
    print("=" * 65)

    url = "https://boatracecsv.github.io/data/programs/race_cards/2026/11/09.csv"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as res:
            df = pd.read_csv(io.StringIO(res.read().decode("utf-8")))
            toda_1r = df[df["レースコード"] == 202611090201]

            if len(toda_1r) == 0:
                print("戸田1Rが見つかりません。")
                return

            row = toda_1r.iloc[0]
            print(f"レース日: {row.get('レース日')} / 場: {row.get('レース場コード')} (戸田) / レース: {row.get('レース回')}")
            print("\n| 艇 | 登番 | 選手名 | 級別 | 全国勝率 | 2連率 | 当地勝率 | 平均ST | モーター | モータ2連 | ボート |")
            print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for p in range(1, 7):
                print(f"| {p} | {row.get(f'艇{p}_登録番号')} | {row.get(f'艇{p}_選手名')} | {row.get(f'艇{p}_級別')} | "
                      f"{row.get(f'艇{p}_全国勝率')} | {row.get(f'艇{p}_全国2連対率')} | {row.get(f'艇{p}_当地勝率')} | "
                      f"{row.get(f'艇{p}_全国平均ST')} | {row.get(f'艇{p}_モーター番号')} | {row.get(f'艇{p}_モーター2連対率')} | "
                      f"{row.get(f'艇{p}_ボート番号')} |")
    except Exception as e:
        print(f"戸田1R抽出エラー: {e}")


def main():
    test_20261111()
    inspect_toda_1r()


if __name__ == "__main__":
    main()
