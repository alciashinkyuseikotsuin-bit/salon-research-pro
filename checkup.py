"""
月次数字の健康診断モジュール（Claude API連携）

月の数字（目標・月商・新規数・成約数・平均単価）から、
売上100万講座の基準でボトルネックを特定し、今月やるべき3手を提案する。
計算はルールベース（正確性）、診断コメントと打ち手はAIが生成。
"""

import json
import os
import re

from config import MODEL_ID, THINKING_OFF, YAKKIHOU_GUARD, extract_text

SYSTEM_PROMPT = f"""
あなたは売上100万講座の講師です。個人サロン（整体院・接骨院・鍼灸院・エステ）の
月次数字を診て、ボトルネックを特定し「今月やるべき打ち手」を指導します。

■ 講座の判断基準
- 売上の方程式: 月商 = 新規数 × 成約率 × コース単価 ＋ 既存リピート売上
- 成約率の目安: 80%以上=優秀 / 50〜80%=改善余地あり / 50%未満=カウンセリングが最優先課題
  （カウンセリング9ステップを正しく踏めば成約率80%超えは可能）
- 新規数の目安: 月10人未満なら集客（リサーチ・SNS・LINE導線）がボトルネック
- 単価: 安売りは禁物。「1回あたりの最低ライン」を下回るメニューは作らない。
  高単価コース（松竹梅）で1人あたりの価値を最大化する
- 打ち手は必ず「一番効くレバー1つ」に集中させる（全部やれは挫折のもと）

■ 対策ツールの番号（actions の tool_step に指定）
1=お客様の悩みを調べる 2=お客様像をつくる 3=価格設定を決める 4=コースメニューをつくる
5=カウンセリング台本をつくる 6=接客の練習をする 7=LINEの配信文をつくる 8=キャッチコピーをつくる

{YAKKIHOU_GUARD}

■ 出力ルール
- 数字の再計算はしない（渡された計算結果を使う）
- 診断は愛のある厳しさで。数字が良い部分は必ず先に褒める
- 出力は必ずJSONのみ
"""


def run_checkup(monthly_target, revenue, new_clients, contracts, avg_price, ad_cost=0, cost=0, salon_profile='', use_ai=True):
    """月次数字を診断する。計算はルールベース、診断・打ち手はAI。"""
    achievement = round(revenue / monthly_target * 100) if monthly_target else 0
    contract_rate = round(contracts / new_clients * 100) if new_clients else 0
    gap = monthly_target - revenue
    cpa = round(ad_cost / new_clients) if (ad_cost and new_clients) else 0

    def status_of(val, good, warn):
        return 'good' if val >= good else ('warn' if val >= warn else 'bad')

    # 利益（固定費+広告費を引いた残り）
    profit = revenue - cost - ad_cost if cost else None
    profit_rate = round(profit / revenue * 100) if (profit is not None and revenue) else None

    metrics = [
        {'label': '目標達成率', 'value': f'{achievement}%', 'status': status_of(achievement, 100, 70),
         'note': f'目標{monthly_target:,}円に対して{revenue:,}円（あと{max(gap,0):,}円）'},
        {'label': '新規のコース成約率', 'value': f'{contract_rate}%', 'status': status_of(contract_rate, 80, 50),
         'note': f'新規{new_clients}人中{contracts}人が成約（講座基準: 80%以上が合格）'},
        {'label': '新規客数', 'value': f'{new_clients}人', 'status': status_of(new_clients, 10, 5),
         'note': '月10人が最初の目安'},
        {'label': '平均単価', 'value': f'{avg_price:,}円', 'status': 'info',
         'note': '安売りしていないか？③価格設定と比べてください'},
    ]
    if profit is not None:
        metrics.insert(1, {'label': '手元に残るお金（利益）', 'value': f'{profit:,}円',
                           'status': 'good' if profit_rate and profit_rate >= 30 else ('warn' if profit_rate and profit_rate >= 10 else 'bad'),
                           'note': f'売上{revenue:,}円 −（かかったお金{cost:,}円＋広告費{ad_cost:,}円）＝利益率{profit_rate}%（30%以上が目安）'})
    if cpa:
        metrics.append({'label': '新規1人あたりの広告費', 'value': f'{cpa:,}円',
                        'status': 'good' if cpa <= 10000 else ('warn' if cpa <= 20000 else 'bad'),
                        'note': 'コース単価の1/10以内なら健全'})

    calc_summary = (
        f"目標月商{monthly_target:,}円 / 実績{revenue:,}円（達成率{achievement}%・不足{max(gap,0):,}円）\n"
        f"新規{new_clients}人 → コース成約{contracts}人（成約率{contract_rate}%）\n"
        f"平均単価{avg_price:,}円 / 広告費{ad_cost:,}円" + (f"（CPA {cpa:,}円）" if cpa else '')
        + (f"\n利益{profit:,}円（利益率{profit_rate}%）" if profit is not None else '')
    )

    # === ルールベース診断（AIなし・無料・即時） ===
    if not use_ai:
        if contract_rate < 50 and new_clients > 0:
            bn, tool = '成約率', [
                {'title': 'カウンセリング台本を作り直す', 'detail': f'成約率{contract_rate}%は講座基準50%未満。9ステップ台本で「急にセールスされた感」をなくすのが最優先です。', 'tool_step': 5},
                {'title': '接客の練習をする', 'detail': '台本ができたらロープレで断り文句への切り返しを特訓しましょう。', 'tool_step': 6},
                {'title': 'コースメニューを見直す', 'detail': '梅の料金逆転など「選びやすい松竹梅」になっているか確認を。', 'tool_step': 4},
            ]
        elif new_clients < 10:
            bn, tool = '新規客数', [
                {'title': 'お客様の悩みを調べ直す', 'detail': f'新規{new_clients}人は月10人の目安未満。刺さる言葉の素材集めからやり直しましょう。', 'tool_step': 1},
                {'title': 'キャッチコピーを作り直す', 'detail': '集客の入口（広告・SNS・HPB）の言葉を勝ちコピーに差し替えます。', 'tool_step': 8},
                {'title': 'LINEの配信文を整える', 'detail': '登録済みのお客様を予約に変える5日間配信を仕込みましょう。', 'tool_step': 7},
            ]
        elif achievement < 100:
            bn, tool = '客単価・メニュー構成', [
                {'title': '価格設定を見直す', 'detail': f'あと{max(gap,0):,}円。単価{avg_price:,}円が最低ラインを下回っていないか確認を。', 'tool_step': 3},
                {'title': 'コースメニューを再設計する', 'detail': '都度払い→高単価コースへの切り替えが単価改善の王道です。', 'tool_step': 4},
                {'title': 'カウンセリング台本を磨く', 'detail': 'コース提案の⑦⑨を重点的に。', 'tool_step': 5},
            ]
        else:
            bn, tool = 'なし（目標達成！）', [
                {'title': '勝ちパターンの横展開', 'detail': '当たったコピー・広告を⭐登録して再現性を作りましょう。', 'tool_step': 8},
                {'title': '広告の結果も診断する', 'detail': '伸びている今こそ広告の健康チェックを。', 'tool_step': 10},
                {'title': '来月の目標を上げる', 'detail': '目標月商を上げて再計算を。', 'tool_step': 9},
            ]
        return {
            'praise': f'今月は月商{revenue:,}円（達成率{achievement}%）。まず数字と向き合ったこと自体が経営者の第一歩です。',
            'bottleneck': bn,
            'diagnosis': f'講座基準で一番効くレバーは「{bn}」です。下の3手を上から順に。さらに詳しい分析が欲しい時は「AI講師の詳しい診断」を押してください。',
            'actions': tool,
            'cheer': '全部やろうとせず、最優先の1つだけで大丈夫です。',
            'metrics': metrics,
            'rule_based': True,
        }

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY未設定のため診断できません')

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = f"""以下のサロンの今月の数字を診断してください。

【自店情報】
{salon_profile if salon_profile else '（未登録）'}

【今月の数字（計算済み）】
{calc_summary}

以下のJSON形式で出力してください:
{{
  "praise": "まず褒めるポイント（1〜2文）",
  "bottleneck": "一番のボトルネック（例: 成約率）",
  "diagnosis": "診断コメント（なぜそこがボトルネックか、直すと月商がいくら変わるかの試算を含めて3〜4文）",
  "actions": [
    {{"title": "打ち手1（最優先）", "detail": "具体的に何をするか（2文以内）", "tool_step": 5}},
    {{"title": "打ち手2", "detail": "...", "tool_step": 6}},
    {{"title": "打ち手3", "detail": "...", "tool_step": 7}}
  ],
  "cheer": "締めの一言（前向きに）"
}}"""

    print(f'[checkup] 診断中... 達成率{achievement}% 成約率{contract_rate}%')

    message = client.messages.create(
        model=MODEL_ID,
        thinking=THINKING_OFF,
        max_tokens=2500,
        timeout=60.0,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_prompt}],
    )

    response_text = extract_text(message).strip()
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        raise ValueError('診断JSONが見つかりません')
    ai = json.loads(json_match.group())
    ai['metrics'] = metrics
    print('[checkup] 診断完了')
    return ai
