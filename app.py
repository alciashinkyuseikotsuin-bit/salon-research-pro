#!/usr/bin/env python3
"""
サロン向け 商品設計サポートツール（Pro版）

機能:
1. Yahoo!知恵袋リサーチ
2. AIペルソナ生成（Claude API・プロのマーケター目線）
3. 目標売上→1回あたりの単価を逆算
4. 松竹梅 商品設計（心理的価格提案付き）
5. AIキャッチコピー生成（Claude API）
"""

import json
import os
import re
import sys

from flask import Flask, request, jsonify, send_from_directory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import search_and_fetch
from analyzer import analyze_results, analyze_concern
from product_designer import design_products
from ai_product_designer import generate_products_ai
from price_calculator import calculate_pricing
from ai_persona_generator import generate_personas_ai
from ai_copywriter import generate_catchcopy_ai
from ai_search_patterns import generate_search_patterns_ai
from aramakijake_scraper import fetch_search_volume

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'static'))

PORT = int(os.environ.get('PORT', 8080))


# ========== ページ配信 ==========

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# ========== API: キーワード検索ボリューム ==========

@app.route('/api/volume')
def api_volume():
    """aramakijake.jpからキーワードの月間検索ボリュームを取得しランク評価"""
    keyword = request.args.get('keyword', '').strip()

    if not keyword:
        return jsonify({'error': 'キーワードを入力してください'}), 400

    try:
        result = fetch_search_volume(keyword)
        return jsonify(result)

    except Exception as e:
        print(f"[volume] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== API: リサーチ ==========

@app.route('/api/search')
def api_search():
    """キーワード検索API"""
    keyword = request.args.get('keyword', '').strip()

    if not keyword:
        return jsonify({'error': 'キーワードを入力してください'}), 400

    try:
        import time as _time
        start = _time.time()
        print(f"[search] キーワード: {keyword}")

        # AI検索パターン生成（擬音・二次的損失・失敗体験・真の願望）
        patterns = generate_search_patterns_ai(keyword)
        pattern_elapsed = _time.time() - start
        print(f"[search] パターン生成完了 ({pattern_elapsed:.1f}秒, source={patterns['source']})")

        raw_results = search_and_fetch(
            keyword,
            max_details=50,
            custom_suffixes=patterns['suffixes'],
        )
        elapsed = _time.time() - start
        print(f"[search] {len(raw_results)}件の投稿を取得 ({elapsed:.1f}秒)")

        analyzed = analyze_results(raw_results)
        total_elapsed = _time.time() - start
        print(f"[search] 分析完了 (合計{total_elapsed:.1f}秒)")

        return jsonify({
            'keyword': keyword,
            'results': analyzed,
            'count': len(analyzed),
        })

    except Exception as e:
        print(f"[search] エラー: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """テキスト分析API"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip() if data else ''

        if not text:
            return jsonify({'error': 'テキストを入力してください'}), 400

        segments = re.split(r'\n{2,}|_{3,}|-{3,}|={3,}', text)
        segments = [s.strip() for s in segments if len(s.strip()) > 20]

        if not segments:
            segments = [text]

        results = []
        for segment in segments:
            analysis = analyze_concern(segment)
            results.append({
                'title': segment[:80] + ('...' if len(segment) > 80 else ''),
                'url': '',
                'full_text': segment,
                'snippet': '',
                'analysis': analysis,
            })

        results.sort(key=lambda x: x['analysis']['total_score'], reverse=True)

        return jsonify({
            'results': results,
            'count': len(results),
        })

    except Exception as e:
        print(f"[analyze] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== API: 単価シミュレーション ==========

@app.route('/api/pricing', methods=['POST'])
def api_pricing():
    """目標売上→1回あたりの単価を算出するAPI"""
    try:
        data = request.get_json()

        monthly_target = data.get('monthly_target', 1000000) if data else 1000000
        working_days = data.get('working_days', 22) if data else 22
        slots_per_day = data.get('slots_per_day', 6) if data else 6

        print(f"[pricing] 目標: {monthly_target:,}円/月, {working_days}日, {slots_per_day}枠/日")

        result = calculate_pricing(
            monthly_target=monthly_target,
            working_days=working_days,
            slots_per_day=slots_per_day,
        )

        print(f"[pricing] 単価: {result['calculation']['unit_price_display']}")

        return jsonify(result)

    except Exception as e:
        print(f"[pricing] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== API: 松竹梅商品設計 ==========

@app.route('/api/product', methods=['POST'])
def api_product():
    """AI松竹梅商品設計API（Claude API連携）"""
    try:
        data = request.get_json()
        keyword = data.get('keyword', '').strip() if data else ''
        target_symptom = data.get('target_symptom', '').strip() if data else ''
        unit_price = data.get('unit_price', 0) if data else 0
        bamboo_sessions = data.get('bamboo_sessions', 12) if data else 12
        bamboo_duration = data.get('bamboo_duration', '3ヶ月') if data else '3ヶ月'
        personas = data.get('personas', []) if data else []

        if not keyword:
            return jsonify({'error': 'キーワードを入力してください'}), 400

        print(f"[product] キーワード: {keyword}, 単価: {unit_price}, 回数: {bamboo_sessions}, 期間: {bamboo_duration}, ペルソナ: {len(personas)}人")

        products = generate_products_ai(
            keyword=keyword,
            target_symptom=target_symptom,
            unit_price=unit_price,
            bamboo_sessions=bamboo_sessions,
            bamboo_duration=bamboo_duration,
            personas=personas,
        )

        print(f"[product] 商品設計完了 - 竹: {products['bamboo']['raw_price_display']}")

        return jsonify(products)

    except Exception as e:
        print(f"[product] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== API: AIペルソナ生成 ==========

@app.route('/api/persona', methods=['POST'])
def api_persona():
    """AIペルソナ生成API（Claude API連携）"""
    try:
        data = request.get_json()
        keyword = data.get('keyword', '').strip() if data else ''
        target_symptom = data.get('target_symptom', '').strip() if data else ''
        search_results = data.get('search_results', []) if data else []

        if not keyword:
            return jsonify({'error': 'キーワードを入力してください'}), 400

        print(f"[persona] キーワード: {keyword}, リサーチ結果: {len(search_results)}件")

        personas = generate_personas_ai(
            keyword=keyword,
            target_symptom=target_symptom,
            search_results=search_results,
        )

        print(f"[persona] 生成完了: {len(personas)}人のペルソナ")

        return jsonify({
            'keyword': keyword,
            'personas': personas,
            'count': len(personas),
        })

    except Exception as e:
        print(f"[persona] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== API: AIキャッチコピー生成 ==========

@app.route('/api/copywrite', methods=['POST'])
def api_copywrite():
    """AIキャッチコピー生成API（Claude API連携）"""
    try:
        data = request.get_json()
        keyword = data.get('keyword', '').strip() if data else ''
        target_symptom = data.get('target_symptom', '').strip() if data else ''
        personas = data.get('personas', []) if data else []
        products = data.get('products', None) if data else None

        if not keyword:
            return jsonify({'error': 'キーワードを入力してください'}), 400

        print(f"[copy] キーワード: {keyword}, ペルソナ: {len(personas)}人")

        copies = generate_catchcopy_ai(
            keyword=keyword,
            target_symptom=target_symptom,
            personas=personas,
            products=products,
        )

        print(f"[copy] 生成完了: {len(copies)}個のキャッチコピー")

        return jsonify({
            'keyword': keyword,
            'copies': copies,
            'count': len(copies),
        })

    except Exception as e:
        print(f"[copy] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== 起動 ==========

if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════════════════╗
║   商品設計サポートツール（Pro版）                  ║
║                                                  ║
║   ブラウザで以下にアクセスしてください:             ║
║   → http://localhost:{PORT}                       ║
║                                                  ║
║   終了: Ctrl+C                                   ║
╚══════════════════════════════════════════════════╝
""")
    app.run(host='0.0.0.0', port=PORT, debug=False)
