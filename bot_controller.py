import os
import re
import logging
from typing import Tuple, Optional
import engine_a
import engine_b

logger = logging.getLogger(__name__)

def parse_race_input(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    ユーザーの入力（例：'大村10' または '大村10R'）から会場名とレース番号を抽出
    """
    places = [
        "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
        "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
        "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
        "下関", "若松", "芦屋", "福岡", "唐津", "大村"
    ]
    pattern = r'(' + '|'.join(places) + r')'
    place_match = re.search(pattern, user_text)

    target_text = user_text
    if place_match:
        target_text = user_text.replace(place_match.group(1), "")

    race_match = re.search(r'(1[0-2]|[1-9])', target_text)

    jcd = place_match.group(1) if place_match else None
    rno = race_match.group(1) if race_match else None

    return jcd, rno


def run_mode_2_post_exhibition(user_text: str) -> str:
    """
    LINEからの手動合図（例：大村10）を受け取り、直前展示データを加味した予想を出力
    """
    jcd, rno = parse_race_input(user_text)
    if not jcd or not rno:
        return "エラー: 会場名またはレース番号が正しく認識できませんでした。（例: 大村12）"

    try:
        # Engine A: データ取得
        data = engine_a.get_race_data(jcd, rno)
        if not data:
            return f"エラー: {jcd} {rno}R のデータを取得できませんでした。"

        # Engine B: 予測と買い目算出（10点・2400円配分）
        result_text = engine_b.calculate_prediction(data)

        # 返信メッセージの作成
        reply_message = f"🚤 【{jcd} {rno}R 最終予想】 🚤\n\n"
        reply_message += result_text
        return reply_message

    except Exception as e:
        logger.error(f"手動予想処理エラー: {e}")
        return f"エラーが発生しました: {e}"


def run_morning_job() -> str:
    """
    毎朝8時の自動タイマー実行処理
    Engine Aで当日候補レースを抽出し、Engine Bでメッセージを成型
    """
    try:
        candidates = engine_a.get_daily_candidates()
        morning_message = engine_b.format_morning_candidates(candidates)
        return morning_message
    except Exception as e:
        logger.error(f"朝のジョブ実行エラー: {e}")
        return f"朝の自動配信処理中にエラーが発生しました: {e}"
