"""입법예고 수집기 (국민참여입법센터 `rest/ogLmPp`).

**이 서비스가 파는 것이 여기서 시작된다.**

지금까지 우리가 잡는 가장 이른 신호는 "공포" 다. 이미 확정된 것이라
알아도 준비할 시간이 짧다. 입법예고는 그보다 앞이다 — 정부가 "이렇게
바꾸려 한다" 고 내놓고 의견을 받는 기간이다.

세무사무소 직원이 남보다 앞서는 지점이 여기다. 공포된 뒤에 아는 사람과
예고 단계에서 아는 사람은 고객에게 할 말이 다르다.

키를 받아 처음 불러 보니 2026년 세법개정안이 통째로 예고 중이었다.
소득세법·법인세법·부가가치세법·상속세및증여세법·종합부동산세법·
국세기본법·국세징수법·조세특례제한법·국제조세조정법·농어촌특별세법
열 건이 같은 날 올라와 의견 마감이 8월 20일이었다.

--- 문서와 실제가 다른 곳들 ---

명세를 보고 먼저 만들어 뒀다가, 키가 나온 뒤 실제 응답과 맞췄다.
틀렸던 곳을 남긴다. 다음에 같은 자리에서 넘어지지 않도록.

1. **주소.** 문서는 `www.lawmaking.go.kr` 인데 실제로는 301 로
   `opinion.lawmaking.go.kr` 로 넘긴다.

2. **소관부처 코드가 안 먹는다.** 국세청(1210000)·기획재정부(1051000)
   둘 다 0건이었다. 정부조직이 바뀌어 지금 세법을 내는 곳은
   **재정경제부**다. 애초에 부처로 거르는 방식이 틀렸다 — 세목 이름으로
   거른다(`app.domain.tax_law`).

3. **날짜가 `2026. 8. 14.`** 다. 점 사이에 공백이 있고 월·일이 한 자리다.
   점만 지우고 8자리로 읽으려 했더니 전부 None 이 됐다.

4. **항목 태그는 `ApiList04Vo`**, `<list>` 안에 들어 있다.

5. **제목 앞에 `[진행]`** 이 붙는다.

--- 본문은 첨부파일이다 ---

목록이 주는 것은 제목·부처·공고번호·예고기간·파일 링크다. 본문은 한글
파일로 붙어 있고 우리는 그걸 열지 않는다. 그래서 여기서도 모델에게
요지를 쓰라고 시키지 않는다 — 제목과 기간까지만 말하고 원문으로 보낸다.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.tax_law import is_tax_law
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "2.0.0"

#: 문서에 적힌 `www.lawmaking.go.kr` 는 301 로 여기로 넘긴다.
#: 처음부터 넘어온 주소로 부른다 — 왕복 한 번을 줄이고, 리다이렉트를
#: 따라가지 않는 클라이언트에서 조용히 실패하는 일도 없앤다.
LIST_URL = "https://opinion.lawmaking.go.kr/rest/ogLmPp.xml"

#: 예고 상태. 0 은 진행 중 — 의견을 낼 수 있는 기간이 남아 있다.
ONGOING = "0"

#: 한 번에 받는 건수. 100 까지 먹는다(`display`·`numOfRows` 는 무시된다).
PAGE_SIZE = 100

#: 안전장치. 전체가 300건 안팎이라 세 쪽이면 끝난다.
MAX_PAGES = 10

#: 사람이 여는 화면. 목록은 일련번호만 주므로 여기서 만든다.
PUBLIC_URL = "https://opinion.lawmaking.go.kr/gcom/ogLmPp"

#: 제목 앞에 붙는 상태 표시. `[진행]부가가치세법 …` 처럼 온다.
#: 상태는 diff 파라미터로 이미 정해서 부르므로 제목에서는 지운다.
_STATUS_PREFIX = re.compile(r"^\s*\[[^\]]{1,10}\]\s*")

#: 제목 끝의 `입법예고`. 이 목록은 전부 입법예고라 붙어 있으나 마나다.
#: 남겨 두면 요약이 이렇게 읽힌다.
#:
#:     「부가가치세법 일부개정법률안 입법예고」이(가) 입법예고됐습니다
#:
#: 종류는 상태(PREANNOUNCED)가 이미 말한다. 제목에는 법령안 이름만 둔다.
_NOTICE_SUFFIX = re.compile(r"\s*(입법|행정)예고\s*$")


class PreannounceError(Exception):
    """입법예고 API 호출 실패."""


@dataclass(frozen=True)
class PreannounceItem:
    serial: str
    title: str
    law_type: str
    agency: str
    notice_no: str
    noticed_at: dt.date | None
    opens_at: dt.date | None
    closes_at: dt.date | None
    file_url: str

    @property
    def canonical_url(self) -> str:
        return f"{PUBLIC_URL}/{self.serial}"


def _parse_date(value: str | None) -> dt.date | None:
    """`2026. 8. 14.` → date. 형식이 다르면 None — 추측하지 않는다 (§9.4 V2).

    이 API 는 점 사이에 공백을 넣고 월·일을 한 자리로 쓴다. 점과 공백을
    지우고 8자리로 읽으려 했더니 `2026814` 가 되어 전부 None 이었다.
    법제처 심판례에서 의결일 20건이 통째로 빈 적이 있는데, 그때와 똑같이
    날짜 구분자를 잘못 본 것이었다. 이번엔 숫자를 따로 뽑는다.
    """
    parts = re.findall(r"\d+", value or "")
    if len(parts) != 3:
        return None
    year, month, day = (int(p) for p in parts)
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    return (found.text or "").strip() if found is not None else ""


def parse_list(xml: str) -> list[PreannounceItem]:
    """목록 XML 을 항목으로 가른다.

    승인 전에는 `<result><retMsg>401</retMsg></result>` 가 온다.
    그때 빈 목록을 돌려주면 "오늘은 예고가 없나 보다" 로 읽힌다.
    그건 사실이 아니므로 예외로 올린다.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise PreannounceError(f"XML 을 파싱할 수 없습니다: {exc}") from exc

    # 성공도 retMsg 200 으로 온다. 200 이 아닐 때만 실패다.
    message = _text(root, "retMsg")
    if message and message != "200":
        raise PreannounceError(
            f"입법예고 API 가 거절했습니다 (retMsg={message}). "
            "국민참여입법센터 정보공개 신청이 승인됐는지, OC 가 맞는지 확인하세요."
        )

    out: list[PreannounceItem] = []
    # 항목 태그는 `ApiList04Vo` 인데 문서에 없던 이름이다. 이름을 못 박는
    # 대신 일련번호를 가진 노드를 항목으로 본다 — 이름이 바뀌는 날
    # 조용히 0건이 되는 것보다 낫다.
    for node in root.iter():
        serial = _text(node, "ogLmPpSeq")
        title = _NOTICE_SUFFIX.sub("", _STATUS_PREFIX.sub("", _text(node, "lsNm")))
        if not (serial and title):
            continue
        out.append(
            PreannounceItem(
                serial=serial,
                title=title,
                law_type=_text(node, "lsClsNm"),
                agency=_text(node, "asndOfiNm"),
                notice_no=_text(node, "pntcNo"),
                noticed_at=_parse_date(_text(node, "pntcDt")),
                opens_at=_parse_date(_text(node, "stYd")),
                closes_at=_parse_date(_text(node, "edYd")),
                file_url=_text(node, "FileDownLink"),
            )
        )
    return out


def total_count(xml: str) -> int:
    """서버가 말하는 전체 건수. 화면에 세어 보여줄 값이 아니라 페이지 계산용이다."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return 0
    raw = root.findtext("totalCnt") or "0"
    return int(raw) if raw.isdigit() else 0


def build_body(item: PreannounceItem) -> str:
    """저장할 본문. 가진 것만 적는다."""
    lines = [f"[입법예고명]\n{item.title}"]
    if item.agency:
        lines.append(f"[소관부처]\n{item.agency}")
    if item.law_type:
        lines.append(f"[법령종류]\n{item.law_type}")
    if item.notice_no:
        lines.append(f"[공고번호]\n{item.notice_no}")
    if item.opens_at and item.closes_at:
        lines.append(
            f"[의견 제출 기간]\n{item.opens_at.isoformat()} ~ {item.closes_at.isoformat()}"
        )
    lines.append(
        "[안내]\n아직 확정된 개정이 아닙니다. 정부가 이렇게 바꾸겠다고 내놓고 "
        "의견을 받는 단계이며, 이 기간에 내용이 달라지거나 무산될 수 있습니다. "
        "본문은 첨부된 원문에서 확인하세요."
    )
    return "\n\n".join(lines)


class PreannounceCollector:
    """입법예고."""

    name = "lawmaking.go.kr:preannounce"
    version = ADAPTER_VERSION

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 40.0) -> None:
        self.oc = get_settings().lawmaking_oc
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
        limit: int = 60,
    ) -> CollectStats:
        stats = CollectStats()

        if not self.configured:
            stats.fail(
                source.display_name,
                PreannounceError(
                    "TAXBRIEFING_LAWMAKING_OC 가 없습니다. "
                    "국민참여입법센터 정보공개 신청 후 승인받은 ID(@ 앞부분)를 넣으세요."
                ),
            )
            return stats

        try:
            items = self._fetch_all()
        except PreannounceError as exc:
            stats.fail(source.display_name, exc)
            return stats

        stats.discovered = len(items)
        # 세법이 아닌 것은 담지 않는다. 전체 276건 중 세법은 15건쯤이다.
        tax_items = [item for item in items if is_tax_law(item.title)]
        logger.info(
            "preannounce.filtered",
            total=len(items),
            tax=len(tax_items),
            dropped=len(items) - len(tax_items),
        )

        kept = 0
        for item in tax_items:
            # 공고일 기준으로 자른다. 예고는 기간이 짧아 오래된 것을
            # 다시 담을 이유가 없다.
            if since and item.noticed_at and item.noticed_at < since:
                continue
            if kept >= limit:
                logger.info("preannounce.limit_reached", limit=limit)
                break
            kept += 1
            try:
                self._ingest_one(db, source, item, stats)
            except Exception as exc:
                stats.fail(item.notice_no or item.serial, exc)

        return stats

    def _fetch_all(self) -> list[PreannounceItem]:
        """진행 중인 예고를 전부 받는다.

        부처로 거르지 않는다 — 코드가 안 먹었고, 먹더라도 부처가 세법의
        경계와 맞지 않는다. 전체가 300건 안팎이라 다 받아서 세목으로
        거르는 편이 정확하고 충분히 싸다.
        """
        items: list[PreannounceItem] = []
        seen: set[str] = set()

        for page in range(1, MAX_PAGES + 1):
            body = self._get(page)
            page_items = parse_list(body)
            if not page_items:
                break
            for item in page_items:
                if item.serial not in seen:
                    seen.add(item.serial)
                    items.append(item)
            if len(items) >= total_count(body):
                break
        else:
            logger.info("preannounce.max_pages", pages=MAX_PAGES, got=len(items))

        return items

    def _get(self, page: int) -> str:
        client = self._client or httpx.Client(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "TaxBriefing/1.0 (+tax briefing aggregator)"},
        )
        owns = self._client is None
        try:
            response = client.get(
                LIST_URL,
                params={
                    "OC": self.oc,
                    "diff": ONGOING,
                    "pageSize": str(PAGE_SIZE),
                    "pageIndex": str(page),
                },
            )
        except httpx.HTTPError as exc:
            raise PreannounceError(f"호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise PreannounceError(f"HTTP {response.status_code}")
        return response.text

    def _ingest_one(
        self,
        db: Session,
        source: Source,
        item: PreannounceItem,
        stats: CollectStats,
    ) -> None:
        ingested = ingest(
            db,
            source_id=source.id,
            canonical_url=item.canonical_url,
            title=item.title[:500],
            publisher=item.agency or "법제처",
            raw_body=build_body(item),
            published_at=(
                dt.datetime.combine(item.noticed_at, dt.time(), tzinfo=dt.UTC)
                if item.noticed_at
                else None
            ),
            source_item_id=item.notice_no or item.serial,
            parser_version=f"preannounce/{ADAPTER_VERSION}",
        )

        ingested.version.doc_metadata = {
            "serial": item.serial,
            "notice_no": item.notice_no,
            "agency": item.agency,
            "law_type": item.law_type,
            "noticed_at": item.noticed_at.isoformat() if item.noticed_at else None,
            "opens_at": item.opens_at.isoformat() if item.opens_at else None,
            # 의견 제출 마감. 화면이 이 날짜로 D-day 를 센다 —
            # 이 기간이 지나면 의견을 낼 수 없다.
            "closes_at": item.closes_at.isoformat() if item.closes_at else None,
            "file_url": item.file_url,
            # 아직 법이 아니다. 공포도 시행도 안 됐다.
            "content_kind": "POLICY",
            "legal_status": "PREANNOUNCED",
            "full_text_stored": False,
        }
        db.flush()
        stats.record(ingested.outcome)


__all__ = [
    "PreannounceCollector",
    "PreannounceError",
    "PreannounceItem",
    "build_body",
    "parse_list",
    "total_count",
]
