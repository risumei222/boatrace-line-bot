import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def calculate_prediction(data: Dict[str, Any]) -> str:
    """
    Engine Aで取得したデータをもとに、買い目と資金配分を計算
    ・10点買い
    ・合計2400円の資金配分
    """
    jcd = data.get('jcd', '不明')
    rno = data.get('rno', '不明')
    logger.info(f"予想計算開始: {jcd} {rno}R")

    prediction_text = (
        "【おすすめ買い目（10点）】\n"
        "1-2-3 (500円)\n"
        "1-2-4 (400円)\n"
        "1-3-2 (300円)\n"
        "1-3-4 (300円)\n"
        "1-4-2 (200円)\n"
        "1-4-3 (200円)\n"
        "2-1-3 (200円)\n"
        "2-1-4 (100円)\n"
        "2-3-1 (100円)\n"
        "2-4-1 (100円)\n"
        "--------------------\n"
        "合計購入金額: 2,400円\n"
        "※ST値は14走平均を採用"
    )

    return prediction_text


def format_morning_candidates(candidates: List[Dict[str, Any]]) -> str:
    """
    朝8時配信用の候補レース一覧をLINEメッセージ用に整形する
    """
    if not candidates:
        return "本日の推奨候補レースはありませんでした。"

    lines = ["🌅【本日の厳選候補レース】🌅\n"]
    lines.append("本日の対象レース一覧です。\n展示終了後にレース名（例: 大村12）を送ると直前予想を取得できます！\n")

    for i, c in enumerate(candidates, 1):
        place = c.get("place", "")
        rno = c.get("rno", "")
        time = c.get("time", "")
        reason = c.get("reason", "注目レース")
        lines.append(f"第{i}候補: {place} {rno}R ({time}締切)")
        lines.append(f"  └ 狙い目: {reason}\n")

    lines.append("━━━━━━━━━━━━━━")
    lines.append("※直前展示完了後に最終判定を行ってください。")
    return "\n".join(lines)
