"""amygdala._ulid — ULID の生成と検証(内部ユーティリティ)。

依存を増やさないための最小実装。生成は InMemoryCore(テスト)用で、
本番の memory_id は mnemosyne が発行する。検証は STM 境界の安全確認に使う。

生成は同一プロセス内で単調増加(ULID 仕様の monotonicity)。同一ミリ秒内に
複数生成しても文字列ソートが生成順と一致し、STM 境界比較が壊れない。
"""
from __future__ import annotations

import os
import threading
import time

# Crockford Base32(I, L, O, U を除く)
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ALPHABET_SET = frozenset(_ALPHABET)
ULID_LEN = 26

_lock = threading.Lock()
_last_ts = -1
_last_rand = 0


def _encode(ts_ms: int, rand: int) -> str:
    value = (ts_ms & ((1 << 48) - 1)) << 80 | (rand & ((1 << 80) - 1))
    return "".join(_ALPHABET[(value >> shift) & 0x1F]
                   for shift in range(125, -1, -5))


def new_ulid(ts_ms: int | None = None) -> str:
    """ULID を生成する(48bit タイムスタンプ + 80bit 乱数)。

    ts_ms 省略時(通常運用)は単調増加を保証する: 同一ミリ秒内の連続生成は
    乱数部をインクリメントする。ts_ms を明示した場合は決定論的な純関数として
    振る舞う(テスト用)。
    """
    global _last_ts, _last_rand
    if ts_ms is not None:
        return _encode(ts_ms, int.from_bytes(os.urandom(10), "big"))
    with _lock:
        now = time.time_ns() // 1_000_000
        if now <= _last_ts:
            _last_rand += 1  # 同一(または逆行)ミリ秒: 乱数部を進めて単調性を保つ
        else:
            _last_ts = now
            _last_rand = int.from_bytes(os.urandom(10), "big")
        return _encode(_last_ts, _last_rand)


def is_ulid(s: object) -> bool:
    """ULID として妥当な形式か(26 文字の Crockford Base32、大文字)。"""
    if not isinstance(s, str) or len(s) != ULID_LEN:
        return False
    return all(c in _ALPHABET_SET for c in s)
