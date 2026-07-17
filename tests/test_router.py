"""MemoryRouter のエンドツーエンドテスト(InMemoryCore 使用)。"""
import pytest

from amygdala import Emotion, InMemoryCore, MemoryRouter


@pytest.fixture()
def router(tmp_path):
    r = MemoryRouter(InMemoryCore(), db_path=str(tmp_path / "amygdala.db"),
                     classifier=lambda _t: Emotion(joy=1.0, neutral=0.0))
    yield r
    r.close()


def test_partner_boost_end_to_end(router):
    """P0: 同じ本文で partner A / B の記憶を作り、A 指定の recall で
    A の候補が partner boost を受ける(FR-2.5 の復元込み)。"""
    mid_a = router.remember("一緒に優勝して嬉しかった", partner_id="A")
    mid_b = router.remember("一緒に優勝して嬉しかった", partner_id="B")
    router.worker.drain_sync()

    hits = router.recall("優勝して 嬉しかった", ctx={"partner_id": "A"}, k=2)
    assert len(hits) == 2
    assert hits[0].candidate.memory_id == mid_a
    assert hits[0].candidate.partner_id == "A"   # DB から復元されている
    assert hits[1].candidate.memory_id == mid_b
    assert hits[0].score > hits[1].score


def test_recall_before_estimation_uses_neutral(router):
    """FR-2.1: 感情未推定でも neutral 既定で recall が動く。"""
    router.remember("まだ推定されていない出来事")
    # drain しない(未推定のまま)
    hits = router.recall("出来事")
    assert len(hits) == 1
    assert hits[0].emotion.is_neutral()


def test_stm_boundary_excludes_recent(router):
    old_id = router.remember("古い 出来事")
    new_id = router.remember("新しい 出来事")
    router.worker.drain_sync()
    hits = router.recall("出来事", ctx={"stm_oldest_id": new_id})
    ids = [h.candidate.memory_id for h in hits]
    assert old_id in ids and new_id not in ids


def test_relation_context_always_available(router):
    router.remember("楽しかった", partner_id="A")
    router.worker.drain_sync()
    ctx = router.relation_context("A")
    assert ctx.startswith("RELATION| partner=A")
    assert "affinity=+" in ctx


def test_remember_fact_goes_to_triples(router):
    router.remember_fact("user_42", "role", "manager", valid_from="2026-06-01")
    assert router.core.triples == [("user_42", "role", "manager", "2026-06-01")]
    # 事実は episodic に入らないので recall 候補にならない
    assert router.recall("manager") == []


def test_tick_relation_decays_slower_than_mood(router):
    """FR-4.4: 関係は気分より遅い時間軸で減衰する。"""
    router.remember("一緒に 遊んで 楽しかった 嬉しい", partner_id="A")
    router.worker.drain_sync()
    before = router.relation_store.get("A").affinity
    assert before > 0

    state = router.tick_relation("A")
    assert 0 < state.affinity < before
    # 既定率: 関係 0.01/tick は気分 0.1/turn の 1/10
    assert state.affinity == pytest.approx(before * 0.99)
    assert router.relation_store.get("A").affinity == pytest.approx(
        state.affinity)


def test_export_and_forget_partner(router):
    router.remember("楽しかった", partner_id="A")
    router.worker.drain_sync()

    exported = router.export_partner("A")
    assert exported["relation"]["affinity"] > 0
    assert len(exported["emotions"]) == 1

    deleted = router.forget_partner("A")
    assert deleted == {"emotions": 1, "relations": 1}
    assert router.export_partner("A")["emotions"] == []


def test_cleanup_orphans(router):
    mid = router.remember("消える 記憶")
    keep = router.remember("残る 記憶")
    router.worker.drain_sync()
    assert router.cleanup_orphans({keep}) == 1
    assert router.emotion_store.get(mid).is_neutral()


def test_recall_per_call_weights_override(router):
    """v1.2: recall(weights=...) が router 既定より優先される。"""
    from amygdala import RerankWeights
    router.remember("勝利 の 記憶", partner_id="A")
    router.remember("勝利 の 記憶", partner_id="B")
    router.worker.drain_sync()
    # partner 全振りなら A 指定で A が明確に上位
    w = RerankWeights(core=0.0, partner=1.0, emotion=0.0, importance=0.0)
    hits = router.recall("勝利", ctx={"partner_id": "A"}, k=2, weights=w)
    assert hits[0].candidate.partner_id == "A"


def test_recall_weights_selector(tmp_path):
    """v1.2: weights_selector(ctx) がコンテキストに応じて重みを切り替える。"""
    from amygdala import Emotion, InMemoryCore, MemoryRouter, RerankWeights

    emotion_heavy = RerankWeights(core=0.5, partner=0.0, emotion=0.5,
                                  importance=0.0)

    def selector(ctx):
        return emotion_heavy if ctx.get("mode") == "emotional" else None

    r = MemoryRouter(InMemoryCore(), db_path=str(tmp_path / "a.db"),
                     classifier=lambda _t: Emotion(joy=1.0, neutral=0.0),
                     weights_selector=selector)
    try:
        calm = r.remember("普通 の 話")       # neutral
        r.worker.drain_sync()
        # emotional モードでは感情強度が効くので joy の記憶が優先されやすい
        hits = r.recall("話", ctx={"mode": "emotional"}, k=1)
        assert hits  # 動作すること(選択フックが例外なく通る)
    finally:
        r.close()


def test_interaction_applied_in_router(tmp_path):
    """v1.2: interaction が背景ワーカで感情に適用される。"""
    from amygdala import (Emotion, InMemoryCore, MemoryRouter,
                          synergy_and_antagonism)
    r = MemoryRouter(InMemoryCore(), db_path=str(tmp_path / "a.db"),
                     classifier=lambda _t: Emotion(joy=0.5, pleasure=0.5,
                                                   neutral=0.0),
                     interaction=lambda e: synergy_and_antagonism(
                         e, synergy=0.2, antagonism=0.0))
    try:
        mid = r.remember("嬉しくて 楽しい")
        r.worker.drain_sync()
        # 相乗で joy が 0.5 から増える
        assert r.emotion_store.get(mid).joy > 0.5
    finally:
        r.close()


def test_stats_exposed(router):
    router.remember("x")
    router.worker.drain_sync()
    stats = router.stats()
    assert stats["processed"] == 1
    assert stats["queue_depth"] == 0
