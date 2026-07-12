"""
広告診断モジュール（Claude API連携・画像対応）

Meta/Instagram広告の結果（テキスト・スクショ画像・スプレッドシート貼り付け）を受け取り、
保管庫の「広告判断基準」で当たり/改善余地あり/外れ/判定保留をジャッジする。
"""

import json
import os
import re

from config import AD_BENCHMARKS, AD_CASES, MODEL_ID, THINKING_OFF, YAKKIHOU_GUARD, extract_text

SYSTEM_PROMPT = f"""
あなたは店舗サロン向けのMeta/Instagram広告運用のプロ分析者です。
渡された広告データ（テキスト・スクショ画像・表）を読み取り、以下の判断基準で厳密にジャッジします。

{AD_BENCHMARKS}

{AD_CASES}

{YAKKIHOU_GUARD}

■ 分析ルール
- まず画像・テキストから読み取れた数値をすべて列挙し、基準と照合する
- 母数不足なら正直に「判定保留」とし、断定しない（何が足りないかを明示）
- 良い点を先に認めてから、問題点を指摘する
- 改善提案は優先順位順に最大3つ。「全部直せ」は禁止
- 読み取れない・不明な指標は捏造しない（unknownとする）
- 出力は必ずJSONのみ
"""


def _fmt(n):
    return f'{n:,.0f}'


def build_metrics(platform, objective, nums):
    """入力数値からルールベースで指標を計算する（AIに捏造させない）"""
    spend = nums.get('spend') or 0
    imp = nums.get('impressions') or 0
    clicks = nums.get('clicks') or 0
    lp_views = nums.get('lp_views') or 0
    line_adds = nums.get('line_adds') or 0
    reservations = nums.get('reservations') or 0
    profile_visits = nums.get('profile_visits') or 0
    follows = nums.get('follows') or 0

    lines = [f"媒体: {platform} / 広告の目的: {objective}", f"消化金額: {_fmt(spend)}円"]
    if imp: lines.append(f"インプレッション: {_fmt(imp)}")
    if clicks: lines.append(f"リンククリック: {_fmt(clicks)}")
    if imp and spend: lines.append(f"CPM: {_fmt(spend/imp*1000)}円")
    if clicks and spend: lines.append(f"CPC: {_fmt(spend/clicks)}円")
    if clicks and imp: lines.append(f"CTR: {clicks/imp*100:.2f}%")
    if lp_views:
        lines.append(f"LP表示: {_fmt(lp_views)}")
        if clicks: lines.append(f"LP到達率: {lp_views/clicks*100:.0f}%")
    if line_adds:
        lines.append(f"LINE追加: {_fmt(line_adds)}件")
        if spend: lines.append(f"LINE追加単価: {_fmt(spend/line_adds)}円")
        if clicks: lines.append(f"クリック→LINE追加率: {line_adds/clicks*100:.2f}%")
        if lp_views: lines.append(f"LP表示→LINE追加率: {line_adds/lp_views*100:.2f}%")
    if reservations:
        lines.append(f"予約・問い合わせ: {_fmt(reservations)}件")
        if spend: lines.append(f"予約CPA: {_fmt(spend/reservations)}円")
    if profile_visits:
        lines.append(f"プロフィールアクセス: {_fmt(profile_visits)}")
        if spend: lines.append(f"プロフィールアクセス単価: {_fmt(spend/profile_visits)}円")
        if clicks: lines.append(f"クリック→プロフィールアクセス率: {profile_visits/clicks*100:.1f}%")
    if follows:
        lines.append(f"フォロー: {_fmt(follows)}件")
        if spend: lines.append(f"フォロー単価: {_fmt(spend/follows)}円")
        if profile_visits: lines.append(f"プロフィール→フォロー率: {follows/profile_visits*100:.1f}%")
    return "\n".join(lines)


def run_ad_check(platform='', objective='', numbers=None, text='', images=None, salon_profile=''):
    """広告データを診断する。numbersは数値入力、text/imagesは補足。"""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY未設定のため診断できません')

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    calc = build_metrics(platform or '不明', objective or '不明', numbers or {}) if numbers else ''

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

【媒体・目的と入力数値（計算済み・この数値が最優先の判断材料）】
{calc if calc else '（数値入力なし — 補足テキスト・画像から読み取ってください）'}

【補足（テキスト・表の貼り付け）】
{text if text.strip() else '（なし）'}

診断ルール:
- 媒体と目的に合った基準を使うこと（例: Instagramプロフィール誘導ならプロフィールアクセス単価・フォロー率基準、Meta LP→LINE登録ならLINE追加率・追加単価基準）
- どの基準表を使ったかをsummaryで一言触れる

以下のJSON形式で出力してください:
{{
  "verdict": "当たり|改善余地あり|外れ|判定保留",
  "score": 0〜100の整数（判定保留ならnull）,
  "summary": "結論を2文で（何基準で見たかを含める）",
  "metrics": [
    {{"label": "CPC", "value": "142円", "benchmark": "基準: 120円以下が良い", "judge": "good|warn|bad|unknown"}},
    ...計算済み指標すべて...
  ],
  "good_points": ["良い点1", "良い点2"],
  "problems": ["問題点1", "問題点2"],
  "improvements": [
    {{"title": "改善1（最優先）", "detail": "具体的に何をどうするか（2文以内）"}},
    ...最大3つ...
  ],
  "missing_data": ["判断に必要だが入力されなかったデータ（あれば）"],
  "next_action": "明日やるべき一手（1文）"
}}"""
    content.append({'type': 'text', 'text': user_text})

    print(f"[ad] 広告診断中... {platform}/{objective} 画像{len(images or [])}枚")

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
