"""
Googleサジェスト取得モジュール

実際にGoogleで検索されている関連ワードを取得する。
リサーチの「お客様が使う言葉」の裏付けと、次のリサーチ候補の提案に使う。
"""

import requests


def fetch_google_suggest(keyword, max_results=10):
    """キーワードのGoogleサジェスト（関連検索ワード）を取得する"""
    try:
        r = requests.get(
            'https://www.google.com/complete/search',
            params={'client': 'firefox', 'hl': 'ja', 'q': keyword},
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},
            timeout=8,
        )
        r.encoding = r.apparent_encoding or 'shift_jis'
        data = r.json()
        suggestions = [s.strip() for s in data[1] if s and s.strip() != keyword]
        return suggestions[:max_results]
    except Exception as e:
        print(f'[suggest] 取得エラー: {e}')
        return []
