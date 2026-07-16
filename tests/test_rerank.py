"""二段ランクの単体テスト。"""
import pytest

from amygdala import Candidate, Emotion, RerankWeights, rerank
from amygdala._ulid import new_ulid


def _cand(text="x", score=0.5, importance=0.5, partner=None, ts=1000):
    return Candidate(memory_id=new_ulid(ts_ms=ts), text=text, score=score,
                     importance=importance, partner_id=partner)


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        RerankWeights(core=0.9, partner=0.9, emotion=0.0, importance=0.0).validate()
    RerankWeights().validate()  # 既定は OK


def test_partner_match_boosts():
    a = _cand(partner="A", ts=1000)
    b = _cand(partner="B", ts=1001)
    hits = rerank([a, b], {}, {"partner_id": "A"}, k=2)
    assert hits[0].candidate.partner_id == "A"
    assert hits[0].score > hits[1].score


def test_emotion_salience_boosts_any_emotion():
    # FR-3.6: 喜でも怒でも、強い感情は同様に上位化する
    calm = _cand(ts=1000)
    angry = _cand(ts=1001)
    joyful = _cand(ts=1002)
    emotions = {
        angry.memory_id: Emotion(anger=0.9, neutral=0.0),
        joyful.memory_id: Emotion(joy=0.9, neutral=0.0),
    }
    hits = rerank([calm, angry, joyful], emotions, {}, k=3)
    scores = {h.candidate.memory_id: h.score for h in hits}
    assert scores[angry.memory_id] == scores[joyful.memory_id]
    assert scores[angry.memory_id] > scores[calm.memory_id]


def test_missing_emotion_defaults_to_neutral():
    c = _cand()
    hits = rerank([c], {}, {}, k=1)
    assert hits[0].emotion.is_neutral()


def test_stm_boundary_applied():
    old = _cand(ts=1000)
    new = _cand(ts=2000)
    boundary = new_ulid(ts_ms=1500)
    hits = rerank([old, new], {}, {"stm_oldest_id": boundary}, k=5)
    assert [h.candidate.memory_id for h in hits] == [old.memory_id]


def test_invalid_stm_boundary_fails_open():
    old = _cand(ts=1000)
    new = _cand(ts=2000)
    hits = rerank([old, new], {}, {"stm_oldest_id": "bogus"}, k=5)
    assert len(hits) == 2


def test_custom_weights_change_ranking():
    # importance を全振りすれば importance の高い候補が勝つ
    low_imp = _cand(score=1.0, importance=0.0, ts=1000)
    high_imp = _cand(score=0.0, importance=1.0, ts=1001)
    w = RerankWeights(core=0.0, partner=0.0, emotion=0.0, importance=1.0)
    hits = rerank([low_imp, high_imp], {}, {}, k=2, weights=w)
    assert hits[0].candidate.memory_id == high_imp.memory_id
