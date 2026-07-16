"""背景ワーカ(耐障害性・冪等性・可観測性)のテスト。"""
import pytest

from amygdala import Emotion, EmotionJob, EmotionWorker, RelationStore
from amygdala.store import EmotionStore


@pytest.fixture()
def stores(tmp_path):
    es = EmotionStore(str(tmp_path / "amygdala.db"))
    rs = RelationStore(es.con, lock=es.lock)
    yield es, rs
    es.close()


def _joy_classifier(_text: str) -> Emotion:
    return Emotion(joy=1.0, neutral=0.0)


def test_drain_sync_applies_emotion_and_relation(stores):
    es, rs = stores
    w = EmotionWorker(es, rs, classifier=_joy_classifier, relation_weight=0.1)
    w.submit(EmotionJob("m1", "嬉しかった", "p"))
    w.drain_sync()
    assert es.get("m1").joy == 1.0
    assert rs.get("p").affinity == pytest.approx(0.1)
    assert w.stats()["processed"] == 1


def test_duplicate_jobs_apply_once(stores):
    """FR-2.6 / P0: 重複投入しても関係性を二重更新しない。"""
    es, rs = stores
    w = EmotionWorker(es, rs, classifier=_joy_classifier, relation_weight=0.1)
    w.submit(EmotionJob("m1", "嬉しかった", "p"))
    w.submit(EmotionJob("m1", "嬉しかった", "p"))  # 同じ job_id(=memory_id)
    w.drain_sync()
    assert rs.get("p").affinity == pytest.approx(0.1)
    stats = w.stats()
    assert stats["processed"] == 1
    assert stats["skipped_duplicates"] == 1


def test_classifier_exception_falls_back_to_neutral(stores):
    es, rs = stores

    def broken(_text):
        raise RuntimeError("boom")

    w = EmotionWorker(es, rs, classifier=broken)
    w.submit(EmotionJob("m1", "x", "p"))
    w.drain_sync()
    assert es.get("m1").is_neutral()
    assert rs.get("p").affinity == 0.0  # neutral は関係に影響しない
    stats = w.stats()
    assert stats["fallbacks"] == 1
    assert stats["processed"] == 1  # フォールバック後も適用は成功


def test_db_exception_does_not_kill_worker(stores):
    """P0: ジョブ全体の例外でもワーカは無言停止しない。"""
    es, rs = stores
    w = EmotionWorker(es, rs, classifier=_joy_classifier)

    original = es.apply_job
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return original(*args, **kwargs)

    es.apply_job = flaky
    w.submit(EmotionJob("m1", "x", "p"))
    w.submit(EmotionJob("m2", "y", "p"))
    w.drain_sync()
    stats = w.stats()
    assert stats["failed"] == 1
    assert stats["processed"] == 1  # 2 件目は処理された
    assert es.get("m2").joy == 1.0


def test_queue_full_drops_new_job(stores):
    """NFR-10: キューは有界。満杯時は破棄して write をブロックしない。"""
    es, rs = stores
    w = EmotionWorker(es, rs, queue_maxsize=2)  # スレッドは起動しない
    assert w.submit(EmotionJob("m1", "a", None)) is True
    assert w.submit(EmotionJob("m2", "b", None)) is True
    assert w.submit(EmotionJob("m3", "c", None)) is False
    assert w.stats()["dropped"] == 1
    assert w.stats()["queue_depth"] == 2


def test_stop_drains_pending_jobs(stores):
    """NFR-10: stop() は先行ジョブを処理してから停止する。"""
    es, rs = stores
    w = EmotionWorker(es, rs, classifier=_joy_classifier)
    for i in range(5):
        w.submit(EmotionJob(f"m{i}", "t", None))
    w.start()
    w.stop(timeout=10.0)
    assert w.stats()["processed"] == 5
    assert es.get("m4").joy == 1.0


def test_background_thread_processes_jobs(stores):
    es, rs = stores
    w = EmotionWorker(es, rs, classifier=_joy_classifier)
    w.start()
    w.submit(EmotionJob("m1", "t", "p"))
    w.join()  # キューが空になるまで待つ
    w.stop()
    assert es.get("m1").joy == 1.0
