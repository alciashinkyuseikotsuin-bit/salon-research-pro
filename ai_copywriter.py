"""
AI コピーライティングモジュール（Claude API連携）

Claude APIを使用して、ペルソナと商品情報から
AIドリブンのキャッチコピーを生成する。
エラー時はルールベース版にフォールバック。
"""

import json
from config import MODEL_ID, THINKING_OFF, extract_text
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

        user_prompt = f"""以下の情報をもとに、「{keyword}」専門サロンの集客用キャッチコピーを10個生成してください。

【キーワード】{keyword}
【対象症状】{target_symptom or keyword}

【ペルソナ情報】
{persona_summary if persona_summary else '（ペルソナ情報なし）'}

【商品情報】
{product_summary if product_summary else '（商品情報なし）'}

リサーチで得られた実際の悩みの表現やペルソナの心の声を反映させ、
各コピーは10タイプすべてを1つずつ網羅してください。
商品情報がある場合は、価格・回数・期間を具体的に含めてください。
出力はJSON配列のみ（説明文不要）。"""

        print(f'[copy] Claude APIでコピー生成中... keyword={keyword}')

        message = client.messages.create(
            model=MODEL_ID,
        thinking=THINKING_OFF,
            max_tokens=4000,
            timeout=50.0,
            system=COPYWRITING_KNOWLEDGE,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        response_text = extract_text(message).strip()
        print(f'[copy] Claude API応答取得 ({len(response_text)}文字)')

        # JSONを抽出
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if not json_match:
            raise ValueError('JSON配列が見つかりません')

        copies = json.loads(json_match.group())

        # バリデーション
        if not isinstance(copies, list) or len(copies) < 5:
            raise ValueError(f'コピーが{len(copies)}個しかありません')

        # IDを振り直す
        for i, c in enumerate(copies):
            c['id'] = i + 1

        print(f'[copy] AI生成完了: {len(copies)}個のキャッチコピー')
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
