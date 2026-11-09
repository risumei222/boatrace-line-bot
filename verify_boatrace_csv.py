"""
BoatraceCSV データ取得・独立検証スクリプト
※ 既存Bot・予想ロジック・LINE通知からは完全に分離されています。
"""

import os
import sys
import io
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
import pandas as pd

# 対象日（検証指定日）
TARGET_YEAR = "2026"
TARGET_MONTH = "11"
TARGET_DAY = "11"
TARGET_DATE_STR = f"{TARGET_YEAR}/{TARGET_MONTH}/{TARGET_DAY}"

# 検査対象URL
TARGET_URLS = {
    "race_cards": f"https://boatracecsv.github.io/data/programs/race_cards/{TARGET_DATE_STR}.csv",
    "title": f"https://boatracecsv.github.io/data/programs/title/{TARGET_DATE_STR}.csv",
    "recent_national": f"https://boatracecsv.github.io/data/programs/recent_national/{TARGET_DATE_STR}.csv",
    "motor_stats": f"https://boatracecsv.github.io/data/programs/motor_stats/{TARGET_DATE_STR}.csv"
}

# 必須検査17項目
REQUIRED_FIELDS = [
    "登録番号", "選手名", "級別",
    "全国勝率", "全国2連対率", "全国3連対率",
    "当地勝率", "当地2連対率", "当地3連対率",
    "全国平均ST", "F本数", "L本数",
    "モーター番号", "モーター2連対率", "モーター3連対率",
    "ボート番号", "ボート2連対率", "ボート3連対率"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VerificationScript/1.0"
}


def test_mbrace_connectivity() -> dict:
    """GitHub Actionsからmbraceへの直接接続性をテスト"""
    test_url = "http://www1.mbrace.or.jp/od2/B/202611/b261111.lzh"
    result = {"url": test_url, "accessible": False, "status": None, "error": None}
    try:
        req = urllib.request.Request(test_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            result["accessible"] = (res.status == 200)
            result["status"] = res.status
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["error"] = f"HTTPError {e.code}"
    except Exception as e:
        result["error"] = str(e)
    return result


def fetch_and_inspect_file(name: str, url: str) -> dict:
    """単一ファイルのHTTPS取得とメタデータ検査"""
    record = {
        "name": name,
        "url": url,
        "http_status": None,
        "success": False,
        "status_code": "FETCH_FAILED",
        "content_length": None,
        "actual_bytes": 0,
        "content_type": None,
        "last_modified": None,
        "etag": None,
        "encoding": None,
        "row_count": 0,
        "col_count": 0,
        "columns": [],
        "head_samples": [],
        "tail_samples": [],
        "raw_df": None,
        "error_message": None
    }

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as res:
            record["http_status"] = res.status
            record["content_type"] = res.headers.get("Content-Type")
            record["content_length"] = res.headers.get("Content-Length")
            record["last_modified"] = res.headers.get("Last-Modified")
            record["etag"] = res.headers.get("ETag")

            if res.status != 200:
                record["status_code"] = "HTTP_NON_200"
                return record

            raw_bytes = res.read()
            record["actual_bytes"] = len(raw_bytes)

            if len(raw_bytes) == 0:
                record["status_code"] = "EMPTY_FILE"
                return record

            # 文字コード判定とデコード
            decoded_text = None
            for enc in ["utf-8", "cp932", "shift_jis", "euc-jp"]:
                try:
                    decoded_text = raw_bytes.decode(enc)
                    record["encoding"] = enc
                    break
                except UnicodeDecodeError:
                    continue

            if decoded_text is None:
                record["status_code"] = "PARSE_FAILED"
                record["error_message"] = "デコード失敗（対応文字コードなし）"
                return record

            # CSV解析
            try:
                df = pd.read_csv(io.StringIO(decoded_text))
            except Exception as e:
                record["status_code"] = "PARSE_FAILED"
                record["error_message"] = f"CSVパース失敗: {e}"
                return record

            record["raw_df"] = df
            record["row_count"] = len(df)
            record["col_count"] = len(df.columns)
            record["columns"] = list(df.columns)
            record["head_samples"] = df.head(3).to_dict(orient="records")
            record["tail_samples"] = df.tail(3).to_dict(orient="records")
            record["success"] = True

    except urllib.error.HTTPError as e:
        record["http_status"] = e.code
        record["status_code"] = "HTTP_NON_200"
        record["error_message"] = f"HTTP Error {e.code}"
    except Exception as e:
        record["status_code"] = "FETCH_FAILED"
        record["error_message"] = str(e)

    return record


def inspect_race_cards(df: pd.DataFrame) -> dict:
    """出走表（race_cards）の必須項目および6艇整合性検査"""
    result = {
        "stadium_count": 0,
        "duplicate_race_codes": 0,
        "total_races": 0,
        "complete_6_boats_races": 0,
        "incomplete_races": 0,
        "field_stats": {},
        "missing_required_columns": [],
        "status_code": "VALIDATED_NO_RACES"
    }

    if df is None or len(df) == 0:
        return result

    # 必須カラムの存在チェック
    present_cols = set(df.columns)
    missing_cols = [f for f in REQUIRED_FIELDS if f not in present_cols]
    result["missing_required_columns"] = missing_cols

    # 各フィールドの「値が存在する件数」と「欠損件数」
    for field in REQUIRED_FIELDS:
        if field in present_cols:
            valid_count = int(df[field].notna().sum())
            null_count = int(df[field].isna().sum())
            result["field_stats"][field] = {
                "exists": True,
                "valid_count": valid_count,
                "null_count": null_count,
                "valid_rate": round(valid_count / len(df) * 100, 2) if len(df) > 0 else 0.0
            }
        else:
            result["field_stats"][field] = {
                "exists": False,
                "valid_count": 0,
                "null_count": len(df),
                "valid_rate": 0.0
            }

    # レースコード・場判定（カラム名推測・検出）
    rc_col = None
    for col in ["レースコード", "race_code", "race_id", "RACE_CODE"]:
        if col in df.columns:
            rc_col = col
            break

    stadium_col = None
    for col in ["場コード", "場名", "stadium", "place"]:
        if col in df.columns:
            stadium_col = col
            break

    boat_col = None
    for col in ["艇番", "boat_number", "pit_number", "枠番"]:
        if col in df.columns:
            boat_col = col
            break

    if stadium_col:
        result["stadium_count"] = int(df[stadium_col].nunique())

    if rc_col:
        race_groups = df.groupby(rc_col)
        result["total_races"] = len(race_groups)
        
        # 6艇揃っているか
        complete_count = 0
        incomplete_count = 0
        for r_code, group in race_groups:
            if len(group) == 6:
                if boat_col and set(group[boat_col].dropna().astype(int)) == {1, 2, 3, 4, 5, 6}:
                    complete_count += 1
                elif not boat_col:
                    complete_count += 1
                else:
                    incomplete_count += 1
            else:
                incomplete_count += 1

        result["complete_6_boats_races"] = complete_count
        result["incomplete_races"] = incomplete_count

    # 総合ステータス
    if missing_cols:
        result["status_code"] = "SCHEMA_MISMATCH"
    elif len(df) == 0:
        result["status_code"] = "VALIDATED_NO_RACES"
    else:
        result["status_code"] = "VALIDATED_WITH_RACES"

    return result


def main():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST")
    print(f"=== BoatraceCSV 独立検証実行: {now_jst} ===")

    # 1. mbrace 接続性テスト
    print("\n[STEP 1] GitHub Actions -> mbrace 直接接続テスト中...")
    mbrace_res = test_mbrace_connectivity()
    print(f"mbrace 接続結果: {mbrace_res}")

    # 2. 4種類のファイル取得
    print("\n[STEP 2] BoatraceCSV 4ファイル取得・解析中...")
    file_results = {}
    for name, url in TARGET_URLS.items():
        print(f"取得中: {name} ({url})")
        res = fetch_and_inspect_file(name, url)
        file_results[name] = res

    # 3. race_cards 詳細検査
    print("\n[STEP 3] race_cards 詳細スキーマ・必須項目検査中...")
    rc_res = file_results.get("race_cards", {})
    rc_detail = inspect_race_cards(rc_res.get("raw_df"))

    # 4. レポート生成
    report_lines = [
        "# BoatraceCSV 独立検証結果レポート",
        f"- 実行時刻: {now_jst}",
        f"- 検証対象日: {TARGET_DATE_STR}",
        "",
        "## 1. mbrace 直接依存性の確認結果",
        f"- 対象URL: `{mbrace_res['url']}`",
        f"- GitHub Actionsからの直接接続可否: {'【可能】' if mbrace_res['accessible'] else '【遮断 / 失敗】'}",
        f"- HTTPステータス: {mbrace_res['status']}",
        f"- エラー詳細: {mbrace_res['error']}",
        "- **アーキテクチャ考察**: BoatraceCSV（GitHub Pages）が正常に取得できる場合、GitHub Actions環境がmbraceへ直接通信する必要は完全に排除されます（HTTPSで静的CSVを取得するのみ）。",
        "",
        "## 2. 4種類のCSVファイル取得結果一覧"
    ]

    for name, res in file_results.items():
        status = res["status_code"]
        report_lines.extend([
            f"### ファイル: {name}",
            f"- URL: `{res['url']}`",
            f"- 判定ステータス: **{status}**",
            f"- HTTPステータス: {res['http_status']}",
            f"- Content-Type: {res['content_type']}",
            f"- Content-Length: {res['content_length']} (実取得バイト数: {res['actual_bytes']:,} B)",
            f"- Last-Modified: {res['last_modified']}",
            f"- ETag: {res['etag']}",
            f"- 文字コード: {res['encoding']}",
            f"- 行数: {res['row_count']} 行 / 列数: {res['col_count']} 列",
            f"- カラム一覧: `{', '.join(res['columns'][:10])}` {'...' if len(res['columns']) > 10 else ''}",
            f"- エラー情報: {res['error_message']}",
            ""
        ])

    report_lines.extend([
        "## 3. 出走表（race_cards）必須17項目検査結果",
        f"- 総合判定: **{rc_detail['status_code']}**",
        f"- 検出レース場数: {rc_detail['stadium_count']} 場",
        f"- 検出全レース数: {rc_detail['total_races']} レース",
        f"- 6艇完全一致レース数: {rc_detail['complete_6_boats_races']} レース",
        f"- 不完全レース数: {rc_detail['incomplete_races']} レース",
        f"- 不足カラム: {rc_detail['missing_required_columns'] if rc_detail['missing_required_columns'] else 'なし（全列存在）'}",
        "",
        "| 項目名 | カラム存在 | 値あり件数 | 欠損件数 | 充足率 |",
        "| :--- | :---: | :---: | :---: | :---: |"
    ])

    for field, stat in rc_detail["field_stats"].items():
        exist_str = "あり" if stat["exists"] else "なし"
        report_lines.append(f"| {field} | {exist_str} | {stat['valid_count']} | {stat['null_count']} | {stat['valid_rate']}% |")

    final_report = "\n".join(report_lines)

    # 成果物の保存
    os.makedirs("verification_output", exist_ok=True)
    with open("verification_output/report.md", "w", encoding="utf-8") as f:
        f.write(final_report)

    print("\n" + "=" * 50)
    print(final_report)
    print("=" * 50)


if __name__ == "__main__":
    main()
