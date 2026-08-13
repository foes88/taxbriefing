"""네이버 뉴스 검색 API 수집 어댑터 (C/D 등급, 이슈 탐지용).

**왜 크롤링이 아니라 API 인가.**

네이버는 공식 검색 API 를 무료로 제공한다(일 25,000회). 크롤링해서 막히는 상황은
대개 "정문이 있는데 담을 넘고 있다"는 신호다. §3.4 가 robots.txt·로그인·캡차 우회를
금지하는 이유이기도 하다.

**저작권** (§NFR-015)
API 가 주는 것은 제목·짧은 요약·링크다. 전문이 아니다. 그대로 저장하고, 본문은
가져오지 않는다. 사용자에게도 제목과 링크만 보여준다.

**등급**
여기서 들어온 항목은 C/D 등급이므로 게이트 G1 에서 단독 승인이 막힌다 (AT-03).
뉴스로 이슈를 탐지하면 운영자가 공식 원문(법령·관보)을 찾아 연결해야 발송할 수 있다.
이 어댑터의 목적은 "무엇이 논의되고 있는가"를 놓치지 않는 것이다.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.collectors.rss import MAX_SUMMARY_CHARS, _parse_date
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
API_URL = "https://openapi.naver.com/v1/search/news.json"

#: 검색어. 출처 설정에서 덮어쓸 수 있다 (부록 A: 하드코딩 금지).
DEFAULT_QUERIES: tuple[str, ...] = (
    "세제개편안",
    "부가가치세",
    "종합소득세",
    "법인세",
    "성실신고확인",
    "원천징수",
    "4대보험 요율",
    "소상공인 지원금",
)

_TAG = re.compile(r"<[^>]+>")


class NaverNewsError(Exception):
    """네이버 API 호출 실패."""


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    origin_link: str
    summary: str
    published_at: dt.datetime | None


def _clean(text: str | None) -> str:
    """API 는 검색어를 <b> 로 감싸서 준다. 태그를 걷고 엔티티를 푼다."""
    if not text:
        return ""
    return html.unescape(_TAG.sub("", text)).strip()


class NaverNewsCollector:
    """네이버 뉴스 검색 수집기."""

    name = "naver-news"
    version = ADAPTER_VERSION

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.client_id = client_id or settings.naver_client_id
        self.client_secret = client_secret or settings.naver_client_secret
        self._timeout = timeout
        self._client = client

    @property
    def configured(self) -> bool:
        """키가 있어도 **검색 권한이 없으면 못 쓴다.**

        2026년 8월 현재 네이버는 검색 API 를 기존 애플리케이션에 추가할 수
        없게 막았다. 사용 API 에 '검색' 을 넣고 저장하면 이렇게 거절한다.

            애플리케이션 설정 실패
            신규로 등록할 수 없는 API 가 선택되었습니다.

        권한 없는 키로 호출하면 401 `Scopes are Empty` 가 돌아온다.
        예전에 발급받은 키가 있는 계정이라면 그대로 동작하므로 어댑터는 남긴다.
        뉴스는 세무 전문지 RSS(세정일보·국세신문)로 모은다 — 키가 필요 없다.
        """
        return bool(self.client_id and self.client_secret)

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 50,
    ) -> CollectStats:
        stats = CollectStats()

        if not self.configured:
            stats.fail(
                source.display_name,
                NaverNewsError(
                    "TAXBRIEFING_NAVER_CLIENT_ID/SECRET 이 없습니다. "
                    "developers.naver.com 에서 애플리케이션을 등록하세요."
                ),
            )
            return stats

        queries = tuple((source.settings or {}).get("queries") or DEFAULT_QUERIES)
        per_query = max(5, min(100, limit // max(1, len(queries))))
        seen: set[str] = set()

        for query in queries:
            try:
                items = self._search(query, per_query)
            except NaverNewsError as exc:
                stats.fail(f"search:{query}", exc)
                continue

            for item in items:
                stats.discovered += 1

                # 같은 기사가 여러 검색어에 걸린다. 한 번만 담는다.
                key = item.origin_link or item.link
                if key in seen:
                    continue
                seen.add(key)

                if since and item.published_at and item.published_at.date() < since:
                    continue

                try:
                    self._ingest_one(db, source, item, query, stats)
                except Exception as exc:
                    stats.fail(item.link, exc)

        return stats

    def _search(self, query: str, display: int) -> list[NewsItem]:
        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.get(
                API_URL,
                params={"query": query, "display": display, "sort": "date"},
                headers={
                    "X-Naver-Client-Id": self.client_id or "",
                    "X-Naver-Client-Secret": self.client_secret or "",
                },
            )
        except httpx.HTTPError as exc:
            raise NaverNewsError(f"네이버 API 호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code == 429:
            raise NaverNewsError("네이버 API 일일 한도를 초과했습니다.")
        if response.status_code >= 400:
            raise NaverNewsError(
                f"네이버 API HTTP {response.status_code}: {response.text[:200]}"
            )

        payload = response.json()
        out: list[NewsItem] = []
        for row in payload.get("items", []):
            title = _clean(row.get("title"))
            link = _clean(row.get("link")) or _clean(row.get("originallink"))
            if not title or not link:
                continue
            out.append(
                NewsItem(
                    title=title,
                    link=link,
                    origin_link=_clean(row.get("originallink")),
                    summary=_clean(row.get("description"))[:MAX_SUMMARY_CHARS],
                    published_at=_parse_date(row.get("pubDate")),
                )
            )
        return out

    def _ingest_one(
        self,
        db: Session,
        source: Source,
        item: NewsItem,
        query: str,
        stats: CollectStats,
    ) -> None:
        # 저장하는 것은 제목·요약·링크뿐이다. 본문은 가져오지 않는다 (§NFR-015).
        body = "\n".join(
            [
                f"제목: {item.title}",
                f"발행: {item.published_at.date().isoformat() if item.published_at else '미상'}",
                f"검색어: {query}",
                "",
                item.summary or "(요약 없음)",
                "",
                "전문은 원문 링크에서 확인하세요. 이 항목은 공식 원문이 아닙니다.",
            ]
        )
        result = ingest(
            db,
            source_id=source.id,
            canonical_url=item.link,
            title=item.title[:500],
            publisher=source.display_name,
            raw_body=body,
            published_at=item.published_at,
            parser_version=f"naver_news/{ADAPTER_VERSION}",
        )
        result.version.doc_metadata = {
            "origin_link": item.origin_link,
            "matched_query": query,
            "authority": source.authority.value,
            # 화면은 이 필드를 읽는다. 본문 텍스트를 파싱해서 요약을 뽑아내면
            # 수집기 형식이 바뀔 때마다 화면이 깨진다.
            "summary": item.summary,
            "full_text_stored": False,
        }
        db.flush()
        stats.record(result.outcome)
