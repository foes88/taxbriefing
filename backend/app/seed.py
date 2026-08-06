"""초기 데이터 시드 (부록 A, ADR-003).

    python -m app.seed

멱등적이다. 여러 번 실행해도 중복 생성되지 않는다.
출처 목록은 부록 A의 **초기 조사 대상**이며, 실제 수집 방식은 미결 ② 확정 후 갱신한다.
"""

from __future__ import annotations

import os
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.domain.enums import AuthorityGrade, CollectorType, Role
from app.models.tables import Source, Tag, User

# (표시명, 도메인, 등급, 수집방식, 비고)
# collector_type 은 docs/COLLECTION-STRATEGY.md 의 판단을 반영한 **잠정값**이다.
SOURCES: list[tuple[str, str, AuthorityGrade, CollectorType, str]] = [
    ("국가법령정보센터", "law.go.kr", AuthorityGrade.A, CollectorType.API,
     "국가법령정보 공동활용 OPEN API. 현행/시행예정 법령, 변경이력"),
    ("대한민국 전자관보", "gwanbo.go.kr", AuthorityGrade.A, CollectorType.HTML,
     "공포 확인. 관보 검색 및 첨부 PDF"),
    ("국민참여입법센터", "opinion.lawmaking.go.kr", AuthorityGrade.A, CollectorType.HTML,
     "입법·행정예고 진행상태"),
    ("국회 의안정보시스템", "likms.assembly.go.kr", AuthorityGrade.A, CollectorType.API,
     "열린국회정보 OPEN API. 의안 발의·심사·의결"),
    ("국세법령정보시스템", "taxlaw.nts.go.kr", AuthorityGrade.A, CollectorType.HTML,
     "조세법령·해석례·판례. 개별 적용은 전문가 검토 필요"),
    ("국세청", "nts.go.kr", AuthorityGrade.B, CollectorType.RSS,
     "보도자료·신고안내·세무일정. 공공데이터포털 API 신청 대상"),
    ("재정경제부", "mofe.go.kr", AuthorityGrade.B, CollectorType.RSS,
     "세제개편·경제정책. 정부조직 개편에 따라 경로 재확인 필요"),
    ("대한민국 정책브리핑", "korea.kr", AuthorityGrade.B, CollectorType.RSS,
     "부처 보도자료 통합. 중복 보조 출처"),
    ("위택스", "wetax.go.kr", AuthorityGrade.B, CollectorType.HTML,
     "지방세 신고·납부·공지. 로그인 없는 공지 중심"),
    ("고용노동부", "moel.go.kr", AuthorityGrade.B, CollectorType.RSS, "노동정책·고시·보도자료"),
    ("4대사회보험 정보연계센터", "4insure.or.kr", AuthorityGrade.B, CollectorType.HTML,
     "사업장 4대보험 안내"),
    ("국민연금공단", "nps.or.kr", AuthorityGrade.B, CollectorType.RSS, "보험료·사업장 안내"),
    ("국민건강보험공단", "nhis.or.kr", AuthorityGrade.B, CollectorType.RSS, "보험료·사업장 안내"),
    ("근로복지공단", "comwel.or.kr", AuthorityGrade.B, CollectorType.RSS, "고용·산재보험"),
    ("기업마당", "bizinfo.go.kr", AuthorityGrade.B, CollectorType.API,
     "지원사업 공고. 신청기간·대상·첨부"),
    ("소상공인24", "sbiz24.kr", AuthorityGrade.B, CollectorType.HTML, "소상공인 지원사업·정책"),
]

# 개인화 축 (§11.1). 운영자가 콘텐츠에 붙이는 정규화 태그다.
TAGS: list[tuple[str, str, str]] = [
    # 사업자 유형
    ("BUSINESS_TYPE", "SOLE_PROPRIETOR", "개인사업자"),
    ("BUSINESS_TYPE", "CORPORATION", "법인사업자"),
    ("BUSINESS_TYPE", "FREELANCER", "프리랜서"),
    ("BUSINESS_TYPE", "NONPROFIT", "비영리"),
    # 과세 유형
    ("TAX_TYPE", "GENERAL", "일반과세"),
    ("TAX_TYPE", "SIMPLIFIED", "간이과세"),
    ("TAX_TYPE", "EXEMPT", "면세"),
    # 세목·주제
    ("TOPIC", "VAT", "부가가치세"),
    ("TOPIC", "INCOME_TAX", "종합소득세"),
    ("TOPIC", "CORPORATE_TAX", "법인세"),
    ("TOPIC", "WITHHOLDING", "원천세"),
    ("TOPIC", "LOCAL_TAX", "지방세"),
    ("TOPIC", "HONEST_REPORTING", "성실신고확인"),
    ("TOPIC", "YEAR_END_SETTLEMENT", "연말정산"),
    ("TOPIC", "LABOR", "노무"),
    ("TOPIC", "SOCIAL_INSURANCE", "4대보험"),
    ("TOPIC", "SUBSIDY", "지원사업"),
    ("TOPIC", "POLICY_FUND", "정책자금"),
    ("TOPIC", "FILING_SCHEDULE", "신고일정"),
    # 고용 규모
    ("EMPLOYEE_BAND", "NONE", "직원 없음"),
    ("EMPLOYEE_BAND", "1_4", "1~4명"),
    ("EMPLOYEE_BAND", "5_PLUS", "5명 이상"),
    # 지역
    ("REGION", "ALL", "전국"),
]


def seed_sources(db: Session) -> int:
    created = 0
    for display_name, domain, authority, collector, note in SOURCES:
        exists = db.execute(
            select(Source).where(Source.canonical_domain == domain)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(
            Source(
                display_name=display_name,
                canonical_domain=domain,
                authority=authority,
                collector_type=collector.value,
                # 자동수집 허용 여부가 확정될 때까지 중지 상태로 둔다 (미결 ②).
                status="PENDING_REVIEW",
                settings={"note": note, "verified_at": None},
            )
        )
        created += 1
    return created


def seed_tags(db: Session) -> int:
    created = 0
    for tag_type, code, label in TAGS:
        exists = db.execute(
            select(Tag).where(Tag.tag_type == tag_type, Tag.code == code)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(Tag(tag_type=tag_type, code=code, label=label))
        created += 1
    return created


#: 로컬 개발용 기본 계정. 운영에서는 절대 쓰지 않는다 (아래 가드 참조).
DEV_ADMIN_ID = "admin"
DEV_ADMIN_PASSWORD = "admin1234"


def seed_admin(db: Session) -> tuple[str, str] | None:
    """관리자 계정을 만든다 (ADR-003).

    로컬은 admin / admin1234 로 고정해 개발을 막지 않는다.
    운영(environment != local/test)에서는 이 기본값을 거부하고
    TAXBRIEFING_SEED_ADMIN_PASSWORD 를 요구한다.
    """
    from app.core.config import get_settings

    settings = get_settings()
    is_local = settings.environment in ("local", "test")

    email = os.environ.get("TAXBRIEFING_SEED_ADMIN_EMAIL", DEV_ADMIN_ID)
    password = os.environ.get("TAXBRIEFING_SEED_ADMIN_PASSWORD")

    if password is None:
        # 운영에서 기본 비밀번호로 관리자 계정이 생기면 §12.2 RBAC 전체가 무의미해진다.
        password = DEV_ADMIN_PASSWORD if is_local else secrets.token_urlsafe(18)
    elif not is_local and password == DEV_ADMIN_PASSWORD:
        raise RuntimeError(
            "운영 환경에서 개발용 기본 비밀번호를 사용할 수 없습니다. "
            "TAXBRIEFING_SEED_ADMIN_PASSWORD 를 다른 값으로 설정하세요."
        )

    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists is not None:
        return None

    db.add(
        User(
            email=email,
            role=Role.SYSTEM_ADMIN.value,
            display_name="최고관리자",
            password_hash=hash_password(password),
        )
    )
    return email, password


def seed_reviewer(db: Session) -> tuple[str, str] | None:
    """검수자 계정 (ADR-003).

    SYSTEM_ADMIN 은 승인할 수 없으므로(§12.2), 검수 흐름을 시험하려면
    REVIEWER 계정이 반드시 따로 있어야 한다.
    """
    from app.core.config import get_settings

    if get_settings().environment not in ("local", "test"):
        return None

    email, password = "reviewer", "reviewer1234"
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists is not None:
        return None

    db.add(
        User(
            email=email,
            role=Role.REVIEWER.value,
            display_name="세무검수자",
            password_hash=hash_password(password),
        )
    )
    return email, password


def main() -> int:
    db = SessionLocal()
    try:
        sources = seed_sources(db)
        tags = seed_tags(db)
        admin = seed_admin(db)
        reviewer = seed_reviewer(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"출처 {sources}건, 태그 {tags}건 생성")

    if admin is not None:
        email, password = admin
        print("\n최고관리자 계정 생성됨 (이 비밀번호는 다시 표시되지 않습니다)")
        print(f"  아이디:   {email}")
        print(f"  비밀번호: {password}")
    else:
        print("최고관리자 계정은 이미 존재합니다.")

    if reviewer is not None:
        email, password = reviewer
        print("\n검수자 계정 생성됨 (SYSTEM_ADMIN 은 승인할 수 없습니다 — §12.2)")
        print(f"  아이디:   {email}")
        print(f"  비밀번호: {password}")

    print("\n⚠ 위 계정은 로컬 개발용입니다. 배포 전에 반드시 변경하세요.")

    print(
        "\n주의: 출처는 status=PENDING_REVIEW 로 생성됩니다.\n"
        "      각 출처의 이용조건·자동수집 허용 방식을 확인한 뒤 ACTIVE 로 전환하세요\n"
        "      (docs/OPEN-DECISIONS.md 미결 ②)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
