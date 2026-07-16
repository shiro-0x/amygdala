"""EmotionStore(永続化・冪等適用・ライフサイクル)のテスト。"""
import pytest

from amygdala import Emotion, RelationStore
from amygdala.store import EmotionStore


@pytest.fixture()
def store(tmp_path):
    es = EmotionStore(str(tmp_path / "amygdala.db"))
    yield es
    es.close()


def test_get_unknown_returns_neutral(store):
    assert store.get("nope").is_neutral()


def test_put_get_roundtrip(store):
    emo = Emotion(joy=0.8, neutral=0.0)
    store.put("m1", emo, partner_id="p")
    got = store.get("m1")
    assert got.joy == 0.8 and got.neutral == 0.0


def test_get_many_fills_missing_with_neutral(store):
    store.put("m1", Emotion(joy=0.5, neutral=0.0))
    result = store.get_many(["m1", "m2"])
    assert result["m1"].joy == 0.5
    assert result["m2"].is_neutral()
    assert store.get_many([]) == {}


def test_get_partner_map(store):
    store.put("m1", Emotion(joy=0.5, neutral=0.0), partner_id="A")
    store.put("m2", Emotion.neutral_default(), partner_id=None)
    pm = store.get_partner_map(["m1", "m2", "m3"])
    assert pm["m1"] == "A"
    assert pm["m2"] is None
    assert "m3" not in pm  # 未登録は含めない


def test_apply_job_is_idempotent(store):
    """FR-2.6 / P0: 同じ job を 2 回処理しても二重更新しない。"""
    rs = RelationStore(store.con, lock=store.lock)
    emo = Emotion(joy=1.0, neutral=0.0)
    assert store.apply_job("j1", "m1", emo, "p", rs, relation_weight=0.1) is True
    assert store.apply_job("j1", "m1", emo, "p", rs, relation_weight=0.1) is False
    state = rs.get("p")
    assert state.affinity == pytest.approx(0.1)  # 1 回分のみ
    assert state.trust == pytest.approx(0.1)


def test_apply_job_without_partner(store):
    assert store.apply_job("j2", "m2", Emotion(joy=0.3, neutral=0.0),
                           None, None) is True
    assert store.get("m2").joy == 0.3


def test_delete_and_export_partner(store):
    store.put("m1", Emotion(joy=0.5, neutral=0.0), partner_id="A")
    store.put("m2", Emotion(anger=0.5, neutral=0.0), partner_id="A")
    store.put("m3", Emotion.neutral_default(), partner_id="B")

    exported = store.export_partner("A")
    assert len(exported) == 2
    assert {r["memory_id"] for r in exported} == {"m1", "m2"}
    assert exported[0]["joy"] in (0.0, 0.5)

    assert store.delete_partner("A") == 2
    assert store.export_partner("A") == []
    assert store.get_partner_map(["m3"])["m3"] == "B"  # 他 partner は無傷


def test_delete_memory(store):
    store.put("m1", Emotion(joy=0.5, neutral=0.0))
    assert store.delete_memory("m1") == 1
    assert store.delete_memory("m1") == 0
    assert store.get("m1").is_neutral()


def test_cleanup_orphans(store):
    """NFR-12 / P0: mnemosyne 側で消えた記憶の孤児レコードを清掃できる。"""
    store.put("live", Emotion(joy=0.5, neutral=0.0))
    store.put("dead", Emotion(anger=0.5, neutral=0.0))
    removed = store.cleanup_orphans({"live"})
    assert removed == 1
    assert store.get("dead").is_neutral()   # 消えた
    assert store.get("live").joy == 0.5     # 残った
    assert store.cleanup_orphans({"live"}) == 0
