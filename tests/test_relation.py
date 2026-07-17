"""関係性進行(RelationState / RelationStore)のテスト。"""
import threading

import pytest

from amygdala import Emotion, RelationState, RelationStore
from amygdala.store import EmotionStore


@pytest.fixture()
def stores(tmp_path):
    es = EmotionStore(str(tmp_path / "amygdala.db"))
    rs = RelationStore(es.con, lock=es.lock)
    yield es, rs
    es.close()


def test_apply_emotion_updates_affinity_and_trust():
    st = RelationState(partner_id="p")
    st.apply_emotion(Emotion(joy=1.0, neutral=0.0), weight=0.1)
    assert st.affinity == pytest.approx(0.1)
    assert st.trust == pytest.approx(0.1)
    st.apply_emotion(Emotion(anger=1.0, sorrow=1.0, neutral=0.0), weight=0.1)
    assert st.affinity == pytest.approx(-0.1)
    assert st.trust == pytest.approx(0.1)  # 怒・哀は trust に影響しない


def test_neutral_has_no_effect():
    st = RelationState(partner_id="p")
    st.apply_emotion(Emotion.neutral_default(), weight=0.5)
    assert st.affinity == 0.0
    assert st.trust == 0.0


def test_affinity_clamped():
    st = RelationState(partner_id="p")
    for _ in range(50):
        st.apply_emotion(Emotion(joy=1.0, pleasure=1.0, neutral=0.0), weight=0.1)
    assert st.affinity == 1.0
    assert st.trust == 1.0


def test_store_roundtrip(stores):
    _, rs = stores
    st = RelationState(partner_id="p", affinity=0.5, trust=0.25,
                       milestones=["初対面"])
    rs.save(st)
    loaded = rs.get("p")
    assert loaded.affinity == 0.5
    assert loaded.trust == 0.25
    assert loaded.milestones == ["初対面"]


def test_unknown_partner_returns_default(stores):
    _, rs = stores
    st = rs.get("nobody")
    assert st.affinity == 0.0 and st.trust == 0.0 and st.milestones == []


def test_add_milestone_atomic(stores):
    _, rs = stores
    rs.add_milestone("p", "初対面")
    rs.add_milestone("p", "初対面")  # 重複は追加しない
    rs.add_milestone("p", "仲直り")
    assert rs.get("p").milestones == ["初対面", "仲直り"]


def test_concurrent_apply_emotion_no_lost_update(stores):
    """FR-4.5 / P0: 並行更新で lost update が起きない。"""
    _, rs = stores
    n_threads, n_iter, weight = 8, 25, 0.004
    emo = Emotion(joy=1.0, neutral=0.0)

    def work():
        for _ in range(n_iter):
            rs.apply_emotion("p", emo, weight=weight)

    threads = [threading.Thread(target=work) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = n_threads * n_iter * weight  # 0.8 (< 1.0 なのでクランプ無関係)
    state = rs.get("p")
    assert state.affinity == pytest.approx(expected)
    assert state.trust == pytest.approx(expected)


def test_decay_moves_toward_zero_and_keeps_milestones():
    st = RelationState(partner_id="p", affinity=0.8, trust=-0.4,
                       milestones=["初対面"])
    st.decay(ticks=1, rate=0.1)
    assert st.affinity == pytest.approx(0.72)
    assert st.trust == pytest.approx(-0.36)   # 負値も 0 へ向かう
    assert st.milestones == ["初対面"]        # 節目は減衰しない


def test_decay_is_deterministic_and_composable():
    a = RelationState(partner_id="p", affinity=0.8)
    b = RelationState(partner_id="p", affinity=0.8)
    a.decay(ticks=5, rate=0.1)
    for _ in range(5):
        b.decay(ticks=1, rate=0.1)
    assert a.affinity == pytest.approx(b.affinity)
    assert a.affinity == pytest.approx(0.8 * 0.9 ** 5)


def test_decay_invalid_args():
    st = RelationState(partner_id="p")
    with pytest.raises(ValueError):
        st.decay(ticks=-1)
    with pytest.raises(ValueError):
        st.decay(rate=1.5)


def test_store_decay_atomic_roundtrip(stores):
    _, rs = stores
    rs.save(RelationState(partner_id="p", affinity=0.5, trust=0.5))
    state = rs.decay("p", ticks=1, rate=0.1)
    assert state.affinity == pytest.approx(0.45)
    assert rs.get("p").affinity == pytest.approx(0.45)  # 保存されている


def test_delete(stores):
    _, rs = stores
    rs.apply_emotion("p", Emotion(joy=1.0, neutral=0.0))
    assert rs.delete("p") == 1
    assert rs.get("p").affinity == 0.0
    assert rs.delete("p") == 0
