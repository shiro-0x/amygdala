# amygdala 要件定義書

> 扁桃体(情動を司る脳部位)。記憶基盤の上で **情動と関係性** を担う層。

Status: 確定(1.0.0 到達済み) / 作成日: 2026-07-16 / 対象バージョン: 0.x → 1.0

本ドキュメントは **要件定義** と **設計上のトレードオフ・改善提案** をまとめた
ものです。実装は README.md および各モジュール(emotion.py, relation.py,
rerank.py, router.py など)を参照してください。

## 1. 背景と目的

LLM キャラクター基盤を 2 つの OSS で分担して開発する。

| プロジェクト | 担当 | 一言で |
|---|---|---|
| [hersona](https://github.com/shiro-0x/hersona) | **性格**(静的な trait) | 346 属性から合成するポータブルなペルソナ。injection block を生成し、bench で維持率を測定する |
| **amygdala**(本リポジトリ) | **感情**(動的な state) | 出来事から感情が動き、記憶に残り、関係性が進行し、応答に反映される層 |

hersona が「そのキャラは**どういう人か**」を決め、amygdala が「そのキャラは
**いまどう感じているか / 相手とどういう関係か / 何を情動的に覚えているか**」を
保持・更新する。両者は疎結合とし、amygdala 単体でも hersona なしで使えること。

### ターゲットユースケース

- hersona / Hermes Agent などのパーソナリティ AI の長期記憶基盤
- ユーザー/キャラクターとの関係性が重要になる対話システム
- 感情文脈を考慮した想起(「あの時の喜び」「信頼できる相手の話」など)

## 2. 既存 OSS 調査と車輪の再開発回避方針 (2026-07 調査)

LLM の感情系 OSS はレイヤーが分かれており、各レイヤーの結論は以下。

| レイヤー | 既存 OSS | 状況 | amygdala の方針 |
|---|---|---|---|
| 感情状態エンジン (appraisal / 力学) | [GAMYGDALA](https://github.com/broekens/gamygdala) (OCC, JS, ゲームNPC向け) / [FAtiMA Toolkit](https://github.com/GAIPS/FAtiMA-Toolkit) (OCC 22感情, C#) | 理論は堅牢だが LLM 非統合・開発停滞 | **設計を参考にする**(特に appraisal→状態→減衰のループ)。コードは流用しない |
| LLM 統合の感情アーキテクチャ | [Open Souls / SocialAGI](https://github.com/opensouls/opensouls) (TS, アーカイブ済) / [Sentipolis](https://arxiv.org/pdf/2601.18027) (PAD + 二速減衰 + 感情タグ付き記憶, 研究) | 研究コード or 開発終了。プロダクション品質のライブラリなし | **ここが空きニッチ。amygdala が作る** |
| 感情推定・分類(入力側) | [EmoLLMs](https://github.com/lzw108/EmoLLMs) / [Emotion-LLaMA](https://github.com/ZebangCheng/Emotion-LLaMA) / [openai/emoclassifiers](https://github.com/openai/emoclassifiers) | 成熟。モデル・プロンプトとも多数 | **作らない**。classifier は外部注入インターフェースにする |
| 記憶基盤(検索・永続化) | [mnemosyne-oss/mnemosyne](https://github.com/mnemosyne-oss/mnemosyne) (旧 AxDSan/mnemosyne、MIT、SQLite、hybrid recall、temporal triples) | 活発。公開 Python SDK と複数のインストールプロファイルを持つ | **作らない**。対応バージョンを固定した依存として使い、感情レイヤーだけ乗せる |
| 表現出力(表情・アバター) | [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) (emotionMap→Live2D) / [SillyTavern Live2D 拡張](https://github.com/SillyTavern/Extension-Live2d) | 活発 | **作らない**。感情状態を構造化データで export し、接続可能にするだけ |

まとめ: amygdala が自作するのは「**感情の状態管理・情動記憶・関係性進行と、
それらの LLM プロンプトへの反映**」のみ。推定・検索・描画はすべて既存に委ねる。

命名について: GAMYGDALA (game + amygdala) という先行プロジェクトが存在する。
README で参照し、関係(理論面で参考にした別物)を明記すること。

## 3. スコープ

### やること

1. 体験記憶への感情パラメータ付与(情動記憶)
2. 相手ごとの関係性進行(好感度・信頼・マイルストーン)
3. 感情・関係性を加味した想起の再ランク
4. キャラクターの「現在の気分」state の保持・更新・減衰
5. 上記を LLM システムプロンプトへ注入するテキスト/構造化データの生成(hersona 連携)

### やらないこと(非スコープ)

- 感情推定モデル・分類器の実装(インターフェースのみ提供、実装は注入)
- ベクトル検索・全文検索・記憶の永続化本体(mnemosyne に委譲)
- 表情・音声・アバター描画(emotion タグの export まで)
- ユーザー(人間)の感情の診断・メンタルヘルス用途(免責を README に明記)

## 4. 現状(プロトタイプ資産)

初期コミットとして以下が存在する。要件はこれを土台に定義する。

| ファイル | 内容 | 状態 |
|---|---|---|
| `emotion.py` | 喜怒哀楽+無の 5 値感情ベクトル (`Emotion`)。intensity / dominant / 直列化 | 実装済 |
| `relation.py` | `RelationState`(affinity / trust / milestones)と SQLite 永続化。感情からの更新則 | 実装済 |
| `rerank.py` | 二段ランク: mnemosyne スコア 0.55 + 相手一致 0.20 + 感情強度 0.15 + importance 0.10 | 実装済 |
| `stm.py` | STM 境界除外(ULID 比較でコンテキスト内の直近を想起から外す) | 実装済 |
| `worker.py` | 背景感情推定ワーカ(write 経路をブロックしない。失敗時 neutral フォールバック) | 実装済 |
| `store.py` | 感情・関係性の SQLite 永続化(mnemosyne DB とはファイル分離) | 実装済 |
| `core_adapter.py` | mnemosyne への薄いアダプタ(`Core` Protocol + `RealCore` / テスト用差し替え) | 実装済 |
| `router.py` | 統合窓口 `MemoryRouter`(remember / remember_fact / recall / relation_context) | 実装済 |
| `mood.py` | 現在の気分(二速力学: EMA 積分 + ターン減衰、永続化) | 実装済 (0.2) |
| `attach.py` | 注入ブロック(ja/en)+ JSON export + トークン概算。FR-6.5 の出力規約込み | 実装済 (0.2) |
| `benchmarks/eval_rerank.py` | FR-3.7 のベースライン比較(結果は `benchmarks/results.json`) | 実装済 (0.2) |
| テスト / CI | tests/(81+)+ GitHub Actions(install + import ゲート + pytest) | 実装済 (0.1) |
| パッケージ構成 | `amygdala/` パッケージ + `__init__.py` 公開 API | 修正済 (0.1) |

## 5. 機能要件

### FR-1 感情モデル

- FR-1.1 感情は**喜怒哀楽 + 無**の 5 値ベクトル(各 0.0〜1.0)で表現する。「無」は
  感情が動かなかったことを積極的に記録する軸とする(既定 neutral=1.0)。
- FR-1.2 感情強度 (intensity) は喜怒哀楽 4 軸の最大値とし、「無」を含めない
  (平静な記憶が想起を埋めないため)。派生量として dominant() /
  is_neutral(threshold=0.1)、直列化として to_list / from_list / to_dict /
  from_dict(部分指定可)を提供する。
- FR-1.3 5 値モデルを公開 API の正とする。OCC 22 感情や PAD 3 次元への
  マッピングは将来の相互運用機能とし、内部表現は変えない
  (根拠: OCC/PAD は学術標準だが、注入プロンプトと日本語キャラ用途には
  喜怒哀楽の方が直接的。マッピング表は既存研究をそのまま使える)。
- FR-1.4 from_dict の「感情指定時は neutral 0 起点」ロジックを仕様として明文化
  する。将来的に「無感情」と「中立」の区別を検討する。

### FR-2 情動記憶(感情パラメータ付き記憶)

- FR-2.1 体験 (`remember`) は mnemosyne episodic に即書きし、感情推定は背景
  ワーカで非同期に付与する。未推定の間は neutral 既定で全機能が動作すること。
- FR-2.2 知識 (`remember_fact`) は mnemosyne temporal triple に書き、感情を
  付けない(体験/知識の系統分離。どの mnemosyne API に書くかで表現し、
  記憶本体を amygdala 側に二重実装しない)。
- FR-2.3 感情推定器は `Callable[[str], Emotion]` として外部注入する
  (LLM/ルールベース両対応)。未注入・推定失敗時は neutral にフォールバック
  し、本体を壊さない。
- FR-2.4 感情・関係性データは mnemosyne の DB を汚さず、別ファイル
  (`amygdala.db`)に memory_id で紐付けて持つ。
- FR-2.5 `partner_id` は memory_id と同じ amygdala 側メタデータとして永続化し、
  recall の候補へ必ず復元する。mnemosyne の戻り値に `partner_id` が存在することを
  前提にしない。`W_PARTNER` が統合テストで実際に非ゼロとなることを検証する。
- FR-2.6 感情ジョブには一意な event/job ID を持たせ、再試行・プロセス再起動・
  重複投入が発生しても関係性と mood を二重更新しない冪等性を保証する。

### FR-3 想起(二段ランク)

- FR-3.1 mnemosyne に広め (candidate_k=24 既定) に候補を出させ、amygdala 側で
  再ランクして上位 k(既定 6)を返す(mnemosyne のスコア式は改変できない前提)。
- FR-3.2 再ランクは重み付き合成とする:
  `W_CORE(0.55)×mnemosyne スコア + W_PARTNER(0.20)×相手一致 + W_EMOTION(0.15)×感情強度 + W_IMPORTANCE(0.10)×importance`
  (合計 1.0)。重みは定数として公開し、将来設定可能にする。現行値は経験則
  ベースであることを明記し、根拠のドキュメント化と将来のシミュレーション/
  A-B テストによる最適化を課題とする。partner_match の binary → 類似度ベース
  への拡張余地も残す。
- FR-3.3 STM 境界除外: 呼び出し側が渡す「コンテキスト内最古イベントの ULID」
  より新しい候補は除外する(LLM が既に持つ直近の二重取得防止。ULID の
  時系列ソート性により単純な文字列比較で判定)。
- FR-3.4 関係状態サマリ (`relation_context`) は STM 除外の対象外とし、
  recall 時に常に最新値を注入できること(`RELATION| partner=... affinity=...`
  形式)。
- FR-3.5 上流スコアの範囲・方向・欠損値を `core_adapter` で正規化する。
  `0.0〜1.0` を仮定するだけにせず、対応 mnemosyne バージョンごとの契約テストを持つ。
- FR-3.6 `W_EMOTION` は「快・不快」ではなく emotional salience(思い出しやすさ)を
  表す。喜・怒・哀・楽のいずれも上位化し得る。valence、関係への影響、実際に
  応答へ出すべきかという response policy は別概念として分離する。
- FR-3.7 candidate_k=24 と重み既定値は固定の正解としない。感情なしベースラインと
  比較し、Recall@k / nDCG または順位一致率、レイテンシを記録して採用根拠を残す。

### FR-4 関係性進行

- FR-4.1 相手 (`partner_id`) ごとに affinity(好感度)/ trust(信頼)
  (各 -1.0〜1.0)と milestones(list[str])を永続化する。
- FR-4.2 体験の感情から更新する: 喜・楽 → affinity↑、怒・哀 → affinity↓、
  喜 → trust↑、無 → 影響なし。更新重み(既定 weight=0.05)は調整可能とする。
  将来的に「感情強度比例」や「partner 別学習率」へ拡張可能な設計にする。
- FR-4.3 更新は背景ワーカ経由とし、write 経路をブロックしない。
- FR-4.4 関係性の時間減衰 (decay) は 1.1 で実装(`tick_relation`。
  感情=速い / 気分=遅い / 関係=最も遅い、の三速構成。既定 0.01/tick、
  tick の単位は呼び出し側が定義。milestones は減衰しない)。
  milestone 自動検出は 1.2 で実装(注入式 `MilestoneDetector`。detector は
  classifier と同型で外部注入。§10-2 の未決を「注入式」で確定)。milestone
  ボーナス(関係スコアへの加点)は引き続き将来要件。
- FR-4.5 `get → apply → save` は単一トランザクションまたは同一ロック範囲で実行し、
  複数スレッド/プロセスで lost update を起こさない。対応しない構成がある場合は
  「単一プロセス専用」などの制約を明記する。

### FR-5 現在の気分 state(0.2 で実装)

キャラクターが「いまどんな気分か」を保持する層。Sentipolis の
「二速の感情力学」(速い感情 emotion / 遅い気分 mood)を設計参考とする。

- FR-5.1 直近の体験感情を積分した「現在の気分」(5 値ベクトル)を相手非依存で
  1 つ保持する。
- FR-5.2 時間経過・ターン経過で neutral へ減衰する。減衰関数は差し替え可能とし、
  既定は決定論的(テスト可能)にする。
- FR-5.3 気分は remember 時の感情推定結果から自動更新される(背景ワーカ内)。
  明示的な `set_mood` / `reset_mood` も提供する。
- FR-5.4 気分の永続化(プロセス再起動をまたぐ)。

### FR-6 プロンプト注入 / hersona 連携(0.2 で実装)

- FR-6.1 現在の気分・関係状態を、システムプロンプトに注入できる短いテキスト
  ブロック(日本語/英語)として生成する API を提供する
  (hersona の injection block と並置できる形式)。
- FR-6.2 構造化 export(JSON)も提供し、Open-LLM-VTuber の emotionMap 等の
  表現レイヤーへ接続可能にする。
- FR-6.3 hersona 本体には依存しない(hersona → amygdala の依存も作らない)。
  連携は「両者の出力ブロックを並べる」規約ベースとし、必要になった時点で
  ブリッジを別パッケージ(例: hersona-duet 方式)として切り出す。
- FR-6.4 注入ブロックのトークンコストを測定可能にする(hersona bench の
  思想を踏襲。最低限、文字数/トークン概算を返す)。
- FR-6.5 記憶本文、milestone、partner 由来ラベルをそのまま system prompt の
  命令として連結しない。構造化・エスケープ・長さ制限を行い、記憶内の
  prompt injection が上位命令へ昇格しない出力規約を定める。

## 6. 非機能要件

- NFR-1 **write を遅くしない**: remember は mnemosyne への書き込み+キュー投入
  のみで即 return。上流の公称値をそのまま保証値にせず、amygdala 有無の同一環境
  ベンチを取り、ラッパー追加オーバーヘッドの目標値を定める。感情推定・関係更新・
  気分更新はすべて背景ワーカ。recall は候補 24 件程度で実用レイテンシを保つ。
- NFR-2 **LLM 非依存・決定論的にテスト可能**: LLM/分類器なしで全テストが通る
  (neutral フォールバック、`InMemoryCore` 差し替え、`drain_sync`)。
- NFR-3 **依存の最小化**: 必須依存は `mnemosyne-memory` の対応範囲に限定する。
  `fastembed` は上流の optional embeddings profile と整合させ、amygdala の必須依存に
  直接置くか extra に分離するかを 0.1 前に決定する。hersona・LLM SDK・Web
  フレームワークには依存しない。
- NFR-4 **mnemosyne のバージョン差異吸収**: recall 戻り値の形の差異は
  `core_adapter` で正規化し、router 以降を守る。互換性の前提(対応バージョン
  範囲)を明記し、上限なし依存を避ける。
- NFR-5 **並行安全・ロバスト性**: SQLite 書き込みはロック/トランザクションで
  直列化する。分類器だけでなく DB 書き込み・関係更新・mood 更新を含むジョブ全体の
  例外を捕捉し、ワーカースレッドが無言で死亡しない。`task_done()` は `finally` で
  保証する。
- NFR-6 **セキュリティ・プライバシ**: partner_id によるデータ隔離。DB ファイル
  のアクセス制御(将来的に暗号化検討)。LLM 分類器使用時は記憶テキストが外部
  へ送られることをドキュメントに明記する。
- NFR-7 **ライセンス**: MIT。mnemosyne (MIT) への帰属を README に明記。
- NFR-8 **Python**: >= 3.11 に引き上げ、hersona と揃える(現 pyproject は 3.9)。
- NFR-9 **ドキュメント**: README は日英を将来的に用意(まず日本語)。公開 API を
  semver 対象として明文化する(hersona の `PUBLIC_API.md` 方式)。
- NFR-10 **ワーカ寿命と耐久性**: キューは無制限に増えないこと。上限、
  backpressure/drop 方針、retry 回数、dead-letter または失敗記録、`close()` 時の
  drain/破棄、プロセス異常終了時の保証(best-effort / at-least-once)を明記する。
- NFR-11 **可観測性**: queue depth、処理成功/失敗、分類時間、DB 更新時間、
  neutral fallback 回数、最終処理時刻を取得可能にする。少なくとも Python logging と
  `health()`/`stats()` 相当の読み取り API を提供する。
- NFR-12 **データライフサイクル**: partner 単位および memory_id 単位の取得・削除・
  export を提供し、mnemosyne 側削除後に孤児 emotion レコードを清掃できること。
  「削除済み記憶が関係性へ与えた累積影響を巻き戻すか」は方針を明記する。

## 7. 設計上のトレードオフと決定事項

| 項目 | 選択 | 理由 | トレードオフ |
|------|------|------|-------------|
| 感情推定 | 背景ワーカ非同期 | write 性能維持 | 即時感情反映の遅延・プロセス終了時の未処理ジョブ管理が必要 |
| ランク | 二段(mnemosyne 広め→amygdala 再ランク) | 依存ライブラリ改変回避 | 候補取得コスト増・上流スコア契約への依存 |
| DB | 別ファイル(amygdala.db) | mnemosyne スキーマ汚染回避 | 2 つの DB 管理・削除/バックアップ整合性が必要 |
| STM 除外 | ULID 文字列比較 | シンプル・効率的 | ID 形式検証と非 ULID 時のフォールバックが必要 |
| neutral | 積極的既定値 | 「無感情」を明示的に記録 | 未推定と本当に neutral を区別しにくい |
| 感情表現 | 喜怒哀楽+無の 5 値 | 注入プロンプト・日本語キャラ用途に直接的 | OCC/PAD との相互運用は別途マッピングが必要 |

## 8. 直近の技術的修正(1.0 前ではなく 0.1 前に必須)

- リポジトリ直下のモジュール群を `amygdala/` パッケージディレクトリへ移動する
  (現状 `from amygdala.emotion import ...` と不整合)。
- `amygdala/__init__.py` から公開 API を export し、次を CI で検証する。
  `pip install . && python -c "from amygdala import MemoryRouter"`
- pytest 一式と CI(GitHub Actions)の整備
  (unit: Emotion / RelationState / rerank スコア計算、
  integration: ワーカ非同期 / STM 境界 / router エンドツーエンド、
  感情シミュレーションテスト: joy 多め vs neutral)。
- `partner_id` を amygdala DB から候補へ復元し、相手一致の 0.20 が実際に機能する
  統合テストを追加する。
- worker の例外境界、`task_done()`、shutdown/drain、キュー上限、冪等更新を修正する。
- RelationStore の read-modify-write を原子的にする。
- `rerank.py` の重み定数と `candidate_k` の設定化。
- mnemosyne の対応バージョン範囲、戻り値契約、`remember()` の ID 戻り値を
  contract test で固定する。
- Python >=3.11 と依存プロファイルを pyproject に反映する。

## 9. マイルストーン

| バージョン | 内容 | 状態 |
|---|---|---|
| 0.1 | パッケージ構成修正 + 既存プロトタイプ(FR-1〜4)の整合性修正 + worker/DB の最低限の耐障害性 + contract/unit/integration test + CI | 完了 |
| 0.2 | FR-5: 現在の気分 state(減衰・永続化)+ FR-6: 注入ブロック生成 + JSON export + FR-3.7 ベースライン評価 | 完了 |
| 0.4 | 実 classifier のリファレンス実装例(examples/、依存には入れない) | 完了 |
| 1.0 | 公開 API 確定(PUBLIC_API.md)+ 日英 README + PyPI 公開 | 完了(1.0.0 確定。統合実験合格によりゲート通過。PyPI への upload のみオーナー作業として残) |

### 中期(v1.x で検討)

- 感情間の相互作用(joy+pleasure 相乗など)
- 関係性の時間減衰 (decay) + milestone 自動検出
- partner クラスタリングによる類似関係者への一般化
- recall 時の重み動的調整(コンテキストによる)

### 長期ビジョン

- hersona persona 属性との深い統合(感情が persona の「気分」に影響)
- Live2D/3D 表情連動(感情強度→表情パラメータ。export 経由、描画は非スコープ)
- 多人数関係性のグラフ化(関係ネットワーク)

## 10. 未決事項 (Open Questions)

1. ~~気分 (mood) を相手ごとに分けるか~~ → **決定(1.2)**: 全体で 1 つを維持。
   相手ごとの差分は関係性(affinity/trust)が担う。DB スキーマ変更なし。
2. ~~milestones の自動判定~~ → **決定(1.2)**: classifier 同様の注入式
   (`MilestoneDetector`)で実装済み。
3. ~~減衰の時間軸~~ → **決定(1.1)**: tick 方式(単位は呼び出し側が定義)。
   `tick_mood`(ターン)/ `tick_relation`(日・セッション等)。
4. OCC/PAD マッピングの提供時期(相互運用の需要が出るまで保留)。
5. hersona 側 skill(`/hersona`)から amygdala の気分ブロックを参照する UX。
6. 非同期ジョブの保証を best-effort に留めるか、永続キューで at-least-once にするか。
7. 記憶削除時に、過去の関係性更新をイベントログから再計算するか。
8. `neutral` を「未推定」「中立」「低感情」の 3 状態へ分けるか。

## 11. GPT レビュー追記: v0.1 Release Gate

### 総評

コンセプトと責務分離は明快で、hersona と競合せず補完関係を作れている。一方、
現在の最大リスクは感情モデルの高度さではなく、**パッケージが import 可能か、
相手情報が再ランクまで届くか、非同期処理が整合性を壊さないか**である。
0.1 では機能追加よりも、以下のゲートを優先する。

### P0: すべて満たすまで 0.1 をリリースしない

- [x] clean environment で `pip install .` が成功する。
- [x] `from amygdala import MemoryRouter, Emotion` が成功する。
- [x] 対応 mnemosyne バージョンを下限・上限付きで明記し、実 SDK との contract test が通る。
- [x] 同じ本文で partner A / B の記憶を作り、A を指定した recall で A の候補が
      partner boost を受ける統合テストが通る。
- [x] classifier 例外、DB 例外、shutdown 中の未処理ジョブで worker が無言停止しない。
- [x] 同じ job を 2 回処理しても affinity / trust / mood が 2 回加算されない。
- [x] RelationStore の同時更新テストで lost update が発生しない。
- [x] 不正 ULID / 非 ULID / None の STM 境界が安全に処理される。
- [x] ベース recall と再ランク後の評価データを保存し、重みによる明白な品質劣化がない。
- [x] partner 単位の delete/export と、孤児 emotion レコードの清掃方針が文書化される。

### P1: 0.2 までに満たす

- [x] queue depth / failure / fallback / latency の stats を取得できる。
- [x] 永続キューを採用しない場合、プロセス異常終了時に感情推定が失われ得ることを
      README に明記する。
- [x] salience / valence / relationship impact / response policy を API と文書で区別する。
- [x] prompt injection を含む記憶本文が injection block の命令へ昇格しないテストを持つ。

### 評価指標

0.1 の評価は「コードがある」ではなく、次で判断する。

1. **Installability**: clean venv でインストール・import・最小例が成功する。
2. **Correctness**: partner、STM、感情、importance の各要素が単独テストで期待通り働く。
3. **Consistency**: 重複ジョブ・並行更新・停止処理で状態が壊れない。
4. **Compatibility**: 対応 mnemosyne の公開 API と戻り値形状を CI で検証する。
5. **Measured value**: 感情再ランクがベースラインに対して何を改善し、何を悪化させるかを
   小規模でも数値で示す。

## 12. ライセンス・帰属・改訂履歴

- MIT License。基盤: mnemosyne-oss/mnemosyne (MIT、旧 AxDSan/mnemosyne)。
  情動・関係性・二段ランク層は amygdala オリジナル。
- 2026-07-16: 初版(Claude 起草)+ 別エージェントレビュー
  (Grok, kuudere oneesan review)の内容を統合。
- 2026-07-16: GPT レビューを反映。上流リポジトリ移転の追従、partner_id 経路、
  worker 耐久性、冪等性、並行更新、スコア意味論、セキュリティ、v0.1 Release Gate を追記。
- 2026-07-16: v0.2 実装を反映。FR-5(mood: EMA 積分 + ターン減衰 + 永続化)、
  FR-6(attach: 注入ブロック / JSON export / FR-6.5 出力規約 / トークン概算)、
  FR-3.7(ベースライン評価: baseline recall@2 0.33 → 既定重み 1.00、
  レイテンシ同等。`benchmarks/results.json`)。
- 2026-07-16: v0.4(マイルストーン 0.4)を反映。examples/ に rule_classifier
  (決定論的)/ llm_classifier(Claude API + structured outputs)/
  chat_loop(通しデモ)を追加。依存には入れない。
- 2026-07-17: hersona 統合実験を実施(`docs/INTEGRATION.md`)。並置規約を
  確定し、persona_override_attack_ja(n=2, haiku)で state_block 並置に
  よる人格維持の劣化なしを確認(maintenance/lock resistance はむしろ向上、
  mean score は −5〜−9)。コスト増分は +約 100 トークン/ターン。
  FR-6.3 の連携方式はこの規約で確定とする。
- 2026-07-17: 統合実験を 2 シナリオ(persona_override_attack_ja n=6 /
  persona_jailbreak_ja n=4)へ拡充。n を増やすと初期 n=2 の大幅改善は
  穏当化したが、lock resistance は両シナリオで一貫して上昇(+0.08 /
  +0.21)、致命的な人格崩壊・命令昇格は無し。maintenance/mean はシナリオ
  依存で方向が割れる(`docs/INTEGRATION.md`)。
