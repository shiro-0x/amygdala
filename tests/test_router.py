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


def test_stats_exposed(router):
    router.remember("x")
    router.worker.drain_sync()
    stats = router.stats()
    assert stats["processed"] == 1
    assert stats["queue_depth"] == 0
