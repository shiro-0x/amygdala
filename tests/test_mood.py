"""現在の気分 state(FR-5)のテスト。"""
import pytest

from amygdala import Emotion, InMemoryCore, MemoryRouter, mood_decay, mood_integrate
from amygdala.mood import DEFAULT_ALPHA


def test_integrate_moves_toward_emotion():
    mood = Emotion.neutral_default()
    joyful = Emotion(joy=1.0, neutral=0.0)
    m1 = mood_integrate(mood, joyful, alpha=0.5)
    assert m1.joy == pytest.approx(0.5)
    assert m1.neutral == pytest.approx(0.5)  # 導出値: 1 - intensity
    m2 = mood_integrate(m1, joyful, alpha=0.5)
    assert m2.joy == pytest.approx(0.75)


def test_integrate_neutral_experience_calms_mood():
    mood = Emotion(joy=0.8, neutral=0.2)
    m = mood_integrate(mood, Emotion.neutral_default(), alpha=0.5)
    assert m.joy == pytest.approx(0.4)


def test_integrate_invalid_alpha():
    with pytest.raises(ValueError):
        mood_integrate(Emotion(), Emotion(), alpha=0.0)
    with pytest.raises(ValueError):
        mood_integrate(Emotion(), Emotion(), alpha=1.5)


def test_decay_is_deterministic_and_monotonic():
    mood = Emotion(joy=1.0, anger=0.5, neutral=0.0)
    d1 = mood_decay(mood, turns=1, rate=0.1)
    assert d1.joy == pytest.approx(0.9)
    assert d1.anger == pytest.approx(0.45)
    d5 = mood_decay(mood, turns=5, rate=0.1)
    assert d5.joy == pytest.approx(0.9 ** 5)
    # 2 回に分けても同じ(決定論的)
    assert mood_decay(d1, turns=4, rate=0.1).joy == pytest.approx(d5.joy)


def test_decay_zero_turns_noop():
    mood = Emotion(joy=0.7, neutral=0.3)
    assert mood_decay(mood, turns=0).joy == pytest.approx(0.7)


def test_decay_invalid_args():
    with pytest.raises(ValueError):
        mood_decay(Emotion(), turns=-1)
    with pytest.raises(ValueError):
        mood_decay(Emotion(), rate=1.5)


@pytest.fixture()
def router(tmp_path):
    r = MemoryRouter(InMemoryCore(), db_path=str(tmp_path / "amygdala.db"),
                     classifier=lambda _t: Emotion(joy=1.0, neutral=0.0))
    yield r
    r.close()


def test_mood_updates_from_remember(router):
    """FR-5.3: remember の感情推定から背景で気分が自動更新される。"""
    assert router.mood().is_neutral()
    router.remember("嬉しい出来事")
    router.worker.drain_sync()
    assert router.mood().joy == pytest.approx(DEFAULT_ALPHA)


def test_mood_update_is_idempotent(router):
    """FR-2.6: 同じジョブの二重処理で気分を二重積分しない。"""
    from amygdala import EmotionJob
    router.worker.submit(EmotionJob("m1", "嬉しい", None))
    router.worker.submit(EmotionJob("m1", "嬉しい", None))
    router.worker.drain_sync()
    assert router.mood().joy == pytest.approx(DEFAULT_ALPHA)  # 1 回分のみ


def test_set_reset_tick_mood(router):
    router.set_mood(Emotion(joy=1.0, neutral=0.0))
    assert router.mood().joy == 1.0

    ticked = router.tick_mood(turns=1)
    assert ticked.joy == pytest.approx(0.9)
    assert router.mood().joy == pytest.approx(0.9)  # 保存されている

    router.reset_mood()
    assert router.mood().is_neutral()


def test_mood_persists_across_restart(tmp_path):
    """FR-5.4: プロセス再起動(= Router 再生成)をまたいで永続化。"""
    db = str(tmp_path / "amygdala.db")
    r1 = MemoryRouter(InMemoryCore(), db_path=db)
    r1.set_mood(Emotion(sorrow=0.6, neutral=0.4))
    r1.close()

    r2 = MemoryRouter(InMemoryCore(), db_path=db)
    try:
        assert r2.mood().sorrow == pytest.approx(0.6)
    finally:
        r2.close()


def test_custom_decay_fn(tmp_path):
    def instant_calm(_mood, _turns):
        return Emotion.neutral_default()

    r = MemoryRouter(InMemoryCore(), db_path=str(tmp_path / "a.db"),
                     mood_decay=instant_calm)
    try:
        r.set_mood(Emotion(anger=1.0, neutral=0.0))
        assert r.tick_mood().is_neutral()
    finally:
        r.close()
