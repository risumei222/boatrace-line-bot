import re
from typing import Tuple, Optional
import engine_a
import engine_b

def parse_race_input(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    ユーザーの入力（例: '大村5R'）から、会場名とレース番号を抽出します。
    """
    place_match = re.search(r'(桐生|戸田|江戸川|平和島|多摩川|浜名湖|蒲郡|常滑|津|三国|びわこ|住之江|尼崎|鳴門|丸亀|児島|宮島|徳山|下関|若松|芦屋|福岡|唐津|大村)', user_text)
    race_match = re.search(r'([1-9]|1[0-2])\s*[rRＲｒ]', user_text)
    
    jcd = place_match.group(1) if place_match else None
    rno = race_match.group(1) if race_match else None
    
    return jcd, rno

def run_mode_2_post_exhibition(user_text: str) -> str:
    """
    展示データ取得後（モード2）の処理を実行し、結果のテキストを返します。
    """
    jcd, rno = parse_race_input(user_text)
    if not jcd or not rno:
        return "エラー: 会場名またはレース番号が正しく認識できませんでした。（例: 大村5R）"
        
    try:
        # Engine A: データ取得（展示データは保存するがスコアには使用しない）
        data = engine_a.get_race_data(jcd, rno)
        if not data:
            return f"エラー: {jcd} {rno}R のデータを取得できませんでした。"
            
        # Engine B: 予測と買い目算出（10点・2400円配分、STは14走平均）
        result_text = engine_b.calculate_prediction(data)
        
        # 返信メッセージの作成
        reply_message = f"🚤 【{jcd} {rno}R 予想】 🚤\n\n"
        reply_message += result_text
        return reply_message
        
    except Exception as e:
        return f"予想処理中にエラーが発生しました。\n詳細: {str(e)}"
