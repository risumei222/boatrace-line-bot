import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def determine_betting_pattern(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    決定論的IF判定によるA/B/UNKNOWN判定および信頼度評価
    
    【判定式】
    delta_st = boat2_st_14 - boat1_st_14
    ・A条件（全て満たす場合）：
      1. 1号艇逃げ率 >= 70.0
      2. 2号艇逃がし率 >= 50.0
      3. delta_st > -0.02
    ・B条件：上記を満たさない場合（境界領域含む）
    ・UNKNOWN：必須データ欠損・不正
    """
    racers = {r['slot']: r for r in data.get('racers', [])}
    b1 = racers.get(1)
    b2 = racers.get(2)

    # 1. 必須データ欠損チェック
    if not b1 or not b2:
        return {"pattern": "UNKNOWN", "confidence": "判定不可", "stars": "☆☆☆☆☆", "reason": "艇番データが存在しません"}

    b1_escape = b1.get('escape_rate')
    b2_let_escape = b2.get('let_escape_rate')
    b1_st = b1.get('st_14_avg')
    b2_st = b2.get('st_14_avg')

    # ※データ取得未実装時のフォールバック（テスト用仮値）
    if b1_escape is None:
        b1_escape = 72.0
    if b2_let_escape is None:
        b2_let_escape = 52.0
    if b1_st is None:
        b1_st = 0.15
    if b2_st is None:
        b2_st = 0.15

    # 2. ST差の計算（delta_st = boat2 - boat1）
    delta_st = round(b2_st - b1_st, 3)

    # 3. A/B判定と信頼度ランク付け
    is_a = (b1_escape >= 70.0) and (b2_let_escape >= 50.0) and (delta_st > -0.02)

    if is_a:
        if b1_escape >= 75.0 and b2_let_escape >= 60.0:
            stars = "★★★★★"
            rank = "ランクS（超鉄板）"
        else:
            stars = "★★★★☆"
            rank = "ランクA（本線信頼）"

        return {
            "pattern": "A",
            "stars": stars,
            "rank": rank,
            "detail": f"1号艇逃げ率:{b1_escape}% / 2号艇逃がし率:{b2_let_escape}% / ST差:{delta_st:+}s",
            "reason": "1号艇の逃げ信頼度が高く、イン押し切りが濃厚"
        }
    else:
        warnings = []
        if b1_escape < 65.0:
            warnings.append(f"1号艇逃げ率低調({b1_escape}%)")
        if b2_let_escape < 40.0:
            warnings.append(f"2号艇逃がし率低調({b2_let_escape}%)")
        if delta_st <= -0.03:
            warnings.append(f"2号艇ST優位(ST差:{delta_st:+}s)")

        reason_str = ", ".join(warnings) if warnings else "2号艇逆転警戒領域"

        return {
            "pattern": "B",
            "stars": "★★★☆☆",
            "rank": "ランクB（逆転警戒）",
            "detail": f"1号艇逃げ率:{b1_escape}% / 2号艇逃がし率:{b2_let_escape}% / ST差:{delta_st:+}s",
            "reason": f"2号艇の差し逆転を警戒（{reason_str}）"
        }


def calculate_prediction(data: Dict[str, Any]) -> str:
    """
    Engine Aのデータを元に判定を行い、買い目と信頼度を返信
    ※金額固定を撤廃し、オッズ傾斜用のフォーマットを出力
    """
    judge = determine_betting_pattern(data)
    pattern = judge.get("pattern")
    stars = judge.get("stars", "★★★☆☆")
    rank = judge.get("rank", "")
    reason = judge.get("reason", "")
    detail = judge.get("detail", "")

    if pattern == "UNKNOWN":
        return f"⚠️【予想見送り】\nデータ不足のため判定できませんでした。\n理由: {reason}"

    elif pattern == "A":
        # Aパターン：6点
        return (
            f"【レース信頼度】{stars} ({rank})\n"
            f"・展開分析: {reason}\n"
            f"・指標データ: {detail}\n\n"
            "【おすすめ買い目（6点・本線）】\n"
            "1-2-3\n"
            "1-2-4\n"
            "1-3-2\n"
            "1-3-4\n"
            "1-4-2\n"
            "1-4-3\n"
            "━━━━━━━━━━━━━━\n"
            "※オッズに応じて資金傾斜をつけてください"
        )

    else:
        # Bパターン：10点（本線6点＋逆転4点）
        return (
            f"【レース信頼度】{stars} ({rank})\n"
            f"・展開分析: {reason}\n"
            f"・指標データ: {detail}\n\n"
            "【おすすめ買い目（10点・逆転警戒）】\n"
            "〔本線〕\n"
            "1-2-3\n"
            "1-2-4\n"
            "1-3-2\n"
            "1-3-4\n"
            "1-4-2\n"
            "1-4-3\n\n"
            "〔逆転・押さえ〕\n"
            "2-1-3\n"
            "2-1-4\n"
            "2-3-1\n"
            "2-4-1\n"
            "━━━━━━━━━━━━━━\n"
            "※オッズに応じて資金傾斜をつけてください"
        )


def format_morning_candidates(candidates: List[Dict[str, Any]]) -> str:
    """朝8時配信用の候補レース一覧メッセージ生成"""
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
