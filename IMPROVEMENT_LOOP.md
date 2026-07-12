# 改善ループ運転指示書（AIスタッフルーム）

## ゴール
オーナー（堀優介）が「改善の余地がもう無い」と言える100点の受講生向けツールにする。
判断基準は常に**顧客目線**（非ITのサロンオーナーが迷わない・現場で使える・刺さる成果物）。

## 作業の約束事
- 1項目ずつ: 実装 → ローカル検証 → `git commit & push` → `vercel deploy --prod --yes` → 本番確認
- ローカル検証: `export $(grep ANTHROPIC_API_KEY ~/Claude/hpb-shindan/.env | head -1 | tr -d ' ') && PORT=8899 python3 app.py`
- JS検証: scriptタグ抽出→`node --check`。Python: `ast.parse`
- モデル/共通プロンプトは config.py（MODEL_ID, THINKING_OFF, extract_text, YAKKIHOU_GUARD, SASARU_KOTOBA, COUNSELING_9STEP, EDUCATION_6STEP）
- 機能名は業界の自然な言葉（「価格設定を決める」式）。誇張・薬機法NG表現は出さない
- Vercel maxDuration=300秒 / コピー生成は2段ループで2〜3分かかる前提

## バックログ（優先順）
1. [x] 生成待ちの経過秒数表示（台本/LINE/コピー。「壊れた？」と思わせない）
2. [x] 自店プロフィール登録（業種・店名・地域・強み・実績数字をlocalStorage保存→全生成APIに salon_profile として注入。固有名詞と数字で成果物の精度UP）
3. [x] エラー時のUX（alert廃止→画面内メッセージ＋「もう一度試す」ボタン）
4. [x] 再生成の世代比較（前回の結果を残して並べる・採用ボタン)
5. [x] 初回ミニチュートリアル（初アクセス時に「まず🔍から3分で体験」）
6. [x] 当たりコピーのフィードバック記録（使った結果を記録→勝ちスワイプとして生成プロンプトに還元)
7. [x] リサーチ源の強化（Googleサジェスト追加・知恵袋依存の低減）
8. [x] ロープレ音声対応（Web Speech APIで音声入力＋お客様AIの読み上げ）
9. [ ] 全体UI磨き込み（実機スクショを見ながらの微調整）

## 完了記録
- 済: 単体利用モード / 自動保存(localStorage) / 印刷・PDF出力 / 一括コピー / 命名の平易化 / サロン調配色 / コピー2段ループ(刺さる言葉+鬼審査員)
