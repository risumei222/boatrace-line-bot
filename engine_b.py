import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# ==========================================
# 変更1: verify_logger のインポート（安全対策）
# ==========================================
try:
    from verify_logger import log_paper_trade
except ImportError:
    log_paper_trade = None


# ==========================================
# 変更2: C/D紙上検証用の補助関数
# ==========================================
def append_cd_paper_section(message: str, data: Dict[str, Any]) -> str:
    """C/Dパターンを購入判断と分離して表示・記録する。"""
    c_tickets = [
        "1-2-5",
        "1-2-6",
        "1-3-5",
        "1-3-6",
        "1-4-5",
        "1-4-6",
    ]
    d_tickets = [
        "1-3-2",
        "1-4-2",
        "1-5-2",
        "1-6-2",
    ]
    paper_section = [
        "",
        "━━━━━━━━━━━━━━",
        "📝【C/D紙上検証・実購入対象外】",
        "",
        "【Cパターン：1-234-56（6点）】",
        *c_tickets,
        "",
        "【Dパターン：1-全-2（4点）】",
        *d_tickets,
        "",
        "※C/Dは検証専用です。購入判断には使用しません。",
        "━━━━━━━━━━━━━━",
    ]
    if log_paper_trade is not None:
        try:
            log_paper_trade(
                race_data=data,
                c_tickets=c_tickets,
                d_tickets=d_tickets,
                race_date=data.get("date"),
                venue=data.get("place"),
                race_no=data.get("rno"),
            )
        except Exception:
            logger.exception(
                "Paper verification logging failed. "
                "Continue LINE response."
            )
    return message + "\n" + "\n".join(paper_section)


def determine_betting_pattern(data: Dict[str, Any]):
    """
    決定論的IF判定によるA/B/UNKNOWN判定および信頼度計算
    ※既存ロジック完全維持（変更なし）
    """
    racers = {r['slot']: r for r in data.get('racers', [])}
    b1 = racers.get(1)
    b2 = racers.get(2)

    # 必須データ欠損チェック
    if not b1 or not b2:
        return "UNKNOWN", "データ欠損", {}

    b1_escape = b1.get('escape_rate')
    b2_let_escape = b2.get('let_escape_rate')
    b1_st = b1.get('st_14_avg', 0.15)
    b2_st = b2.get('st_14_avg', 0.15)

    if b1_escape is None or b2_let_escape is None:
        return "UNKNOWN", "データ欠損", {}

    delta_st = round(b2_st - b1_st, 3)

    if b1_escape >= 70.0 and b2_let_escape >= 50.0 and delta_st > -0.02:
        pattern = "A"
        reason = "1号艇の逃げ信頼度が高く、イン押し切り濃厚"
    else:
        pattern = "B"
        reason = "イン逃げ本線だが2号艇の追走・逆転に警戒"

    stats = {
        "b1_escape": b1_escape,
        "b2_let_escape": b2_let_escape,
        "delta_st": delta_st
    }
    return pattern, reason, stats


def calculate_prediction(data: Dict[str, Any]) -> str:
    """
    レース予想メッセージを生成する
    """
    pattern, reason, stats = determine_betting_pattern(data)
    place = data.get("place", "ボートレース")
    rno = data.get("rno", 1)

    # 1. UNKNOWN の return
    if pattern == "UNKNOWN":
        msg = f"🚤【{place} {rno}R】🚤\n判定：対象外（データ不足）"
        return append_cd_paper_section(msg, data)

    stars = "★★★★☆" if pattern == "A" else "★★★☆☆"
    base_msg = [
        f"🚤【{place} {rno}R 最終予想】🚤\n",
        f"【レース信頼度】{stars} (ランク{pattern})",
        f"・展開分析: {reason}",
        f"・指標: 1逃げ:{stats.get('b1_escape')}% / 2逃がし:{stats.get('b2_let_escape')}% / ST差:{stats.get('delta_st'):+.2f}s\n"
    ]

    # 2. A判定 の return
    if pattern == "A":
        base_msg.extend([
            "【おすすめ買い目（6点・本線）】",
            "1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3",
            "\n※オッズに応じて資金傾斜をつけてください"
        ])
        return append_cd_paper_section("\n".join(base_msg), data)

    # 3. B判定 の return
    base_msg.extend([
        "【おすすめ買い目（10点・本線）】",
        "1-2-3", "1-2-4", "1-3-2", "1-3-4", "1-4-2", "1-4-3",
        "2-1-3", "2-1-4", "2-3-1", "2-4-1",
        "\n※オッズに応じて資金傾斜をつけてください"
    ])
    return append_cd_paper_section("\n".join(base_msg), data)
