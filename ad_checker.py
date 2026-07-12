"""
広告診断モジュール（Claude API連携・画像対応）

Meta/Instagram広告の結果（テキスト・スクショ画像・スプレッドシート貼り付け）を受け取り、
保管庫の「広告判断基準」で当たり/改善余地あり/外れ/判定保留をジャッジする。
"""

import json
import os
import re

from config import AD_BENCHMARKS, MODEL_ID, THINKING_OFF, YAKKIHOU_GUARD, extract_text

SYSTEM_PROMPT = f"""
あなたは店舗サロン向けのMeta/Instagram広告運用のプロ分析者です。
渡された広告データ（テキスト・スクショ画像・表）を読み取り、以下の判断基準で厳密にジャッジします。

{AD_BENCHMARKS}

{YAKKIHOU_GUARD}

■ 分析ルール
- まず画像・テキストから読み取れた数値をすべて列挙し、基準と照合する
- 母数不足なら正直に「判定保留」とし、断定しない（何が足りないかを明示）
- 良い点を先に認めてから、問題点を指摘する
- 改善提案は優先順位順に最大3つ。「全部直せ」は禁止
- 読み取れない・不明な指標は捏造しない（unknownとする）
- 出力は必ずJSONのみ
"""


def run_ad_check(text='', images=None, salon_profile=''):
    """広告データを診断する。imagesは[{'media_type':..., 'data': base64str}]"""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY未設定のため診断できません')

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    content = []
    for img in (images or [])[:4]:
        if img.get('data'):
            content.append({
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': img.get('media_type', 'image/jpeg'),
                    'data': img['data'],
                },
            })

    user_text = f"""以下の広告データを診断してください。

【自店情報】
{salon_profile if salon_profile else '（未登録）'}

【広告データ（テキスト・スプレッドシート貼り付け）】
{text if text.strip() else '（テキストなし — 添付画像から読み取ってください）'}

以下のJSON形式で出力してください:
{{
  "verdict": "当たり|改善余地あり|外れ|判定保留",
  "score": 0〜100の整数（判定保留ならnull）,
  "summary": "結論を2文で（オーナーが読んで一瞬でわかるように）",
  "metrics": [
    {{"label": "CPC", "value": "142円", "benchmark": "基準: 120円以下が良い", "judge": "good|warn|bad|unknown"}},
    ...読み取れた指標すべて...
  ],
  "good_points": ["良い点1", "良い点2"],
  "problems": ["問題点1", "問題点2"],
  "improvements": [
    {{"title": "改善1（最優先）", "detail": "具体的に何をどうするか（2文以内）"}},
    ...最大3つ...
  ],
  "missing_data": ["判断に必要だが読み取れなかったデータ（あれば）"],
  "next_action": "明日やるべき一手（1文）"
}}"""
    content.append({'type': 'text', 'text': user_text})

    print(f'[ad] 広告診断中... 画像{len(images or [])}枚 テキスト{len(text)}文字')

    message = client.messages.create(
        model=MODEL_ID,
        thinking=THINKING_OFF,
        max_tokens=3500,
        timeout=110.0,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': content}],
    )

    response_text = extract_text(message).strip()
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        raise ValueError('診断JSONが見つかりません')
    result = json.loads(json_match.group())
    print(f"[ad] 診断完了: {result.get('verdict')}")
    return result
