# TaxBriefing 문서

세무·정책 최신정보 수집·검증·분석·발송 플랫폼.
원본 개발패키지 v1.0(기준일 2026-08-06)을 구조화한 개발 기준 문서다.

## 읽는 순서

**처음 합류했다면** → [1. 제품 정의](spec/00-product.md) → [3. 출처·검증 정책](spec/02-sources.md) → [14. 인수 기준](spec/13-testing.md)
§3은 이 제품에서 가장 중요한 장이다. 잘못된 세무정보 발송을 막는 장치가 전부 여기 있다.

**바로 코드를 만지려면** → [`backend/README.md`](../backend/README.md)

## 명세서

| # | 문서 | 내용 |
| --- | --- | --- |
| 1 | [제품 정의와 성공 기준](spec/00-product.md) | 제품 원칙 6개, MVP 성공지표 |
| 2 | [범위, 사용자, 시나리오](spec/01-scope-users.md) | 사용자 유형, In/Out of Scope, UC-01~06 |
| 3 | [출처·수집·검증 정책](spec/02-sources.md) | **A~D 등급, legal_status, 게이트 G1~G6, 신뢰도 점수** |
| 4 | [기능 요구사항](spec/03-functional.md) | FR-SRC/NRM/VER/AI/CMS/PER/DLV/USR/ADM/B2B/BIL |
| 5 | [비기능 요구사항](spec/04-nfr.md) | NFR-001~015 |
| 6 | [시스템 아키텍처](spec/05-architecture.md) | 기술스택, 컴포넌트, 파이프라인, 실패정책 |
| 7 | [데이터 모델](spec/06-data-model.md) | 테이블 책임, 관계, 필드 규칙, **초안 이슈 D-01~08** |
| 8 | [API 명세](spec/07-api.md) | 공통 규약, 엔드포인트, **불일치 A-01~07** |
| 9 | [AI 분석 명세](spec/08-ai.md) | 사용 경계, 출력 필드, **검증 규칙 V1~V7**, 이슈 S-01~06 |
| 10 | [화면·UX](spec/09-ux.md) | 관리자 12화면, 사용자 8화면, 표시 안전 규칙 |
| 11 | [발송·개인화·과금](spec/10-delivery.md) | 매칭 가중치, 발송 유형, 채널 정책, 멱등성 키 |
| 12 | [보안·개인정보·감사](spec/11-security.md) | 데이터 등급, RBAC, SSRF 사양, 수신동의 |
| 13 | [운영·모니터링](spec/12-operations.md) | 관측 지표, 장애 P1~P4, 정정 프로세스, 백업 |
| 14 | [테스트·인수 기준](spec/13-testing.md) | **AT-01~AT-15**, 골든셋, DoD |
| 15 | [일정·역할·리스크](spec/14-plan-risks.md) | 12주 일정, **스프린트 백로그 S1~S3**, 리스크 |
| A | [공식 출처 레지스트리](spec/A-source-registry.md) | 초기 조사 대상 19개, 레지스트리 필드 |
| B | [설계 검증 체크리스트](spec/B-review-checklist.md) | 15개 체크리스트, 계약 검토 결과 요약 |
| C | [용어집](spec/C-glossary.md) | 공식 원문, 정책 클러스터, evidence 등 |

## 계약 파일 (정본)

코드가 반드시 따라야 하는 인터페이스 정의다. **이 파일들은 원본 그대로 보존한다.**
불일치를 발견하면 파일을 고치지 말고 해당 장의 "구현 결정" 표에 기록한 뒤 승인을 받는다.

| 파일 | 용도 |
| --- | --- |
| [`contracts/schema.sql`](contracts/schema.sql) | PostgreSQL 데이터 모델 — 마이그레이션·ERD 검토 기준 |
| [`contracts/openapi.yaml`](contracts/openapi.yaml) | API 계약 — 프론트·백엔드 합의 및 mock 서버 기준 |
| [`contracts/ai_output_schema.json`](contracts/ai_output_schema.json) | AI 구조화 출력 — 검증·평가 파이프라인 계약 |

## 명세서 이후의 결정

명세서 v1.0 발행 뒤에 내려진 결정이다. **본문과 충돌하면 여기가 최신이다.**

| 경로 | 내용 |
| --- | --- |
| [`DECISIONS.md`](DECISIONS.md) | ADR-001 텔레그램=알림·웹=기준화면 · ADR-002 비로그인 공개 · ADR-003 관리자 3역할 · ADR-004 배포 분리 |
| [`COLLECTION-STRATEGY.md`](COLLECTION-STRATEGY.md) | 수집 차단 대응 — 공식 OPEN API 경로와 출처별 수집 방식 |
| [`API-SIGNUP-GUIDE.md`](API-SIGNUP-GUIDE.md) | **어디서 어떤 API를 신청하는가** — 사이트별 절차, 신청할 API 목록, 인증 방식 |

## 기타

| 경로 | 내용 |
| --- | --- |
| [`OPEN-DECISIONS.md`](OPEN-DECISIONS.md) | 사람이 결정해야 하는 미결 항목 |
| [`prompts/claude-design-review.md`](prompts/claude-design-review.md) | 외부 AI 설계 리뷰 지시문 |
| [`assets/`](assets/) | 명세서 다이어그램 2종 |
| [`_source/`](_source/) | 원본 DOCX와 패키지 README (수정 금지) |

AI 분석 프롬프트 원문은 [`backend/app/services/ai/prompts/analysis_v1.md`](../backend/app/services/ai/prompts/analysis_v1.md)에 있다.

## 문서 규칙

- 명세 본문(`spec/`)은 원본 DOCX의 내용을 손실 없이 옮긴 것이다. **원문 표·수치를 임의로 바꾸지 않는다.**
- 구현 과정에서 발견한 판단은 각 장의 "구현 결정" 표에만 추가하고, 원문 서술과 구분한다.
- 원본과 충돌하면 원본이 우선이다(§1.5 우선순위 규칙). 원본을 고쳐야 한다면 승인권자 결재 후 `_source/`에 새 버전을 넣고 이 문서를 갱신한다.
