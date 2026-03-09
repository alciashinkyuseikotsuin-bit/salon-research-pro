"""
AI 商品設計モジュール（Claude API連携）

Claude APIを使用して、ペルソナの悩みに合わせた松竹梅の商品を設計する。
価格計算はルールベース（正確性が必要）、商品名・特徴・セールスTipsはAIが生成。
エラー時はルールベース版にフォールバック。
"""

import json
import os
import re
import math

from knowledge_base import PRODUCT_KNOWLEDGE
from product_designer import design_products as design_products_fallback
from product_designer import suggest_psychological_price


def _parse_duration_to_days(duration: str) -> int:
    """期間文字列を日数に変換"""
    m = re.search(r'(\d+)', duration)
    if not m:
        return 90
    num = int(m.group(1))
    if 'ヶ月' in duration or '月' in duration:
        return num * 30
    elif '週' in duration:
        return num * 7
    elif '日' in duration:
        return num
    return num * 30


def generate_products_ai(
    keyword,
    target_symptom='',
    unit_price=0,
    bamboo_sessions=12,
    bamboo_duration='3ヶ月',
    personas=None,
):
    """
    Claude APIを使って商品を設計する。
    価格計算はルールベース、商品名・特徴・Tips はAI生成。
    エラー時はルールベース版にフォールバック。
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('[product] ANTHROPIC_API_KEY未設定 → ルールベース版で生成')
        return design_products_fallback(
            keyword=keyword,
            target_symptom=target_symptom,
            unit_price=unit_price,
            bamboo_sessions=bamboo_sessions,
            bamboo_duration=bamboo_duration,
        )

    # === 価格計算（ルールベース: 正確性が必要） ===
    bamboo_raw_price = unit_price * bamboo_sessions
    bamboo_suggestions = suggest_psychological_price(bamboo_raw_price)

    pine_multiplier = 2.5
    pine_raw_price = int(bamboo_raw_price * pine_multiplier)
    pine_sessions = bamboo_sessions * 2
    pine_suggestions = suggest_psychological_price(pine_raw_price)

    plum_sessions = 3
    plum_raw_price = unit_price * plum_sessions
    plum_suggestions = suggest_psychological_price(plum_raw_price)

    bamboo_duration_days = _parse_duration_to_days(bamboo_duration)
    per_day = int(bamboo_raw_price / bamboo_duration_days) if bamboo_duration_days > 0 else 0
    pine_duration = f'{int(bamboo_duration_days * 2 / 30)}ヶ月' if bamboo_duration_days > 0 else ''

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # ペルソナ情報を要約
        persona_summary = ''
        if personas:
            for p in personas[:5]:
                persona_summary += f"- {p.get('name', '')}（{p.get('type_label', '')}）: {p.get('inner_voice', '')}\n"

        symptom = target_symptom or keyword

        user_prompt = f"""以下の情報をもとに、「{symptom}」に悩むサロンのお客様向けの松竹梅商品を設計してください。

【キーワード】{keyword}
【対象症状】{symptom}

【ペルソナ（②で生成した悩むお客様たち）】
{persona_summary if persona_summary else '（ペルソナ情報なし — 一般的な知識で設計してください）'}

【価格情報（計算済み）】
- 1回あたりの施術単価: {unit_price:,}円
- 松コース: {pine_sessions}回 / {pine_duration} / 合計{pine_raw_price:,}円
- 竹コース: {bamboo_sessions}回 / {bamboo_duration} / 合計{bamboo_raw_price:,}円
- 梅コース: {plum_sessions}回 / 3週間 / 合計{plum_raw_price:,}円
- 竹の1日あたり: {per_day:,}円

重要な指示:
- ペルソナの悩み・心の声に直接応える商品名と特徴にしてください
- 上記の価格情報を反論処理トークに活用してください（1日○円の投資 等）
- 出力はJSON（説明文不要）。"""

        print(f'[product] Claude APIで商品設計中... keyword={keyword}')

        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            timeout=50.0,
            system=PRODUCT_KNOWLEDGE,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        response_text = message.content[0].text.strip()
        print(f'[product] Claude API応答取得 ({len(response_text)}文字)')

        # JSONを抽出
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError('JSONが見つかりません')

        ai_data = json.loads(json_match.group())

        # バリデーション
        if 'pine' not in ai_data or 'bamboo' not in ai_data or 'plum' not in ai_data:
            raise ValueError('松竹梅が揃っていません')

        # AI生成の内容と価格計算を統合
        result = {
            'category': 'ai_generated',
            'service_name': ai_data.get('bamboo', {}).get('name', f'{symptom}改善プログラム'),
            'symptom': symptom,
            'unit_price': unit_price,
            'unit_price_display': f'{unit_price:,}円',

            'pine': {
                'rank': '松',
                'name': ai_data.get('pine', {}).get('name', f'プレミアム完全{symptom}改善コース'),
                'raw_price': pine_raw_price,
                'raw_price_display': f'{pine_raw_price:,}円',
                'suggested_prices': pine_suggestions,
                'sessions': pine_sessions,
                'sessions_display': f'{pine_sessions}回',
                'duration': pine_duration,
                'features': ai_data.get('pine', {}).get('features', []),
                'guarantee': ai_data.get('pine', {}).get('guarantee', '改善を実感できなければ追加施術を無料で提供'),
                'role': ai_data.get('pine', {}).get('role', 'アンカリング商品：竹コースが「お得」に見える基準を作る'),
            },

            'bamboo': {
                'rank': '竹',
                'name': ai_data.get('bamboo', {}).get('name', f'集中{symptom}改善コース'),
                'raw_price': bamboo_raw_price,
                'raw_price_display': f'{bamboo_raw_price:,}円',
                'suggested_prices': bamboo_suggestions,
                'sessions': bamboo_sessions,
                'sessions_display': f'{bamboo_sessions}回',
                'duration': bamboo_duration,
                'features': ai_data.get('bamboo', {}).get('features', []),
                'guarantee': ai_data.get('bamboo', {}).get('guarantee', '改善を実感できなければ追加施術を無料で提供'),
                'selling_points': ai_data.get('bamboo', {}).get('selling_points', [
                    '一番人気のコース',
                    '多くの方がこのコースで改善を実感',
                    '費用対効果が最も高い',
                ]),
                'role': ai_data.get('bamboo', {}).get('role', 'メイン商品：一番売りたい商品。費用対効果が最も高い'),
                'per_session': f'{unit_price:,}円/回',
                'per_day': f'{per_day:,}円/日' if per_day > 0 else '',
            },

            'plum': {
                'rank': '梅',
                'name': ai_data.get('plum', {}).get('name', '体験お試しコース'),
                'raw_price': plum_raw_price,
                'raw_price_display': f'{plum_raw_price:,}円',
                'suggested_prices': plum_suggestions,
                'sessions': plum_sessions,
                'sessions_display': f'{plum_sessions}回',
                'duration': '3週間',
                'features': ai_data.get('plum', {}).get('features', []),
                'role': ai_data.get('plum', {}).get('role', 'ダウンセル：「まずはお試し」から始めて竹への導線を作る'),
            },

            'sales_tips': ai_data.get('sales_tips', {
                'presentation_order': '松→竹→梅の順に提示（アンカリング効果）',
                'closing_phrase': '「どちらのコースが良いと思いましたか？」（二者択一法）',
                'objection_handling': {
                    'expensive': f'1日あたりに換算すると{per_day:,}円の投資です' if per_day > 0 else '',
                    'uncertain': '改善を実感できなければ追加施術を無料で提供します',
                    'time': f'週1回、たった{bamboo_duration}の投資で何年もの悩みが解決します',
                },
            }),
        }

        # sales_tips に objection_handling がない場合のデフォルト
        if 'objection_handling' not in result['sales_tips']:
            result['sales_tips']['objection_handling'] = {
                'expensive': f'1日あたりに換算すると{per_day:,}円の投資です' if per_day > 0 else '',
                'uncertain': '改善を実感できなければ追加施術を無料で提供します',
                'time': f'週1回、たった{bamboo_duration}の投資で何年もの悩みが解決します',
            }

        print(f'[product] AI商品設計完了')
        return result

    except Exception as e:
        print(f'[product] Claude APIエラー: {e} → ルールベース版にフォールバック')
        return design_products_fallback(
            keyword=keyword,
            target_symptom=target_symptom,
            unit_price=unit_price,
            bamboo_sessions=bamboo_sessions,
            bamboo_duration=bamboo_duration,
        )
