"""RSS/Atom 수집 어댑터 (FR-SRC-001, collector_type=RSS).

**저작권 때문에 본문을 저장하지 않는다** (§NFR-015 뉴스 전문 재배포 금지).
제목·링크·발행일과, 피드가 준 짧은 요약만 담는다. 전문이 필요하면
운영자가 원문 링크를 열어 확인한다.

C/D 등급 출처는 게이트 G1 에서 단독 승인이 막히므로(AT-03), 여기서 들어온
뉴스만으로는 사업자에게 발송되지 않는다. 이슈 탐지와 맥락 확인이 용도다 (§3.1).
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.news_topic import is_tax_news
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
ATOM = "{http://www.w3.org/2005/Atom}"

#: 피드가 주는 요약은 종종 본문 앞부분이다. 저작권상 짧게 자른다.
MAX_SUMMARY_CHARS = 300

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


class RssError(Exception):
    """피드를 읽지 못했다."""


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    published_at: dt.datetime | None
    summary: str


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", _TAG.sub(" ", text)).strip()


def _parse_date(value: str | None) -> dt.datetime | None:
    """RFC 822(RSS)와 ISO 8601(Atom)을 모두 받는다. 실패하면 None 이다.

    날짜를 짐작하지 않는다 — 틀린 날짜는 없는 날짜보다 나쁘다 (§9.4 V2).
    """
    if not value:
        return None
    raw = value.strip()
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        # 한국 기관·언론 피드는 표기가 없으면 KST 로 보는 게 맞다.
        parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=9)))
    return parsed.astimezone(dt.UTC)


def parse_feed(content: bytes) -> list[FeedItem]:
    """RSS 2.0 과 Atom 을 모두 파싱한다."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RssError(f"피드를 파싱할 수 없습니다: {exc}") from exc

    items: list[FeedItem] = []

    for node in root.findall(".//item"):
        link = _clean(node.findtext("link"))
        title = _clean(node.findtext("title"))
        if title and link:
            items.append(
                FeedItem(
                    title=title,
                    link=link,
                    published_at=_parse_date(
                        node.findtext("pubDate") or node.findtext("date")
                    ),
                    summary=_clean(node.findtext("description"))[:MAX_SUMMARY_CHARS],
                )
            )

    for node in root.findall(f".//{ATOM}entry"):
        link_node = node.find(f"{ATOM}link")
        link = _clean(link_node.get("href")) if link_node is not None else ""
        title = _clean(node.findtext(f"{ATOM}title"))
        if title and link:
            items.append(
                FeedItem(
                    title=title,
                    link=link,
                    published_at=_parse_date(
                        node.findtext(f"{ATOM}updated") or node.findtext(f"{ATOM}published")
                    ),
                    summary=_clean(node.findtext(f"{ATOM}summary"))[:MAX_SUMMARY_CHARS],
                )
            )

    return items


class RssCollector:
    """피드 하나를 수집한다.

    피드 주소는 sources.settings["feed_url"] 에서 읽는다.
    출처를 코드에 하드코딩하지 않는다는 부록 A 원칙을 따른다.
    """

    name = "rss"
    version = ADAPTER_VERSION

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 20.0) -> None:
        self._client = client
        self._timeout = timeout

    def collect(
        self,
        db: Session,
        source: Source,
        *,
        since: dt.date | None = None,
        limit: int = 50,
    ) -> CollectStats:
        stats = CollectStats()

        feed_url = (source.settings or {}).get("feed_url")
        if not feed_url:
            stats.fail(source.display_name, RssError("settings.feed_url 이 없습니다."))
            return stats

        try:
            items = self._fetch(feed_url)
        except RssError as exc:
            stats.fail(feed_url, exc)
            return stats

        for item in items[:limit]:
            stats.discovered += 1

            if since and item.published_at and item.published_at.date() < since:
                continue

            # **세무 기사가 아니면 담지도 않는다.**
            #
            # 세무 전문지 RSS 라도 기업 홍보와 지역 행사가 섞여 온다.
            # 112건 중 39건(34%)이 이랬다.
            #
            #     하나금융그룹, JOB매칭 페스타 in 대전 성료!!!
            #     넷마블문화재단, 게임소통학교 성료
            #
            # 화면에서만 걸러도 되지만, 그러면 안 볼 것을 계속 받아 쌓는다.
            # 저장하지 않으면 백업도 색인도 그만큼 가벼워진다.
            if not is_tax_news(item.title):
                stats.off_topic += 1
                continue

            try:
                # 저장하는 것은 제목·요약·링크뿐이다. 본문은 담지 않는다.
                body = "\n".join(
                    [
                        f"제목: {item.title}",
                        f"발행: {item.published_at.date().isoformat() if item.published_at else '미상'}",
                        f"출처: {source.display_name}",
                        "",
                        item.summary or "(피드가 요약을 제공하지 않았습니다)",
                        "",
                        "전문은 원문 링크에서 확인하세요.",
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
                    parser_version=f"rss/{ADAPTER_VERSION}",
                )
                result.version.doc_metadata = {
                    "feed_url": feed_url,
                    "authority": source.authority.value,
                    # 화면은 이 필드를 읽는다. 본문 텍스트를 파싱해서 요약을 뽑아내면
                    # 수집기 형식이 바뀔 때마다 화면이 깨진다.
                    "summary": item.summary,
                    # 전문을 저장하지 않았다는 사실을 명시한다 (§NFR-015).
                    "full_text_stored": False,
                }
                db.flush()
                stats.record(result.outcome)
            except Exception as exc:
                stats.fail(item.link, exc)

        return stats

    def _fetch(self, url: str) -> list[FeedItem]:
        client = self._client or httpx.Client(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "TaxBriefing/1.0 (+tax briefing aggregator)"},
        )
        owns = self._client is None
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise RssError(f"피드를 가져오지 못했습니다: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise RssError(f"피드 HTTP {response.status_code}")

        items = parse_feed(response.content)
        if not items:
            raise RssError("피드에 항목이 없습니다.")
        return items


__all__ = ["Any", "FeedItem", "RssCollector", "RssError", "parse_feed"]
