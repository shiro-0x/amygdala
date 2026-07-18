"""amygdala — 情動と関係性のメモリレイヤ。

mnemosyne(事実メモリ基盤)の上に、喜怒哀楽+無の感情パラメータ・
関係性進行・二段ランク想起を乗せる薄いレイヤ。

公開 API はこのモジュールから import する:

    from amygdala import MemoryRouter, Emotion
"""
from amygdala.attach import (compose_system_prompt, export_state,
                             render_state_block, sanitize_value,
                             token_estimate)
from amygdala.core_adapter import Core, InMemoryCore, RealCore
from amygdala.emotion import AXES, Emotion
from amygdala.interaction import identity as interaction_identity
from amygdala.interaction import synergy_and_antagonism
from amygdala.mood import decay as mood_decay
from amygdala.mood import integrate as mood_integrate
from amygdala.relation import RelationState, RelationStore
from amygdala.rerank import Candidate, RankedHit, RerankWeights, rerank
from amygdala.router import MemoryRouter
from amygdala.stm import filter_beyond_stm
from amygdala.store import EmotionStore
from amygdala.worker import (EmotionClassifier, EmotionJob, EmotionWorker,
                             MilestoneDetector)

__version__ = "2.0.0"

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
    "MilestoneDetector",
    "RankedHit",
    "RealCore",
    "RelationState",
    "RelationStore",
    "RerankWeights",
    "compose_system_prompt",
    "export_state",
    "filter_beyond_stm",
    "interaction_identity",
    "mood_decay",
    "mood_integrate",
    "render_state_block",
    "rerank",
    "sanitize_value",
    "synergy_and_antagonism",
    "token_estimate",
]
