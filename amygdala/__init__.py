"""amygdala — 情動と関係性のメモリレイヤ。

mnemosyne(事実メモリ基盤)の上に、喜怒哀楽+無の感情パラメータ・
関係性進行・二段ランク想起を乗せる薄いレイヤ。

公開 API はこのモジュールから import する:

    from amygdala import MemoryRouter, Emotion
"""
from amygdala.core_adapter import Core, InMemoryCore, RealCore
from amygdala.emotion import AXES, Emotion
from amygdala.relation import RelationState, RelationStore
from amygdala.rerank import Candidate, RankedHit, RerankWeights, rerank
from amygdala.router import MemoryRouter
from amygdala.stm import filter_beyond_stm
from amygdala.store import EmotionStore
from amygdala.worker import EmotionClassifier, EmotionJob, EmotionWorker

__version__ = "0.1.0"

__all__ = [
    "AXES",
    "Candidate",
    "Core",
    "Emotion",
    "EmotionClassifier",
    "EmotionJob",
    "EmotionStore",
    "EmotionWorker",
    "InMemoryCore",
    "MemoryRouter",
    "RankedHit",
    "RealCore",
    "RelationState",
    "RelationStore",
    "RerankWeights",
    "filter_beyond_stm",
    "rerank",
]
