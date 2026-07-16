"""amygdala.stm — 短期記憶(STM)境界による除外。

短期記憶は LLM のコンテキストウィンドウが持つ。直近イベントはそこに既に
載っているため、長期記憶(amygdala/mnemosyne)が直近を返すと二重取得になる。

呼び出し側は「いまコンテキストに載っている最古イベントの ULID」を境界として
渡す。それ以降(=新しい)は STM 射程内なので除外する。ULID は時系列ソート可能
なので単純な文字列比較で判定でき、要約圧縮や沈黙時間に影響されない。

境界の安全規約(FR-3.3 / P0):
- 境界が None → 除外しない(全件)。
- 境界が ULID として不正 → 警告ログを出して除外しない(fail-open)。
  誤った文字列比較で古い記憶を失うより、直近の重複を許す方が安全。
- 候補の ID が ULID として不正 → その候補は除外せず残す(新旧を判定できない)。
"""
from __future__ import annotations

import logging
from typing import Callable, Iterable, TypeVar

from amygdala._ulid import is_ulid

log = logging.getLogger(__name__)

T = TypeVar("T")


def filter_beyond_stm(
    items: Iterable[T],
    stm_oldest_id: str | None,
    id_getter: Callable[[T], str],
) -> list[T]:
    """STM 射程外(=境界より古い)だけを残す。

    Args:
        items: 候補(mnemosyne の recall 結果など)。
        stm_oldest_id: STM に載っている最古イベントの ULID。None なら除外しない。
        id_getter: 候補から ULID 文字列を取り出す関数。

    Returns:
        境界より古い候補のみ。境界が None / 不正なら全件そのまま。
    """
    if stm_oldest_id is None:
        return list(items)
    if not is_ulid(stm_oldest_id):
        log.warning(
            "stm_oldest_id %r is not a valid ULID; skipping STM exclusion",
            stm_oldest_id,
        )
        return list(items)

    kept: list[T] = []
    for it in items:
        mid = id_getter(it)
        if not is_ulid(mid):
            # 新旧を判定できないので保守的に残す
            log.debug("candidate id %r is not a valid ULID; keeping it", mid)
            kept.append(it)
        elif mid < stm_oldest_id:
            kept.append(it)
    return kept
