"""ルールベースの milestone 検出器のリファレンス実装(v1.2、注入式)。

体験テキストから「節目」ラベルをキーワードで抽出する決定論的な検出器。
`MemoryRouter(..., milestone_detector=rule_milestone_detector)` に渡すと、
背景ワーカが検出したラベルを冪等トランザクション内で関係性に追記する。

LLM 検出器を使う場合も同じ `Callable[[str], list[str]]` 型で差し込める
(examples/llm_classifier.py と同様に structured outputs で labels を得る)。
"""
from __future__ import annotations

# ラベル -> それを示すキーワード群。最初に一致したラベルを返す(重複は付けない)。
_MILESTONE_RULES: dict[str, tuple[str, ...]] = {
    "初対面": ("初めて 会", "はじめて 会", "初対面", "first met", "first time we"),
    "打ち明け": ("打ち明け", "秘密を話", "本音を", "confided", "opened up"),
    "喧嘩": ("喧嘩", "口論", "言い争", "quarrel", "argument", "fought"),
    "仲直り": ("仲直り", "和解", "許して", "謝って", "made up", "reconcil"),
    "約束": ("約束した", "誓っ", "promise", "vowed"),
    "別れ": ("別れ", "さよなら", "去っ", "farewell", "said goodbye"),
}


def rule_milestone_detector(text: str) -> list[str]:
    """テキストから節目ラベル列を返す。該当なしなら空リスト。"""
    found: list[str] = []
    for label, words in _MILESTONE_RULES.items():
        if any(w in text for w in words):
            found.append(label)
    return found


if __name__ == "__main__":
    for sample in ("今日 初めて 会って 話した",
                   "些細な ことで 喧嘩 したけど、すぐ 仲直り した",
                   "普通に 買い物 した"):
        print(f"{sample!r} -> {rule_milestone_detector(sample)}")
