"""공개 응답 캐시. 네트워크 없이 실행된다.

빠르게 만드는 것보다 **틀린 것을 주지 않는 것**이 먼저다. 여기서 보는
것은 속도가 아니라, 남의 값이 섞이지 않는가와 때가 되면 새로 오는가다.
"""

from __future__ import annotations

from app.core.cache import TtlCache, cache_key


class TestKey:
    def test_query_order_does_not_make_a_second_entry(self):
        """`?a=1&b=2` 와 `?b=2&a=1` 은 같은 화면이다.

        정렬하지 않으면 같은 화면을 두 번 담고, 둘 중 하나만 새로 온다.
        """
        assert cache_key("/f", "b=2&a=1") == cache_key("/f", "a=1&b=2")

    def test_different_queries_are_different_keys(self):
        assert cache_key("/f", "limit=3") != cache_key("/f", "limit=20")

    def test_different_paths_are_different_keys(self):
        assert cache_key("/feed", "") != cache_key("/news", "")

    def test_no_query_is_just_the_path(self):
        assert cache_key("/feed", "") == "/feed"


class TestTtl:
    def test_holds_the_value(self):
        cache = TtlCache(ttl=100)
        cache.set("a", 1, now=0)
        assert cache.get("a", now=50) == 1

    def test_lets_go_when_time_passes(self):
        """정정이 늦게 보이는 것이 이 결정의 대가다. 그래서 짧게 잡았다."""
        cache = TtlCache(ttl=100)
        cache.set("a", 1, now=0)
        assert cache.get("a", now=101) is None

    def test_expired_entry_is_dropped_not_kept(self):
        cache = TtlCache(ttl=10)
        cache.set("a", 1, now=0)
        cache.get("a", now=99)
        assert len(cache) == 0

    def test_missing_key_is_none_not_an_error(self):
        assert TtlCache().get("없음") is None


class TestBounds:
    def test_old_entries_are_evicted(self):
        """검색어가 제각각이면 열쇠가 무한히 늘어난다."""
        cache = TtlCache(ttl=100, max_entries=3)
        for i in range(5):
            cache.set(str(i), i, now=0)
        assert len(cache) == 3
        assert cache.get("0", now=1) is None
        assert cache.get("4", now=1) == 4

    def test_reading_keeps_it_alive(self):
        """방금 본 화면이 다시 열릴 확률이 높다. 그걸 먼저 버리지 않는다."""
        cache = TtlCache(ttl=100, max_entries=2)
        cache.set("a", 1, now=0)
        cache.set("b", 2, now=0)
        cache.get("a", now=1)
        cache.set("c", 3, now=1)
        assert cache.get("a", now=2) == 1
        assert cache.get("b", now=2) is None
