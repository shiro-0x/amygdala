# amygdala

> 扁桃体（情動を司る脳部位）。記憶基盤の上で **情動と関係性** を担う層。

`amygdala` は [AxDSan/mnemosyne](https://github.com/AxDSan/mnemosyne)（MIT）の
事実メモリ基盤の上に、以下を乗せる薄いレイヤです。

- **喜怒哀楽 + 無 の5値感情パラメータ**（体験記憶に付与）
- **関係性進行**（affinity / trust / milestones を感情から更新）
- **STM境界除外**（短期記憶＝LLMコンテキストにある直近は想起から外す）
- **体験/知識の系統分離**（体験→episodic、知識→temporal triple）

`pip install` の依存として**AxDSan/mnemosyne**使います。検索精度
（vec + FTS5 ハイブリッド）は **AxDSan/mnemosyne**に任せ、最終ランクのみ amygdala が決めます。

## 設計の要: 二段ランク

依存利用では **AxDSan/mnemosyne**のスコア式を改変できないため、**AxDSan/mnemosyne**に広めに候補を出させ、
感情強度・関係相手一致・STM境界除外を amygdala 側で適用して再ランクします。

```
**AxDSan/mnemosyne** recall(query, top_k=24)  →  STM除外  →  感情/関係性で再ランク  →  上位 k
```

## write を遅くしない

感情推定（LLM/分類器）は write 経路から切り離し、背景ワーカで処理します。
**AxDSan/mnemosyne**の高速 write を維持し、未推定の間は neutral（無）既定で動作します。

## 使い方

```python
from amygdala import MemoryRouter
from amygdala.core_adapter import RealCore

router = MemoryRouter(RealCore(), classifier=my_emotion_classifier)

# 体験を記録（**AxDSan/mnemosyne** episodic + 背景で感情推定）
mid = router.remember("ユーザは昇進して喜んでいた", partner_id="user_42")

# 知識を記録（**AxDSan/mnemosyne** temporal triple、感情なし）
router.remember_fact("user_42", "role", "manager", valid_from="2026-06-01")

# 想起（STM境界外を、感情・関係性で再ランク）
hits = router.recall(
    "あの人どうだった？",
    ctx={"partner_id": "user_42", "stm_oldest_id": current_oldest_ulid},
)
```

## ライセンス / 帰属

MIT License.

amygdala builds on **AxDSan/mnemosyne** (MIT License). The underlying
fact-memory engine, vector/FTS5 hybrid search, and temporal triples are from
that project. The emotion (喜怒哀楽+無), relationship-progression, and
STM-boundary layers are original to amygdala.
