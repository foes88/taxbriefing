"""공개 화면 응답을 잠깐 들고 있는다.

**왜 필요한가.**

DB 가 미국(Neon us-east-2)에 있고 화면을 여는 사람은 한국에 있다. 왕복
한 번이 393ms 다. 쿼리를 다섯 번에서 한 번으로 줄여 2.0초를 0.40초로
만들었지만, 그 0.40초도 대부분 왕복이다.

    +195ms  연결 살아 있나 확인 (pool_pre_ping)
    +220ms  조회

**자료는 하루 한 번만 바뀐다.** 아침 배치가 돌 때다. 그런데 오늘/일정/찾기를
오가면 같은 값을 매번 다시 물어 온다. 두 번째부터는 물어볼 이유가 없다.

**얼마나 들고 있을 것인가.**

정정(correction)이 늦게 보이는 것이 이 결정의 대가다. 2분으로 잡는다 —
정정은 드물고, 2분이면 화면 한 번 오가는 동안은 빠르고 커피 한 잔
사이에는 새로 온다. 하루로 잡으면 잘못 나간 내용을 고쳐도 안 바뀐다.

**무엇을 안 담는가.**

관리자 화면과 로그인이 필요한 것은 담지 않는다. 사람마다 보이는 것이
다른 응답을 한 통에 담으면 남의 것이 보인다. 여기서는 경로로 가른다 —
`/api/v1/public/` 로 시작하는 것만 담고, 그마저 GET·200 만 담는다.
"""

from __future__ import annotations

import time
from collections import OrderedDict

#: 얼마나 들고 있을지.
TTL_SECONDS = 120

#: 몇 개까지. 검색어가 제각각이면 열쇠가 무한히 늘어난다.
#: 오래된 것부터 버린다 — 방금 본 화면이 다시 열릴 확률이 높다.
MAX_ENTRIES = 256


class TtlCache:
    """열쇠 하나에 값 하나. 시간이 지나면 없는 것으로 친다.

    프로세스 안에만 산다. 서버가 여러 대면 각자 따로 들고 있는데,
    그래도 상관없다 — 어차피 같은 값이고, 늦어야 2분 차이다.
    """

    def __init__(self, *, ttl: float = TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._items: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str, *, now: float | None = None) -> object | None:
        stamp = now if now is not None else time.monotonic()
        found = self._items.get(key)
        if found is None:
            return None
        expires, value = found
        if expires <= stamp:
            # 지난 것은 지운다. 두고 있으면 자리만 먹는다.
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: str, value: object, *, now: float | None = None) -> None:
        stamp = now if now is not None else time.monotonic()
        self._items[key] = (stamp + self._ttl, value)
        self._items.move_to_end(key)
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def cache_key(path: str, query: str) -> str:
    """경로 + 물음표 뒤. 순서가 달라도 같은 요청이면 같은 열쇠가 되게 정렬한다.

    `?a=1&b=2` 와 `?b=2&a=1` 은 같은 화면이다. 정렬하지 않으면 같은
    화면을 두 번 담고, 둘 중 하나만 새로 온다.
    """
    if not query:
        return path
    parts = sorted(query.split("&"))
    return f"{path}?{'&'.join(parts)}"


__all__ = ["MAX_ENTRIES", "TTL_SECONDS", "TtlCache", "cache_key"]
