# TaxBriefing 백엔드

FastAPI + PostgreSQL. 세무·정책 정보를 수집·검증·분석하고 검수를 거쳐 발송한다.

## 빠른 시작

```bash
# 1. 인프라
docker compose up -d db          # 저장소 루트에서. PostgreSQL → localhost:5433

# 2. 의존성
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows
# .venv/bin/python -m pip install -e ".[dev]"       # macOS/Linux

# 3. 설정
cp .env.example .env

# 4. 스키마
.venv/Scripts/python -m alembic upgrade head

# 5. 초기 데이터 (출처 16개, 태그 23개, 최고관리자 계정)
.venv/Scripts/python -m app.seed

# 6. 실행
.venv/Scripts/python -m uvicorn app.main:app --reload
```

- API 문서 http://localhost:8000/docs
- 헬스체크 http://localhost:8000/health

## 테스트

```bash
# 테스트 DB 생성 (최초 1회)
docker exec taxbriefing-db psql -U taxbriefing -d taxbriefing -c "CREATE DATABASE taxbriefing_test"

export TAXBRIEFING_TEST_DATABASE_URL=postgresql+psycopg://taxbriefing:taxbriefing@localhost:5433/taxbriefing_test

pytest                          # 전체
pytest -m "not integration"     # DB 없이 (도메인·계약 테스트만)
pytest tests/acceptance -v      # 인수 시나리오 AT-01~14
```

DB가 없으면 통합 테스트는 자동으로 skip 된다. 도메인 로직은 순수 함수라 DB 없이 전부 돈다.

## 구조

```
app/
  core/          설정, 로깅, DB, JWT, RBAC, 멱등성, 감사로그, SSRF
  domain/        ★ 순수 함수. DB·네트워크 의존 없음
    enums.py            legal_status / workflow_status / 권한 등
    gates.py            검증 게이트 G1~G6
    workflow.py         상태 전이, 승인 해제 규칙
    confidence.py       신뢰도 점수 + 산정 내역
    personalization.py  개인화 매칭 + 하드 제외
  models/        SQLAlchemy ORM (schema.sql 기준 + 구현 결정 D-01~08)
  schemas/       API 요청·응답 (openapi.yaml 기준 + 결정 A-01~07)
  services/
    ingest.py           수집·정규화·버전 판정
    content.py          콘텐츠 생성·편집·검수 (게이트 조립)
    ai/                 계약, V1~V7 검증, 제공자 어댑터, 실행 이력
    delivery/           채널 어댑터, 대상 선정, 발송
    render/             텔레그램 요약 렌더링
  api/v1/        라우터
tests/
  domain/        DB 불필요
  contract/      계약 파일 ↔ 코드 정합성, AI 검증 규칙
  acceptance/    AT-01~14, API RBAC, 공개 API
```

### 왜 도메인 로직이 순수 함수인가

게이트·상태전이·개인화는 **잘못된 세무정보 발송을 막는 안전장치**다.
DB나 HTTP에 얽혀 있으면 테스트가 어렵고, 어려운 테스트는 결국 안 쓰인다.
순수 함수로 두면 63개 단위 테스트가 0.1초에 돌고, 어떤 호출 경로에서든 같은 판정이 나온다.

## 핵심 불변식

코드가 지키는 규칙이다. 우회 경로를 만들면 결함으로 취급한다.

| # | 규칙 | 강제 지점 | 검증 |
| --- | --- | --- | --- |
| 1 | 뉴스(C/D)만으로는 승인·발송 불가 | `gates.gate_g1_authenticity` | AT-03 |
| 2 | 공포·시행 주장은 A등급 근거 필수 | `gates.gate_g5_cross_check`, AI `V3` | AT-04 |
| 3 | 근거 없는 날짜는 null | `gates.gate_g3_dates`, AI `V2` | AT-05 |
| 4 | HIGH/CRITICAL은 REVIEWER 승인 필수 | `gates.gate_g6_expert_approval` | AT-06 |
| 5 | 승인 후 보호 필드 수정 → 승인 해제 | `workflow.apply_edit` | AT-07 |
| 6 | 명시적 제외·수신철회는 점수 무관 하드 제외 | `personalization.match` | AT-08, AT-10 |
| 7 | 동일 캠페인·사용자·채널은 1건만 발송 | `dispatch` + UNIQUE 제약 | AT-09 |
| 8 | SYSTEM_ADMIN도 검수를 대체할 수 없다 | `core.rbac.REVIEW_ROLES` | AT-06 |
| 9 | 미승인 콘텐츠는 공개 경로에 노출되지 않음 | `api/v1/public.PUBLIC_STATES` | `test_unpublished_content_never_leaks` |
| 10 | 수집 URL은 사설 IP로 리다이렉트 불가 | `core.ssrf` | AT-14 |

## 계약 파일

`docs/contracts/` 아래 3개 파일이 정본이며 **코드가 따라간다**.

- `schema.sql` — DB 모델
- `openapi.yaml` — API 계약
- `ai_output_schema.json` — AI 출력. 런타임에 jsonschema로 **직접** 검증한다.
  손으로 옮긴 Pydantic 모델만 믿지 않기 위해서다.

`tests/contract/test_contract_parity.py`가 enum 값·순서·필수 필드를 대조한다.
계약을 고치면 이 테스트가 먼저 깨진다.

## 환경변수

`.env.example` 참조. 비밀키는 환경변수 또는 Secret Manager에서만 읽는다(§12.1).

| 변수 | 용도 |
| --- | --- |
| `TAXBRIEFING_DATABASE_URL` | PostgreSQL 접속 |
| `TAXBRIEFING_JWT_SECRET` | 토큰 서명. 운영에서는 32바이트 이상 필수 |
| `TAXBRIEFING_AI_PROVIDER` | `stub` (기본) — 실제 모델은 미결 ⑨ |
| `TAXBRIEFING_TELEGRAM_BOT_TOKEN` | 텔레그램 봇 (ADR-001) |
| `TAXBRIEFING_TELEGRAM_CHAT_ID` | 기본 발송 대상 |

## 발송은 기본적으로 실제 전송하지 않는다

`dispatch(..., actually_send=False)`가 기본값이다. 발송 레코드와 스냅샷만 만들고
`PENDING`으로 둔다. 발송은 되돌릴 수 없으므로 호출자가 명시적으로 켜야 한다.

## 다음 작업 (S2)

- 수집 어댑터 (API/RSS/HTML) — [`docs/COLLECTION-STRATEGY.md`](../docs/COLLECTION-STRATEGY.md)
- Celery 스케줄러 + `source_runs` 기록
- 첨부파일 처리 (PDF/HWP/DOCX/XLSX)
- 정책 클러스터링
- 캠페인 생성·예약·발송 실행
