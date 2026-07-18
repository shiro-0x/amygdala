"""amygdala.core_adapter — mnemosyne への薄いアダプタ。

上流の実関数(remember/recall/triple_add)をこのプロトコルの裏に隠す。
- 本番: RealCore が `from mnemosyne import ...` を呼ぶ。
- テスト: InMemoryCore で上流なしに動かす。

上流 recall の戻り値はバージョンで形が変わりうるため、ここで Candidate へ
正規化する責務も持たせる(router を上流スキーマ変更から守る)。スコアは
0.0〜1.0 へクランプし、欠損は 0.0 とする(FR-3.5。対応バージョンとの契約は
tests/test_contract_mnemosyne.py で検証する)。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from amygdala._ulid import new_ulid
from amygdala.rerank import Candidate


def _clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(0.0, min(1.0, v))


@runtime_checkable
class Core(Protocol):
    """記憶基盤が提供すべき最小インターフェース(バックエンド非依存の継ぎ目)。

    amygdala は mnemosyne 前提ではなく、この 3 メソッドを満たす任意の
    バックエンドに載る。既定実装は `RealCore`(mnemosyne)だが、ベクトル DB
    や他の記憶システムを使う場合はこの Protocol を実装したアダプタを渡せば
    よい(`examples/custom_backend.py` 参照)。テスト用の `InMemoryCore` は
    mnemosyne ゼロでこの Protocol を満たす実例。

    契約(バックエンドが守るべき点):
    - `remember` の戻り値 memory_id が **ULID(時系列ソート可能)** なら
      STM 境界除外が効く。非 ULID の場合 STM は安全に無効化される(fail-open)。
    - `recall` は `Candidate`(memory_id / text / score 0〜1 / importance /
      partner_id)へ正規化して返す。score の正規化はアダプタの責務。
    - triple(知識グラフ)概念が無いバックエンドは `triple_add` を no-op に
      してよい(体験の感情処理には影響しない)。
    """

    def remember(self, content: str, importance: float = 0.5) -> str:
        """体験を書き、memory_id(できれば ULID)を返す。"""
        ...

    def recall(self, query: str, top_k: int) -> list[Candidate]:
        """検索候補を Candidate 正規化済みで返す。"""
        ...

    def triple_add(self, subject: str, predicate: str, obj: str,
                   valid_from: str | None = None) -> None:
        """知識(事実)を書く。感情は付けない。無ければ no-op でよい。"""
        ...


class RealCore:
    """本番用。mnemosyne を実呼び出しする。

    上流 recall の戻り値オブジェクトの属性名はバージョン依存。差異はここで吸収。
    """

    def __init__(self):
        try:
            from mnemosyne import remember, recall  # type: ignore
            from mnemosyne.core.triples import TripleStore  # type: ignore
        except ImportError as e:  # pragma: no cover - 環境依存
            raise ImportError(
                "RealCore は mnemosyne バックエンドを必要とします: "
                "`pip install amygdala[mnemosyne]`。"
                "別の記憶基盤を使う場合は Core Protocol を実装したアダプタを "
                "MemoryRouter に渡してください(examples/custom_backend.py)。"
            ) from e
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
                memory_id=str(_attr(r, "memory_id", "id")),
                text=_attr(r, "content", "text", default=""),
                score=_clamp01(_attr(r, "score", default=0.0)),
                importance=_clamp01(_attr(r, "importance", default=0.5)),
                # partner_id は amygdala DB から復元する(FR-2.5)。
                # 上流が返す場合のみ初期値として拾う。
                partner_id=_attr(r, "partner_id", default=None),
            ))
        return out

    def triple_add(self, subject, predicate, obj, valid_from=None):
        self._kg.add(subject, predicate, obj, valid_from=valid_from)


class InMemoryCore:
    """テスト用。mnemosyne なしで Core Protocol を満たす最小実装。

    スコアはクエリと本文の単語重なり率(Jaccard 風)による素朴なもの。
    順位の絶対値ではなく「router / rerank / worker の配線」を検証する用途。
    """

    def __init__(self):
        self._memories: list[tuple[str, str, float]] = []  # (ulid, text, importance)
        self.triples: list[tuple[str, str, str, str | None]] = []

    def remember(self, content: str, importance: float = 0.5) -> str:
        memory_id = new_ulid()
        self._memories.append((memory_id, content, importance))
        return memory_id

    def recall(self, query: str, top_k: int) -> list[Candidate]:
        q_tokens = set(query.lower().split())
        scored: list[Candidate] = []
        for memory_id, text, importance in self._memories:
            t_tokens = set(text.lower().split())
            union = q_tokens | t_tokens
            overlap = len(q_tokens & t_tokens) / len(union) if union else 0.0
            scored.append(Candidate(
                memory_id=memory_id, text=text,
                score=overlap, importance=importance, partner_id=None,
            ))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    def triple_add(self, subject, predicate, obj, valid_from=None):
        self.triples.append((subject, predicate, obj, valid_from))


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
