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


# ===== ルールベース判定（AIなし・0円・即時） =====
# 基準表: (良い上限/下限, 注意上限/下限, 方向) dir=-1は低いほど良い / +1は高いほど良い
BENCH = {
    'CPC':            {'good': 120,  'warn': 220,   'dir': -1, 'unit': '円', 'note': '美容・店舗系の目安: 120円以下が良い'},
    'CPM':            {'good': 1300, 'warn': 2400,  'dir': -1, 'unit': '円', 'note': '1,300円以下が良い'},
    'CTR':            {'good': 1.5,  'warn': 0.8,   'dir': 1,  'unit': '%',  'note': 'リンククリック率 1.5%以上が良い'},
    'LP到達率':        {'good': 80,   'warn': 60,    'dir': 1,  'unit': '%',  'note': '80%以上が良い（低いと表示速度やURLの問題）'},
    'LINE追加単価':    {'good': 300,  'warn': 600,   'dir': -1, 'unit': '円', 'note': '300円以下が良い'},
    'クリック→LINE追加率': {'good': 8, 'warn': 4,    'dir': 1,  'unit': '%',  'note': '8%以上が良い'},
    'プロフィールアクセス単価': {'good': 30, 'warn': 100, 'dir': -1, 'unit': '円', 'note': '30円以下が良い'},
    'フォロー単価':    {'good': 311,  'warn': 1000,  'dir': -1, 'unit': '円', 'note': '実例水準: 110〜311円が良い'},
    'プロフィール→フォロー率': {'good': 10, 'warn': 5, 'dir': 1, 'unit': '%', 'note': '10%以上が良い'},
    '予約CPA':        {'good': 15000, 'warn': 20000, 'dir': -1, 'unit': '円', 'note': '店舗系の実例水準: 来店CPA1.5〜2万円'},
    '予約CVR':        {'good': 8,    'warn': 4,     'dir': 1,  'unit': '%',  'note': '8%以上が良い'},
}


def judge_value(name, value):
    b = BENCH.get(name)
    if not b:
        return 'unknown', ''
    if b['dir'] < 0:
        j = 'good' if value <= b['good'] else ('warn' if value <= b['warn'] else 'bad')
    else:
        j = 'good' if value >= b['good'] else ('warn' if value >= b['warn'] else 'bad')
    return j, b['note']


def rule_check(platform, objective, n):
    """数値からルールベースで判定する（AIを使わない）"""
    spend = n.get('spend') or 0
    imp = n.get('impressions') or 0
    clicks = n.get('clicks') or 0
    lp = n.get('lp_views') or 0
    line = n.get('line_adds') or 0
    rsv = n.get('reservations') or 0
    prof = n.get('profile_visits') or 0
    fol = n.get('follows') or 0

    calc = {}
    if clicks and spend: calc['CPC'] = round(spend / clicks)
    if imp and spend:    calc['CPM'] = round(spend / imp * 1000)
    if imp and clicks:   calc['CTR'] = round(clicks / imp * 100, 2)
    if clicks and lp:    calc['LP到達率'] = round(lp / clicks * 100)
    if line and spend:   calc['LINE追加単価'] = round(spend / line)
    if line and clicks:  calc['クリック→LINE追加率'] = round(line / clicks * 100, 2)
    if prof and spend:   calc['プロフィールアクセス単価'] = round(spend / prof)
    if fol and spend:    calc['フォロー単価'] = round(spend / fol)
    if fol and prof:     calc['プロフィール→フォロー率'] = round(fol / prof * 100, 1)
    if rsv and spend:    calc['予約CPA'] = round(spend / rsv)
    if rsv and lp:       calc['予約CVR'] = round(rsv / lp * 100, 1)

    metrics = []
    for k, v in calc.items():
        j, note = judge_value(k, v)
        metrics.append({'label': k, 'value': f"{v:,}{BENCH[k]['unit']}", 'benchmark': note, 'judge': j})

    cv = line + rsv + fol
    # 母数不足の判定
    holds = []
    if clicks and clicks < 100: holds.append(f'クリック{clicks}回（100未満だとCTR・CPCの判断は低信頼）')
    if cv and cv < 10: holds.append(f'成果{cv}件（10件未満だと成果単価の判断は保留寄り）')
    if not clicks and not cv: holds.append('クリック数・成果数の入力がありません')

    bads = [m for m in metrics if m['judge'] == 'bad']
    goods = [m for m in metrics if m['judge'] == 'good']

    if holds and len(metrics) < 3:
        verdict, score = '判定保留', None
    elif not metrics:
        verdict, score = '判定保留', None
    else:
        ratio = len(goods) / len(metrics)
        if bads and ratio < 0.34: verdict, score = '外れ', max(20, round(ratio * 100))
        elif bads: verdict, score = '改善余地あり', round(40 + ratio * 30)
        elif ratio >= 0.8: verdict, score = '当たり', round(80 + ratio * 20)
        else: verdict, score = '改善余地あり', round(50 + ratio * 30)

    # ボトルネックの切り分け（広告判断基準の切り分け表）
    problems, improvements = [], []
    def has_bad(name): return any(m['label'] == name and m['judge'] == 'bad' for m in metrics)

    if has_bad('CTR'):
        problems.append('CTRが基準未満＝広告そのものが見られていない（クリエイティブ・ターゲティング・オファーが弱い）')
        improvements.append({'title': 'クリエイティブを入れ替える（最優先）', 'detail': '症状名をド直球で最も目立つ位置に、地域名でターゲットコール、バナー文字は3行以内に。キャッチコピーづくりで作った勝ちコピーを使いましょう。'})
    if has_bad('LP到達率'):
        problems.append('LP到達率が低い＝クリックされてもページが開かれていない（表示速度・URL・計測の技術問題）')
        improvements.append({'title': 'リンク先と表示速度を確認する', 'detail': '広告のリンク先URLが正しいか、スマホで3秒以内に表示されるかを確認してください。数値の急落は導線事故が原因のことが多いです。'})
    if has_bad('クリック→LINE追加率') or has_bad('予約CVR'):
        problems.append('ページには来ているのに登録・予約されていない（LP冒頭とCTAの問題）')
        improvements.append({'title': 'LPの冒頭とボタンを直す', 'detail': '1画面目に「誰の・どの悩み・何が手に入るか」を置き、LINE登録ボタンを目立たせてください。広告とLPの言っていることを揃えるのも重要です。'})
    if has_bad('LINE追加単価') or has_bad('予約CPA') or has_bad('プロフィールアクセス単価') or has_bad('フォロー単価'):
        problems.append('獲得単価が基準を超えている＝このまま続けると赤字になりやすい')
        improvements.append({'title': '予算を止めて配信内容を作り直す', 'detail': '単価が基準の2倍を超える配信は一度停止し、勝ちパターンのクリエイティブに絞って1日500〜1,000円で再テストしましょう。'})
    if not problems and metrics:
        improvements.append({'title': '勝ちパターンを横展開する', 'detail': 'この配信は基準を満たしています。同じ訴求で予算を増やすか、別の悩みキーワードでも同じ型を試しましょう。'})

    good_points = [f"{m['label']} {m['value']} は基準クリア" for m in goods[:3]] or ['入力ありがとうございます。数字を記録することが改善の第一歩です']

    summary_parts = []
    if platform or objective:
        summary_parts.append(f"{platform}／{objective}の基準で判定しました。")
    if verdict == '判定保留':
        summary_parts.append('データが少なく断定できません。' + ('／'.join(holds) if holds else ''))
    else:
        summary_parts.append(('良い数値が多く、この配信は続ける価値があります。' if verdict == '当たり'
                              else '一部の数値が基準未満です。下の改善から手をつけてください。' if verdict == '改善余地あり'
                              else '主要な数値が基準を下回っています。改善より一度止めて作り直すことを検討してください。'))

    return {
        'verdict': verdict, 'score': score, 'summary': ' '.join(summary_parts),
        'metrics': metrics, 'good_points': good_points, 'problems': problems,
        'improvements': improvements[:3],
        'missing_data': holds,
        'next_action': improvements[0]['title'] if improvements else 'データを追加で集めてから再診断しましょう',
        'rule_based': True,
    }


def run_ad_check(platform='', objective='', numbers=None, text='', images=None, salon_profile='', use_ai=True):
    """広告データを診断する。use_ai=Falseなら数値からルールベースで即時判定（0円）。"""
    if not use_ai and numbers and any(numbers.values()):
        print('[ad] ルールベース判定（AIなし）')
        return rule_check(platform, objective, numbers)

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
