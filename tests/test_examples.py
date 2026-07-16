"""examples/(リファレンス分類器・デモ)のスモークテスト。"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from examples.rule_classifier import rule_classifier  # noqa: E402


def test_rule_classifier_joy():
    emo = rule_classifier("試験に合格して嬉しかった")
    assert emo.joy > 0
    assert emo.dominant() == "joy"


def test_rule_classifier_multiple_hits_score_higher():
    one = rule_classifier("嬉しかった")
    two = rule_classifier("合格して嬉しかった、やった")
    assert two.joy > one.joy


def test_rule_classifier_neutral():
    emo = rule_classifier("今日は天気の話をした")
    assert emo.is_neutral()
    assert emo.neutral == 1.0


def test_rule_classifier_mixed():
    emo = rule_classifier("楽しかったけど別れ際は悲しかった")
    assert emo.pleasure > 0 and emo.sorrow > 0


def test_chat_loop_demo_runs():
    """デモが例外なく最後まで走る(エンドツーエンドの配線確認)。"""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "examples" / "chat_loop.py")],
        capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert "state_block" in result.stdout
    assert "RELATION|" not in result.stdout  # state_block 形式であること
    assert "関係[user_42]" in result.stdout
    assert "score=" in result.stdout


def test_llm_classifier_schema_is_valid():
    """anthropic が入っている環境でのみ、スキーマと生成器の形を検証する。"""
    pytest.importorskip("anthropic")
    from examples.llm_classifier import _SCHEMA, make_llm_classifier
    assert _SCHEMA["additionalProperties"] is False
    assert set(_SCHEMA["required"]) == {"joy", "anger", "sorrow", "pleasure"}
    # 数値範囲制約は structured outputs 非対応なので入れない
    for prop in _SCHEMA["properties"].values():
        assert "minimum" not in prop and "maximum" not in prop
    assert callable(make_llm_classifier)
