"""
公式LINE 5日間シナリオ生成モジュール（Claude API連携）

売上100万講座の「教育6ステップ × カウンセリング9ステップの心理プロセス」を組み込んだ
LINEステップ配信（5日間・登録直後含む6通）を生成する。
（Gemini Gem「LINE 5日間シナリオライター」のWeb統合版）

出力された文章は、そのままLINE公式アカウントの管理画面に
コピペで貼り付けられる形式にする。
"""

import json
import os
import re

from config import COUNSELING_9STEP, EDUCATION_6STEP, MODEL_ID, THINKING_OFF, YAKKIHOU_GUARD, extract_text

SYSTEM_PROMPT = f"""
あなたは個人サロン（整体院・接骨院・エステ・鍼灸院・美容サロン）の
公式LINEステップ配信を設計するプロのマーケティングコピーライターです。

以下のメソッドに厳密に沿って、登録直後〜5日目までの計6通の
ステップ配信シナリオを作成してください。

{EDUCATION_6STEP}

■ カウンセリング9ステップの心理プロセス（配信の流れに織り込む）
{COUNSELING_9STEP}

{YAKKIHOU_GUARD}

■ 配信文作成のルール
- そのままLINE管理画面にコピペできる完成形の本文を書く（プレースホルダは【店名】【予約リンク】のみ許可）
- 1通あたり300〜500文字。スマホで読みやすい改行・絵文字を適度に使用
- 「皆さん」ではなく「あなた」— 一斉配信でも個人宛てに見せる
- 各通に「配信のねらい（教育ステップとの対応）」を添える
- 5日目は明確なオファー（予約への行動喚起）で締める
- 出力は必ずJSONのみ（説明文・前置き不要）
"""


def generate_line_scenario(
    keyword,
    target_symptom='',
    personas=None,
    products=None,
    menu_note='',
    salon_profile='',
):
    """
    5日間のLINEステップ配信シナリオ（登録直後+5日=6通）を生成する。

    Returns:
        {
            'strategy': str,                # 5日間全体の戦略
            'messages': [
                {day, timing, title, education_step, body, aim}, ...
            ],
            'operation_tips': [...],        # 運用のコツ
        }
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY未設定のためシナリオを生成できません')

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    symptom = target_symptom or keyword

    persona_summary = ''
    if personas:
        for p in personas[:5]:
            persona_summary += (
                f"- {p.get('name', '')}（{p.get('type_label', '')} / {p.get('age', '')}）: "
                f"{p.get('inner_voice', '')}\n"
            )

    product_summary = ''
    if products:
        plum = products.get('plum', {})
        bamboo = products.get('bamboo', {})
        if plum:
            product_summary += f"- お試し（梅）: {plum.get('name', '')} {plum.get('raw_price_display', '')} / {plum.get('sessions_display', '')}\n"
        if bamboo:
            product_summary += f"- メイン（竹）: {bamboo.get('name', '')} {bamboo.get('raw_price_display', '')} / {bamboo.get('sessions_display', '')}\n"
    if menu_note:
        product_summary += f"- メニュー情報（オーナー入力）: {menu_note}\n"

    user_prompt = f"""以下の情報をもとに、「{symptom}」に悩む方が登録する公式LINEの
5日間ステップ配信シナリオ（登録直後の挨拶 + 1日目〜5日目 = 計6通）を作成してください。

【自店情報】
{salon_profile if salon_profile else '（未登録）'}

【キーワード】{keyword}
【対象症状】{symptom}

【ペルソナ（読者像）】
{persona_summary if persona_summary else '（ペルソナ情報なし — 症状から想定して作成）'}

【オファーする商品】
{product_summary if product_summary else '（商品情報なし — 体験メニューへの予約をゴールに作成）'}

【6通の設計指針】
- 登録直後: 挨拶 + 登録特典 + 信用（教育ステップ1）
- 1日目: 信用の上積み — 価値提供・共感（教育ステップ1）
- 2日目: 目的 — 理想の未来を具体化（教育ステップ2）
- 3日目: 問題 — 立ち塞がる壁を突きつける（教育ステップ3）
- 4日目: 解決策 + 投資 — うちなら解決できる・今やるべき理由（教育ステップ4・5）
- 5日目: 行動 — 明確なオファーで背中を押す（教育ステップ6）

以下のJSON形式で出力してください:
{{
  "strategy": "5日間全体の戦略（2〜3文）",
  "messages": [
    {{"day": "登録直後", "timing": "登録と同時に自動送信", "title": "配信タイトル（管理用）", "education_step": "1. 信用", "body": "LINE本文（コピペ用・改行は\\n）", "aim": "この配信のねらい"}},
    {{"day": "1日目", "timing": "翌日 20:00", ...}},
    ... 計6通 ...
  ],
  "operation_tips": ["運用のコツ1", "運用のコツ2", "運用のコツ3"]
}}"""

    print(f'[line] Claude APIでLINEシナリオ生成中... keyword={keyword}')

    message = client.messages.create(
        model=MODEL_ID,
        thinking=THINKING_OFF,
        max_tokens=6000,
        timeout=110.0,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_prompt}],
    )

    response_text = extract_text(message).strip()
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        raise ValueError('シナリオJSONが見つかりません')

    scenario = json.loads(json_match.group())

    if 'messages' not in scenario or len(scenario['messages']) < 5:
        raise ValueError('配信メッセージが揃っていません')

    print(f'[line] シナリオ生成完了（{len(scenario["messages"])}通）')
    return scenario
