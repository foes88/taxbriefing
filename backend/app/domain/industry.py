"""업종 분류 (상담 참고용).

**왜 `affected_users` 를 그대로 쓸 수 없는가.**

AI 가 채우는 `affected_users` 는 법조문에 적힌 대상을 그대로 옮긴 것이다.
실제로 저장된 값을 보면 이렇다.

    납세자 · 원천징수의무자 · 재정경제부 공무원 · 한국자산관리공사
    전남광주통합특별시 지원위원회
    수유자 등인 영리법인의 주주인 상속인의 배우자 및 상속인의 직계비속의 배우자

법률적으로는 정확하지만, "학원 원장님한테 해당되나"를 이걸로는 판단할 수 없다.
그래서 **고정된 분류표에 따로 매핑**한다. 자유 문자열이 아니라 열거형인 이유는
화면의 필터 버튼이 데이터에 따라 늘어났다 줄었다 하면 안 되기 때문이다.

분류는 **상담 참고용 색인**이지 적용 여부 판정이 아니다. 어떤 개정이 특정
사업자에게 실제로 적용되는지는 사실관계를 봐야 알 수 있고, 그건 세무전문가의
일이다 (§1.3). 그래서 애매하면 넓게 잡는다 — 놓치는 것보다 낫다.
"""

from __future__ import annotations

from enum import StrEnum


class Industry(StrEnum):
    """업종 분류표.

    세분류가 아니라 **상담에서 실제로 구분되는 단위**로 잡았다.
    분류가 잘게 쪼개질수록 경계 사례가 늘고, 경계 사례는 오분류가 된다.
    """

    #: 기관 내부 문서. 업종이 아니라 **화면에서 숨긴다는 표시**다.
    #: 규칙(is_internal_document)만 이 값을 붙인다 — 모델은 붙이지 못한다.
    INTERNAL = "INTERNAL"

    ALL = "ALL"
    FOOD = "FOOD"
    EDU = "EDU"
    RETAIL = "RETAIL"
    BEAUTY = "BEAUTY"
    LODGING = "LODGING"
    TRANSPORT = "TRANSPORT"
    FREELANCE = "FREELANCE"
    MEDICAL = "MEDICAL"
    CONSTRUCTION = "CONSTRUCTION"
    REALESTATE = "REALESTATE"
    MANUFACTURING = "MANUFACTURING"
    CORPORATE = "CORPORATE"


#: 화면·텔레그램에 나가는 이름.
LABEL: dict[Industry, str] = {
    Industry.INTERNAL: "기관 내부 문서",
    Industry.ALL: "전 업종 공통",
    Industry.FOOD: "요식·음식점",
    Industry.EDU: "학원·교육",
    Industry.RETAIL: "도소매·유통",
    Industry.BEAUTY: "미용·서비스",
    Industry.LODGING: "숙박",
    Industry.TRANSPORT: "운수·배달",
    Industry.FREELANCE: "프리랜서·인적용역",
    Industry.MEDICAL: "의료·약국",
    Industry.CONSTRUCTION: "건설",
    Industry.REALESTATE: "부동산임대",
    Industry.MANUFACTURING: "제조",
    Industry.CORPORATE: "법인 일반",
}

#: 분류 모델에 주는 설명. 경계를 말로 못 그으면 모델도 못 긋는다.
#: INTERNAL 은 여기 없다 — 모델에게 보여주지 않으므로 모델이 고를 수 없다.
GUIDE: dict[Industry, str] = {
    Industry.ALL: (
        "업종을 가리지 않고 모든 사업자에게 적용. "
        "부가세·소득세 신고절차, 가산세, 4대보험처럼 사업 종류와 무관한 것"
    ),
    Industry.FOOD: "음식점·카페·주점·배달음식. 의제매입세액공제, 식자재 매입, 음식점업 특례",
    Industry.EDU: "학원·교습소·과외·교육서비스. 교육비 세액공제, 학원 사업자 관련",
    Industry.RETAIL: "소매점·편의점·도매·온라인 판매. 신용카드 매출, 현금영수증, 재고",
    Industry.BEAUTY: "미용실·네일·피부관리·세탁 등 대인 서비스업",
    Industry.LODGING: "숙박업·펜션·게스트하우스",
    Industry.TRANSPORT: "화물·택시·대리운전·배달라이더·퀵서비스",
    Industry.FREELANCE: (
        "인적용역 사업자, 3.3% 원천징수 대상, 1인 사업자, 강사·디자이너·작가"
    ),
    Industry.MEDICAL: "병의원·약국·한의원·치과",
    Industry.CONSTRUCTION: "건설업·인테리어·전문공사",
    Industry.REALESTATE: "부동산 임대·중개. 임대소득, 상가 임대",
    Industry.MANUFACTURING: "제조·가공·공장",
    Industry.CORPORATE: "법인에만 해당. 법인세, 주주·배당, 법인 조직변경",
}


#: 기관 내부 문서를 가려내는 제목 패턴.
#:
#: 국세청·재정경제부 행정규칙을 수집하면 이런 것들이 함께 들어온다.
#:   "재정경제부 고문변호사 운영규정 (훈령)"
#:   "국세청 체납관리단 기간제 근로자 인사관리규정 (훈령)"
#:   "국제기구 초급전문가·중견전문가·인턴 파견 및 관리 규정 (예규)"
#:
#: 사장님 화면에 이런 게 섞이면 진짜 개정이 묻힌다.
#:
#: **모델에게 물어보지 않는다.** 제목만 봐도 아는 것에 AI 호출을 쓰면 무료 한도가
#: 정작 필요한 판단에서 떨어진다. 실제로 그렇게 떨어졌다. 규칙은 목록이 눈에
#: 보여서 틀렸을 때 고치기도 쉽다.
INTERNAL_DOCUMENT_PATTERNS: tuple[str, ...] = (
    # 인사·복무
    "인사관리",
    "인사규정",
    "복무규정",
    "파견 및 관리",
    "국외출장",
    "공무국외",
    "당직",
    "노사협의",
    "직장어린이집",
    # 공무원 개인에게 거는 의무. 사업자와 무관하다.
    "공무원의 ",
    "공무원 행동강령",
    "이해충돌",
    "회계직공무원",
    "회계관계 공무원",
    "회계관계공무원",
    # 기관 내부 운영
    "고문변호사",
    "재정보증",
    "갈등관리",
    "성과평가 운영",
    "성과관리지침",
    "적극행정",
    "위임전결",
    "사무분장",
    "청사 관리",
    "물품관리",
    "기록물관리",
    "정보보안",
)


def is_internal_document(title: str) -> bool:
    """기관 내부 문서인가.

    참이면 사업자와 무관하다고 보고 화면에서 숨긴다. 지우지는 않는다 —
    링크를 타고 들어오면 상세는 그대로 보인다.
    """
    return any(pattern in title for pattern in INTERNAL_DOCUMENT_PATTERNS)


def label(value: str) -> str:
    """저장된 값을 화면 이름으로. 모르는 값이면 그대로 돌려준다.

    분류표가 나중에 늘어날 수 있는데, 그때 옛 데이터가 화면에서 사라지면
    "왜 없어졌냐"는 말이 나온다. 이름을 못 찾는 것과 항목이 없는 것은 다르다.
    """
    try:
        return LABEL[Industry(value)]
    except ValueError:
        return value


def normalize(values: object) -> list[str]:
    """모델이 뱉은 것을 분류표 안의 값으로만 걸러낸다.

    모델은 `"요식업"`, `"FOOD_SERVICE"`, `"음식점"` 처럼 제멋대로 쓴다.
    분류표에 없는 값은 **버린다.** 지어낸 업종을 화면에 띄우느니 없는 게 낫다.

    INTERNAL 은 모델이 뭐라고 하든 받지 않는다. 그 값은 화면에서 숨긴다는
    뜻이고, 숨기는 결정은 눈으로 읽을 수 있는 규칙만 내려야 한다.
    """
    if not isinstance(values, list):
        return []

    out: list[str] = []
    for raw in values:
        try:
            item = Industry(str(raw).strip().upper())
        except ValueError:
            continue
        if item is Industry.INTERNAL:
            continue
        if item.value not in out:
            out.append(item.value)

    # ALL 이 붙었으면 나머지는 군더더기다. "전 업종 공통 + 요식업"은 읽는 사람을
    # 헷갈리게 한다 — 요식업만 해당된다는 뜻인지 아닌지 알 수 없다.
    if Industry.ALL.value in out:
        return [Industry.ALL.value]
    return out
