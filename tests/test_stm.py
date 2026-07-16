"""STM 境界除外と ULID ユーティリティのテスト。"""
from amygdala._ulid import is_ulid, new_ulid
from amygdala.stm import filter_beyond_stm


def _ids(items):
    return items


def test_new_ulid_is_valid_and_sortable():
    a = new_ulid(ts_ms=1_000_000)
    b = new_ulid(ts_ms=2_000_000)
    assert is_ulid(a) and is_ulid(b)
    assert len(a) == 26
    assert a < b  # タイムスタンプ順に文字列ソート可能


def test_new_ulid_monotonic_within_same_millisecond():
    # 同一ミリ秒内の連続生成でも生成順=ソート順(STM 境界比較の前提)
    ids = [new_ulid() for _ in range(200)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_is_ulid_rejects_invalid():
    assert not is_ulid(None)
    assert not is_ulid("")
    assert not is_ulid("short")
    assert not is_ulid("l" * 26)          # 小文字 / 除外文字
    assert not is_ulid("I" * 26)          # I は Crockford Base32 に無い
    assert not is_ulid(12345)


def test_no_boundary_keeps_all():
    items = [new_ulid(ts_ms=t) for t in (1000, 2000, 3000)]
    assert filter_beyond_stm(items, None, _id) == items


def _id(x):
    return x


def test_boundary_excludes_recent():
    old, mid, new = (new_ulid(ts_ms=t) for t in (1000, 2000, 3000))
    kept = filter_beyond_stm([old, mid, new], mid, _id)
    # 境界より古いものだけ残る(境界自身もコンテキスト内なので除外)
    assert kept == [old]


def test_invalid_boundary_fails_open():
    items = [new_ulid(ts_ms=t) for t in (1000, 2000)]
    assert filter_beyond_stm(items, "not-a-ulid", _id) == items


def test_invalid_candidate_id_is_kept():
    old = new_ulid(ts_ms=1000)
    boundary = new_ulid(ts_ms=2000)
    weird = "zzz"  # 非 ULID
    kept = filter_beyond_stm([old, weird], boundary, _id)
    assert old in kept and weird in kept
