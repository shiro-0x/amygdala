# amygdala

> 扁桃体(情動を司る脳部位)。記憶基盤の上で **情動と関係性** を担う層。

`amygdala` は [mnemosyne](https://github.com/mnemosyne-oss/mnemosyne)(MIT)の
事実メモリ基盤の上に、以下を乗せる薄いレイヤです。

- **喜怒哀楽 + 無 の5値感情パラメータ**(体験記憶に付与)
- **関係性進行**(affinity / trust / milestones を感情から更新)
- **STM境界除外**(短期記憶=LLMコンテキストにある直近は想起から外す)
- **体験/知識の系統分離**(体験→episodic、知識→temporal triple)

姉妹プロジェクト [hersona](https://github.com/shiro-0x/hersona) が**性格**
(静的な trait)を、amygdala が**感情**(動的な state)を担当します。
要件・設計判断・ロードマップは [docs/REQUIREMENTS.md](./docs/REQUIREMENTS.md) を
参照してください。

依存は `mnemosyne-memory`(pip)です。検索精度(vec + FTS5 ハイブリッド)は
mnemosyne に任せ、最終ランクのみ amygdala が決めます。

## 設計の要: 二段ランク

依存利用では mnemosyne のスコア式を改変できないため、mnemosyne に広めに候補を
出させ、感情強度・関係相手一致・STM境界除外を amygdala 側で適用して再ランクします。

```
mnemosyne recall(query, top_k=24) → STM除外 → 感情/関係性で再ランク → 上位 k
```

相手一致(`partner_id`)は amygdala 側の DB から復元されるため、mnemosyne の
戻り値形式に依存しません。

## write を遅くしない

感情推定(LLM/分類器)は write 経路から切り離し、背景ワーカで処理します。
mnemosyne の高速 write を維持し、未推定の間は neutral(無)既定で動作します。

- ジョブは冪等(同じ記憶を二重処理しても関係性を二重更新しない)
- 分類器・DB の例外でワーカは無言停止しない(`router.stats()` で観測可能)
- **キューはインメモリ(非永続)です。** プロセス異常終了時、未処理の感情推定
  ジョブは失われます(該当記憶は neutral 既定のまま動き続けます)

## 使い方

```python
from amygdala import MemoryRouter, RealCore

router = MemoryRouter(RealCore(), classifier=my_emotion_classifier)

# 体験を記録(mnemosyne episodic + 背景で感情推定)
mid = router.remember("ユーザは昇進して喜んでいた", partner_id="user_42")

# 知識を記録(mnemosyne temporal triple、感情なし)
router.remember_fact("user_42", "role", "manager", valid_from="2026-06-01")

# 想起(STM境界外を、感情・関係性で再ランク)
hits = router.recall(
    "あの人どうだった?",
    ctx={"partner_id": "user_42", "stm_oldest_id": current_oldest_ulid},
)

# 関係状態サマリ(recall 時に常時注入する)
print(router.relation_context("user_42"))
# RELATION| partner=user_42 affinity=+0.05 trust=+0.05
```

テストや mnemosyne なしの試用には `InMemoryCore` が使えます。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

mnemosyne 実 SDK との契約テスト(`tests/test_contract_mnemosyne.py`)は
`mnemosyne-memory` がインストールされた環境でのみ実行されます。

## 免責

amygdala はキャラクター表現のための感情「パラメータ」を扱うライブラリであり、
人間の感情の診断・メンタルヘルス用途を意図していません。

## ライセンス / 帰属

MIT License.

amygdala builds on [mnemosyne](https://github.com/mnemosyne-oss/mnemosyne)
(MIT License). The underlying fact-memory engine, vector/FTS5 hybrid search,
and temporal triples are from that project. The emotion (喜怒哀楽+無),
relationship-progression, and STM-boundary layers are original to amygdala.

名前について: ゲームNPC向け感情エンジンの先行研究
[GAMYGDALA](https://github.com/broekens/gamygdala) (game + amygdala) とは
別プロジェクトです。appraisal→状態のループ設計など理論面で参考にしています。
