import re
from typing import Tuple, Optional
import engine_a
import engine_b

def parse_race_input(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    ユーザーの入力（例: '大村10' または '大村10R'）から、会場名とレース番号を抽出します。
    """
    # 競馬場名を抽出
    place_match = re.search(r'(桐生|戸田|江戸川|平和島|多摩川|浜名湖|蒲郡|常滑|津|三国|びわこ|住之江|尼崎|鳴門|丸亀|児島|宮島|徳山|下関|若松|芦屋|福岡|唐津|大村)', user_text)
    
    # レース番号を抽出（「R」がなくても数字だけで反応するように修正）
    race_match = re.search(r'(1[0-2]|[1-9])', user_text)
    
    jcd = place_match.group(1) if place_match else None
    rno = race_match.group(1) if race_match else None
    
    return jcd, rno

def run_mode_2_post_exhibition(user_text: str) -> str:
    """
    LINEからの手動合図（例: 大村10）を受け取り、直前展示データを取得して予想結果を返します。
    """
    jcd, rno = parse_race_input(user_text)
    if not jcd or not rno:
        return "エラー: 会場名またはレース番号が正しく認識できませんでした。（例: 大村10）"
        
    try:
        # Engine A: データ取得（直前展示データを取得・保存）
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
        return f"予想処理中にエラーが発生しました。\n詳細: {str(e)}"

def run_morning_job() -> str:
    """
    朝8時のタイマー（外部トリガー）で実行される処理。
    1-234-234式とリースメイ式の事前条件に合うレースを抽出し、LINEに通知します。
    """
    try:
        # ※エンジン側に朝の全レースチェック用機能がある前提で呼び出します
        if hasattr(engine_a, 'get_morning_candidates'):
            result_text = engine_a.get_morning_candidates()
        else:
            # エンジン側に専用関数がない場合の仮メッセージ（後でロジックを直結可能）
            result_text = "本日の候補レースの抽出処理が完了しました。\n（※現在、朝の抽出エンジンと接続確認中です）"
            
        return f"🌅 【朝の自動候補出し】 🌅\n\n{result_text}"
        
    except Exception as e:
        return f"朝の自動抽出処理中にエラーが発生しました。\n詳細: {str(e)}"

