"""amygdala.interaction — 感情間の相互作用(オプトイン、v1.2 / §中期)。

感情推定の生値に対し、軸どうしの相乗・拮抗を適用して補正する純関数。
既定は恒等(何もしない)。オプトインで `MemoryRouter(..., interaction=...)`
に渡す。決定論的でテスト可能。

設計方針:
- 生の分類結果を壊さない(積分・関係更新の直前に 1 回だけ適用)。
- 補正はあくまで軸間の弱い結合であり、valence(快/不快)や response policy
  とは別概念(FR-3.6 の区別を踏襲)。
- 既定ルール `synergy_and_antagonism` は控えめ:
    - joy と pleasure は同時に立つと弱く相乗(嬉しくかつ楽しい → 増幅)
    - joy/pleasure と anger/sorrow は互いに弱く相殺(混在時は薄める)
  係数は経験則。RerankWeights 同様、値に依存する場合は明示的に渡すこと。
"""
from __future__ import annotations

from typing import Callable

from amygdala.emotion import Emotion

# text ではなく推定済み Emotion を受け取り、補正後 Emotion を返す型。
InteractionFn = Callable[[Emotion], Emotion]

DEFAULT_SYNERGY = 0.15      # 快感情どうしの相乗係数
DEFAULT_ANTAGONISM = 0.20   # 快 vs 不快の相殺係数


def identity(emo: Emotion) -> Emotion:
    """既定。相互作用なし。"""
    return emo


def synergy_and_antagonism(
    emo: Emotion,
    synergy: float = DEFAULT_SYNERGY,
    antagonism: float = DEFAULT_ANTAGONISM,
) -> Emotion:
    """快感情の相乗と、快 vs 不快の相殺を適用する(既定ルール)。

    - positive = joy + pleasure、negative = anger + sorrow の総量で結合を測る。
    - 相乗: joy/pleasure に (1 + synergy * 相手の快強度) を掛ける。
    - 相殺: 各軸から antagonism * (反対極の総量) を引く。
    neutral は intensity から導出し直す(mood と同じ扱い)。
    """
    neg_total = emo.anger + emo.sorrow
    pos_total = emo.joy + emo.pleasure

    joy = emo.joy * (1.0 + synergy * emo.pleasure) - antagonism * neg_total
    pleasure = emo.pleasure * (1.0 + synergy * emo.joy) - antagonism * neg_total
    anger = emo.anger - antagonism * pos_total
    sorrow = emo.sorrow - antagonism * pos_total

    # clamp は Emotion.__post_init__ が行う。neutral は intensity から導出。
    result = Emotion(joy=joy, anger=anger, sorrow=sorrow, pleasure=pleasure,
                     neutral=0.0)
    return Emotion(joy=result.joy, anger=result.anger, sorrow=result.sorrow,
                   pleasure=result.pleasure,
                   neutral=1.0 - result.intensity())
