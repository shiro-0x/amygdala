"""任意の記憶バックエンドに amygdala を載せる例(Core Protocol アダプタ)。

amygdala は mnemosyne 専用ではない。記憶基盤とのやり取りは `Core` Protocol
(remember / recall / triple_add の 3 メソッド)だけに閉じており、これを実装
すればベクトル DB(Chroma / Qdrant 等)や他の記憶システム、独自ストアにも
そのまま載る。既定の `RealCore`(mnemosyne)や `InMemoryCore`(テスト用)も
同じ Protocol の実装にすぎない。

ここでは「あなたの検索関数」を包む最小アダプタを示す。実際には
`_search(query, k)` の中身を Chroma の `collection.query(...)`、Qdrant の
`client.search(...)`、あるいは自前の embedding + コサイン類似度などに
差し替えればよい。

STM 境界除外について:
- memory_id が **ULID(時系列ソート可能)** なら STM 除外が効く。
- 非 ULID(UUID4 / 連番など)を返すバックエンドでは STM 除外は安全に
  無効化(fail-open = 全件返す)され、感情・関係性・気分・注入ブロックは
  そのまま動く。時系列 ID が使えるなら ULID を推奨(`python-ulid` 等)。

実行:
    python examples/custom_backend.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amygdala import Candidate, MemoryRouter  # noqa: E402
from examples.rule_classifier import rule_classifier  # noqa: E402

# --- 時系列ソート可能な ID(STM 除外のため。最小の ULID 実装)-------------
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    """48bit ミリ秒 + 80bit 乱数の ULID。時系列ソート可能。

    本番では `python-ulid` 等のライブラリか、バックエンド発行の時系列 ID を
    使うとよい。ここでは依存を増やさないための最小実装。
    """
    value = ((int(time.time() * 1000) & ((1 << 48) - 1)) << 80
             | int.from_bytes(os.urandom(10), "big"))
    return "".join(_CROCKFORD[(value >> shift) & 0x1F]
                   for shift in range(125, -1, -5))


# --- 任意バックエンドを包む Core アダプタ ---------------------------------

class MyBackendCore:
    """Core Protocol を満たす自前バックエンドのアダプタ。

    `remember` / `recall` / `triple_add` の 3 つだけ実装すればよい。
    ここでは説明用にインメモリだが、`_search` を実 DB 呼び出しに置換すれば
    そのまま任意の記憶基盤アダプタになる。
    """

    def __init__(self):
        # (memory_id, text, importance, partner_id)
        self._rows: list[tuple[str, str, float, str | None]] = []
        self._triples: list[tuple[str, str, str, str | None]] = []
        self._pending_partner: str | None = None  # デモ簡略化用

    # 体験を書いて ID を返す
    def remember(self, content: str, importance: float = 0.5) -> str:
        memory_id = _ulid()
        self._rows.append((memory_id, content, importance, self._pending_partner))
        return memory_id

    # 検索候補を Candidate に正規化して返す(ここを実 DB に差し替える)
    def recall(self, query: str, top_k: int) -> list[Candidate]:
        q = set(query.lower().split())
        scored = []
        for memory_id, text, importance, partner_id in self._rows:
            t = set(text.lower().split())
            union = q | t
            score = len(q & t) / len(union) if union else 0.0  # 例: 素朴な一致率
            scored.append(Candidate(
                memory_id=memory_id, text=text,
                score=score,           # Core 側で 0〜1 に正規化する責務
                importance=importance,
                partner_id=partner_id,  # 分かるなら入れる(amygdala 側でも復元)
            ))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    # 知識グラフが無ければ no-op でもよい
    def triple_add(self, subject, predicate, obj, valid_from=None):
        self._triples.append((subject, predicate, obj, valid_from))


def main() -> None:
    core = MyBackendCore()
    router = MemoryRouter(core, db_path=":memory:", classifier=rule_classifier)
    try:
        # partner_id はデモ簡略化のためバックエンド側へ手渡し
        core._pending_partner = "user"
        for text in ("一緒に 出かけて 楽しかった",
                     "手伝って もらえて 嬉しかった"):
            router.remember(text, partner_id="user")
            router.worker.drain_sync()
            router.tick_mood()

        print("mnemosyne 無しでも動く(バックエンド =", type(core).__name__, ")")
        print(router.state_block(partner_id="user", lang="ja"))
        print("\nrecall:")
        for hit in router.recall("楽しかった 出かけた",
                                 ctx={"partner_id": "user"}, k=2):
            print(f"  {hit.score:.3f} {hit.candidate.text!r}")
    finally:
        router.close()


if __name__ == "__main__":
    main()
