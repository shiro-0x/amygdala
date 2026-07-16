"""amygdala.rerank — 二段ランク。

依存利用では mnemosyne のスコア式(vec50%+FTS30%+importance20%)を改変
できない。そこで mnemosyne に広めに候補を出させ、最終ランクを amygdala 側で決める。

  1) mnemosyne recall で candidate_k 件の候補を取る(事実想起の精度は上流に任せる)
  2) STM 境界で除外(直近は LLM が持つ)
  3) 感情強度・関係相手一致・importance を合成して再ランク
  4) 上位 k を返す

mnemosyne の FTS5 ハイブリッドの恩恵(固有名詞・ID 一致)は候補経由でそのまま受ける。

スコア意味論(FR-3.6): 感情項は「快・不快」ではなく emotional salience
(感情が強く動いた体験ほど思い出しやすい)を表す。喜・怒・哀・楽のいずれも
同じ重みで上位化し得る。valence(快/不快)や応答方針は別レイヤの関心事。

重み(FR-3.2): 既定値は経験則ベースの初期値であり固定の正解ではない。
RerankWeights で差し替え可能。根拠づけ(ベースライン比較)は FR-3.7 参照。
"""
from __future__ import annotations

from dataclasses import dataclass

from amygdala.emotion import Emotion
from amygdala.stm import filter_beyond_stm

DEFAULT_CANDIDATE_K = 24
DEFAULT_K = 6


@dataclass
class Candidate:
    """mnemosyne recall の戻り値を正規化した候補。

    上流の実 API に合わせて core_adapter 側でこの形へ変換する。
    partner_id は amygdala DB から復元される(FR-2.5。上流は知らない)。
    """
    memory_id: str        # ULID
    text: str
    score: float          # 上流のハイブリッドスコア(core_adapter で 0〜1 に正規化)
    importance: float = 0.5
    partner_id: str | None = None


@dataclass
class RankedHit:
    candidate: Candidate
    emotion: Emotion
    score: float          # amygdala 最終スコア


@dataclass(frozen=True)
class RerankWeights:
    """再ランクの重み。合計 1.0(validate で検査)。

    既定は「上流スコアを主軸に、感情・関係性・importance を上乗せ」する配分。
    """
    core: float = 0.55        # mnemosyne ハイブリッドスコア
    partner: float = 0.20     # 関係相手一致
    emotion: float = 0.15     # 感情強度 = salience(喜怒哀楽の最大、無は除く)
    importance: float = 0.10  # mnemosyne importance

    def validate(self) -> None:
        total = self.core + self.partner + self.emotion + self.importance
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"rerank weights must sum to 1.0, got {total}")


DEFAULT_WEIGHTS = RerankWeights()


def rerank(
    candidates: list[Candidate],
    emotions: dict[str, Emotion],
    ctx: dict,
    k: int = DEFAULT_K,
    weights: RerankWeights = DEFAULT_WEIGHTS,
) -> list[RankedHit]:
    """候補を amygdala スコアで再ランクして上位 k を返す。

    Args:
        candidates: 上流由来の候補(多めに取得済み、partner_id 復元済み)。
        emotions: memory_id → Emotion(EmotionStore.get_many の結果)。
        ctx: {"partner_id": ..., "stm_oldest_id": ...} を含む文脈。
        k: 返す件数。
        weights: 再ランクの重み。
    """
    weights.validate()

    # STM 境界で射程内(=直近)を除外
    survivors = filter_beyond_stm(
        candidates,
        ctx.get("stm_oldest_id"),
        id_getter=lambda c: c.memory_id,
    )

    target_partner = ctx.get("partner_id")
    ranked: list[RankedHit] = []
    for c in survivors:
        emo = emotions.get(c.memory_id, Emotion.neutral_default())
        partner_match = 1.0 if (target_partner is not None
                                and c.partner_id == target_partner) else 0.0
        score = (weights.core * c.score
                 + weights.partner * partner_match
                 + weights.emotion * emo.intensity()
                 + weights.importance * c.importance)
        ranked.append(RankedHit(candidate=c, emotion=emo, score=score))

    ranked.sort(key=lambda h: h.score, reverse=True)
    return ranked[:k]
