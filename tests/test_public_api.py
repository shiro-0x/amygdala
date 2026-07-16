"""公開 API の import 契約(P0: from amygdala import MemoryRouter, Emotion)。"""
import amygdala


def test_public_symbols_importable():
    from amygdala import (AXES, Candidate, Core, Emotion, EmotionClassifier,
                          EmotionJob, EmotionStore, EmotionWorker,
                          InMemoryCore, MemoryRouter, RankedHit,
                          RelationState, RelationStore, RerankWeights,
                          filter_beyond_stm, rerank)
    assert MemoryRouter and Emotion  # 使用済みにする

    for name in amygdala.__all__:
        assert hasattr(amygdala, name), name


def test_version():
    assert amygdala.__version__
