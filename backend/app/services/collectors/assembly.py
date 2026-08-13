"""국회 의안(법률안) 수집기.

**공포된 법령만 보면 이미 늦다.**

관보에 실릴 때쯤이면 다들 안다. 세무사무소 직원이 앞서려면 "이런 개정이
논의되고 있습니다" 를 먼저 알아야 하고, 그 시작점이 국회 발의다.

    정부 발표 → 입법예고 → **국회 발의** → 상임위 → 본회의 → 공포 → 시행

실측: 제22대 최근 500건 중 세법 관련 58건, 그중 45건이 재정경제기획위원회
소관이었다. 최신 건은 당일 발의된 조세특례제한법 개정안이었다.

**본문은 없다.**
이 API 는 의안 목록만 준다 — 법안 조문은 국회 사이트에서 봐야 한다.
그래서 저장하는 것은 의안명·제안자·소관위·진행 일자·링크뿐이고,
AI 에게 "이 법안이 무엇을 바꾸는지" 를 쓰게 하지 않는다. 제목만 주고
내용을 쓰라고 하면 그건 지어내는 것이다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.enums import LegalStatus
from app.models.tables import Source
from app.services.collectors.base import CollectStats
from app.services.ingest import ingest

logger = get_logger(__name__)

ADAPTER_VERSION = "1.0.0"
BASE_URL = "https://open.assembly.go.kr/portal/openapi"
BILL_SERVICE = "nzmimeepazxkubdpn"
"""국회의원 발의법률안."""

#: 제22대. AGE 는 필수 인자이며, 빼면 ERROR-300 이 돌아온다.
DEFAULT_AGE = "22"

#: 의안명에 이 말이 들어가면 우리 대상이다.
#:
#: 의안 전체를 가져와 AI 로 거르지 않는다 — 하루 수백 건이고, 제목만 봐도
#: 세법인지 아닌지는 사람이 안다. 모델을 쓸 자리가 아니다.
TAX_KEYWORDS: tuple[str, ...] = (
    "소득세",
    "법인세",
    "부가가치세",
    "조세특례",
    "국세기본",
    "국세징수",
    "상속세",
    "증여세",
    "종합부동산세",
    "개별소비세",
    "지방세",
    "고용보험",
    "국민연금",
    "국민건강보험",
    "산업재해보상보험",
    "보험료징수",
)

#: 이미 끝난 법안. 수집하지 않는다.
#:
#: "무엇을 준비해야 하나" 를 답하는 서비스다. 폐기된 법안은 준비할 것이
#: 없고, 목록에 섞이면 살아 있는 법안이 묻힌다.
DEAD_RESULTS: tuple[str, ...] = ("부결", "폐기", "철회", "대안반영폐기")

#: 가결된 법안. 곧 공포된다.
PASSED_RESULTS: tuple[str, ...] = ("원안가결", "수정가결", "가결")


class AssemblyError(Exception):
    """열린국회정보 API 호출 실패."""


@dataclass(frozen=True)
class Bill:
    bill_id: str
    bill_no: str
    name: str
    committee: str
    proposer: str
    proposed_at: dt.date | None
    proc_result: str
    committee_at: dt.date | None
    detail_link: str

    @property
    def canonical_url(self) -> str:
        """의안번호로 영구 식별된다. 심사가 진행돼도 같은 의안이다."""
        return f"https://likms.assembly.go.kr/bill/billDetail.do?billId={self.bill_id}"

    @property
    def legal_status(self) -> LegalStatus:
        """어느 단계까지 왔는가.

        **추측하지 않는다.** 처리 결과가 비어 있으면 아직 심사 중이라는 뜻이고,
        그건 "발의됨" 이다. 부결된 법안을 통과로 표시하면 사업자가 있지도 않은
        제도를 준비하게 된다.
        """
        if any(word in self.proc_result for word in PASSED_RESULTS):
            return LegalStatus.ASSEMBLY_PASSED
        return LegalStatus.BILL_PROPOSED

    @property
    def is_dead(self) -> bool:
        return any(word in self.proc_result for word in DEAD_RESULTS)


def _parse_date(value: Any) -> dt.date | None:
    """`2026-08-12` → date. 형식이 다르면 None — 지어내지 않는다 (§9.4 V2)."""
    text = str(value or "").strip().replace(".", "-")
    if len(text) != 10:
        return None
    try:
        year, month, day = (int(part) for part in text.split("-"))
        return dt.date(year, month, day)
    except ValueError:
        return None


def is_tax_bill(name: str) -> bool:
    return any(word in name for word in TAX_KEYWORDS)


def build_body(bill: Bill) -> str:
    """저장할 본문.

    법안 조문은 이 API 에 없다. 있는 사실만 적고, 내용은 원문 링크로 보낸다.
    """
    lines = [
        f"의안명: {bill.name}",
        f"의안번호: {bill.bill_no}",
        f"소관위원회: {bill.committee or '미정'}",
        f"제안자: {bill.proposer or '미상'}",
        f"제안일: {bill.proposed_at.isoformat() if bill.proposed_at else '미상'}",
    ]
    if bill.committee_at:
        lines.append(f"위원회 상정일: {bill.committee_at.isoformat()}")
    lines.append(f"처리결과: {bill.proc_result or '심사 중'}")
    lines += [
        "",
        "이 항목은 국회에 발의된 법률안입니다. 아직 법이 아니며 심사 과정에서",
        "내용이 바뀌거나 폐기될 수 있습니다. 법안 조문은 원문 링크에서 확인하세요.",
    ]
    return "\n".join(lines)


class AssemblyBillCollector:
    """세법 관련 국회 법률안."""

    name = "assembly:bills"
    version = ADAPTER_VERSION

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 40.0) -> None:
        self.key = get_settings().assembly_api_key
        self._client = client
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.key)

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
                AssemblyError(
                    "TAXBRIEFING_ASSEMBLY_API_KEY 가 없습니다. "
                    "open.assembly.go.kr 마이페이지에서 인증키를 발급하세요."
                ),
            )
            return stats

        age = str((source.settings or {}).get("age") or DEFAULT_AGE)
        kept = 0
        page = 1

        # 목록에서 세법 관련은 10건 중 1건 남짓이다. 원하는 만큼 모일 때까지
        # 페이지를 넘기되, 상한을 둬서 무한히 돌지 않게 한다.
        while kept < limit and page <= 12:
            try:
                rows = self._fetch(age, page)
            except AssemblyError as exc:
                stats.fail(f"page:{page}", exc)
                break

            if not rows:
                break

            for row in rows:
                bill = self._to_bill(row)
                if not bill or not is_tax_bill(bill.name):
                    continue

                stats.discovered += 1

                if bill.is_dead:
                    continue
                if since and bill.proposed_at and bill.proposed_at < since:
                    continue

                try:
                    self._ingest_one(db, source, bill, stats)
                    kept += 1
                except Exception as exc:
                    stats.fail(f"{bill.bill_no} {bill.name[:20]}", exc)

                if kept >= limit:
                    break

            page += 1

        return stats

    def _fetch(self, age: str, page: int) -> list[dict[str, Any]]:
        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.get(
                f"{BASE_URL}/{BILL_SERVICE}",
                params={"KEY": self.key, "Type": "json", "pIndex": page, "pSize": 100, "AGE": age},
            )
        except httpx.HTTPError as exc:
            raise AssemblyError(f"호출 실패: {exc}") from exc
        finally:
            if owns:
                client.close()

        if response.status_code >= 400:
            raise AssemblyError(f"HTTP {response.status_code}")

        payload = response.json()
        # 실패는 {"RESULT": {"CODE": "...", "MESSAGE": "..."}} 로 온다.
        if "RESULT" in payload:
            result = payload["RESULT"]
            raise AssemblyError(f"{result.get('CODE')} {result.get('MESSAGE', '')[:80]}")

        body = next(iter(payload.values()), [])
        if not isinstance(body, list) or len(body) < 2:
            return []
        return body[1].get("row", []) or []

    def _to_bill(self, row: dict[str, Any]) -> Bill | None:
        bill_id = str(row.get("BILL_ID") or "").strip()
        name = str(row.get("BILL_NAME") or "").strip()
        if not bill_id or not name:
            return None
        return Bill(
            bill_id=bill_id,
            bill_no=str(row.get("BILL_NO") or "").strip(),
            name=name,
            committee=str(row.get("COMMITTEE") or "").strip(),
            proposer=str(row.get("PROPOSER") or "").strip(),
            proposed_at=_parse_date(row.get("PROPOSE_DT")),
            proc_result=str(row.get("PROC_RESULT") or "").strip(),
            committee_at=_parse_date(row.get("COMMITTEE_DT")),
            detail_link=str(row.get("DETAIL_LINK") or "").strip(),
        )

    def _ingest_one(
        self, db: Session, source: Source, bill: Bill, stats: CollectStats
    ) -> None:
        # 제목에 대표발의자를 붙인다.
        #
        # 의안명만 쓰면 목록이 "조세특례제한법 일부개정법률안" 으로 도배된다 —
        # 여러 의원이 같은 이름으로 각자 발의하기 때문이다. 국회 자신도
        # 대표발의자로 구분한다.
        title = f"{bill.name} — {bill.proposer}" if bill.proposer else bill.name

        result = ingest(
            db,
            source_id=source.id,
            canonical_url=bill.canonical_url,
            title=title[:500],
            publisher=bill.committee or "국회",
            raw_body=build_body(bill),
            published_at=(
                dt.datetime.combine(bill.proposed_at, dt.time(), tzinfo=dt.UTC)
                if bill.proposed_at
                else None
            ),
            source_item_id=bill.bill_no or bill.bill_id,
            parser_version=f"assembly/{ADAPTER_VERSION}",
        )

        result.version.doc_metadata = {
            "bill_id": bill.bill_id,
            "bill_no": bill.bill_no,
            "committee": bill.committee,
            "proposer": bill.proposer,
            "proposed_at": bill.proposed_at.isoformat() if bill.proposed_at else None,
            "committee_at": bill.committee_at.isoformat() if bill.committee_at else None,
            "proc_result": bill.proc_result,
            "legal_status": bill.legal_status.value,
            "detail_link": bill.detail_link,
            # 법안은 법이 아니다. 시행일을 붙이면 안 된다 —
            # 통과할지도 모르는 것에 날짜가 있으면 확정으로 읽힌다.
            "content_kind": "BILL",
            "full_text_stored": False,
        }
        db.flush()
        stats.record(result.outcome)
