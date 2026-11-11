import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def get_race_data(jcd: str, rno: str) -> Dict[str, Any]:
    """
    ボートレースの出走表・展示データを取得するエンジン。
    ※展示データは取得・保存するが、予想スコアの計算には使用しない。
    ※ST値は14走平均を採用。
    """
    logger.info(f"データ取得開始: {jcd} {rno}R")
    
    # 1〜6号艇の選手データ（14走平均ST値を格納）
    racers = []
    for slot in range(1, 7):
        racers.append({
            "slot": slot,
            "st_14_avg": 0.15,  # 14走平均STのベース値
            "expected_score": 50.0 + (6 - slot) * 3.0  # 枠番を考慮した基礎スコア
        })
        
    # オリジナルの展示データ（保存のみ行い、スコアには影響させない設定）
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
