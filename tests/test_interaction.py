"""感情間相互作用(v1.2)のテスト。"""
import pytest

from amygdala import Emotion, interaction_identity, synergy_and_antagonism


def test_identity_is_noop():
    emo = Emotion(joy=0.5, anger=0.3, neutral=0.0)
    assert interaction_identity(emo) == emo


def test_synergy_boosts_co_present_positive():
    both = Emotion(joy=0.5, pleasure=0.5, neutral=0.0)
    out = synergy_and_antagonism(both, synergy=0.2, antagonism=0.0)
    # joy = 0.5 * (1 + 0.2*0.5) = 0.55
    assert out.joy == pytest.approx(0.55)
    assert out.pleasure == pytest.approx(0.55)


def test_antagonism_dampens_opposite_poles():
    mixed = Emotion(joy=0.6, anger=0.5, neutral=0.0)
    out = synergy_and_antagonism(mixed, synergy=0.0, antagonism=0.2)
    # joy = 0.6 - 0.2*(anger 0.5) = 0.5 ; anger = 0.5 - 0.2*(pos 0.6) = 0.38
    assert out.joy == pytest.approx(0.5)
    assert out.anger == pytest.approx(0.38)


def test_result_is_clamped_and_neutral_derived():
    out = synergy_and_antagonism(Emotion(anger=0.4, neutral=0.0),
                                 synergy=0.0, antagonism=0.5)
    # anger = 0.4 - 0.5*0 = 0.4 (pos_total 0); joy/pleasure clamped to 0
    assert out.joy == 0.0
    assert out.neutral == pytest.approx(1.0 - out.intensity())


def test_pure_positive_unaffected_by_antagonism():
    pos = Emotion(joy=0.8, neutral=0.0)
    out = synergy_and_antagonism(pos, synergy=0.0, antagonism=0.3)
    assert out.joy == pytest.approx(0.8)  # 相手極が無いので変化なし
