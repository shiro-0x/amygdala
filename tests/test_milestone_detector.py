"""milestone 自動検出(v1.2、注入式)のテスト。"""
import sys
from pathlib import Path

import pytest

from amygdala import Emotion, EmotionWorker, EmotionJob, RelationStore
from amygdala.store import EmotionStore

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from examples.rule_milestone_detector import rule_milestone_detector  # noqa: E402


@pytest.fixture()
def stores(tmp_path):
    es = EmotionStore(str(tmp_path / "a.db"))
    rs = RelationStore(es.con, lock=es.lock)
    yield es, rs
    es.close()


def test_rule_detector():
    assert rule_milestone_detector("今日 初めて 会って 話した") == ["初対面"]
    assert set(rule_milestone_detector("喧嘩 したけど 仲直り した")) == {"喧嘩", "仲直り"}
    assert rule_milestone_detector("普通の 一日") == []


def test_worker_records_detected_milestones(stores):
    es, rs = stores
    w = EmotionWorker(es, rs, classifier=lambda _t: Emotion(joy=1.0, neutral=0.0),
                      milestone_detector=rule_milestone_detector)
    w.submit(EmotionJob("m1", "初めて 会った", "p"))
    w.drain_sync()
    assert rs.get("p").milestones == ["初対面"]


def test_milestone_detection_is_idempotent(stores):
    es, rs = stores
    w = EmotionWorker(es, rs, milestone_detector=rule_milestone_detector)
    w.submit(EmotionJob("m1", "初めて 会った", "p"))
    w.submit(EmotionJob("m1", "初めて 会った", "p"))  # 同一 job_id
    w.drain_sync()
    assert rs.get("p").milestones == ["初対面"]  # 重複追加なし


def test_detector_without_partner_is_skipped(stores):
    es, rs = stores
    w = EmotionWorker(es, rs, milestone_detector=rule_milestone_detector)
    w.submit(EmotionJob("m1", "初めて 会った", None))
    w.drain_sync()
    assert rs.get("nobody").milestones == []


def test_detector_exception_does_not_break_worker(stores):
    es, rs = stores

    def boom(_t):
        raise RuntimeError("detector down")

    w = EmotionWorker(es, rs,
                      classifier=lambda _t: Emotion(joy=1.0, neutral=0.0),
                      milestone_detector=boom)
    w.submit(EmotionJob("m1", "初めて 会った", "p"))
    w.drain_sync()
    # 感情・関係は適用され、milestone だけスキップされる
    assert es.get("m1").joy == 1.0
    assert rs.get("p").milestones == []
    assert w.stats()["processed"] == 1
