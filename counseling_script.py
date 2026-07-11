"""
カウンセリング台本生成モジュール（Claude API連携）

売上100万講座の「カウンセリング9ステップ」に沿って、
リサーチ結果・ペルソナ・松竹梅商品からあなた専用のカウンセリング台本を生成する。
（Gemini Gem「カウンセリング台本作成GEM」のWeb統合版）
"""

import json
import os
import re

from config import COUNSELING_9STEP, MODEL_ID, THINKING_OFF, YAKKIHOU_GUARD, extract_text

SYSTEM_PROMPT = f"""
あなたは個人サロン（整体院・接骨院・エステ・鍼灸院・美容サロン）の
成約率80%超えカウンセリングを設計するプロのセールスコンサルタントです。

以下の9ステップメソッドに厳密に沿って、オーナーがそのまま読み上げられる
「あなた専用のカウンセリング台本」を作成してください。

{COUNSELING_9STEP}

{YAKKIHOU_GUARD}

■ 台本作成のルール
- セリフは実際に口に出す言葉として自然な話し言葉で書く（敬語・丁寧語）
- ペルソナの「心の声」「擬音・体感表現」をセリフに織り込む（②④で特に重要）
- 専門用語は素人向けの言葉に翻訳した形でセリフに入れる（⑥で特に重要）
- 各ステップに「やってはいけないNG」を1つ添える
- セリフ（script）は各ステップ150字以内、point/ngは各60字以内で簡潔に
- 出力は必ずJSONのみ（説明文・前置き不要）
"""


def generate_counseling_script(
    keyword,
    target_symptom='',
    personas=None,
    products=None,
    menu_note='',
):
    """
    9ステップのカウンセリング台本を生成する。

    Returns:
        {
            'preparation': {...},           # 施術前の準備
            'mind_flow': [...],             # 3段階の心の動き
            'steps': [{step, name, goal, script, point, ng}, ...],  # 9ステップ台本
            'objections': [{trigger, magic_question, follow}, ...], # 断り文句への切り返し
            'silence_rule': str,            # 沈黙の鉄則
            'mindset': str,                 # 心構え
        }
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY未設定のため台本を生成できません')

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    symptom = target_symptom or keyword

    persona_summary = ''
    if personas:
        for p in personas[:5]:
            persona_summary += (
                f"- {p.get('name', '')}（{p.get('type_label', '')} / {p.get('age', '')} / {p.get('occupation', '')}）: "
                f"{p.get('inner_voice', '')}\n"
            )

    product_summary = ''
    if products:
        for rank in ('pine', 'bamboo', 'plum'):
            item = products.get(rank, {})
            if item:
                product_summary += (
                    f"- {item.get('rank', '')}: {item.get('name', '')} "
                    f"{item.get('raw_price_display', '')} / {item.get('sessions_display', '')} / {item.get('duration', '')}\n"
                )
        tips = products.get('sales_tips', {})
        if tips.get('closing_phrase'):
            product_summary += f"- クロージング推奨フレーズ: {tips['closing_phrase']}\n"
    if menu_note:
        product_summary += f"- メニュー情報（オーナー入力）: {menu_note}\n"

    user_prompt = f"""以下の情報をもとに、「{symptom}」に悩むお客様への新規カウンセリング台本を9ステップで作成してください。

【キーワード】{keyword}
【対象症状】{symptom}

【ペルソナ（想定されるお客様）】
{persona_summary if persona_summary else '（ペルソナ情報なし — 症状から想定して作成）'}

【松竹梅メニュー（④で設計済み）】
{product_summary if product_summary else '（商品情報なし — 一般的な回数コースを想定して作成）'}

以下のJSON形式で出力してください:
{{
  "preparation": {{"title": "施術前の準備", "actions": ["準備1", "準備2", "準備3"]}},
  "mind_flow": [
    {{"order": 1, "state": "危機感", "description": "..."}},
    {{"order": 2, "state": "安心感", "description": "..."}},
    {{"order": 3, "state": "納得", "description": "..."}}
  ],
  "steps": [
    {{"step": 1, "name": "最初のお約束", "goal": "このステップの目的", "script": "実際に読み上げるセリフ（複数文OK・改行は\\n）", "point": "成功のポイント", "ng": "やってはいけないNG"}},
    ... 9ステップすべて ...
  ],
  "objections": [
    {{"trigger": "家族に相談します", "receive": "受け止めのセリフ", "magic_question": "魔法の質問のセリフ", "follow": "その後の対応セリフ"}},
    {{"trigger": "お金がない", ...}},
    {{"trigger": "考えます", ...}}
  ],
  "silence_rule": "沈黙の鉄則の説明",
  "mindset": "心構えメッセージ"
}}"""

    print(f'[counseling] Claude APIで台本生成中... keyword={keyword}')

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
        raise ValueError('台本JSONが見つかりません')

    script = json.loads(json_match.group())

    if 'steps' not in script or len(script['steps']) < 9:
        raise ValueError('9ステップが揃っていません')

    print(f'[counseling] 台本生成完了（{len(script["steps"])}ステップ）')
    return script
