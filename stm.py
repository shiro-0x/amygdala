"""amygdala.stm — 短期記憶(STM)境界による除外。

短期記憶は LLM のコンテキストウィンドウが持つ。直近イベントはそこに既に
載っているため、長期記憶(amygdala/A版)が直近を返すと二重取得になる。

呼び出し側は「いまコンテキストに載っている最古イベントの ULID」を境界として
渡す。それ以降(=新しい)は STM 射程内なので除外する。ULID は時系列ソート可能
なので単純な文字列比較で判定でき、要約圧縮や沈黙時間に影響されない。
"""
from __future__ import annotations

from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def filter_beyond_stm(
    items: Iterable[T],
    stm_oldest_id: str | None,
    id_getter: Callable[[T], str],
) -> list[T]:
    """STM 射程外(=境界より古い)だけを残す。

    Args:
        items: 候補(A版の recall 結果など)。
        stm_oldest_id: STM に載っている最古イベントの ULID。None なら除外しない。
        id_getter: 候補から ULID 文字列を取り出す関数。

    Returns:
        境界より古い候補のみ。境界が None なら全件そのまま。
    """
    if stm_oldest_id is None:
        return list(items)
    return [it for it in items if id_getter(it) < stm_oldest_id]
