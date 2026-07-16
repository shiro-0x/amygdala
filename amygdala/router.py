"""amygdala.router — 統合窓口。

体験(remember)は mnemosyne episodic + 背景感情推定。
知識(remember_fact)は mnemosyne temporal triple(感情なし)。
recall は mnemosyne で広く候補取得 → partner_id 復元 → amygdala 二段ランク。

体験/知識の系統分離は「どの mnemosyne API に書くか」で表現し、amygdala 側に
記憶本体を二重実装しない。
"""
from __future__ import annotations

from amygdala import attach, mood as mood_dynamics
from amygdala.core_adapter import Core
from amygdala.emotion import Emotion
from amygdala.rerank import (DEFAULT_CANDIDATE_K, DEFAULT_K, DEFAULT_WEIGHTS,
                             RankedHit, RerankWeights, rerank)
from amygdala.relation import RelationStore
from amygdala.store import EmotionStore
from amygdala.worker import (DEFAULT_QUEUE_MAXSIZE, EmotionClassifier,
                             EmotionJob, EmotionWorker)


class MemoryRouter:
    def __init__(
        self,
        core: Core,
        db_path: str = "amygdala.db",
        classifier: EmotionClassifier | None = None,
        weights: RerankWeights = DEFAULT_WEIGHTS,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        relation_weight: float = 0.05,
        mood_alpha: float = mood_dynamics.DEFAULT_ALPHA,
        mood_decay: mood_dynamics.DecayFn | None = None,
    ):
        weights.validate()
        self.core = core
        self.weights = weights
        self.mood_decay = mood_decay or mood_dynamics.decay
        self.emotion_store = EmotionStore(db_path)
        self.relation_store = RelationStore(
            self.emotion_store.con, lock=self.emotion_store.lock,
        )
        self.worker = EmotionWorker(
            self.emotion_store, self.relation_store, classifier=classifier,
            queue_maxsize=queue_maxsize, relation_weight=relation_weight,
            mood_alpha=mood_alpha,
        )
        self.worker.start()

    # --- 体験記憶 ---
    def remember(self, text: str, ctx: dict | None = None,
                 partner_id: str | None = None) -> str:
        """体験を記録する。mnemosyne へ即書き込み、感情は背景推定。"""
        ctx = ctx or {}
        memory_id = self.core.remember(
            content=text, importance=ctx.get("importance", 0.5),
        )
        # 感情推定と関係性更新は背景へ(write をブロックしない)。
        # job_id = memory_id で冪等(FR-2.6)。
        self.worker.submit(EmotionJob(memory_id, text, partner_id))
        return memory_id

    # --- 知識記憶 ---
    def remember_fact(self, subject: str, predicate: str, obj: str,
                      valid_from: str | None = None) -> None:
        """事実を temporal triple に記録する。感情は付けない。"""
        self.core.triple_add(subject, predicate, obj, valid_from=valid_from)

    # --- 想起 ---
    def recall(self, query: str, ctx: dict | None = None,
               k: int = DEFAULT_K,
               candidate_k: int = DEFAULT_CANDIDATE_K) -> list[RankedHit]:
        """mnemosyne で広く候補取得 → partner_id 復元 → 二段ランク。

        ctx に partner_id / stm_oldest_id を入れると、関係相手一致と
        STM 境界除外が効く。
        """
        ctx = ctx or {}
        candidates = self.core.recall(query, top_k=candidate_k)
        ids = [c.memory_id for c in candidates]
        emotions = self.emotion_store.get_many(ids)
        # 上流は partner_id を知らないため amygdala DB から復元する(FR-2.5)
        partner_map = self.emotion_store.get_partner_map(ids)
        for c in candidates:
            if c.partner_id is None:
                c.partner_id = partner_map.get(c.memory_id)
        return rerank(candidates, emotions, ctx, k=k, weights=self.weights)

    def relation_context(self, partner_id: str) -> str:
        """recall 時に常時注入する関係状態サマリ(STM除外の対象外)。"""
        return self.relation_store.get(partner_id).to_context()

    # --- 現在の気分(FR-5) ---

    def mood(self) -> Emotion:
        """現在の気分(未初期化なら neutral)。"""
        return self.emotion_store.get_mood()

    def set_mood(self, emo: Emotion) -> None:
        """気分を明示的に設定する(FR-5.3)。"""
        self.emotion_store.save_mood(emo)

    def reset_mood(self) -> None:
        """気分を neutral に戻す(FR-5.3)。"""
        self.emotion_store.save_mood(Emotion.neutral_default())

    def tick_mood(self, turns: int = 1) -> Emotion:
        """会話ターン経過による減衰を適用して保存する(FR-5.2)。

        呼び出し側(会話ループ)がターンごとに呼ぶ。実時間ベースにしたい
        場合は経過時間をターン数へ換算して渡す。
        """
        decayed = self.mood_decay(self.emotion_store.get_mood(), turns)
        self.emotion_store.save_mood(decayed)
        return decayed

    # --- プロンプト注入 / export(FR-6) ---

    def state_block(self, partner_id: str | None = None,
                    lang: str = "ja") -> str:
        """気分(+関係状態)のシステムプロンプト注入ブロック(FR-6.1)。

        hersona の injection block の後ろに並置する想定。
        """
        relation = (self.relation_store.get(partner_id)
                    if partner_id is not None else None)
        return attach.render_state_block(self.mood(), relation, lang=lang)

    def export_state(self, partner_id: str | None = None) -> dict:
        """気分(+関係状態)の JSON 化可能な dict(FR-6.2)。"""
        relation = (self.relation_store.get(partner_id)
                    if partner_id is not None else None)
        return attach.export_state(self.mood(), relation)

    # --- データライフサイクル(NFR-12) ---

    def export_partner(self, partner_id: str) -> dict:
        """partner の関係状態と感情レコードをまとめて返す。"""
        state = self.relation_store.get(partner_id)
        return {
            "partner_id": partner_id,
            "relation": {"affinity": state.affinity, "trust": state.trust,
                         "milestones": list(state.milestones)},
            "emotions": self.emotion_store.export_partner(partner_id),
        }

    def forget_partner(self, partner_id: str) -> dict:
        """partner の感情レコードと関係状態を削除する。

        注意: 記憶本体(mnemosyne 側)は削除しない。過去の関係性更新の
        巻き戻しも行わない(REQUIREMENTS.md §10-7)。
        """
        deleted_emotions = self.emotion_store.delete_partner(partner_id)
        deleted_relations = self.relation_store.delete(partner_id)
        return {"emotions": deleted_emotions, "relations": deleted_relations}

    def cleanup_orphans(self, live_memory_ids: set[str]) -> int:
        """mnemosyne 側で削除された記憶の孤児感情レコードを清掃する。"""
        return self.emotion_store.cleanup_orphans(live_memory_ids)

    # --- 可観測性(NFR-11) ---

    def stats(self) -> dict:
        """背景ワーカの処理状況を返す。"""
        return self.worker.stats()

    def close(self) -> None:
        self.worker.stop()
        self.emotion_store.close()
