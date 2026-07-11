"""
AI コピーライティングモジュール（Claude API連携）

Claude APIを使用して、ペルソナと商品情報から
AIドリブンのキャッチコピーを生成する。
エラー時はルールベース版にフォールバック。
"""

import json
from config import MODEL_ID, SASARU_KOTOBA, THINKING_OFF, YAKKIHOU_GUARD, extract_text
import os
import re

from knowledge_base import COPYWRITING_KNOWLEDGE

# ルールベースのフォールバック用定義
COPY_TYPES = [
    {
        'type': 'conclusion_first', 'label': '結論先出し型',
        'template': '結局、{keyword}を根本から変えるには正しい施術しかなかった',
        'effect': '読者の常識を覆し、長期的な価値（LTV）を暗示',
        'usage': '新聞風の大見出し、LP冒頭に最適',
    },
    {
        'type': 'pain_direct', 'label': '痛み直撃型',
        'template': 'まだ{keyword}で消耗してるの？ その我慢、もう終わりにしませんか',
        'effect': '悩みを突いて解決策へ誘導',
        'usage': 'チラシ風のキャッチ、新聞風見出し、SNS投稿の1行目に最適',
    },
    {
        'type': 'authority_proof', 'label': '権威証明型',
        'template': '{keyword}のプロが選んだ、本当に結果が出る改善メソッド',
        'effect': '権威性で読む価値を判断させる',
        'usage': '新聞風の本文冒頭、雑誌風リード、固定投稿に最適',
    },
    {
        'type': 'simple_focus', 'label': 'シンプル＆フォーカス型',
        'template': '{keyword}改善に必要なのは、たった1つの正しいアプローチだけ',
        'effect': 'ノイズを排除し本質を伝える',
        'usage': '雑誌風サブタイトル、チラシ風キャッチに最適',
    },
    {
        'type': 'number_impact', 'label': '数字インパクト型',
        'template': '{keyword}に悩む方の92%が「もっと早く来ればよかった」と実感',
        'effect': '具体的な数字で社会的証明を満たす',
        'usage': '全レイアウトの見出し・コピー、ホットペッパー、LPに最適',
    },
    {
        'type': 'story_intro', 'label': 'ストーリー導入型',
        'template': '10年間{keyword}に苦しんだ私が、3ヶ月で笑顔を取り戻すまで',
        'effect': '物語で引き込み共感を生む',
        'usage': '雑誌風の見出し、新聞風の本文導入、Instagram投稿に最適',
    },
    {
        'type': 'urgency_limited', 'label': '緊急性＆限定型',
        'template': '【今月残り3名限定】{keyword}の根本改善、まずは体験から',
        'effect': '今すぐ動く理由を作る',
        'usage': 'チラシ風のバッジ、新聞風CTA、LINE配信に最適',
    },
    {
        'type': 'question_trigger', 'label': '疑問提起型',
        'template': 'なぜ{keyword}は自己流ケアでは治らないのか？',
        'effect': '好奇心のギャップを作り対話を誘発する',
        'usage': '新聞風・雑誌風の大見出し、Threads投稿に最適',
    },
    {
        'type': 'before_after', 'label': 'ビフォーアフター型',
        'template': '毎朝ツラかった{keyword}が、3ヶ月後には快適な毎日に変わる',
        'effect': '現状と理想を対比させる',
        'usage': 'チラシ風の大見出しまわり、SNS投稿に最適',
    },
    {
        'type': 'paradox', 'label': '逆説・常識破壊型',
        'template': '{keyword}は「我慢」しなくていい。実はセルフケアだけでは不十分です',
        'effect': 'マインドブロックを破壊して注目を集める',
        'usage': '新聞風の大見出しで最強のフック、バズ投稿に最適',
    },
]


def generate_catchcopy_ai(keyword, target_symptom='', personas=None, products=None):
    """
    Claude APIを使ってキャッチコピーを生成する。
    エラー時はルールベース版にフォールバック。
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('[copy] ANTHROPIC_API_KEY未設定 → ルールベース版で生成')
        return generate_catchcopy_fallback(keyword, target_symptom)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # ペルソナ情報を要約
        persona_summary = ''
        if personas:
            for p in personas[:5]:
                persona_summary += f"- {p.get('name','')}: {p.get('type_label','')} / {p.get('age','')} / {p.get('occupation','')}\n"
                persona_summary += f"  心の声: {p.get('inner_voice','')[:100]}\n"

        # 商品情報を要約
        product_summary = ''
        if products:
            for tier in ['pine', 'bamboo', 'plum']:
                if tier in products:
                    prod = products[tier]
                    product_summary += f"- {prod.get('rank',tier)}: {prod.get('name','')} / {prod.get('raw_price_display','')} / {prod.get('sessions_display','')} / {prod.get('duration','')}\n"

        # ========== パス1: 刺さる言葉メソッドで15本生成 ==========
        user_prompt = f"""以下の情報をもとに、「{keyword}」専門サロンの集客用キャッチコピーを15本生成してください。

【キーワード】{keyword}
【対象症状】{target_symptom or keyword}

【ペルソナ情報】
{persona_summary if persona_summary else '（ペルソナ情報なし）'}

【商品情報】
{product_summary if product_summary else '（商品情報なし）'}

生成ルール:
- 必ず「事実 × 視点ずらし」で作る。LF8のどの欲求に向けるかを1本ごとに変え、3つの切り口（文脈の変更・物語の付加・解決策の提示）を使い分ける
- 最初の20〜30文字で目を止める。うち5本は22文字以内の超短文で切れ味勝負
- ペルソナの心の声・日常シーン（写真・鏡・抱っこ・同窓会など）に変換して自分ごと化する
- 数字と固有名詞で具体化。専門用語は翻訳。嘘・煽り・誇張・医療効果の断定は絶対にしない
- 商品情報がある場合は「価格」ではなく「得られる結果」の見せ方で活かす

出力はJSON配列のみ（説明文不要）:
[{{"copy": "コピー本文", "label": "型の名前（例: 視点転換型）", "lf8": "狙った欲求", "technique": "使った切り口", "effect": "狙える効果", "usage": "最適な使い所（媒体）"}}, ...]"""

        print(f'[copy] パス1: 15本生成中... keyword={keyword}')

        message = client.messages.create(
            model=MODEL_ID,
            thinking=THINKING_OFF,
            max_tokens=5000,
            timeout=110.0,
            system=COPYWRITING_KNOWLEDGE + SASARU_KOTOBA + YAKKIHOU_GUARD,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        response_text = extract_text(message).strip()
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if not json_match:
            raise ValueError('JSON配列が見つかりません')
        candidates = json.loads(json_match.group())
        if not isinstance(candidates, list) or len(candidates) < 5:
            raise ValueError(f'コピーが{len(candidates)}個しかありません')

        print(f'[copy] パス1完了: {len(candidates)}本 → パス2: 鬼審査員が採点・改稿中...')

        # ========== パス2: 鬼審査員が採点し、弱いものは書き直して上位10本 ==========
        judge_prompt = f"""あなたは月間3億PVメディアの編集長を務めた、日本一厳しいコピー審査員です。
以下の15本のキャッチコピー候補を審査してください。対象:「{keyword}」に悩むお客様。

【ペルソナ】
{persona_summary if persona_summary else '（一般的なサロン顧客）'}

【候補】
{json.dumps(candidates, ensure_ascii=False)}

審査ルール:
1. 各コピーを5軸で採点: 自分ごと化(そのお客様の日常シーンが浮かぶか) / 具体性(数字・固有名詞) / 意外性(視点ずらしの効き) / 切れ味(最初の20文字で目が止まるか) / 安全性(薬機法・誇張なし)
2. 合計90点未満のコピーは、事実を変えずにあなたが書き直して90点以上にする（視点ずらし・数字の具体化・語感の強化を使う）
3. 似たコピーは1本に統合し、最終的に上位10本だけを score の高い順に返す
4. ありきたりな「〜しませんか？」「〜をあなたへ」の羅列は減点。プロの一撃だけを残す

出力はJSON配列のみ:
[{{"copy": "最終コピー", "label": "型の名前", "effect": "狙える効果", "usage": "最適な使い所", "score": 95, "lf8": "狙った欲求"}}, ...]"""

        message2 = client.messages.create(
            model=MODEL_ID,
            thinking=THINKING_OFF,
            max_tokens=4000,
            timeout=110.0,
            system=SASARU_KOTOBA + YAKKIHOU_GUARD,
            messages=[{'role': 'user', 'content': judge_prompt}],
        )

        response_text2 = extract_text(message2).strip()
        json_match2 = re.search(r'\[[\s\S]*\]', response_text2)
        if json_match2:
            judged = json.loads(json_match2.group())
            if isinstance(judged, list) and len(judged) >= 5:
                copies = judged
            else:
                copies = candidates[:10]
        else:
            # 審査に失敗してもパス1の結果は返す
            copies = candidates[:10]

        # IDを振り直す
        for i, c in enumerate(copies):
            c['id'] = i + 1

        print(f'[copy] 2段ループ完了: {len(copies)}本のキャッチコピー')
        return copies

    except Exception as e:
        print(f'[copy] Claude APIエラー: {e} → ルールベース版にフォールバック')
        return generate_catchcopy_fallback(keyword, target_symptom)


def generate_catchcopy_fallback(keyword, target_symptom=''):
    """ルールベース版のキャッチコピー生成（フォールバック用）"""
    symptom = target_symptom or keyword
    copies = []

    for i, ct in enumerate(COPY_TYPES):
        copy = {
            'id': i + 1,
            'type': ct['type'],
            'label': ct['label'],
            'copy': ct['template'].format(keyword=symptom),
            'effect': ct['effect'],
            'usage': ct['usage'],
        }
        copies.append(copy)

    return copies
