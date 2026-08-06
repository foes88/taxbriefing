# 부록 A. 공식 출처 레지스트리

> 원본: 통합개발명세서 부록 A

> **하드코딩 금지.** 정부 조직 개편, 사이트 개편, 도메인 변경이 발생할 수 있으므로
> 출처명과 URL을 코드에 하드코딩하지 않고 `sources` 테이블에서 관리한다.
> 아래는 기준일(2026-08-06) 현재 **초기 조사 대상**이며, 구현 직전에 재확인이 필요하다.

## A.1 초기 조사 대상

| 등급 | 출처 | 수집 내용 | 대표 URL | 비고 |
| --- | --- | --- | --- | --- |
| A | 국가법령정보센터 | 법률·시행령·시행규칙·현행/시행예정 | https://www.law.go.kr | 법령 API·공개 방식 기술조사 |
| A | 대한민국 전자관보 | 법률·명령 공포, 고시, 관보 PDF | https://www.gwanbo.go.kr | 관보 검색·첨부 수집 |
| A | 국민참여입법센터 | 정부 입법·행정예고, 진행상태 | https://opinion.lawmaking.go.kr | 목록·상세·첨부 |
| A | 국회 의안정보시스템 | 의안 발의·심사·의결 | https://likms.assembly.go.kr/bill | 의안번호 기반 |
| A/B | 국세법령정보시스템 | 조세법령, 해석례, 판례·결정례 | https://taxlaw.nts.go.kr | 검색·원문 연결 |
| B | 국세청 | 보도자료, 신고안내, 세무일정 | https://www.nts.go.kr | 목록·상세·첨부 |
| B | 재정경제부 | 세제개편·경제정책·보도자료 | https://www.mofe.go.kr | 정부조직 개편·기존 자료 경로 확인 |
| B | 대한민국 정책브리핑 | 부처 정책·보도자료 통합 | https://www.korea.kr | 중복 보조 출처 |
| B | 위택스·지방세 관련 기관 | 지방세 신고·납부·공지 | https://www.wetax.go.kr | 로그인 없는 공지 중심 |
| B | 고용노동부 | 노동정책, 고시, 보도자료 | https://www.moel.go.kr | 노무 태그 |
| B | 4대사회보험 정보연계센터 | 사업장 4대보험 안내 | https://www.4insure.or.kr | 공지·안내 |
| B | 국민연금공단 | 보험료·사업장 안내 | https://www.nps.or.kr | 공지·보도자료 |
| B | 국민건강보험공단 | 보험료·사업장 안내 | https://www.nhis.or.kr | 공지·보도자료 |
| B | 근로복지공단 | 고용·산재보험 | https://www.comwel.or.kr | 공지·보도자료 |
| B | 기업마당 | 정부·지자체 지원사업 공고 | https://www.bizinfo.go.kr | 신청기간·대상·첨부 |
| B | 소상공인24 | 소상공인 지원사업·정책 | https://www.sbiz24.kr | 지원사업·공지 |
| B | 지자체·지역기관 | 지역 지원·지방세·조례 | 출처별 등록 | 우선지역부터 단계 확장 |
| C | 세무·회계 전문언론 | 해설·쟁점·업계반응 | 계약/출처별 | **전문 재배포 금지** |
| D | 일반 경제뉴스 | 이슈 탐지 | 출처별 | **공식 근거 연결 전 발송 금지** |

## A.2 출처 레지스트리 필드

- `display_name`, `organization_code`, `canonical_domain`
- `authority_grade`, `content_categories`, `legal_roles`
- `collector_type`, `schedule`, `rate_limit`, `timeout`, `retry_policy`
- `terms_url`, `copyright_policy`, `robots_checked_at`, `approval_note`
- `adapter_name`, `adapter_version`, `parser_test_fixture`
- `last_success_at`, `failure_streak`, `health_status`, `owner_user_id`

> `schema.sql`의 `sources` 테이블에는 `content_categories`, `legal_roles`, `robots_checked_at`,
> `approval_note`, `parser_test_fixture`, `health_status`, `owner_user_id`, `timeout`,
> `retry_policy` 컬럼이 없다. MVP는 이들을 `settings jsonb`에 담고,
> 운영 빈도가 확인되면 정식 컬럼으로 승격한다.

## A.3 출처 역할 메모

- **전자관보**는 법률·대통령령·총리령·부령 등의 **공포 수단**이다.
- **국가법령정보센터**는 현행과 시행예정 법령을 확인하는 기준 출처다.
- **국세법령정보시스템**은 조세법령·해석례·판례·결정례를 제공하지만, 개별 사실관계에 대한 적용은 전문가 검토가 필요하다.
- **국민참여입법센터**와 **국회 의안정보시스템**은 입법예고·법안 진행상태 추적에 사용한다.

## A.4 참고 URL

| 기관 | URL |
| --- | --- |
| 국가법령정보센터 | https://www.law.go.kr |
| 대한민국 전자관보 | https://www.gwanbo.go.kr |
| 국민참여입법센터 | https://opinion.lawmaking.go.kr |
| 국회 의안정보시스템 | https://likms.assembly.go.kr/bill |
| 국세청 | https://www.nts.go.kr |
| 국세법령정보시스템 | https://taxlaw.nts.go.kr |
| 기업마당 | https://www.bizinfo.go.kr |
| 고용노동부 | https://www.moel.go.kr |

※ 출처명, 조직명, URL, 자동수집 허용 방식은 개발 착수 시 다시 확인하고 source registry에서 변경 가능하게 관리한다.
