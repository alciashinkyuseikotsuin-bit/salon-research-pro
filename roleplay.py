"""
反論処理・ロープレAIモジュール（Claude API連携）— カウンセリング道場

②で生成したペルソナをAIが「新規のお客様」として演じ、
オーナーがカウンセリング9ステップを24時間いつでも特訓できる。

- generate_customer_reply: お客様AIの返答（心の声・信頼度つき）
- generate_feedback: 会話履歴を9ステップ基準で採点しフィードバック
"""

import json
import os
import re

from config import COUNSELING_9STEP, MODEL_ID, THINKING_OFF, extract_text


def _client():
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY未設定のためロープレを開始できません')
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _persona_block(persona):
    p = persona or {}
    return f"""【あなたが演じるお客様】
- 名前: {p.get('name', '匿名のお客様')}
- タイプ: {p.get('type_label', '')}
- 年齢/性別/職業: {p.get('age', '')} / {p.get('gender', '')} / {p.get('occupation', '')}
- 家族構成: {p.get('family', '')}
- 日常: {p.get('daily_pattern', '')}
- 今まで試したこと: {p.get('tried_solution', '')}
- 心の声（本音）: {p.get('inner_voice', '')}"""


def _products_block(products):
    if not products:
        return '（メニュー情報なし）'
    lines = []
    for rank in ('pine', 'bamboo', 'plum'):
        item = products.get(rank, {})
        if item:
            lines.append(
                f"- {item.get('rank', '')}: {item.get('name', '')} "
                f"{item.get('raw_price_display', '')} / {item.get('sessions_display', '')}"
            )
    return '\n'.join(lines) if lines else '（メニュー情報なし）'


ROLEPLAY_SYSTEM = """
あなたはサロンに初めて来店した「新規のお客様」を演じるロールプレイAIです。
相手はサロンオーナーで、カウンセリングの練習をしています。

■ 演技のルール
- ペルソナになりきり、リアルな新規客として自然な話し言葉で返答する
- 最初は少し警戒している。信頼関係ができるまで本音（心の声）は出さない
- オーナーが良い質問（悩みの深掘り・共感・理想の未来を聞く）をしたら、少しずつ心を開いて具体的に話す
- オーナーがいきなり売り込んだり、専門用語を使ったり、話を聞かずに提案したら、警戒して口数を減らす
- オーナーがクロージング（コースの提案・料金の話）に入ったら、信頼度に応じて反応する:
  - 信頼度が低い（〜40）: 「考えます」「また連絡します」と逃げる
  - 信頼度が中（41〜70）: 「家族に相談します」「お金が…」など断り文句を1つ出す
  - 信頼度が高い（71〜）: 前向きだが1つだけ軽い不安を口にする（切り返しの練習機会を与える）
- 断り文句への切り返しが上手ければ（受け止め→魔法の質問）、素直に本音を認めて前進する
- 1回の返答は1〜4文程度。お客様が長広舌をふるうのは不自然

■ 出力形式（必ずJSONのみ）
{"reply": "お客様としての返答", "inner_voice": "今の心の声（本音・不安・オーナーへの印象）", "trust": 信頼度0〜100の整数}

信頼度の初期値は30。オーナーの対応の質に応じて上下させること。
"""


def generate_customer_reply(persona, products, history, owner_message):
    """
    お客様AIの返答を生成する。

    Args:
        persona: ペルソナdict
        products: 松竹梅商品dict（お客様はメニュー表をチラ見している設定）
        history: [{'role': 'owner'|'customer', 'text': str}, ...]
        owner_message: 今回のオーナーの発言

    Returns:
        {'reply': str, 'inner_voice': str, 'trust': int}
    """
    client = _client()

    system = ROLEPLAY_SYSTEM + f"""

{_persona_block(persona)}

【カウンセリングシートの横にさりげなく置いてあるメニュー表（チラッと見た）】
{_products_block(products)}
"""

    messages = []
    for h in (history or [])[-20:]:
        role = 'user' if h.get('role') == 'owner' else 'assistant'
        text = h.get('text', '')
        if role == 'assistant':
            # 過去の自分の返答はJSON形式で渡して形式を維持させる
            text = json.dumps({'reply': text, 'inner_voice': '', 'trust': h.get('trust', 30)}, ensure_ascii=False)
        messages.append({'role': role, 'content': text})
    messages.append({'role': 'user', 'content': owner_message})

    print(f'[roleplay] お客様AI返答生成中... (履歴{len(messages)}件)')

    message = client.messages.create(
        model=MODEL_ID,
        thinking=THINKING_OFF,
        max_tokens=1000,
        timeout=40.0,
        system=system,
        messages=messages,
    )

    response_text = extract_text(message).strip()
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        # JSONで返らなかった場合はそのまま返答として扱う
        return {'reply': response_text, 'inner_voice': '', 'trust': 30}

    data = json.loads(json_match.group())
    return {
        'reply': data.get('reply', ''),
        'inner_voice': data.get('inner_voice', ''),
        'trust': max(0, min(100, int(data.get('trust', 30)))),
    }


FEEDBACK_SYSTEM = f"""
あなたは売上100万講座の講師です。受講生（サロンオーナー）が行った
カウンセリングのロールプレイを、9ステップメソッドに照らして採点・指導してください。

{COUNSELING_9STEP}

■ 採点のルール
- 9ステップそれぞれについて: done（できた）/ partial（惜しい）/ missed（できていない・未到達）で判定
- ロープレが途中で終わっていて未到達のステップは missed とし、コメントは「未到達」と明記
- 断り文句が出た場合は「受け止め→魔法の質問」の切り返しができたかを必ず評価
- 講師として愛のある厳しさで。良かった点は具体的に褒め、改善点は「次はこう言う」の形で示す
- 出力は必ずJSONのみ
"""


def generate_feedback(persona, products, history):
    """
    ロープレの会話履歴を9ステップ基準で採点する。

    Returns:
        {
            'total_score': int (0-100),
            'grade': str,
            'step_scores': [{step, name, status, comment}, ...],
            'objection_review': str,
            'best_moment': str,
            'advice': str,
            'next_practice': str,
        }
    """
    client = _client()

    transcript = ''
    for h in (history or []):
        speaker = 'オーナー' if h.get('role') == 'owner' else 'お客様'
        transcript += f"{speaker}: {h.get('text', '')}\n"

    user_prompt = f"""以下のロールプレイを採点してください。

{_persona_block(persona)}

【メニュー】
{_products_block(products)}

【ロープレの会話記録】
{transcript if transcript else '（会話なし）'}

以下のJSON形式で出力してください:
{{
  "total_score": 0〜100の整数,
  "grade": "S/A/B/C/Dのいずれか",
  "step_scores": [
    {{"step": 1, "name": "最初のお約束", "status": "done|partial|missed", "comment": "具体的な講評"}},
    ... 9ステップすべて ...
  ],
  "objection_review": "断り文句への切り返しの講評（出なかった場合はその旨）",
  "best_moment": "一番良かった場面の引用と褒めポイント",
  "advice": "次はこう言う、の形の具体的アドバイス（2〜3個）",
  "next_practice": "次に練習すべきテーマ"
}}"""

    print(f'[roleplay] フィードバック生成中... (会話{len(history or [])}件)')

    message = client.messages.create(
        model=MODEL_ID,
        thinking=THINKING_OFF,
        max_tokens=4000,
        timeout=110.0,
        system=FEEDBACK_SYSTEM,
        messages=[{'role': 'user', 'content': user_prompt}],
    )

    response_text = extract_text(message).strip()
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        raise ValueError('フィードバックJSONが見つかりません')

    return json.loads(json_match.group())
