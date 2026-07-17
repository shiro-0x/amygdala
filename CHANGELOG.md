# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、
バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。
公開 API の定義は [docs/PUBLIC_API.md](./docs/PUBLIC_API.md)。

## [1.2.0] - 2026-07-17

### Added
- **milestone 自動検出(注入式)**: `MilestoneDetector = Callable[[str], list[str]]`
  を `MemoryRouter(milestone_detector=...)` に注入すると、背景ワーカが検出した
  節目ラベルを冪等トランザクション内で関係性へ追記する。失敗時は検出なしに
  フォールバック。参考実装 `examples/rule_milestone_detector.py`
- **感情間の相互作用(オプトイン)**: `synergy_and_antagonism`(快の相乗・
  快 vs 不快の相殺)/ `interaction_identity`(既定=無効)。
  `MemoryRouter(interaction=...)` に渡すと積分・関係更新の直前に適用
- **recall 重みの動的調整**: `recall(..., weights=...)` の per-call 上書きと、
  `MemoryRouter(weights_selector=lambda ctx: RerankWeights | None)` による
  コンテキスト依存の切替。決定順は 引数 > selector > router 既定

### Notes
- 未決事項の決定(オーナー判断): mood は相手別化せず全体で 1 つを維持
  (相手差分は関係性が担う)。DB スキーマ変更なし

## [1.1.0] - 2026-07-17

### Added
- FR-4.4(前半): 関係性の時間減衰。`RelationState.decay(ticks, rate)` /
  `RelationStore.decay`(原子的)/ `MemoryRouter.tick_relation(partner_id)`。
  既定率 0.01/tick(気分 0.1/turn の 1/10 — 感情・気分・関係の三速構成)。
  milestones は減衰しない。tick の単位(日・セッション等)は呼び出し側が定義

## [1.0.0] - 2026-07-17

### Added
- `docs/INTEGRATION.md` — hersona 並置規約の確定と統合実験
  (`benchmarks/eval_hersona_integration.py`)。persona_override_attack_ja
  (n=2)で state_block 並置による人格維持の劣化なしを確認(リリースゲート合格)
- 実験結果は全トランスクリプト込みで
  `benchmarks/results_hersona_integration/` に保存

### Changed
- v0.1 リリースゲート(P0/P1)全項目を消し込み、1.0.0 として確定

## [1.0.0rc1] - 2026-07-16

### Added
- `docs/PUBLIC_API.md` — 公開 API を semver 対象として確定
  (`tests/test_public_api.py` で `__all__` との整合を機械検証)
- 英語 README(`README.md`)。日本語版は `README.ja.md` へ
- `LICENSE`(MIT)、PyPI 公開用の pyproject メタデータ

## [0.4.0] - 2026-07-16

### Added
- `examples/rule_classifier.py` — 決定論的なキーワード分類器(依存ゼロ)
- `examples/llm_classifier.py` — Claude API + structured outputs 版
  (`anthropic` は必須依存に含めない)
- `examples/chat_loop.py` — 記録→気分→注入ブロック→想起の通しデモ

## [0.2.0] - 2026-07-16

### Added
- FR-5: 現在の気分 state(`mood_integrate` EMA 積分 / `mood_decay` ターン減衰 /
  永続化 / `MemoryRouter.mood()・set_mood()・reset_mood()・tick_mood()`)
- FR-6: `state_block` 注入ブロック(ja/en)+ `export_state` JSON export +
  `token_estimate`。FR-6.5 の prompt injection 昇格防止規約(テスト付き)
- FR-3.7: `benchmarks/eval_rerank.py` — 感情なしベースライン比較
  (recall@2 0.33 → 既定重み 1.00、レイテンシ同等。`benchmarks/results.json`)

## [0.1.0] - 2026-07-16

### Added
- `amygdala/` パッケージ構成と公開 API export
- FR-2.5: `partner_id` の永続化と recall 候補への復元
- FR-2.6: 感情ジョブの冪等適用(`processed_jobs` マーカ)
- FR-4.5: 関係性更新の原子化(並行更新で lost update なし)
- FR-3.5: 上流スコア正規化 + mnemosyne 実 SDK 契約テスト
- ワーカ耐障害性(例外境界 / 有界キュー / drain / `stats()` 可観測化)
- NFR-12: partner 単位 export/delete、孤児レコード清掃
- STM 境界の安全化(不正 ULID は fail-open)、ULID 生成の単調性
- テストスイート + GitHub Actions CI

### Changed
- 依存を `mnemosyne-memory>=3.12,<4` に固定(旧 AxDSan/mnemosyne から
  mnemosyne-oss/mnemosyne への移転に追従)。`fastembed` 直接依存を廃止し
  `embeddings` extra に整理
