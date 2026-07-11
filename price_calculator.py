"""
単価シミュレーションモジュール（売上100万講座 準拠）

目標月商・営業日数・予約枠から「1回あたりの最低ライン料金」を算出する。
講座の計算式: 目標売上 ÷（月の営業日数 × 1日に施術できる人数 × 0.7）

「0.7」にする理由 — 残り3割は既存客フォロー・SNS・LINEの仕組みづくりなど
「来月も再来月も売上を安定させる」ための大事な余白。

入力:
- 月の目標売上
- 理想の営業日数（月）
- 理想の1日の予約枠数

出力:
- 1回あたりの最低ライン料金（講座式）
- 全枠が埋まった場合の理論値（参考）
"""

from typing import Dict
import math


def calculate_pricing(
    monthly_target: int,
    working_days: int = 22,
    slots_per_day: int = 6,
) -> Dict:
    """
    目標売上から1回あたりの最低ライン料金を逆算する（講座式: ×0.7の余白ルール）

    Args:
        monthly_target: 月の目標売上（円）
        working_days: 理想の営業日数/月
        slots_per_day: 理想の1日の予約枠数

    Returns:
        単価シミュレーション結果
    """
    # === 講座式の計算（メイン） ===
    # 目標売上 ÷（営業日数 × 1日の枠数 × 0.7）＝ 最低ライン
    total_monthly_slots = working_days * slots_per_day
    effective_slots = total_monthly_slots * 0.7
    unit_price = monthly_target / effective_slots

    # 端数を100円単位に丸める（切り上げ）
    unit_price_rounded = math.ceil(unit_price / 100) * 100

    daily_target = monthly_target / working_days

    # === 参考: 全枠が埋まった場合の理論値 ===
    unit_price_full = monthly_target / total_monthly_slots
    unit_price_full_rounded = math.ceil(unit_price_full / 100) * 100

    result = {
        'input': {
            'monthly_target': monthly_target,
            'monthly_target_display': f'{monthly_target:,}円',
            'working_days': working_days,
            'slots_per_day': slots_per_day,
        },

        'calculation': {
            'total_monthly_slots': total_monthly_slots,
            'effective_slots': int(effective_slots),
            'daily_target': int(daily_target),
            'daily_target_display': f'{int(daily_target):,}円',
            'unit_price': unit_price_rounded,
            'unit_price_display': f'{unit_price_rounded:,}円',
            'unit_price_raw': int(unit_price),
            'formula': f'{monthly_target:,}円 ÷（{working_days}日 × {slots_per_day}枠 × 0.7）',
        },

        'realistic': {
            'label': 'なぜ×0.7で計算するのか',
            'effective_slots': int(effective_slots),
            'unit_price': unit_price_rounded,
            'unit_price_display': f'{unit_price_rounded:,}円',
            'description': (
                f'枠の7割（月{int(effective_slots)}枠）で目標達成する設計にします。'
                '残り3割は既存客フォロー・SNS・LINEの仕組みづくりなど、'
                '来月も再来月も売上を安定させるための大事な余白です。'
            ),
        },

        'reference_full': {
            'label': '全枠が埋まった場合（理論値）',
            'unit_price': unit_price_full_rounded,
            'unit_price_display': f'{unit_price_full_rounded:,}円',
            'description': f'月{total_monthly_slots}枠すべて埋まる前提なら1回 {unit_price_full_rounded:,}円。ただし現実には余白が必要です。',
        },

        'summary': {
            'message': f'月商{monthly_target:,}円を達成するには、1回あたり {unit_price_rounded:,}円 が最低ラインです（この金額を下回るメニューは作らない）',
            'daily_message': f'1日の目標売上は {int(daily_target):,}円。安さで勝負せず「悩みの深いお客様」に選ばれる設計にしましょう',
        },
    }

    return result
