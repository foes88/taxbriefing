# 신정 결재시스템으로 통째로 옮기기 — 이관 목록과 계획

taxbriefing 을 신정세무회계법인 통합관리 시스템(`C:\dev\shinjung-system`) 안으로
합친다. **빠진 것 하나가 나중에 조용히 깨지므로**, 먼저 옮길 것을 전부 센다.

이 문서는 실제로 열어 보고 센 것만 적었다. 짐작한 것은 없다.

---

## 1. 옮길 것 — 전체 목록

### 1.1 데이터 (표 29개 · 행 6,531)

실제로 값이 들어 있는 것:

| 행 수 | 표 | 무엇 |
|---:|---|---|
| 2,133 | `content_evidence` | 어느 원문 어디를 근거로 삼았는지 |
| 1,133 | `raw_content_versions` | 원문 버전 (내용 해시로 중복 판정) |
| 1,025 | `raw_contents` | 수집한 원문 (뉴스 포함) |
| 427 | `tax_contents` | 사람이 보는 콘텐츠 |
| 427 | `content_sources` · `reviews` · `content_versions` | 각각 출처·검수기록·본문 |
| 259 | `ai_analyses` | AI 호출 기록 |
| 213 | `source_runs` | 수집 실행 이력 |
| 23 | `sources` · `tags` | 수집 출처 23곳 · 태그 |
| 6 | `audit_logs` | |
| 5 | `idempotency_records` | |
| 2 | `users` | 관리자·검수자 계정 |

**비어 있는 표 14개** — `corrections` `deliveries` `engagement_events`
`business_profiles` `campaigns` `campaign_recipients` `campaign_contents`
`consents` `consultation_requests` `tenants` `policy_cluster_items`
`attachments` `policy_clusters` `content_tags`

> 비어 있다고 빼면 안 되는 것: `corrections`(정정 이력) · `deliveries`(발송 기록)
> 는 **아직 안 쓰였을 뿐 설계상 필요한 자리**다. `tenants` 는 다중 사무소를
> 염두에 둔 것이라 신정 한 곳만 쓰면 뺄 수 있다.

### 1.2 배치 (8개)

```
python -m app.collect            수집  — 출처 23곳
python -m app.bulk_draft         게시  — 원문 → 콘텐츠 (--auto-approve)
python -m app.summarize          요약  — GROQ
python -m app.classify           업종 분류 — GROQ
python -m app.classify_offline   업종 분류를 밖에서 (내보내기/받아넣기)
python -m app.notify             텔레그램 발송 (--send)
python -m app.compare            신구법 대조
python -m app.seed               초기 계정·출처 심기
```

매일 아침 도는 것은 **collect → bulk_draft → summarize → classify → notify**
다섯이다. GitHub Actions `daily.yml` 이 07:17 KST 에 돌린다.

### 1.3 API (7개 공개 + 관리자)

Vue 로 다시 짤 화면이 부를 것:

```
GET /api/v1/public/feed              목록 (검색·업종·종류·상태·기간)
GET /api/v1/public/contents/{id}     상세
GET /api/v1/public/calendar          신고·납부 마감일 (DB 안 봄)
GET /api/v1/public/industries        업종별 건수
GET /api/v1/public/months            공포월별 건수
GET /api/v1/public/news              뉴스
GET /api/v1/public/share/deadlines   사장님께 돌릴 안내문
```

관리자: `/contents` `/raw-contents` `/sources` `/analyses` `/me`

### 1.4 화면 (공개 6 + 관리자 5)

| 경로 | 무엇 | Vue 이식 |
|---|---|---|
| `/` | 오늘 — 지금 확인 · 예고 단계 · 최근 확정 · 뉴스 | **필요** |
| `/search` | 통합 검색 (종류 8칩 + 업종 11칩) | **필요** |
| `/upcoming` | 일정 — 마감/시행예정 + 사장님께 돌리기 | **필요** |
| `/contents/[id]` | 상세 (법령/심판례 두 틀) | **필요** |
| `/news` `/tips` | `/search` 로 넘기는 리다이렉트 | 불필요 |
| `/gate` | 사이트 잠금 | 신정 로그인으로 대체 |
| `/admin/*` (5개) | 검수·원문·출처 관리 | **판단 필요** (아래 3.3) |

공용 컴포넌트 10개: `Card` `DeadlineCard` `ShareCard` `TribunalArticle`
`Comparison` `DetailParts` `Authority` `Masthead` `Logo` `GateForm`

### 1.5 바깥 열쇠 5개

```
TAXBRIEFING_LAW_API_OC          법제처 국가법령정보
TAXBRIEFING_ASSEMBLY_API_KEY    열린국회정보
TAXBRIEFING_LAWMAKING_OC        국민참여입법센터 (입법예고)
TAXBRIEFING_NAVER_CLIENT_ID/SECRET  네이버 뉴스
TAXBRIEFING_AI_API_KEY          GROQ
TAXBRIEFING_TELEGRAM_BOT_TOKEN/CHAT_ID
```

설정 항목은 모두 25개(`app/core/config.py`). **접두어 `TAXBRIEFING_` 를 신정
쪽과 어떻게 맞출지 정해야 한다.**

### 1.6 시험 592건

**이건 코드가 아니라 그동안의 판단이 굳어 있는 곳이다.** 옮길 때 같이 안 가면
같은 실수를 다시 한다. 아래는 `tests/domain` · `tests/collectors` 의 큰 것만이고,
나머지는 API 인수시험(`tests/acceptance`)이다:

| 건수 | 무엇을 막고 있나 |
|---:|---|
| 30 | 검수 흐름·신뢰도 |
| 29 | 검증 게이트 G1~G6 |
| 26 | 사장님께 보낼 글 (없는 값 안 만들기, 관청 일 안 섞기) |
| 16 | 심판례 파싱 |
| 15 | GROQ 한도 (분당/하루 구분) · 밖에서 분류 받아넣기 |
| 14 | 세무 일정 13개 기한 |
| 13 | 입법예고 (실제 응답으로 시험) |
| 11 | 입법예고에 AI 안 돌리기 |
| 8 | 종류별 텔레그램 말투 · 부처 내부 규정 걸러내기 |
| 7 | 법안에 AI 안 돌리기 · 법안 건수 중복 안 세기 |

---

## 2. 부딪히는 곳

### 2.1 표 이름이 겹친다 — 2개

```
attachments    양쪽에 있음. 내용이 다름
audit_logs     양쪽에 있음. 내용이 다름
```

`users`(taxbriefing) 와 `employees`(신정) 는 이름은 다르지만 **역할이 겹친다.**
신정 것으로 합치고 taxbriefing `users` 는 버리는 쪽이 맞다 — 지금 2건뿐이다.

**정할 것:** 접두어(`tb_`)를 붙일지, 스키마를 나눌지(`taxbriefing.*`), 아니면
겹치는 둘만 바꿀지.

### 2.2 마이그레이션 방식이 다르다

```
taxbriefing   Alembic (alembic_version 표)
신정          database.py 안 자체 마이그레이션 (기동 시 실행으로 보임)
```

한 DB 에 둘이 공존할 수 있는지가 **1단계 방법을 가른다.** 신정 쪽에 물어봐야
한다(질문지 1-4).

### 2.3 프론트가 다르다 — 여기가 이 작업의 대부분

```
taxbriefing   Next.js 16 + React 19 + Tailwind    4,557줄
신정          Vue 3 + Vite + Tailwind            14,323줄
```

**React 화면을 Vue 앱에 녹일 수 없다.** 화면 4개 + 공용 컴포넌트를 다시 짜야
한다. 백엔드는 붙지만 화면은 이식이 아니라 재작성이다.

### 2.4 인증이 다르다

taxbriefing 은 자체 JWT + `users` 표, 신정은 자체 JWT + `employees` + `roles`.
**신정 것으로 통일한다.** taxbriefing 쪽 `app/core/security.py` ·
`app/api/deps.py` 의 의존성을 신정 것으로 갈아 끼운다.

공개 화면(`/public/*`)은 지금 인증이 없고 사이트 전체를 비밀번호로 막아 뒀다
(`middleware.ts`). 신정 안으로 들어가면 **로그인한 직원만** 보게 되므로 그 잠금은
없앤다.

### 2.5 DB 위치

taxbriefing 은 Neon(us-east-2, 미국). 왕복 393ms 라 이미 문제였고
`docs/MIGRATE-REGION.md` 에 옮기는 절차를 적어 뒀다.

**신정 DB 로 합치면 그 문제가 자동으로 정리되거나, 반대로 신정 쪽으로 옮겨간다.**
신정 DB 가 어디에 있는지 먼저 확인해야 한다(질문지 1-1, 1-2).

---

## 2.6 신정 README 와 코드가 어긋난다

신정 `README.md` 의 「향후 개선사항」에 이렇게 적혀 있다.

    - [ ] 로그인/인증 시스템
    - [ ] 카카오톡 알림 연동
    - [ ] 뉴스 수집 및 AI 요약
    - [ ] 고객 관리 시스템

그런데 `CLAUDE.md` 와 코드에는 `auth.py`(JWT + bcrypt)· `clients` · `client_assignees`
· `notifications.py` 가 **이미 있다.** README 가 오래된 것으로 보인다.

**어느 쪽이 지금 사실인지 확인해야 한다**(질문지 2-1, 4-1). README 를 믿고
"인증부터 만들어야 한다" 고 판단하면 있는 것을 또 만든다.

같은 README 가 DB 를 SQLite 라고 적었는데 `render.yaml` 에는 `DATABASE_URL` 이
있고 `database.py` 는 Postgres 를 받는다. 운영이 무엇인지도 확인 대상이다(1-1).

--- 

**한편 방향은 맞다.** 「뉴스 수집 및 AI 요약」 과 「고객 관리 시스템」 이 이미
계획에 적혀 있다. 우리가 합치려는 것이 그 두 칸을 채운다.

---

## 3. 합치는 진짜 이유 — 거래처

taxbriefing 에 없고 신정에 있는 것:

```
clients            거래처 (name, business_number, client_type, manager_id)
client_assignees   주담당 1명 + 부담당 여러 명, released_at 으로 담당 이력
employees          담당 직원 · 팀 · 권한
```

taxbriefing 은 "이 개정이 어느 고객에게 해당하는가" 를 못 잇는다. 일부러 안
만들었다 — 누가 자료를 넣고 어디까지 볼지 정해지지 않아서다. **신정에는 그
자료가 이미 있다.**

합치면 이렇게 된다.

    지금:  업종을 손으로 골라 안내문을 뽑는다
    합치면: 김실장이 맡은 거래처 14곳 중 음식점 3곳에 해당하는 개정 2건

**막는 것 하나** — `clients` 에 업종 칸이 없다. `client_type` 은 법인/개인/기타
뿐이다. taxbriefing 의 업종 분류(12개)와 이을 칸을 새로 만들어야 하고, **누가
언제 채우는지**를 정해야 한다(질문지 4-2, 4-3).

---

## 4. 순서

### 1단계 — 백엔드만 (되돌리기 쉬움)

- taxbriefing `app/` 을 신정 백엔드의 모듈로 옮긴다
- 표를 신정 DB 로 옮긴다 (`docs/MIGRATE-REGION.md` 의 덤프·복원·대조 절차 재사용)
- 인증을 신정 것으로 갈아 끼운다
- 배치 5개를 신정 쪽에서 돌게 한다
- **화면은 안 건드린다.** 기존 taxbriefing 사이트가 그대로 돌고 텔레그램도
  그대로 나간다

여기까지 되면 **자료가 한 곳에 모인다.** 되돌리려면 접속 문자열만 되돌리면 된다.

### 2단계 — 화면을 Vue 로

- 사이드바에 「세무 브리핑」
- **오늘 · 찾기 둘만 먼저.** 상세는 기존 사이트로 보내도 된다
- 신정 쪽 공용 컴포넌트와 색 토큰을 따른다(질문지 3-2, 3-3)

### 3단계 — 거래처와 잇기

- `clients` 에 업종 칸
- 담당자별 안내문
- 업무일지에 "이 거래처에 안내함" 남기기

---

## 5. 옮기면서 잃기 쉬운 것

코드를 옮기는 것보다 이것들이 위험하다. **전부 사람이 겪고 나서야 알게 된 것들
이고, 시험으로만 지켜지고 있다.**

- **종류에 따라 말을 바꾼다.** 법령·심판례·해석례·판례·법안·입법예고가 각각
  다른 문장을 쓴다. 하나로 뭉치면 "심판례가 개정되어 시행됩니다" 가 나온다
- **본문이 없으면 AI 를 안 돌린다.** 심판례·해석례·판례·법안·입법예고. 제목만
  주고 요지를 쓰라고 하면 지어낸다. 세 번 겪었다
- **모르는 값은 비운다.** "확인 필요" 로 채우면 확인할 것이 없는데 있는 것처럼 읽힌다
- **건수는 서버에 묻는다.** 화면에 나온 것을 세면 틀린다
- **자를 때는 자른 사실을 적는다**
- **오류 메시지가 사실과 다르면 그것부터 고친다.** 틀린 메시지 하나로 하루를 버렸다
- **검수 기록에 사람이 봤다고 적지 않는다.** 자동 승인은 자동이라고 적는다
- **크롤링 차단을 우회하지 않는다.** 막힌 곳은 막힌 대로 두고 한계로 적는다

`docs/ROADMAP.md` 의 「확인된 한계」 도 같이 옮긴다. 거기 적힌 막다른 길을
모르면 다음 사람이 같은 곳을 다시 판다.

---

## 6. 아직 못 정하는 것 — 신정 쪽 답이 필요하다

`docs/` 옆에 둔 질문지를 신정 쪽에 보내고 답을 받아야 아래가 정해진다.

| 질문 | 무엇이 갈리나 |
|---|---|
| 1-4 Alembic 공존 | 1단계를 어떻게 할지 |
| 1-1·1-2 DB 위치 | 리전 이전을 따로 할지, 합치면서 할지 |
| 3-2·3-3 공용 컴포넌트·색 토큰 | 2단계 화면을 어떤 언어로 짤지 |
| 4-2·4-3 업종 칸 | 3단계가 가능한지 |
| 6-3 배치 자리 | GitHub Actions 를 그대로 쓸지 |
| 7-2 손대면 위험한 곳 | 건드리지 말 곳 |
