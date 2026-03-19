"""
aramakijake.jp スクレイピングモジュール

キーワードの月間推定検索数（Yahoo! JAPAN / Google）を取得し、
サロン集客におけるターゲットキーワードの有効性をランク評価する。
"""

import urllib.request
import urllib.parse
import re
from typing import Dict, Optional


def fetch_search_volume(keyword: str) -> Dict:
    """
    aramakijake.jp からキーワードの月間推定検索数を取得する。

    Args:
        keyword: 検索キーワード

    Returns:
        {
            'keyword': str,
            'yahoo_volume': int or None,
            'google_volume': int or None,
            'total_volume': int,
            'rank': str,           # 'S', 'A', 'B', 'C'
            'rank_label': str,     # ランクの説明
            'rank_color': str,     # 表示用カラー
            'rank_message': str,   # アドバイスメッセージ
            'ranking_data': list,  # 順位別アクセス予測 [{rank, google, yahoo}, ...]
            'has_data': bool,
        }
    """
    encoded = urllib.parse.quote(keyword)
    url = f'https://aramakijake.jp/keyword/index.php?keyword={encoded}'

    print(f'[aramakijake] 検索ボリューム取得中: {keyword}')

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'ja,en;q=0.9',
            'Referer': 'https://aramakijake.jp/',
        })

        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')

    except Exception as e:
        print(f'[aramakijake] 取得エラー: {e}')
        return _no_data_result(keyword, error=str(e))

    # データなしチェック
    if 'データが見つかりませんでした' in html:
        print(f'[aramakijake] データなし: {keyword}')
        return _no_data_result(keyword)

    # 月間推定検索数を抽出
    yahoo_vol = None
    google_vol = None

    vol_section = re.search(r'月間推定検索数([\s\S]*?)(?:で1位になるため)', html)
    if vol_section:
        nums = re.findall(r'>([\d,]+)<', vol_section.group(1))
        if len(nums) >= 2:
            yahoo_vol = _parse_num(nums[0])
            google_vol = _parse_num(nums[1])

    # 順位別アクセス予測テーブルを抽出
    ranking_data = []
    rows = re.findall(
        r'<td[^>]*>(\d+)位</td>\s*<td[^>]*>([\d,]+)</td>\s*<td[^>]*>([\d,]+)</td>',
        html
    )
    for r in rows[:10]:  # 上位10位まで
        ranking_data.append({
            'rank': int(r[0]),
            'google': _parse_num(r[1]),
            'yahoo': _parse_num(r[2]),
        })

    total = (google_vol or 0) + (yahoo_vol or 0)
    rank_info = _evaluate_rank(total)

    print(f'[aramakijake] {keyword}: Yahoo={yahoo_vol}, Google={google_vol}, Total={total}, Rank={rank_info["rank"]}')

    return {
        'keyword': keyword,
        'yahoo_volume': yahoo_vol,
        'google_volume': google_vol,
        'total_volume': total,
        **rank_info,
        'ranking_data': ranking_data,
        'has_data': True,
    }


def _parse_num(s: str) -> int:
    """カンマ付き数字を int に変換"""
    return int(s.replace(',', ''))


def _evaluate_rank(total_volume: int) -> Dict:
    """
    月間検索ボリュームからターゲットキーワードの有効性をランク評価する。

    S: 20,000以上 → 主戦場。メインターゲットにすべき
    A: 5,000〜19,999 → 合格ラインだがやや物足りない
    B: 3,000〜4,999 → ギリギリ。サブキーワードとして検討
    C: 3,000未満 → 論外。キーワードの洗い直しが必要
    """
    if total_volume >= 20000:
        return {
            'rank': 'S',
            'rank_label': '主戦場キーワード',
            'rank_color': '#dc2626',
            'rank_message': (
                'ここが主戦場です！このキーワードをメインターゲットにして '
                '知恵袋リサーチ・ペルソナ設計・商品設計を進めましょう。'
            ),
            'rank_detail': '月間検索数20,000以上。十分な市場規模があり、集客の柱になるキーワードです。',
        }
    elif total_volume >= 5000:
        return {
            'rank': 'A',
            'rank_label': '合格ライン',
            'rank_color': '#ea580c',
            'rank_message': (
                '合格ラインですが、やや物足りません。このまま進めてもOKですが、'
                'より検索ボリュームの大きい関連キーワードも検討してみてください。'
            ),
            'rank_detail': '月間検索数5,000〜19,999。ニッチだが一定の需要あり。サブキーワードとの併用が効果的。',
        }
    elif total_volume >= 3000:
        return {
            'rank': 'B',
            'rank_label': 'ギリギリ',
            'rank_color': '#ca8a04',
            'rank_message': (
                'ギリギリのラインです。サブキーワードとしてなら使えますが、'
                'メインターゲットとしては弱いです。別の切り口も検討してください。'
            ),
            'rank_detail': '月間検索数3,000〜4,999。市場は小さめ。複数キーワードを組み合わせた戦略が必要。',
        }
    else:
        return {
            'rank': 'C',
            'rank_label': 'キーワード見直し推奨',
            'rank_color': '#6b7280',
            'rank_message': (
                'このキーワードでは検索ボリュームが不足しています。'
                'キーワードを洗い直して、より多くの人が検索しているワードを見つけましょう。'
            ),
            'rank_detail': '月間検索数3,000未満。集客のメインには不向き。キーワードの再選定が必要です。',
        }


def _no_data_result(keyword: str, error: str = '') -> Dict:
    """データが取得できなかった場合の結果"""
    return {
        'keyword': keyword,
        'yahoo_volume': None,
        'google_volume': None,
        'total_volume': 0,
        'rank': '?',
        'rank_label': 'データなし',
        'rank_color': '#9ca3af',
        'rank_message': (
            f'「{keyword}」の検索ボリュームデータが見つかりませんでした。'
            'キーワードの表記を変えて再度お試しください（例: ひらがな↔カタカナ、略称↔正式名称）。'
        ),
        'rank_detail': error or 'aramakijake.jpにデータが存在しないキーワードです。',
        'ranking_data': [],
        'has_data': False,
    }
