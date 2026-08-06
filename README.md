# TaxBriefing

세무·정책 최신정보를 **공식 원문 기준으로** 수집·검증·분석하고, 전문가 검수를 거쳐
사업자에게 매일 전달하는 플랫폼.

국세·지방세·노무·4대보험·성실신고·소상공인 지원사업 등 공공기관이 발표·공표한 정보를
개인사업자·법인 사장님이 "나에게 해당되는가"와 "지금 뭘 해야 하는가"로 바로 읽을 수 있게 만든다.

```
공식 출처 수집 → AI 구조화 분석 → 관리자 검수·승인 → 사이트 게시 → 텔레그램 요약 발송
```

## 이 제품의 핵심

세무 정보 서비스에서 가장 위험한 건 **틀린 정보를 자신 있게 보내는 것**이다.
그래서 전체 설계가 그 하나를 막는 데 맞춰져 있다.

- **공식 원문 우선** — 뉴스는 탐지용. 확정은 법령·관보·정부기관 원문으로만
- **상태 분리** — "입법예고"와 "시행 중"을 절대 섞지 않는다
- **근거 없는 생성 금지** — AI가 원문에 없는 날짜·수치·대상을 만들면 지운다
- **사람이 최종 승인** — 고위험 정보는 세무전문가 승인 없이 나가지 않는다
- **추적 가능성** — 누가 어떤 근거를 보고 승인했는지 전부 남는다
- **정정 우선** — 틀렸으면 받은 사람에게 정정을 보낸다

## 저장소 구성

| 경로 | 내용 |
| --- | --- |
| [`docs/`](docs/) | 개발 기준 문서. **여기서 시작하세요** |
| [`docs/contracts/`](docs/contracts/) | DB·API·AI 스키마 **정본** (수정 시 승인 필요) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 아키텍처 결정 기록 (ADR-001~004) |
| [`docs/COLLECTION-STRATEGY.md`](docs/COLLECTION-STRATEGY.md) | 수집 경로 — 공식 OPEN API 활용 방안 |
| [`docs/API-SIGNUP-GUIDE.md`](docs/API-SIGNUP-GUIDE.md) | 어디서 어떤 API를 신청하는가 |
| [`docs/OPEN-DECISIONS.md`](docs/OPEN-DECISIONS.md) | 사람이 결정해야 하는 미결 항목 |
| [`docs/WEB.md`](docs/WEB.md) | 웹 화면 구성과 디자인 원칙 |
| [`backend/`](backend/) | FastAPI + PostgreSQL API 서버 |
| `app/` `components/` `lib/` | Next.js 공개 사이트 + 관리자 화면 |

> 웹 앱은 **저장소 루트**에 있다. Vercel이 별도 설정 없이 인식하게 하기 위해서다 (ADR-004).
> 백엔드는 `backend/` 에 있고 별도 호스트에 배포한다.

## 실행

```bash
# 1. 인프라
docker compose up -d db

# 2. 백엔드
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env                      # TAXBRIEFING_LAW_API_OC 설정
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.seed          # 출처·태그·관리자 계정
.venv/Scripts/python -m app.collect       # 법령 원문 수집
.venv/Scripts/python -m app.bulk_draft --auto-approve   # 로컬: 수집분 게시
.venv/Scripts/python -m uvicorn app.main:app --reload

# 3. 웹 (저장소 루트에서)
cd .. && npm install && npm run dev
```

## 배포 환경변수 (Vercel)

| 이름 | 용도 |
| --- | --- |
| `SITE_PASSWORD` | 사이트 접근 비밀번호. **미설정 시 운영에서는 열리지 않는다** |
| `NEXT_PUBLIC_API_BASE` | 백엔드 주소 + `/api/v1` |

| | 주소 |
| --- | --- |
| 공개 사이트 | http://localhost:3100 |
| 관리자 | http://localhost:3100/admin (`admin` / `admin1234`) |
| API 문서 | http://localhost:8000/docs |

로컬 계정은 `admin/admin1234`(운영·관리)와 `reviewer/reviewer1234`(검수)다.
**승인은 검수자만 가능하다** — 관리자로 승인을 시도하면 403이다 (§12.2).

## 일일 운영

```bash
python -m app.collect              # 최근 30일 공포 법령 수집
python -m app.notify               # 텔레그램 브리핑 미리보기
python -m app.notify --send        # 실제 발송
```

발송은 기본이 미리보기다. `--send` 를 명시해야 나간다.

### 구현 완료

| 영역 | 내용 |
| --- | --- |
| 데이터 | 28개 테이블, Alembic 마이그레이션 |
| 검증 게이트 | G1 원문성 · G2 상태성 · G3 날짜성 · G4 적용성 · G5 교차검증 · G6 전문가승인 |
| AI 파이프라인 | 계약 스키마 직접 검증 + 환각 차단 규칙 V1~V7, 실행 이력, stub 제공자 |
| 검수 워크플로 | 12단계 상태 전이, 승인 해제, 낙관적 잠금, 근거 연결, 게시 |
| **수집** | **국가법령정보 OPEN API 어댑터 — 법령·행정규칙** |
| 개인화 | 규칙 매칭 + 하드 제외 + 매칭 이유 |
| 보안 | JWT, RBAC 3역할, SSRF 방어, 감사로그, 멱등성 |
| 발송 | 텔레그램 요약 렌더러 + 채널 어댑터, 대상 선정, 발송 스냅샷 |
| **공개 웹** | **로그인 없는 피드·상세·검색·필터 (Next.js)** |
| **관리자 웹** | **대시보드·수집원문·검수편집기·출처관리** |

### 실제로 검증한 것

- **AT-01 멱등 수집** — 법령 API 재수집: 1차 신규 69건 → 2차 신규 0건 · 동일 69건
- **전체 흐름** — 수집 → 콘텐츠 생성 → 근거 연결 → 검수 요청 → 승인 → 게시 → 공개 노출
- **§12.2 권한 분리** — SYSTEM_ADMIN 의 승인 시도가 403 으로 차단됨
- **216개 테스트 통과** (인수 AT-01~AT-14 중 12개 자동화)

```
tests/domain/       63개   DB 불필요 — 게이트, 상태전이, 신뢰도, 개인화
tests/contract/     46개   계약 파일 ↔ 코드 정합성, AI 검증 V1~V7
tests/acceptance/  107개   AT 시나리오, API RBAC, 공개 API, 텔레그램 렌더링
```

### 다음 (S2)

수집 어댑터 · 스케줄러 · 첨부파일 처리 · 정책 클러스터링 · 캠페인 발송

## 배포 구성 (ADR-004)

| 구성요소 | 권장 |
| --- | --- |
| 공개 웹 + 관리자 (Next.js) | Vercel |
| API (FastAPI) | Railway / Render / Fly.io |
| PostgreSQL | Neon / Supabase |
| 수집·발송 스케줄러 | GitHub Actions cron |

백엔드를 Vercel에 올리지 않는 이유는 [`docs/DECISIONS.md#adr-004`](docs/DECISIONS.md)에 있다.

## 착수 전 확정 필요

[`docs/OPEN-DECISIONS.md`](docs/OPEN-DECISIONS.md)의 차단 항목이 미결이면 해당 스프린트를 시작할 수 없다.
가장 시급한 것은 **② 공식 출처별 자동수집 허용 방식** — API 신청에 시간이 걸리므로 지금 시작해야 한다.

## 주의

이 서비스는 **개별 세무 판단을 자동화하지 않는다.** 일반적인 제도 변경을 알리고,
사업자가 무엇을 확인해야 하는지 안내하며, 판단이 필요한 지점에서 전문가 상담으로 연결한다.

개인정보·광고성 정보 발송·저작권·전자상거래 요건은 출시 전 법률 검토가 필요하다.
