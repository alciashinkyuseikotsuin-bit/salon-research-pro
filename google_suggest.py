"""
Googleサジェスト取得モジュール（標準ライブラリのみ使用）

実際にGoogleで検索されている関連ワードを取得する。
リサーチの「お客様が使う言葉」の裏付けと、次のリサーチ候補の提案に使う。
"""

import json
import urllib.parse
import urllib.request


def fetch_google_suggest(keyword, max_results=10):
    """キーワードのGoogleサジェスト（関連検索ワード）を取得する"""
    try:
        url = 'https://www.google.com/complete/search?' + urllib.parse.urlencode({
            'client': 'firefox', 'hl': 'ja', 'q': keyword,
        })
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or 'shift_jis'
        try:
            text = raw.decode(charset)
        except (UnicodeDecodeError, LookupError):
            text = raw.decode('utf-8', errors='replace')
        data = json.loads(text)
        suggestions = [s.strip() for s in data[1] if s and s.strip() != keyword]
        return suggestions[:max_results]
    except Exception as e:
        print(f'[suggest] 取得エラー: {e}')
        return []
