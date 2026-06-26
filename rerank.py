"""amygdala.rerank — 二段ランク。

依存利用では A版(mnemosyne)のスコア式(vec50%+FTS30%+importance20%)を改変
できない。そこで A版に広めに候補を出させ、最終ランクを amygdala 側で決める。

  1) A版 recall で candidate_k 件の候補を取る(事実想起の精度は A版に任せる)
  2) STM 境界で除外(直近は LLM が持つ)
  3) 感情強度・関係相手一致・importance を合成して再ランク
  4) 上位 k を返す

A版の FTS5 ハイブリッドの恩恵(固有名詞・ID 一致)は候補経由でそのまま受ける。
"""
from __future__ import annotations

from dataclasses import dataclass

from amygdala.emotion import Emotion
from amygdala.stm import filter_beyond_stm


@dataclass
class Candidate:
    """A版 recall の戻り値を正規化した候補。

    A版の実 API に合わせて router 側でこの形へ変換する。
    """
    memory_id: str        # ULID
    text: str
    score: float          # A版のハイブリッドスコア(0〜1想定)
    importance: float = 0.5
    partner_id: str | None = None


@dataclass
class RankedHit:
    candidate: Candidate
    emotion: Emotion
    score: float          # amygdala 最終スコア


# 再ランクの重み。合計 1.0。
# A版スコアを主軸に、感情・関係性・importance を上乗せする配分。
W_CORE = 0.55         # A版ハイブリッドスコア
W_PARTNER = 0.20      # 関係相手一致
W_EMOTION = 0.15      # 感情強度(喜怒哀楽の最大、無は除く)
W_IMPORTANCE = 0.10   # A版 importance


def rerank(
    candidates: list[Candidate],
    emotions: dict[str, Emotion],
    ctx: dict,
    k: int = 6,
) -> list[RankedHit]:
    """候補を amygdala スコアで再ランクして上位 k を返す。

    Args:
        candidates: A版由来の候補(多めに取得済み)。
        emotions: memory_id → Emotion(EmotionStore.get_many の結果)。
        ctx: {"partner_id": ..., "stm_oldest_id": ...} を含む文脈。
        k: 返す件数。
    """
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
        score = (W_CORE * c.score
                 + W_PARTNER * partner_match
                 + W_EMOTION * emo.intensity()
                 + W_IMPORTANCE * c.importance)
        ranked.append(RankedHit(candidate=c, emotion=emo, score=score))

    ranked.sort(key=lambda h: h.score, reverse=True)
    return ranked[:k]
