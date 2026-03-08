"""
AI コピーライティングモジュール（Claude API連携）

Claude APIを使用して、ペルソナと商品情報から
AIドリブンのキャッチコピーを生成する。
エラー時はルールベース版にフォールバック。
"""

import json
import os
import re

from knowledge_base import COPYWRITING_KNOWLEDGE

# ルールベースのフォールバック用定義
COPY_TYPES = [
    {
        'type': 'loss_aversion', 'label': '損失回避型',
        'brain_target': '🧠 爬虫類脳（生存本能）',
        'template': 'その{keyword}、放置していませんか？ 3年後のあなたの体は…',
        'principle': '人は得る喜びより「失う恐怖」の方が2倍強く反応する',
        'usage': 'SNS投稿の1行目、チラシの見出しに最適',
    },
    {
        'type': 'specific_number', 'label': '具体数字型',
        'brain_target': '🧠 人間脳（論理・分析）',
        'template': '{keyword}に悩む方の92%が「もっと早く来ればよかった」と言います',
        'principle': '具体的な数字は信頼性と説得力を高める',
        'usage': 'ホットペッパーのキャッチコピー、LPに最適',
    },
    {
        'type': 'curiosity', 'label': '好奇心型',
        'brain_target': '🧠 哺乳類脳（感情・興味）',
        'template': '実は{keyword}の本当の原因、ほとんどの人が知りません',
        'principle': '「知りたい」という欲求は行動の強力なトリガー',
        'usage': 'Threads投稿、Instagram投稿に最適',
    },
    {
        'type': 'social_proof', 'label': '社会的証明型',
        'brain_target': '🧠 哺乳類脳（帰属欲求）',
        'template': '「なぜこんなに予約が取れないの？」{keyword}専門で口コミ評価No.1の理由',
        'principle': 'みんなが選んでいるものを自分も選びたい心理（バンドワゴン効果）',
        'usage': 'ホットペッパー、Googleビジネスプロフィールに最適',
    },
    {
        'type': 'sensation', 'label': '体感型',
        'brain_target': '🧠 爬虫類脳（身体感覚）',
        'template': '朝起きた瞬間のズーンと重い{keyword}…もう何年我慢していますか？',
        'principle': '体感を言語化すると「この人はわかってくれている」と感じる',
        'usage': 'SNS共感投稿、カウンセリングトークに最適',
    },
    {
        'type': 'return', 'label': '回帰型',
        'brain_target': '🧠 哺乳類脳（ノスタルジー）',
        'template': 'あの頃のように、{keyword}を気にせず笑える毎日を取り戻しませんか？',
        'principle': '「あの頃に戻りたい」という感情は行動の強い動機になる',
        'usage': '40代以上向けのSNS投稿、チラシに最適',
    },
    {
        'type': 'authority', 'label': '専門家型',
        'brain_target': '🧠 人間脳（信頼・権威）',
        'template': '施術歴15年・累計3,000人以上を見てきたプロが、{keyword}について断言します',
        'principle': '専門家の発言は「権威性」として無条件に信頼されやすい',
        'usage': 'プロフィール、固定投稿、自己紹介に最適',
    },
    {
        'type': 'alternative', 'label': '二者択一型',
        'brain_target': '🧠 人間脳（選択の簡略化）',
        'template': '{keyword}と一生付き合うか、3ヶ月で卒業するか。あなたはどっち？',
        'principle': '選択肢を2つに絞ると脳は決断しやすくなる',
        'usage': 'エンゲージメント投稿、クロージングトークに最適',
    },
    {
        'type': 'negation', 'label': '否定形型',
        'brain_target': '🧠 爬虫類脳（危機回避）',
        'template': '{keyword}で悩んでいる人、絶対にコレだけはやめてください',
        'principle': '「やめて」「ダメ」という禁止ワードは注意を強制的に引く',
        'usage': 'SNS拡散狙い投稿、バズ投稿に最適',
    },
    {
        'type': 'empathy', 'label': '共感型',
        'brain_target': '🧠 哺乳類脳（共感・安心）',
        'template': '「{keyword}がツラい」って、なかなか周りにはわかってもらえないですよね',
        'principle': '「わかってもらえた」という感覚は最強の信頼構築手段',
        'usage': 'ストーリー投稿、LINE配信、初回接客トークに最適',
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
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            timeout=50.0,
            system=COPYWRITING_KNOWLEDGE,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        response_text = message.content[0].text.strip()
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
            'brain_target': ct['brain_target'],
            'copy': ct['template'].format(keyword=symptom),
            'principle': ct['principle'],
            'usage': ct['usage'],
        }
        copies.append(copy)

    return copies
