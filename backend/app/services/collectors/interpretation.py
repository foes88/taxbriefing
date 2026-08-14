"""국세청·기획재정부 법령해석 수집기 (법제처 DRF `ntsCgmExpc` · `moefCgmExpc`).

**왜 필요한가.**

법령은 "무엇이 바뀌었나", 심판례는 "다퉜을 때 어떻게 판단되나" 를 알려준다.
해석례는 그 사이에 있다 — **다투기 전에 물어본 답**이다. 실무자가 상담
중에 "이런 경우는 어떻게 되나요" 를 만나면 먼저 찾는 것이 이것이다.

    구독회원 배달비 공제액의 매출에누리 해당 여부
    플랫폼사업자로부터 수취하지 못한 판매대금이 대손세액공제 대상인지

**본문을 주지 않는다.**

목록은 JSON 으로 오는데 상세는 JSON 이 아니다(HTML 안내 페이지가 온다).
그래서 우리가 가진 것은 안건명·안건번호·해석일자·원문 링크뿐이다.

여기서 **모델에게 쟁점을 쓰라고 시키지 않는다.** 제목만 주고 "이 해석의
요지를 정리하라" 고 하면 그건 요약이 아니라 창작이다. 세무 실무자가 그걸
근거로 상담하면 우리가 지어낸 말이 고객에게 간다.

그래서 이 종류는 **"이런 해석이 있다" 까지만** 말한다. 제목이 이미
쟁점을 담고 있어서 그것만으로도 값이 있다 — 있는 줄 몰라서 못 찾는 것과
알고 원문을 여는 것은 다르다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"

#: 해석기관별 target. 둘 다 같은 응답 모양이다.
TARGETS: tuple[tuple[str, str], ...] = (
    ("ntsCgmExpc", "국세청"),
    ("moefCgmExpc", "기획재정부"),
)

#: 사업자에게 실제로 걸리는 세목. 12,530건을 다 가져오지 않는다 —
#: 심판례와 같은 기준으로 고른다.
DEFAULT_QUERIES: tuple[str, ...] = (
    "부가가치세",
    "법인세",
    "종합소득세",
    "원천징수",
    "가산세",
    "세금계산서",
    "매입세액",
    "접대비",
    "가지급금",
    "감가상각",
)


class InterpretationError(Exception):
    """법령해석 API 호출 실패."""


@dataclass(frozen=True)
class InterpretationItem:
    serial: str
    title: str
    case_no: str
    agency: str
    decided_at: dt.date | None
    detail_url: str

    @property
    def canonical_url(self) -> str:
        """원문 주소를 그대로 정본으로 쓴다.

        국세법령정보시스템 문서 하나에 주소 하나가 붙고, 그 주소가
        바뀌지 않는다. 우리가 따로 만든 주소를 쓰면 같은 해석이
        두 건으로 들어올 수 있다.
        """
        return self.detail_url


def _parse_date(value: Any) -> dt.date | None:
    """`2026.07.24` → date. 형식이 다르면 None — 추측하지 않는다 (§9.4 V2).

    심판례가 점 구분을 쓰는데 그걸 안 떼서 의결일이 전부 빈 적이 있다.
    여기도 점 구분이라 같은 자리에서 넘어지지 않도록 처음부터 받는다.
    """
    text = str(value or "").strip().replace("-", "").replace(".", "").replace("/", "")
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """응답에서 목록을 꺼낸다. 1건일 때 배열 대신 객체가 오는 것을 흡수한다."""
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        for inner in value.values():
            if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                return inner
            if isinstance(inner, dict) and "법령해석일련번호" in inner:
                return [inner]
    return []


def build_body(item: InterpretationItem) -> str:
    """저장할 본문.

    **요약하지 않는다.** 우리가 가진 것을 그대로 적고, 본문은 원문에
    있다고 말한다. 여기에 없는 것을 지어내면 그게 곧 이 화면의 값을
    깎아먹는다.
    """
    lines = [
        f"[안건명]\n{item.title}",
        f"[해석기관]\n{item.agency}",
    ]
    if item.case_no:
        lines.append(f"[안건번호]\n{item.case_no}")
    if item.decided_at:
        lines.append(f"[해석일자]\n{item.decided_at.isoformat()}")
    lines.append(
        "[안내]\n본문은 국세법령정보시스템 원문에서 확인하세요. "
        "이 항목은 해석이 있다는 사실과 찾아갈 곳만 알려 드립니다 — "
        "요지를 우리가 정리하지 않았습니다."
    )
    return "\n\n".join(lines)


class InterpretationCollector:
    """국세청·기재부 법령해석."""

    name = "law.go.kr:interpretation"
    version = ADAPTER_VERSION

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 40.0) -> None:
        self.oc = get_settings().law_api_oc
        self._client = client
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.oc)

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 40,
    ) -> CollectStats:
        stats = CollectStats()

        if not self.configured:
            stats.fail(
                source.display_name,
                InterpretationError("TAXBRIEFING_LAW_API_OC 가 없습니다."),
            )
            return stats

        queries = tuple((source.settings or {}).get("queries") or DEFAULT_QUERIES)
        targets = tuple((source.settings or {}).get("targets") or [t for t, _ in TARGETS])
        # 세목과 기관으로 나눠 담는다. 한쪽이 실패해도 나머지는 들어온다.
        per_query = max(2, limit // max(1, len(queries) * len(targets)))
        seen: set[str] = set()

        for target in targets:
            for query in queries:
                try:
                    items = self._search(target, query, per_query)
                except InterpretationError as exc:
                    stats.fail(f"{target}:{query}", exc)
                    continue

                for item in items:
                    stats.discovered += 1

                    # 같은 해석이 여러 세목 검색에 걸린다. 한 번만 담는다.
                    if item.serial in seen:
                        continue
                    seen.add(item.serial)

                    if since and item.decided_at and item.decided_at < since:
                        continue

                    try:
                        self._ingest_one(db, source, item, query, stats)
                    except Exception as exc:
                        stats.fail(item.case_no or item.serial, exc)

        return stats

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.get(SEARCH_URL, params={"OC": self.oc, "type": "JSON", **params})
        except httpx.HTTPError as exc:
            raise InterpretationError(f"호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise InterpretationError(f"HTTP {response.status_code}")
        body = response.text.strip()
        if not body.startswith("{"):
            raise InterpretationError(f"JSON 이 아닙니다 ({body[:60]!r})")
        return response.json()

    def _search(self, target: str, query: str, display: int) -> list[InterpretationItem]:
        payload = self._get(
            {"target": target, "query": query, "display": display, "sort": "ddes"}
        )
        out: list[InterpretationItem] = []
        for row in _rows(payload):
            serial = str(row.get("법령해석일련번호", "")).strip()
            url = str(row.get("법령해석상세링크", "")).strip()
            title = str(row.get("안건명", "")).strip()
            # 셋 중 하나라도 없으면 담지 않는다. 링크 없는 해석은
            # "있다더라" 로만 남아 아무 데도 데려다주지 못한다.
            if not (serial and url and title):
                continue
            out.append(
                InterpretationItem(
                    serial=serial,
                    title=title,
                    case_no=str(row.get("안건번호", "")).strip(),
                    agency=str(row.get("해석기관명", "")).strip(),
                    decided_at=_parse_date(row.get("해석일자")),
                    detail_url=url,
                )
            )
        return out

    def _ingest_one(
        self,
        db: Session,
        source: Source,
        item: InterpretationItem,
        query: str,
        stats: CollectStats,
    ) -> None:
        ingested = ingest(
            db,
            source_id=source.id,
            canonical_url=item.canonical_url,
            title=item.title[:500],
            publisher=item.agency or "국세청",
            raw_body=build_body(item),
            published_at=(
                dt.datetime.combine(item.decided_at, dt.time(), tzinfo=dt.UTC)
                if item.decided_at
                else None
            ),
            source_item_id=item.case_no or item.serial,
            parser_version=f"interpretation/{ADAPTER_VERSION}",
        )

        ingested.version.doc_metadata = {
            "serial": item.serial,
            "case_no": item.case_no,
            "agency": item.agency,
            "decided_at": item.decided_at.isoformat() if item.decided_at else None,
            "detail_link": item.detail_url,
            "matched_query": query,
            # 해석례는 법령이 아니다. 시행일도 정책 상태도 붙이면 안 된다.
            "content_kind": "INTERPRETATION",
            # 본문을 저장하지 않았다는 사실을 명시한다.
            # 이 표시가 있어야 화면이 "요약이 없다" 와 "요약할 것이 없다" 를
            # 구분해서 말할 수 있다.
            "full_text_stored": False,
        }
        db.flush()
        stats.record(ingested.outcome)


__all__ = [
    "DEFAULT_QUERIES",
    "TARGETS",
    "InterpretationCollector",
    "InterpretationError",
    "InterpretationItem",
    "build_body",
]
