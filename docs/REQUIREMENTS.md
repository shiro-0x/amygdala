# amygdala 要件定義書

> 扁桃体(情動を司る脳部位)。記憶基盤の上で **情動と関係性** を担う層。

Status: Draft / 作成日: 2026-07-16 / 対象バージョン: 0.x → 1.0

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
| 記憶基盤(検索・永続化) | [AxDSan/mnemosyne](https://github.com/AxDSan/mnemosyne) (MIT, vec+FTS5 ハイブリッド, temporal triples) | 成熟・高速 (write ~0.8ms) | **作らない**。依存として使い、感情レイヤーだけ乗せる |
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
| 「現在の気分」state | — | **未実装** |
| hersona 連携 | — | **未実装** |
| テスト / CI | — | **未実装** |
| パッケージ構成 | モジュールがリポジトリ直下にあるが import は `amygdala.` 前提 | **要修正** |

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

### FR-4 関係性進行

- FR-4.1 相手 (`partner_id`) ごとに affinity(好感度)/ trust(信頼)
  (各 -1.0〜1.0)と milestones(list[str])を永続化する。
- FR-4.2 体験の感情から更新する: 喜・楽 → affinity↑、怒・哀 → affinity↓、
  喜 → trust↑、無 → 影響なし。更新重み(既定 weight=0.05)は調整可能とする。
  将来的に「感情強度比例」や「partner 別学習率」へ拡張可能な設計にする。
- FR-4.3 更新は背景ワーカ経由とし、write 経路をブロックしない。
- FR-4.4 関係性の時間減衰 (decay) と milestone ボーナス/自動検出は将来要件
  として検討する(§9・§10 参照)。

### FR-5 現在の気分 state(新規・未実装)

キャラクターが「いまどんな気分か」を保持する層。Sentipolis の
「二速の感情力学」(速い感情 emotion / 遅い気分 mood)を設計参考とする。

- FR-5.1 直近の体験感情を積分した「現在の気分」(5 値ベクトル)を相手非依存で
  1 つ保持する。
- FR-5.2 時間経過・ターン経過で neutral へ減衰する。減衰関数は差し替え可能とし、
  既定は決定論的(テスト可能)にする。
- FR-5.3 気分は remember 時の感情推定結果から自動更新される(背景ワーカ内)。
  明示的な `set_mood` / `reset_mood` も提供する。
- FR-5.4 気分の永続化(プロセス再起動をまたぐ)。

### FR-6 プロンプト注入 / hersona 連携(新規・未実装)

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

## 6. 非機能要件

- NFR-1 **write を遅くしない**: remember は mnemosyne への書き込み+キュー投入
  のみで即 return(mnemosyne の ~0.8ms write を維持)。感情推定・関係更新・
  気分更新はすべて背景ワーカ。recall は候補 24 件程度で実用レイテンシを保つ。
- NFR-2 **LLM 非依存・決定論的にテスト可能**: LLM/分類器なしで全テストが通る
  (neutral フォールバック、`InMemoryCore` 差し替え、`drain_sync`)。
- NFR-3 **依存の最小化**: 実行時依存は mnemosyne-memory(+その要求)のみ。
  hersona・LLM SDK・Web フレームワークに依存しない。
- NFR-4 **mnemosyne のバージョン差異吸収**: recall 戻り値の形の差異は
  `core_adapter` で正規化し、router 以降を守る。互換性の前提(対応バージョン
  範囲)を明記する。
- NFR-5 **並行安全・ロバスト性**: SQLite 書き込みはロックで直列化
  (WAL + synchronous NORMAL、単一ライタ制約)。ワーカ停止・例外でも本体機能が
  縮退動作(neutral)で継続する。
- NFR-6 **セキュリティ・プライバシ**: partner_id によるデータ隔離。DB ファイル
  のアクセス制御(将来的に暗号化検討)。LLM 分類器使用時は記憶テキストが外部
  へ送られることをドキュメントに明記する。
- NFR-7 **ライセンス**: MIT。mnemosyne (MIT) への帰属を README に明記。
- NFR-8 **Python**: >= 3.11 に引き上げ、hersona と揃える(現 pyproject は 3.9)。
- NFR-9 **ドキュメント**: README は日英を将来的に用意(まず日本語)。公開 API を
  semver 対象として明文化する(hersona の `PUBLIC_API.md` 方式)。

## 7. 設計上のトレードオフと決定事項

| 項目 | 選択 | 理由 | トレードオフ |
|------|------|------|-------------|
| 感情推定 | 背景ワーカ非同期 | write 性能維持 | 即時感情反映の遅延 |
| ランク | 二段(mnemosyne 広め→amygdala 再ランク) | 依存ライブラリ改変回避 | 候補取得コスト増 |
| DB | 別ファイル(amygdala.db) | mnemosyne スキーマ汚染回避 | 2 つの DB 管理 |
| STM 除外 | ULID 文字列比較 | シンプル・効率的 | より高度な文脈理解が必要な場合の限界 |
| neutral | 積極的既定値 | 「無感情」を明示的に記録 | 感情推定器の精度に依存 |
| 感情表現 | 喜怒哀楽+無の 5 値 | 注入プロンプト・日本語キャラ用途に直接的 | OCC/PAD との相互運用は別途マッピングが必要 |

## 8. 直近の技術的修正(要件外だが 1.0 前に必須)

- リポジトリ直下のモジュール群を `amygdala/` パッケージディレクトリへ移動する
  (現状 `from amygdala.emotion import ...` と不整合)。
- pytest 一式と CI(GitHub Actions)の整備
  (unit: Emotion / RelationState / rerank スコア計算、
  integration: ワーカ非同期 / STM 境界 / router エンドツーエンド、
  感情シミュレーションテスト: joy 多め vs neutral)。
- `rerank.py` の重み定数と `candidate_k` の設定化。

## 9. マイルストーン

| バージョン | 内容 |
|---|---|
| 0.1 | パッケージ構成修正 + 既存プロトタイプ(FR-1〜4)にテストを付けて固める + 重み・更新ルールの根拠明文化 |
| 0.2 | FR-5: 現在の気分 state(減衰・永続化) |
| 0.3 | FR-6: 注入ブロック生成 + JSON export(hersona 並置規約の文書化) |
| 0.4 | 実 classifier のリファレンス実装例(examples/、依存には入れない) |
| 1.0 | 公開 API 確定(PUBLIC_API.md)+ 日英 README + PyPI 公開 |

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

1. 気分 (mood) を相手ごとに分けるか(現案: 全体で 1 つ。関係性が相手ごとの
   差分を担う)。
2. milestones の自動判定(現案: 呼び出し側が明示登録。自動化は classifier
   同様に注入式とするか)。
3. 減衰の時間軸: 実時間ベースかターン数ベースか(現案: 両対応のインター
   フェースにして既定はターン数)。
4. OCC/PAD マッピングの提供時期(相互運用の需要が出るまで保留)。
5. hersona 側 skill(`/hersona`)から amygdala の気分ブロックを参照する UX。

## 11. ライセンス・帰属・改訂履歴

- MIT License。基盤: AxDSan/mnemosyne (MIT)。情動・関係性・二段ランク層は
  amygdala オリジナル。
- 2026-07-16: 初版(Claude 起草)+ 別エージェントレビュー
  (Grok, kuudere oneesan review)の内容を統合。
