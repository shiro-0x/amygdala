# amygdala REQUIREMENTS

> 扁桃体（情動を司る脳部位）。記憶基盤の上で **情動と関係性** を担う層。

`amygdala` は [AxDSan/mnemosyne](https://github.com/AxDSan/mnemosyne)（MIT）の事実メモリ基盤の上に、薄い情動・関係性レイヤを乗せるプロジェクトです。

本ドキュメントは **要件定義** と **設計上のトレードオフ・改善提案** をまとめたものです。実装は README.md および各モジュール（emotion.py, relation.py, rerank.py, router.py など）を参照してください。

## 1. プロジェクトの目的・ゴール

### 1.1 核心コンセプト
- **情動の付与**: 体験記憶（episodic）に喜怒哀楽+無の5値感情ベクトルを付与
- **関係性の進行**: 感情から affinity（好感度）/ trust（信頼）/ milestones を自然に更新
- **想起の洗練**: mnemosyneの広め候補取得 → amygdala側で二段ランク（STM除外 + 感情/関係性/importance）
- **非侵入性**: mnemosyneのwrite性能を殺さず、スキーマを汚さない

### 1.2 ターゲットユースケース
- Hersona / Hermes Agent などのパーソナリティAIの長期記憶基盤
- ユーザー/キャラクターとの関係性が重要になる対話システム
- 感情文脈を考慮した想起（「あの時の喜び」「信頼できる相手の話」など）

## 2. 機能要件 (Functional Requirements)

### 2.1 感情モデル (Emotion)
- **5軸モデル**: joy(喜), anger(怒), sorrow(哀), pleasure(楽), neutral(無)
  - 各値: 0.0〜1.0
  - neutralは「感情が動かなかった積極的記録」として既定1.0
- **派生量**:
  - intensity(): 喜怒哀楽4軸の最大値（想起スコアに使用）
  - dominant(): 最も強い感情軸
  - is_neutral(threshold=0.1)
- **直列化**: to_list / from_list / from_dict / to_dict（部分指定可）

**要件メモ**: neutralの「感情指定時0起点」ロジックを明確化。将来的に「無感情」と「中立」の区別を検討。

### 2.2 関係性進行 (Relation)
- **RelationState**:
  - affinity: -1.0〜1.0（喜・楽で↑、怒・哀で↓）
  - trust: -1.0〜1.0（主にjoyで寄与）
  - milestones: list[str]（手動追加可能）
- **更新ルール**: apply_emotion(emo, weight=0.05)
- **context注入**: recall時に「RELATION| partner=... affinity=...」形式で常時提供（STM除外対象外）

**要件メモ**: 
- weightの固定値を要件として明記。将来的に「感情強度比例」や「partner別学習率」を拡張可能に。
- 時間減衰（decay）やmilestoneボーナスを将来要件として検討。

### 2.3 二段ランク & 想起 (Rerank + STM)
- **フロー**:
  1. mnemosyne.recall(query, top_k=24) で広め候補取得
  2. STM境界除外（stm_oldest_idより古いもののみ）
  3. 再スコア = W_CORE * core_score + W_PARTNER * partner_match + W_EMOTION * intensity + W_IMPORTANCE * importance
  4. 上位k（デフォルト6）返却
- **重み定数**（合計1.0）:
  - W_CORE = 0.55
  - W_PARTNER = 0.20
  - W_EMOTION = 0.15
  - W_IMPORTANCE = 0.10
- **STM除外**: ULID文字列比較で効率的（時系列保証）

**要件メモ**:
- 重み調整の根拠をドキュメント化（経験則ベース → 将来的にシミュレーション/A-Bテストで最適化）
- partner_matchをbinaryから類似度ベースへ拡張可能性を要件に。

### 2.4 系統分離
- **体験記憶**: remember() → episodic + 背景感情推定
- **知識記憶**: remember_fact() → temporal triple（感情なし）

### 2.5 背景ワーカ (EmotionWorker)
- remember()は即return（mnemosyne write性能維持）
- 別スレッドで感情推定 + relation更新
- 例外時はneutral_defaultにフォールバック（ロバスト性）

## 3. 非機能要件 (Non-Functional Requirements)

### 3.1 性能
- write latency: mnemosyneの高速性（~0.8ms）を維持（感情推定は非同期）
- recall: 候補24件程度で実用的なレイテンシ
- DB: SQLite (WAL + NORMAL同期) で十分。単一ライタ制約をロックで対応

### 3.2 ロバスト性・可用性
- 感情分類器未注入/失敗時 → neutral
- ワーカ例外 → 本体動作継続
- DB分離（amygdala.db）でmnemosyneを汚さない

### 3.3 拡張性・テスト容易性
- Core ProtocolでRealCore / InMemoryCore切り替え
- EmotionClassifierを注入可能（LLM/ルールベース両対応）
- 型ヒント + dataclass多用

### 3.4 セキュリティ・プライバシ
- partner_idによる隔離
- DBファイルのアクセス制御（将来的に暗号化検討）
- LLM分類器使用時のデータ漏洩リスクを考慮

## 4. 設計上のトレードオフと決定事項

| 項目 | 選択 | 理由 | トレードオフ |
|------|------|------|-------------|
| 感情推定 | 背景ワーカ非同期 | write性能維持 | 即時感情反映の遅延 |
| ランク | 二段（mnemosyne広め→amygdala再ランク） | 依存ライブラリ改変回避 | 候補取得コスト増 |
| DB | 別ファイル（amygdala.db） | mnemosyneスキーマ汚染回避 | 2つのDB管理 |
| STM除外 | ULID文字列比較 | シンプル・効率的 | より高度な文脈理解が必要な場合の限界 |
| neutral | 積極的既定値 | 「無感情」を明示的に記録 | 感情推定器の精度に依存 |

## 5. 追加意見・改善提案（2026-07-16時点）

### 5.1 優先度高め（次バージョンで対応推奨）
1. **docs/REQUIREMENTS.md の正式化**（本ドキュメント）
2. **テストスイート追加**
   - unit: Emotion, RelationState, rerankスコア計算
   - integration: ワーカ非同期、STM境界、routerエンドツーエンド
   - 感情シミュレーションテスト（joy多め vs neutral）
3. **重み・更新ルールの根拠明文化**と調整ガイド
4. **mnemosyneバージョン互換性**の明記（_attrで吸収しているが、要件として固定 or 互換レイヤ）

### 5.2 中期（v1.xで検討）
- 感情間の相互作用（joy+pleasure相乗など）
- 関係性の時間減衰（decay） + milestone自動検出
- partnerクラスタリングによる類似関係者への一般化
- recall時の重み動的調整（コンテキストによる）

### 5.3 長期ビジョン
- Hersona persona属性との深い統合（感情がpersonaの「気分」に影響）
- Live2D/3D表情連動（感情強度→表情パラメータ）
- 多人数関係性のグラフ化（関係ネットワーク）
- 自己感情（エージェント自身の感情状態）への拡張

## 6. ライセンス・帰属

- MIT License
- 基盤: AxDSan/mnemosyne (MIT)
- 情動・関係性・二段ランク層: amygdalaオリジナル

---

**作成日**: 2026-07-16  
**作成者**: Grok (kuudere oneesan review) + shiro-0x  
**次アクション**: 本ドキュメントを基に実装を安定化 → テスト追加 → Hersona統合実験
