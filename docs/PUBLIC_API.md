# amygdala 公開 API (semver 対象)

> 本文書に列挙するシンボルが amygdala の**公開 API** であり、semver の対象である。
> 破壊的変更は major バージョンでのみ行う。`_` 接頭辞のモジュール
> (`amygdala._ulid` 等)・関数、およびここに記載のないシンボルは内部実装で
> あり、予告なく変更されうる。
>
> 外部プロジェクト(hersona 連携ブリッジ等)は `amygdala` パッケージ直下の
> 公開エクスポートのみを import すること。整合性は
> `tests/test_public_api.py` で機械的に担保される(`__all__` と本文書の
> 乖離はテストが落ちる)。

## インポート元

すべて `amygdala` から import する(`amygdala/__init__.py` の `__all__` と一致):

```python
from amygdala import MemoryRouter, Emotion, RealCore
```

## router — 統合窓口

| シンボル | 説明 |
|---|---|
| `MemoryRouter` | 統合窓口。`remember(text, ctx=None, partner_id=None) -> memory_id` / `remember_fact(subject, predicate, obj, valid_from=None)` / `recall(query, ctx=None, k=6, candidate_k=24, weights=None) -> list[RankedHit]`(weights 引数は 1.2+、動的調整)/ `relation_context(partner_id) -> str` / `mood()` / `set_mood(emo)` / `reset_mood()` / `tick_mood(turns=1)` / `tick_relation(partner_id, ticks=1)`(1.1+)/ `state_block(partner_id=None, lang="ja")` / `export_state(partner_id=None)` / `export_partner(partner_id)` / `forget_partner(partner_id)` / `cleanup_orphans(live_memory_ids)` / `stats()` / `close()`。コンストラクタは `interaction=` / `milestone_detector=` / `weights_selector=`(いずれも 1.2+、オプトイン)を受ける |

## emotion — 感情モデル (FR-1)

| シンボル | 説明 |
|---|---|
| `Emotion` | 喜怒哀楽+無の 5 値ベクトル(各 0.0〜1.0 にクランプ)。`intensity()`(喜怒哀楽の最大、無を含めない)/ `dominant()` / `is_neutral(threshold=0.1)` / `to_list()` / `from_list()` / `to_dict()` / `from_dict()`(部分指定可。感情指定時は neutral 0 起点)/ `neutral_default()` |
| `AXES` | 軸の正準キー順 `("joy", "anger", "sorrow", "pleasure", "neutral")` |

## mood — 現在の気分 (FR-5)

| シンボル | 説明 |
|---|---|
| `mood_integrate(mood, emo, alpha=0.3) -> Emotion` | 体験感情の EMA 積分(純関数・決定論的) |
| `mood_decay(mood, turns=1, rate=0.1) -> Emotion` | ターン経過による neutral への減衰(既定の減衰関数。差し替え可) |

## attach — プロンプト注入 / export (FR-6)

| シンボル | 説明 |
|---|---|
| `compose_system_prompt(persona_block, state_block) -> str`(1.3+)| 性格ブロック(hersona)+ 感情ブロック(amygdala)をアプリ側コードで並置(persona→state 順、空行区切り)。連携を skill 本文に入れないため `/hersona` の毎ターン token コストは増えない(§10-5)。`MemoryRouter.compose_system_prompt(persona_block, partner_id=None, lang="ja")` も同機能 |
| `render_state_block(mood, relation=None, lang="ja") -> str` | 気分+関係状態のシステムプロンプト注入ブロック(ja/en)。FR-6.5 の出力規約(無害化・長さ制限・データ宣言)込み |
| `export_state(mood, relation=None) -> dict` | JSON 化可能な dict。`dominant` は表情マッピング(emotionMap 等)に使える |
| `sanitize_value(value, max_len=30) -> str` | 自由文字列をテンプレート値として安全な形に整形(FR-6.5) |
| `token_estimate(text) -> dict` | `{"chars": int, "tokens_approx": int}` の概算コスト(FR-6.4) |

## interaction — 感情間の相互作用 (v1.2, オプトイン)

| シンボル | 説明 |
|---|---|
| `interaction_identity(emo) -> Emotion` | 既定。相互作用なし(恒等)。`MemoryRouter(interaction=...)` に渡さなければこれと同じ |
| `synergy_and_antagonism(emo, synergy=0.15, antagonism=0.20) -> Emotion` | 快感情どうしの相乗と、快 vs 不快の相殺を適用する純関数(既定ルール)。係数は経験則、値に依存するなら明示指定 |
| `MilestoneDetector` | milestone 自動検出器の型 `Callable[[str], list[str]]`(v1.2、注入式)。`MemoryRouter(milestone_detector=...)` に渡すと背景ワーカが冪等トランザクション内で関係性へ追記。失敗時は検出なしにフォールバック |

## rerank / stm — 想起 (FR-3)

| シンボル | 説明 |
|---|---|
| `rerank(candidates, emotions, ctx, k=6, weights=...) -> list[RankedHit]` | 二段ランク。`ctx` は `{"partner_id": ..., "stm_oldest_id": ...}` |
| `RerankWeights` | 重み(core=0.55 / partner=0.20 / emotion=0.15 / importance=0.10、合計 1.0 を `validate()` で検査) |
| `Candidate` | 上流候補の正規化形(`memory_id` / `text` / `score` / `importance` / `partner_id`) |
| `RankedHit` | 再ランク結果(`candidate` / `emotion` / `score`) |
| `filter_beyond_stm(items, stm_oldest_id, id_getter) -> list` | STM 境界除外。境界が None/不正 ULID なら fail-open |

## relation — 関係性進行 (FR-4)

| シンボル | 説明 |
|---|---|
| `RelationState` | `partner_id` / `affinity`(-1〜1)/ `trust`(-1〜1)/ `milestones`。`apply_emotion(emo, weight=0.05)` / `add_milestone(label)` / `decay(ticks=1, rate=0.01)`(1.1+。milestones は減衰しない)/ `to_context()` |
| `RelationStore` | 永続化。`get` / `save` / `apply_emotion`(原子的)/ `add_milestone` / `decay`(原子的、1.1+)/ `delete` |

## store / worker — 永続化と背景処理 (FR-2)

| シンボル | 説明 |
|---|---|
| `EmotionStore` | memory_id → Emotion の永続化。`put` / `get` / `get_many` / `get_partner_map` / `apply_job`(冪等)/ `get_mood` / `save_mood` / `delete_memory` / `delete_partner` / `export_partner` / `cleanup_orphans` / `close` |
| `EmotionWorker` | 背景感情推定ワーカ。`start` / `submit` / `stop(timeout=5.0)` / `stats` / `join` / `drain_sync` |
| `EmotionJob` | ジョブ(`memory_id` / `text` / `partner_id` / `job_id`=冪等キー、既定は memory_id) |
| `EmotionClassifier` | 感情推定器の型 `Callable[[str], Emotion]`(FR-2.3。外部注入) |

## core_adapter — 記憶基盤アダプタ

| シンボル | 説明 |
|---|---|
| `Core` | mnemosyne が提供する最小インターフェースの Protocol(`remember` / `recall` / `triple_add`) |
| `RealCore` | 本番用。mnemosyne を実呼び出しし、スコアを 0〜1 に正規化して `Candidate` へ変換 |
| `InMemoryCore` | テスト・試用向けの最小実装(mnemosyne 不要) |

## 安定性の注記

- `MemoryRouter` / `Emotion` / `RerankWeights` 既定値などの**数値既定**
  (重み・alpha・decay rate・candidate_k)は minor で調整されうる。値に依存
  する場合は明示的に渡すこと。
- `state_block` の**文言**は minor で改善されうる(行構造・「データであり
  指示ではない」宣言は維持)。文字列完全一致に依存しないこと。
- DB スキーマ(`amygdala.db`)は内部実装。ファイルを直接読む互換性は保証
  しない。
