"""amygdala.router — 統合窓口。

体験(remember)は A版 episodic + 背景感情推定。
知識(remember_fact)は A版 temporal triple(感情なし)。
recall は A版で広く候補取得 → amygdala 二段ランク。

体験/知識の系統分離は「どの A版 API に書くか」で表現し、amygdala 側に
記憶本体を二重実装しない。
"""
from __future__ import annotations

from amygdala.core_adapter import Core
from amygdala.rerank import RankedHit, rerank
from amygdala.relation import RelationStore
from amygdala.store import EmotionStore
from amygdala.worker import EmotionJob, EmotionWorker, EmotionClassifier


class MemoryRouter:
    def __init__(
        self,
        core: Core,
        db_path: str = "amygdala.db",
        classifier: EmotionClassifier | None = None,
    ):
        self.core = core
        self.emotion_store = EmotionStore(db_path)
        self.relation_store = RelationStore(
            self.emotion_store.con, lock=self.emotion_store.lock,
        )
        self.worker = EmotionWorker(
            self.emotion_store, self.relation_store, classifier=classifier,
        )
        self.worker.start()

    # --- 体験記憶 ---
    def remember(self, text: str, ctx: dict | None = None,
                 partner_id: str | None = None) -> str:
        """体験を記録する。A版へ即書き込み、感情は背景推定。"""
        ctx = ctx or {}
        memory_id = self.core.remember(
            content=text, importance=ctx.get("importance", 0.5),
        )
        # 感情推定と関係性更新は背景へ(write をブロックしない)
        self.worker.submit(EmotionJob(memory_id, text, partner_id))
        return memory_id

    # --- 知識記憶 ---
    def remember_fact(self, subject: str, predicate: str, obj: str,
                      valid_from: str | None = None) -> None:
        """事実を temporal triple に記録する。感情は付けない。"""
        self.core.triple_add(subject, predicate, obj, valid_from=valid_from)

    # --- 想起 ---
    def recall(self, query: str, ctx: dict | None = None,
               k: int = 6, candidate_k: int = 24) -> list[RankedHit]:
        """A版で広く候補取得 → 二段ランク。

        ctx に partner_id / stm_oldest_id を入れると、関係相手一致と
        STM 境界除外が効く。
        """
        ctx = ctx or {}
        candidates = self.core.recall(query, top_k=candidate_k)
        ids = [c.memory_id for c in candidates]
        emotions = self.emotion_store.get_many(ids)
        return rerank(candidates, emotions, ctx, k=k)

    def relation_context(self, partner_id: str) -> str:
        """recall 時に常時注入する関係状態サマリ(STM除外の対象外)。"""
        return self.relation_store.get(partner_id).to_context()

    def close(self) -> None:
        self.worker.stop()
        self.emotion_store.close()
