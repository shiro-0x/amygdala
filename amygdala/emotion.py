"""amygdala.emotion — 体験記憶の感情パラメータ。

喜怒哀楽 + 無 の5値モデル。各値は 0.0〜1.0。
- joy(喜), anger(怒), sorrow(哀), pleasure(楽): 情動4軸。複数同時に立ってよい。
- neutral(無): 感情が動かなかったことを積極的に記録する軸。既定は 1.0。

感情強度(intensity)は喜怒哀楽4軸の最大値で、neutral は含めない。
想起スコアの感情項に使う(平静な記憶が想起を埋めないようにするため)。
"""
from __future__ import annotations

from dataclasses import dataclass

# 感情軸の正準キー順。to_list / from_list はこの順序に従う。
AXES = ("joy", "anger", "sorrow", "pleasure", "neutral")


def _clamp01(x: float) -> float:
    """0.0〜1.0 に丸める。"""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


@dataclass
class Emotion:
    """喜怒哀楽+無の5値感情ベクトル。"""

    joy: float = 0.0       # 喜
    anger: float = 0.0     # 怒
    sorrow: float = 0.0    # 哀
    pleasure: float = 0.0  # 楽
    neutral: float = 1.0   # 無（既定: 感情が動いていない状態）

    def __post_init__(self) -> None:
        self.joy = _clamp01(self.joy)
        self.anger = _clamp01(self.anger)
        self.sorrow = _clamp01(self.sorrow)
        self.pleasure = _clamp01(self.pleasure)
        self.neutral = _clamp01(self.neutral)

    # --- 派生量 ---
    def intensity(self) -> float:
        """感情強度 = 喜怒哀楽4軸の最大値（無は含めない）。

        想起スコアの感情項に使用。感情が強く動いた体験ほど大きくなる。
        """
        return max(self.joy, self.anger, self.sorrow, self.pleasure)

    def is_neutral(self, threshold: float = 0.1) -> bool:
        """感情がほぼ動いていないか（喜怒哀楽がすべて threshold 未満）。"""
        return self.intensity() < threshold

    def dominant(self) -> str:
        """最も強い感情軸のキーを返す。

        喜怒哀楽の最大値が neutral 以上なら、その感情を支配的とみなす。
        逆に neutral の方が大きい場合のみ 'neutral' を返す。
        """
        emo4 = {"joy": self.joy, "anger": self.anger,
                "sorrow": self.sorrow, "pleasure": self.pleasure}
        key, val = max(emo4.items(), key=lambda kv: kv[1])
        return key if val >= self.neutral else "neutral"

    # --- 直列化 ---
    def to_list(self) -> list[float]:
        """[joy, anger, sorrow, pleasure, neutral] の順で返す。"""
        return [self.joy, self.anger, self.sorrow, self.pleasure, self.neutral]

    def to_dict(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in AXES}

    @classmethod
    def from_list(cls, values: list[float] | tuple[float, ...]) -> "Emotion":
        """to_list と対称。長さ5を想定。"""
        if len(values) != len(AXES):
            raise ValueError(f"expected {len(AXES)} values, got {len(values)}")
        return cls(*values)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Emotion":
        """部分指定可。空/None なら neutral=1.0 の既定。

        仕様(FR-1.4): 喜怒哀楽のいずれかが指定されていて neutral の明示が
        無い場合、neutral は 0.0 起点とする(「感情が動いた」ことが分かって
        いるのに既定の無=1.0 を残さないため)。何も指定が無ければ既定の
        neutral=1.0(=未推定/平静)になる。
        """
        if not d:
            return cls()
        return cls(
            joy=d.get("joy", 0.0),
            anger=d.get("anger", 0.0),
            sorrow=d.get("sorrow", 0.0),
            pleasure=d.get("pleasure", 0.0),
            # 何か感情が指定されていれば neutral は明示が無い限り 0 起点にする
            neutral=d.get("neutral", 0.0 if any(
                d.get(k, 0.0) for k in ("joy", "anger", "sorrow", "pleasure")
            ) else 1.0),
        )

    @classmethod
    def neutral_default(cls) -> "Emotion":
        """未推定時の既定（無=1.0）。"""
        return cls()
