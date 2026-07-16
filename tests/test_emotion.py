"""Emotion(喜怒哀楽+無)の単体テスト。"""
import pytest

from amygdala import AXES, Emotion


def test_default_is_neutral():
    emo = Emotion()
    assert emo.neutral == 1.0
    assert emo.intensity() == 0.0
    assert emo.is_neutral()
    assert emo.dominant() == "neutral"


def test_clamp_to_unit_range():
    emo = Emotion(joy=1.5, anger=-0.3, sorrow=0.5, pleasure=2.0, neutral=-1.0)
    assert emo.joy == 1.0
    assert emo.anger == 0.0
    assert emo.sorrow == 0.5
    assert emo.pleasure == 1.0
    assert emo.neutral == 0.0


def test_intensity_excludes_neutral():
    emo = Emotion(joy=0.2, anger=0.7, neutral=1.0)
    assert emo.intensity() == 0.7


def test_dominant_prefers_emotion_on_tie():
    # 感情軸が neutral 以上なら感情を支配的とみなす(>= 判定)
    emo = Emotion(joy=0.5, neutral=0.5)
    assert emo.dominant() == "joy"
    emo2 = Emotion(joy=0.3, neutral=0.6)
    assert emo2.dominant() == "neutral"


def test_from_dict_neutral_zeroed_when_emotion_given():
    # FR-1.4: 感情指定時は neutral 0 起点
    emo = Emotion.from_dict({"joy": 0.8})
    assert emo.joy == 0.8
    assert emo.neutral == 0.0


def test_from_dict_explicit_neutral_kept():
    emo = Emotion.from_dict({"joy": 0.8, "neutral": 0.3})
    assert emo.neutral == 0.3


def test_from_dict_empty_defaults_to_neutral():
    assert Emotion.from_dict({}).neutral == 1.0
    assert Emotion.from_dict(None).neutral == 1.0


def test_list_roundtrip_follows_axes_order():
    emo = Emotion(joy=0.1, anger=0.2, sorrow=0.3, pleasure=0.4, neutral=0.5)
    values = emo.to_list()
    assert values == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert Emotion.from_list(values) == emo
    assert list(emo.to_dict().keys()) == list(AXES)


def test_from_list_wrong_length_raises():
    with pytest.raises(ValueError):
        Emotion.from_list([0.1, 0.2])
