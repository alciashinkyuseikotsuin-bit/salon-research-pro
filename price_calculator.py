"""
単価シミュレーションモジュール

目標月商・営業日数・予約枠から「1回あたりの理想単価」を算出する。
この単価をベースに商品設計（松竹梅）を組み立てる。

入力:
- 月の目標売上
- 理想の営業日数（月）
- 理想の1日の予約枠数

出力:
- 1回あたりの理想単価
- 月の総予約枠
- 参考情報（日商目標など）
"""

from typing import Dict
import math


def calculate_pricing(
    monthly_target: int,
    working_days: int = 22,
    slots_per_day: int = 6,
) -> Dict:
    """
    目標売上から1回あたりの理想単価を逆算する

    Args:
        monthly_target: 月の目標売上（円）
        working_days: 理想の営業日数/月
        slots_per_day: 理想の1日の予約枠数

    Returns:
        単価シミュレーション結果
    """
    # === 基本計算 ===
    total_monthly_slots = working_days * slots_per_day
    daily_target = monthly_target / working_days
    unit_price = monthly_target / total_monthly_slots  # 1回あたりの理想単価

    # 端数を100円単位に丸める（切り上げ）
    unit_price_rounded = math.ceil(unit_price / 100) * 100

    # === 稼働率シミュレーション ===
    # 稼働率80%の場合（現実的な目安）
    effective_slots = total_monthly_slots * 0.8
    unit_price_80pct = monthly_target / effective_slots
    unit_price_80pct_rounded = math.ceil(unit_price_80pct / 100) * 100

    # === 結果をまとめる ===
    result = {
        'input': {
            'monthly_target': monthly_target,
            'monthly_target_display': f'{monthly_target:,}円',
            'working_days': working_days,
            'slots_per_day': slots_per_day,
        },

        'calculation': {
            'total_monthly_slots': total_monthly_slots,
            'daily_target': int(daily_target),
            'daily_target_display': f'{int(daily_target):,}円',
            'unit_price': unit_price_rounded,
            'unit_price_display': f'{unit_price_rounded:,}円',
            'unit_price_raw': int(unit_price),
        },

        'realistic': {
            'label': '稼働率80%の場合',
            'effective_slots': int(effective_slots),
            'unit_price': unit_price_80pct_rounded,
            'unit_price_display': f'{unit_price_80pct_rounded:,}円',
            'description': f'稼働率80%（月{int(effective_slots)}枠）なら1回 {unit_price_80pct_rounded:,}円が目安',
        },

        'summary': {
            'message': f'月商{monthly_target:,}円を達成するには、1回あたり {unit_price_rounded:,}円 が理想単価です',
            'daily_message': f'1日の目標売上は {int(daily_target):,}円（{slots_per_day}枠 × {unit_price_rounded:,}円）',
        },
    }

    return result
