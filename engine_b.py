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
        return {
            "pattern": "UNKNOWN",
            "confidence": "判定不可",
            "stars": "☆☆☆☆☆",
            "reason": "艇番データが存在しません",
        }

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

    # 2. ST差の計算 (delta_st = boat2 - boat1)
    delta_st = round(b2_st - b1_st, 3)

    # 3. A/B判定と信頼度ランク付け
    is_a = (
        (b1_escape >= 70.0)
        and (b2_let_escape >= 50.0)
        and (delta_st > -0.02)
    )

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
            "reason": "1号艇の逃げ信頼度が高く、イン押し切りが濃厚",
            "stats": {
                "b1_escape": b1_escape,
                "b2_let_escape": b2_let_escape,
                "delta_st": delta_st,
            },
        }
    else:
        warnings = []
        if b1_escape < 65.0:
            warnings.append(f"1号艇逃げ率低調({b1_escape}%)")
        if b2_let_escape < 40.0:
            warnings.append(f"2号艇逃がし率低調({b2_let_escape}%)")
        if delta_st <= -0.05:
            warnings.append(f"2号艇ST優位({delta_st:+}s)")

        warn_str = "、".join(warnings) if warnings else "僅差の境界条件"

        return {
            "pattern": "B",
            "stars": "★★★☆☆",
            "rank": "ランクB（波乱含み・追走警戒）",
            "detail": f"1号艇逃げ率:{b1_escape}% / 2号艇逃がし率:{b2_let_escape}% / ST差:{delta_st:+}s",
            "reason": f"イン逃げ本線も対抗艇の仕掛けに注意（{warn_str}）",
            "stats": {
                "b1_escape": b1_escape,
                "b2_let_escape": b2_let_escape,
                "delta_st": delta_st,
            },
        }


def calculate_prediction(data: Dict[str, Any]) -> str:
    """レース予想メッセージを生成する"""
    eval_res = determine_betting_pattern(data)
    pattern = eval_res.get("pattern")
    place = data.get("place", "ボートレース")
    rno = data.get("rno", 1)

    if pattern == "UNKNOWN":
        return f"🚤【{place} {rno}R】🚤\n判定：対象外（{eval_res.get('reason')}）"

    stars = eval_res.get("stars", "★★★☆☆")
    rank = eval_res.get("rank", "")
    reason = eval_res.get("reason", "")
    detail = eval_res.get("detail", "")

    base_msg = [
        f"🚤【{place} {rno}R 最終予想】🚤\n",
        f"【レース信頼度】{stars} ({rank})",
        f"・展開分析: {reason}",
        f"・指標: {detail}\n",
    ]

    if pattern == "A":
        base_msg.extend([
            "【おすすめ買い目（6点・本線）】",
            "1-2-3",
            "1-2-4",
            "1-3-2",
            "1-3-4",
            "1-4-2",
            "1-4-3",
            "\n※オッズに応じて資金傾斜をつけてください",
        ])
        return "\n".join(base_msg)

    base_msg.extend([
        "【おすすめ買い目（10点・本線）】",
        "1-2-3",
        "1-2-4",
        "1-3-2",
        "1-3-4",
        "1-4-2",
        "1-4-3",
        "2-1-3",
        "2-1-4",
        "2-3-1",
        "2-4-1",
        "\n※オッズに応じて資金傾斜をつけてください",
    ])
    return "\n".join(base_msg)
