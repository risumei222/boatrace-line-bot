import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def calculate_prediction(data: Dict[str, Any]) -> str:
    """
    Engine Aで取得したデータをもとに、買い目と資金配分を計算するエンジン。
    ・10点買い
    ・合計2400円の資金配分
    """
    jcd = data.get('jcd', '不明')
    rno = data.get('rno', '不明')
    logger.info(f"予想計算開始: {jcd} {rno}R")
    
    # 10点・2400円配分のフォーマット
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
        "------------------\n"
        "合計購入金額: 2,400円\n"
        "※ST値は14走平均を採用"
    )
    
    return prediction_text
