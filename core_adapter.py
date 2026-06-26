"""amygdala.core_adapter — A版(mnemosyne)への薄いアダプタ。

A版の実関数(remember/recall/triple_add)をこのプロトコルの裏に隠す。
- 本番: RealCore が `from mnemosyne import ...` を呼ぶ。
- テスト: InMemoryCore で A版なしに動かす。

A版の recall 戻り値はバージョンで形が変わりうるため、ここで Candidate へ正規化
する責務も持たせる(router を A版スキーマ変更から守る)。
"""
from __future__ import annotations

from typing import Protocol

from amygdala.rerank import Candidate


class Core(Protocol):
    """A版が提供する記憶機能の最小インターフェース。"""

    def remember(self, content: str, importance: float = 0.5) -> str:
        """体験を episodic に書き、memory_id(ULID) を返す。"""
        ...

    def recall(self, query: str, top_k: int) -> list[Candidate]:
        """ハイブリッド検索の候補を Candidate 正規化済みで返す。"""
        ...

    def triple_add(self, subject: str, predicate: str, obj: str,
                   valid_from: str | None = None) -> None:
        """知識(事実)を temporal triple に書く。感情は付けない。"""
        ...


class RealCore:
    """本番用。A版 mnemosyne を実呼び出しする。

    A版の recall 戻り値オブジェクトの属性名はバージョン依存。差異はここで吸収。
    """

    def __init__(self):
        from mnemosyne import remember, recall  # type: ignore
        from mnemosyne.core.triples import TripleStore  # type: ignore
        self._remember = remember
        self._recall = recall
        self._kg = TripleStore()

    def remember(self, content: str, importance: float = 0.5) -> str:
        return self._remember(content=content, importance=importance)

    def recall(self, query: str, top_k: int) -> list[Candidate]:
        raw = self._recall(query, top_k=top_k)
        out: list[Candidate] = []
        for r in raw:
            out.append(Candidate(
                memory_id=_attr(r, "memory_id", "id"),
                text=_attr(r, "content", "text", default=""),
                score=float(_attr(r, "score", default=0.0)),
                importance=float(_attr(r, "importance", default=0.5)),
                partner_id=_attr(r, "partner_id", default=None),
            ))
        return out

    def triple_add(self, subject, predicate, obj, valid_from=None):
        self._kg.add(subject, predicate, obj, valid_from=valid_from)


def _attr(obj, *names, default=...):
    """obj から最初に見つかった属性 or dict キーを返す。"""
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    if default is ...:
        raise AttributeError(f"none of {names} found on {type(obj)}")
    return default
