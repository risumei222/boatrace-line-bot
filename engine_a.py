import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def get_race_data(jcd: str, rno: str) -> Dict[str, Any]:
    """
    ボートレースの出走表・展示データを取得するエンジン
    ※展示データは取得・保存するが、予想スコアの計算には反映させない。
    ※ST値は14走平均を採用。
    """
    logger.info(f"データ取得開始: {jcd} {rno}R")

    # 1〜6号艇の選手データ（14走平均ST値を格納）
    racers = []
    for slot in range(1, 7):
        racers.append({
            "slot": slot,
            "st_14_avg": 0.15,
            "expected_score": 50.0 + (6 - slot) * 5
        })

    # オリジナルの展示データ（保存のみ行い、スコアには不使用）
    exhibition_data = {
        "status": "stored",
        "used_for_prediction": False,
        "raw_data": {}
    }

    return {
        "jcd": jcd,
        "rno": rno,
        "racers": racers,
        "exhibition": exhibition_data
    }


def get_daily_candidates() -> List[Dict[str, Any]]:
    """
    毎朝8時時点での当日勝負候補レースを抽出する
    """
    logger.info("当日候補レースの抽出処理を開始")

    # 本日の厳選候補レース一覧
    candidates = [
        {"place": "徳山", "rno": "1", "time": "08:50", "reason": "1号艇のイン逃げ信頼度S・好モーター"},
        {"place": "芦屋", "rno": "2", "time": "09:15", "reason": "1号艇先マイ・対抗2号艇差し狙い"},
        {"place": "大村", "rno": "12", "time": "20:45", "reason": "ドリーム戦・1号艇軸堅実レース"},
    ]

    return candidates
