"""
AI ペルソナ生成モジュール（Claude API連携）

Claude APIを使用して、リサーチ結果からAI駆動のペルソナを生成する。
エラー時はルールベース版にフォールバック。
"""

import json
from config import MODEL_ID, THINKING_OFF, extract_text
import os
import re

from knowledge_base import PERSONA_KNOWLEDGE

# ルールベースのフォールバック用定義
PERSONA_TYPES = [
    {
        'type': 'ideal', 'type_label': '理想追求型',
        'template': {
            'age': '30代前半', 'gender': '女性', 'occupation': '会社員',
            'family': '独身・一人暮らし',
            'daily_pattern': '仕事帰りにジムに通うが、{keyword}が気になり集中できない',
            'tried_solution': 'セルフケアやYouTubeの動画を試したが、根本的な改善には至っていない',
            'inner_voice': 'もっと自信を持ちたい…{keyword}さえ良くなれば、もっと積極的になれるのに',
        }
    },
    {
        'type': 'urgent', 'type_label': '緊急型',
        'template': {
            'age': '40代後半', 'gender': '男性', 'occupation': '営業職',
            'family': '妻と中学生の子供1人',
            'daily_pattern': '外回りの営業で1日中歩き回り、{keyword}が悪化して仕事に支障が出ている',
            'tried_solution': '整形外科で痛み止めと湿布をもらったが一時的な効果しかなかった',
            'inner_voice': '来週の大事なプレゼンまでに何とかしたい…このままじゃ仕事を休むしかない',
        }
    },
    {
        'type': 'complex', 'type_label': 'コンプレックス型',
        'template': {
            'age': '20代後半', 'gender': '女性', 'occupation': '事務職',
            'family': '実家暮らし',
            'daily_pattern': '人目が気になり、外出時は常に{keyword}を隠そうとしてしまう',
            'tried_solution': '市販の商品をいくつも試したが効果がなく、お金だけが消えていった',
            'inner_voice': '誰にも相談できない…友達と写真を撮るのも怖い。いつまでこんな思いをすればいいの',
        }
    },
    {
        'type': 'chronic', 'type_label': '慢性型',
        'template': {
            'age': '50代前半', 'gender': '女性', 'occupation': 'パート勤務',
            'family': '夫と成人した子供2人',
            'daily_pattern': '朝起きた瞬間から{keyword}を感じ、家事をするのも一苦労の毎日',
            'tried_solution': '10年以上いろんな病院や治療院を回ったが、どこでも「様子を見ましょう」と言われるだけ',
            'inner_voice': 'もう何年もこの辛さと付き合ってる…諦めるしかないのかな。でも本当はもっと楽に動きたい',
        }
    },
    {
        'type': 'isolated', 'type_label': '孤立型',
        'template': {
            'age': '30代後半', 'gender': '女性', 'occupation': '専業主婦',
            'family': '夫と幼児2人',
            'daily_pattern': '育児に追われ自分の時間がなく、{keyword}について調べる余裕もない',
            'tried_solution': 'ネットで調べても情報が多すぎて何が正しいかわからず、病院では「異常なし」と言われた',
            'inner_voice': 'この辛さをわかってくれる人がいない…夫に言っても「気のせいでしょ」で終わる',
        }
    },
]

NAMES = ['佐藤 美咲', '田中 健太', '鈴木 あかり', '高橋 洋子', '伊藤 さやか']


def generate_personas_ai(keyword, target_symptom='', search_results=None):
    """
    Claude APIを使ってペルソナを生成する。
    エラー時はルールベース版にフォールバック。
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('[persona] ANTHROPIC_API_KEY未設定 → ルールベース版で生成')
        return generate_personas_fallback(keyword, target_symptom)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # リサーチ結果を高優先度順にソートして要約
        research_summary = ''
        if search_results:
            sorted_results = sorted(
                search_results,
                key=lambda r: r.get('analysis', {}).get('total_score', 0),
                reverse=True
            )
            top_results = sorted_results[:10]
            for i, r in enumerate(top_results, 1):
                title = r.get('title', '')
                text = r.get('full_text', r.get('snippet', ''))[:200]
                score_info = ''
                priority_label = ''
                if 'analysis' in r:
                    a = r['analysis']
                    score_info = f" [スコア: 緊急性{a.get('urgency',{}).get('score',0)}/深さ{a.get('depth',{}).get('score',0)}/コンプレックス{a.get('complex',{}).get('score',0)}]"
                    priority_label = f" 【{a.get('priority', '')}】" if a.get('priority') else ''
                research_summary += f'{i}. {title}{priority_label}{score_info}\n{text}\n\n'

        user_prompt = f"""以下の情報をもとに、プロのマーケター目線で「{keyword}」に悩むサロンのターゲットペルソナを5人生成してください。

【キーワード】{keyword}
【対象症状】{target_symptom or keyword}

【リサーチ結果（Yahoo!知恵袋から取得した実際の悩み - 高優先度順）】
{research_summary if research_summary else '（リサーチ結果なし — 一般的な知識で生成してください）'}

重要な指示:
- 上位の高優先度結果（緊急性・深さ・コンプレックスのスコアが高いもの）を特に重視してください
- プロのマーケターとして、「この人にどう商品を届けるか」という視点でペルソナを設計してください
- リサーチ結果に含まれる実際の悩みの表現や感情を反映させてください
- 各ペルソナが将来の商品設計やコピーライティングに直結するよう、購買動機や支払い意欲も考慮してください
出力はJSON配列のみ（説明文不要）。"""

        print(f'[persona] Claude APIでペルソナ生成中... keyword={keyword}')

        message = client.messages.create(
            model=MODEL_ID,
        thinking=THINKING_OFF,
            max_tokens=4000,
            timeout=50.0,
            system=PERSONA_KNOWLEDGE,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        response_text = extract_text(message).strip()
        print(f'[persona] Claude API応答取得 ({len(response_text)}文字)')

        # JSONを抽出
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if not json_match:
            raise ValueError('JSON配列が見つかりません')

        personas = json.loads(json_match.group())

        # バリデーション
        if not isinstance(personas, list) or len(personas) < 3:
            raise ValueError(f'ペルソナが{len(personas)}人しかありません')

        # IDを振り直す
        for i, p in enumerate(personas):
            p['id'] = i + 1

        print(f'[persona] AI生成完了: {len(personas)}人のペルソナ')
        return personas

    except Exception as e:
        print(f'[persona] Claude APIエラー: {e} → ルールベース版にフォールバック')
        return generate_personas_fallback(keyword, target_symptom)


def generate_personas_fallback(keyword, target_symptom=''):
    """ルールベース版のペルソナ生成（フォールバック用）"""
    symptom = target_symptom or keyword
    personas = []

    for i, pt in enumerate(PERSONA_TYPES):
        t = pt['template']
        persona = {
            'id': i + 1,
            'name': NAMES[i],
            'type': pt['type'],
            'type_label': pt['type_label'],
            'age': t['age'],
            'gender': t['gender'],
            'occupation': t['occupation'],
            'family': t['family'],
            'daily_pattern': t['daily_pattern'].format(keyword=symptom),
            'tried_solution': t['tried_solution'],
            'inner_voice': t['inner_voice'].format(keyword=symptom),
        }
        personas.append(persona)

    return personas
