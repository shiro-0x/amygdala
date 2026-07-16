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


def test_all_symbols_documented_in_public_api_md():
    """docs/PUBLIC_API.md と __all__ の乖離を機械検証する(1.0 契約)。"""
    import re
    from pathlib import Path

    doc = (Path(__file__).resolve().parent.parent / "docs"
           / "PUBLIC_API.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)", doc))
    missing = [name for name in amygdala.__all__ if name not in documented]
    assert not missing, f"PUBLIC_API.md に未記載の公開シンボル: {missing}"
