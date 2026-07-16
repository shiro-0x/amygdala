"""mnemosyne 実 SDK との契約テスト(FR-3.5 / NFR-4)。

mnemosyne-memory がインストールされている環境(CI)でのみ実行される。
未インストールならスキップ。上流の公開 API 形状と RealCore の正規化が
噛み合っていることだけを検証する(検索品質は上流の責務)。
"""
import pytest

mnemosyne = pytest.importorskip("mnemosyne")


@pytest.fixture()
def core(tmp_path, monkeypatch):
    # mnemosyne が既定でホームや CWD に DB を作る場合に備えて隔離する
    monkeypatch.chdir(tmp_path)
    from amygdala import RealCore
    return RealCore()


def test_remember_returns_string_id(core):
    mid = core.remember("契約テスト: 昇進して喜んでいた", importance=0.5)
    assert isinstance(mid, str) and mid


def test_recall_returns_normalized_candidates(core):
    core.remember("契約テスト: 昇進して喜んでいた", importance=0.5)
    candidates = core.recall("昇進", top_k=5)
    assert isinstance(candidates, list)
    for c in candidates:
        assert isinstance(c.memory_id, str) and c.memory_id
        assert isinstance(c.text, str)
        assert 0.0 <= c.score <= 1.0       # FR-3.5: 正規化済み
        assert 0.0 <= c.importance <= 1.0


def test_triple_add_accepts_valid_from(core):
    core.triple_add("user_42", "role", "manager", valid_from="2026-06-01")
