"""amygdala.mood — 現在の気分 state(FR-5)。

キャラクターが「いまどんな気分か」を表す、相手非依存の 5 値ベクトル
(Emotion を再利用)。Sentipolis の「二速の感情力学」を設計参考とする:

- 速い層 = 体験ごとの感情(emotion.py。記憶に紐づき変化しない)
- 遅い層 = 気分(mood)。体験感情を EMA(指数移動平均)で積分し、
  ターン経過で neutral へ減衰する

更新は 2 系統:
- integrate(): remember 時の感情推定結果から自動更新(背景ワーカ内、
  processed_jobs マーカにより冪等)
- decay(): 呼び出し側が会話ターンごとに tick する(既定はターン数ベース。
  実時間ベースにしたい場合は経過時間からターン数を換算して渡す)

いずれも純関数(Emotion → Emotion)で決定論的。減衰関数は差し替え可能。
neutral 軸は「感情が動いていない度合い」として 1 - intensity を維持する
(mood では未推定と平静を区別しないため、導出値とする)。
"""
from __future__ import annotations

from typing import Callable

from amygdala.emotion import Emotion

DEFAULT_ALPHA = 0.3       # 積分の学習率(1 に近いほど直近の体験に敏感)
DEFAULT_DECAY_RATE = 0.1  # 1 ターンあたりの neutral への減衰率

# ターン数を受け取り減衰後の気分を返す関数型。差し替え可能(FR-5.2)。
DecayFn = Callable[[Emotion, int], Emotion]


def _with_derived_neutral(joy: float, anger: float, sorrow: float,
                          pleasure: float) -> Emotion:
    emo = Emotion(joy=joy, anger=anger, sorrow=sorrow, pleasure=pleasure,
                  neutral=0.0)
    # clamp 後の値で neutral を導出する
    return Emotion(joy=emo.joy, anger=emo.anger, sorrow=emo.sorrow,
                   pleasure=emo.pleasure, neutral=1.0 - emo.intensity())


def integrate(mood: Emotion, emo: Emotion,
              alpha: float = DEFAULT_ALPHA) -> Emotion:
    """体験感情を気分へ積分する(EMA)。

    喜怒哀楽の各軸を mood*(1-alpha) + emo*alpha で更新する。
    体験が neutral(感情が動いていない)なら気分は 0 へ向かって薄まる
    (「何も起きないと落ち着いていく」に一致するのでそのまま採用)。
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")
    return _with_derived_neutral(
        joy=mood.joy * (1 - alpha) + emo.joy * alpha,
        anger=mood.anger * (1 - alpha) + emo.anger * alpha,
        sorrow=mood.sorrow * (1 - alpha) + emo.sorrow * alpha,
        pleasure=mood.pleasure * (1 - alpha) + emo.pleasure * alpha,
    )


def decay(mood: Emotion, turns: int = 1,
          rate: float = DEFAULT_DECAY_RATE) -> Emotion:
    """ターン経過で気分を neutral へ減衰させる(既定の減衰関数)。

    各感情軸に (1-rate)^turns を掛ける。決定論的でテスト可能(FR-5.2)。
    """
    if turns < 0:
        raise ValueError(f"turns must be >= 0, got {turns}")
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"rate must be in [0, 1], got {rate}")
    factor = (1.0 - rate) ** turns
    return _with_derived_neutral(
        joy=mood.joy * factor,
        anger=mood.anger * factor,
        sorrow=mood.sorrow * factor,
        pleasure=mood.pleasure * factor,
    )
