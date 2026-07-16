"""ルールベースの感情分類器のリファレンス実装(FR-2.3 / マイルストーン 0.4)。

LLM を使わない決定論的な分類器。キーワード一致で喜怒哀楽を推定する。
精度は低いが、依存ゼロ・コストゼロ・完全に再現可能なので、
開発時のデフォルトやテスト、LLM 分類器のフォールバックに向く。

使い方:
    from examples.rule_classifier import rule_classifier
    router = MemoryRouter(core, classifier=rule_classifier)
"""
from __future__ import annotations

from amygdala import Emotion

# 軸ごとのキーワード(日本語 + 英語)。1 ヒット 0.4、2 ヒット以上 0.8。
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "joy": ("嬉し", "うれし", "喜", "やった", "最高", "合格", "優勝", "昇進",
            "happy", "glad", "joy", "delight"),
    "anger": ("怒", "腹立", "むかつ", "ムカ", "許せ", "イライラ", "苛立",
              "angry", "furious", "annoy", "mad"),
    "sorrow": ("悲し", "かなし", "泣", "辛", "つら", "寂し", "さみし", "落ち込",
               "喪失", "sad", "sorrow", "grief", "lonely", "cry"),
    "pleasure": ("楽し", "たのし", "面白", "おもしろ", "心地", "気持ちい", "遊",
                 "ワクワク", "わくわく", "fun", "enjoy", "pleasant", "exciting"),
}


def rule_classifier(text: str) -> Emotion:
    """キーワード一致で喜怒哀楽を推定する。ヒットなしなら neutral。"""
    scores: dict[str, float] = {}
    for axis, words in _KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits:
            scores[axis] = 0.4 if hits == 1 else 0.8
    return Emotion.from_dict(scores)  # 空なら neutral=1.0


if __name__ == "__main__":
    for sample in ("試験に合格して嬉しかった",
                   "約束を破られて腹が立った",
                   "今日は天気の話をした"):
        emo = rule_classifier(sample)
        print(f"{sample!r} -> dominant={emo.dominant()} {emo.to_dict()}")
