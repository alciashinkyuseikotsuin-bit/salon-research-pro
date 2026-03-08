"""
松竹梅 商品設計モジュール（ルールベース）

Obsidian知識ベース:
- 売上 = 新規数 x 客単価 x リピート回数
- LTVを最速で上げる: 客単価とリピート回数をセットで売る
- 18万〜50万円のコース設計が基本
- 梅（ダウンセル）: 体験3回お試し
- 竹（メイン）: 本命商品。一番売りたい内容と金額
- 松（アンカリング）: 竹が安く見えるための高額商品
- アンカリング: 提示金額の約2.5倍の合計金額を見せる

新フロー:
  ③単価シミュレーション → 1回あたりの単価が決まる
  ④商品設計 → 単価 × 回数 = 竹コースの合計金額 → 松・梅を自動設計
"""

from typing import Dict, List, Optional
import math


# ============================================================
# 心理的価格算出ロジック
# ============================================================

def suggest_psychological_price(raw_price: int) -> Dict:
    """
    計算上の合計金額から、心理的に安く見える価格を提案する

    端数心理効果：
    - X9,800円（198,000円 → 20万円未満に見える）
    - X8,000円（178,000円 → 18万円に見える）
    - 端数をつけることで割引感を演出

    Args:
        raw_price: 計算上の合計金額

    Returns:
        推奨価格の情報
    """
    suggestions = []

    if raw_price < 30000:
        # 3万未満: X,800円パターン
        base = (raw_price // 1000) * 1000
        s1 = base - 200  # X,800円
        if s1 > 0 and s1 != raw_price:
            suggestions.append({
                'price': s1,
                'display': f'{s1:,}円',
                'reason': '端数心理効果（千円未満の「800」で割安感を演出）',
            })

    elif raw_price < 100000:
        # 3万〜10万: X9,800円パターン
        base_10k = raw_price // 10000
        s1 = (base_10k) * 10000 - 200  # X9,800円
        s2 = base_10k * 10000 + 8000  # XX,8000円
        if s1 > 0 and abs(s1 - raw_price) / raw_price < 0.15:
            suggestions.append({
                'price': s1,
                'display': f'{s1:,}円',
                'reason': f'{(base_10k) * 10000 // 10000}万円を切る「9,800」で割安感を演出',
            })
        if abs(s2 - raw_price) / raw_price < 0.1:
            suggestions.append({
                'price': s2,
                'display': f'{s2:,}円',
                'reason': 'キリの良い数字で信頼感を演出',
            })

    elif raw_price < 200000:
        # 10万〜20万: 10万台のX9,800円 or X8,000円
        base_10k = raw_price // 10000
        # X9,800円パターン（切り下げ）
        s1 = (base_10k) * 10000 - 200
        # X8,000円パターン
        s2 = (base_10k - 1) * 10000 + 8000 if base_10k > 10 else base_10k * 10000 + 8000
        # X0,000円のキリ番パターン
        s3 = base_10k * 10000

        if abs(s1 - raw_price) / raw_price < 0.1:
            suggestions.append({
                'price': s1,
                'display': f'{s1:,}円',
                'reason': f'{base_10k}万円を切る価格で心理的ハードルを下げる',
            })
        if abs(s2 - raw_price) / raw_price < 0.1:
            suggestions.append({
                'price': s2,
                'display': f'{s2:,}円',
                'reason': '「8,000」で安定感のある印象を与える',
            })

    elif raw_price < 500000:
        # 20万〜50万: X8,000円 or X9,000円
        base_10k = raw_price // 10000
        s1 = base_10k * 10000 - 2000  # X8,000円
        s2 = base_10k * 10000  # キリ番
        s3 = (base_10k - 1) * 10000 + 8000  # 一つ下のX8,000円

        for s, reason in [
            (s1, f'{base_10k}万円を切る「8,000」で割安感'),
            (s3, f'{base_10k - 1}万8千円で大台を下回る印象'),
        ]:
            if s > 0 and abs(s - raw_price) / raw_price < 0.1:
                suggestions.append({
                    'price': s,
                    'display': f'{s:,}円',
                    'reason': reason,
                })

    else:
        # 50万超: X万円
        base_man = raw_price // 10000
        s1 = base_man * 10000
        s2 = (base_man - 1) * 10000 + 8000
        if abs(s1 - raw_price) / raw_price < 0.1:
            suggestions.append({
                'price': s1,
                'display': f'{s1:,}円',
                'reason': 'キリの良い金額で分かりやすさを重視',
            })

    # 重複排除 & 上位2つに限定
    seen = set()
    unique = []
    for s in suggestions:
        if s['price'] not in seen and s['price'] != raw_price and s['price'] > 0:
            seen.add(s['price'])
            unique.append(s)
    return unique[:2]


# ============================================================
# 業種別 商品テンプレート
# ============================================================

PRODUCT_TEMPLATES = {
    'pain': {
        'service_name': '根本改善プログラム',
        'pine_features': [
            '週2回の施術（月8回）',
            '完全オーダーメイドの施術プラン',
            'LINEでの毎日の経過サポート',
            'セルフケア動画（専用撮影）',
            '姿勢・歩行分析レポート（月1回）',
            '再発防止メンテナンスプラン付き',
            '優先予約枠の確保',
        ],
        'bamboo_features': [
            '週1回の施術',
            'カスタマイズ施術プラン',
            'LINEでの質問サポート',
            'セルフケア指導（来院時）',
            '中間チェック＆プラン調整',
        ],
        'plum_features': [
            '原因特定のための検査・カウンセリング',
            '施術体験',
            '改善プランのご提案',
        ],
        'guarantee': '改善を実感できなければ追加施術を無料で提供',
    },
    'posture': {
        'service_name': '姿勢改善プログラム',
        'pine_features': [
            '週2回の施術＆トレーニング',
            'AI姿勢分析（月1回）',
            'パーソナルトレーニング指導',
            'LINEでの姿勢チェック（写真添削）',
            'ビフォーアフター写真撮影',
            'メンテナンスプラン付き',
        ],
        'bamboo_features': [
            '週1回の施術',
            '姿勢分析レポート',
            'セルフケアエクササイズ指導',
            '中間チェック',
        ],
        'plum_features': [
            '姿勢の歪みチェック',
            '施術体験',
            '改善プランの提案',
        ],
        'guarantee': '姿勢の変化を実感できなければ追加施術無料',
    },
    'beauty': {
        'service_name': '美容改善プログラム',
        'pine_features': [
            '週2回の施術',
            'フェイシャル＆ボディのトータルケア',
            'ホームケア化粧品セット付き',
            'LINEでのスキンケア相談',
            'ビフォーアフター写真撮影',
            '食事・生活習慣アドバイス',
        ],
        'bamboo_features': [
            '週1回の施術',
            '肌・体質分析',
            'ホームケアアドバイス',
            '経過チェック',
        ],
        'plum_features': [
            'カウンセリング＆肌分析',
            '施術体験',
            '改善プランのご提案',
        ],
        'guarantee': '変化を実感できなければ追加施術無料',
    },
    'mental': {
        'service_name': '心身バランス回復プログラム',
        'pine_features': [
            '週2回の施術',
            '自律神経測定（月1回）',
            '生活習慣改善サポート',
            'LINEでの体調相談',
            '睡眠改善プログラム',
        ],
        'bamboo_features': [
            '週1回の施術',
            '自律神経チェック',
            'セルフケア指導',
            '経過チェック＆プラン調整',
        ],
        'plum_features': [
            '自律神経チェック＆カウンセリング',
            '施術体験',
            '改善プランのご提案',
        ],
        'guarantee': '体調の変化を実感できなければ追加施術無料',
    },
}

DEFAULT_TEMPLATE = PRODUCT_TEMPLATES['pain']


def design_products(
    keyword: str,
    target_symptom: str = '',
    unit_price: int = 0,
    bamboo_sessions: int = 12,
    bamboo_duration: str = '3ヶ月',
    category: str = '',
) -> Dict:
    """
    単価ベースで松竹梅の商品を設計する

    Args:
        keyword: キーワード
        target_symptom: ターゲット症状
        unit_price: 1回あたりの施術単価（③で算出）
        bamboo_sessions: 竹コースの施術回数
        bamboo_duration: 竹コースの期間（例: "3ヶ月"）
        category: カテゴリ（空の場合はキーワードから自動判定）

    Returns:
        松竹梅の商品設計（心理的価格提案付き）
    """
    # カテゴリ判定
    if not category:
        category_keywords = {
            'pain': ['痛', '腰', '肩', '首', '膝', 'ヘルニア', '神経痛', '頭痛'],
            'posture': ['猫背', 'O脚', '骨盤', '姿勢', '歪み', '反り腰'],
            'beauty': ['小顔', 'エラ', 'たるみ', 'シワ', 'ニキビ', '肌', '美容', '痩'],
            'mental': ['自律神経', '不眠', 'ストレス', 'うつ', '疲労', 'めまい'],
        }
        best_cat = 'pain'
        best_score = 0
        for cat, words in category_keywords.items():
            score = sum(len(w) for w in words if w in keyword)
            if score > best_score:
                best_score = score
                best_cat = cat
        category = best_cat

    template = PRODUCT_TEMPLATES.get(category, DEFAULT_TEMPLATE)
    symptom = target_symptom if target_symptom else keyword

    # === 竹コースの合計金額 ===
    bamboo_raw_price = unit_price * bamboo_sessions
    bamboo_suggestions = suggest_psychological_price(bamboo_raw_price)

    # === 松コース（竹の2.5倍） ===
    pine_multiplier = 2.5
    pine_raw_price = int(bamboo_raw_price * pine_multiplier)
    pine_sessions = bamboo_sessions * 2  # 竹の倍の回数
    pine_suggestions = suggest_psychological_price(pine_raw_price)

    # === 梅コース（体験3回） ===
    plum_sessions = 3
    plum_raw_price = unit_price * plum_sessions
    plum_suggestions = suggest_psychological_price(plum_raw_price)

    # 1日あたりの換算
    bamboo_duration_days = _parse_duration_to_days(bamboo_duration)
    per_day = int(bamboo_raw_price / bamboo_duration_days) if bamboo_duration_days > 0 else 0

    result = {
        'category': category,
        'service_name': template['service_name'],
        'symptom': symptom,
        'unit_price': unit_price,
        'unit_price_display': f'{unit_price:,}円',

        'pine': {
            'rank': '松',
            'name': f'プレミアム完全{symptom}改善コース',
            'raw_price': pine_raw_price,
            'raw_price_display': f'{pine_raw_price:,}円',
            'suggested_prices': pine_suggestions,
            'sessions': pine_sessions,
            'sessions_display': f'{pine_sessions}回',
            'duration': f'{int(bamboo_duration_days * 2 / 30)}ヶ月' if bamboo_duration_days > 0 else '',
            'features': template['pine_features'],
            'guarantee': template['guarantee'],
            'role': 'アンカリング商品：竹コースが「お得」に見える基準を作る',
        },

        'bamboo': {
            'rank': '竹',
            'name': f'集中{symptom}改善コース',
            'raw_price': bamboo_raw_price,
            'raw_price_display': f'{bamboo_raw_price:,}円',
            'suggested_prices': bamboo_suggestions,
            'sessions': bamboo_sessions,
            'sessions_display': f'{bamboo_sessions}回',
            'duration': bamboo_duration,
            'features': template['bamboo_features'],
            'guarantee': template['guarantee'],
            'selling_points': [
                '一番人気のコース',
                '多くの方がこのコースで改善を実感',
                '費用対効果が最も高い',
            ],
            'role': 'メイン商品：一番売りたい商品。費用対効果が最も高い',
            'per_session': f'{unit_price:,}円/回',
            'per_day': f'{per_day:,}円/日' if per_day > 0 else '',
        },

        'plum': {
            'rank': '梅',
            'name': '体験お試しコース',
            'raw_price': plum_raw_price,
            'raw_price_display': f'{plum_raw_price:,}円',
            'suggested_prices': plum_suggestions,
            'sessions': plum_sessions,
            'sessions_display': f'{plum_sessions}回',
            'duration': '3週間',
            'features': template['plum_features'],
            'role': 'ダウンセル：「まずはお試し」から始めて竹への導線を作る',
        },

        'sales_tips': {
            'presentation_order': '松→竹→梅の順に提示（アンカリング効果）',
            'closing_phrase': '「どちらのコースが良いと思いましたか？」（二者択一法）',
            'objection_handling': {
                'expensive': f'1日あたりに換算すると{per_day:,}円の投資です' if per_day > 0 else '',
                'uncertain': '改善を実感できなければ追加施術を無料で提供します',
                'time': f'週1回、たった{bamboo_duration}の投資で何年もの悩みが解決します',
            },
        },
    }

    return result


def _parse_duration_to_days(duration: str) -> int:
    """期間文字列を日数に変換"""
    import re
    m = re.search(r'(\d+)', duration)
    if not m:
        return 90  # デフォルト3ヶ月
    num = int(m.group(1))
    if 'ヶ月' in duration or '月' in duration:
        return num * 30
    elif '週' in duration:
        return num * 7
    elif '日' in duration:
        return num
    return num * 30  # デフォルトは月換算
