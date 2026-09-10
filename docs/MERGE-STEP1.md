# 1단계 — 백엔드를 신정으로 합치기 (실행 계획)

신정 쪽 조사 답변(`docs/ASK-SHINJUNG.md` 에 대한 회신)을 받고 정한 것.
화면은 안 건드린다. 자료와 배치만 옮긴다. **되돌리려면 접속 문자열만 되돌린다.**

---

## 0. Actions 예산 — 계산이 틀렸고, 답도 달라졌다

### 내가 틀린 것

`keep-awake.yml` 의 cron 을 보고 "평일 07~19시 10분마다 = 하루 72회 × 22일 =
1,584분/월" 이라고 곱했다. **워크플로가 그만큼 돈다고 가정한 것이지 센 것이
아니었다.** 실제 청구 화면은 이랬다.

    Actions minutes    30 min used / 2,000 min included

50배 넘게 빗나갔다.

### 진짜 이유 — 저장소 공개 여부

    foes88/taxbriefing       공개   → Actions 무료·무제한
    foes88/shinjung-system   비공개 → 2,000분/월 계량

**taxbriefing 배치는 공개 저장소라 지금 공짜로 돈다.** 계량되는 것은 신정
것뿐이고 그게 30분이다.

그러면 답이 뒤집힌다. **배치를 신정(비공개)으로 옮기는 순간 과금이 시작된다.**
월 600~900분. 2,000분 안에 들어가긴 하지만, 공짜였던 것에 값을 붙이는 셈이다.

### 그래서 — 배치는 공개 저장소에 남긴다

무료를 지키는 것이 목표라면 이게 답이다.

    코드     taxbriefing 공개 저장소 (파이썬 패키지)
    배치     taxbriefing 공개 저장소 (Actions 무료)
    DB       신정 Supabase 의 tb 스키마          ← 여기서 합쳐진다
    화면·API 신정 (패키지를 의존성으로 설치)

`backend/pyproject.toml` 이 이미 있고 (`taxbriefing-backend 0.1.0`),
워크플로도 이미 `pip install ./backend` 로 설치해서 쓴다. **신정도 같은 방식으로
쓰면 된다.**

```
# 신정 requirements.txt
taxbriefing-backend @ git+https://github.com/foes88/taxbriefing@main#subdirectory=backend
```

모델이 한 곳에만 있으므로 **정의가 갈라지지 않는다.** 신정은 그 모델로
`tb` 스키마를 읽기만 한다.

### keep-awake 는 그냥 지워도 된다

**"누가 로그인하면 어차피 깨어난다."** 맞다. keep-awake 가 하는 일은
"아침 첫 사람이 1분 안 기다리게" 하는 것뿐이다.

지금 쓰는 사람이 3명이고 아직 실사용 전이다. 한 사람이 아침에 한 번 1분
기다리는 값이 워크플로 하나를 유지할 값보다 크지 않다.

**배치는 API 를 안 쓴다.** 수집·게시·요약·발송이 전부 DB 에 직접 붙는다
(`daily.yml` 주석: "Render 가 없어도 돈다"). 서버가 자고 있어도 아침 배치는
그대로 돈다.

다만 **아침 텔레그램 링크를 누르는 사람은 그 1분을 맞는다.** 그게 매일
아침이라면 값어치가 있다. 그때는 워크플로를 따로 만들 것 없이 **배치 맨
끝에 핑 한 번**을 붙이면 된다 — 이미 도는 작업이라 공짜다.

---

## 1. 표를 어떻게 넣나 — 별도 Base + 스키마 `tb`

### 접두어에서 스키마로 바꿨다

처음에는 `tb_` 접두어를 골랐다. **신정 로컬이 SQLite 이고 SQLite 는 스키마를
지원하지 않아서**였다. 그런데 신정 쪽 조사에서 사실 하나가 나왔다.

    재직 직원 3명 · 휴가 1건 · 업무일지 1건 · 지출·공지·도장 0건
    감사로그 4건 (마지막 2026-08-21)

**아직 실사용 전이다.** 지킬 운영 데이터가 사실상 없다. 그러면 로컬을
SQLite 에 맞출 이유도 없다 — **로컬도 Postgres 로 옮긴다.**

그게 덤으로 2026-08-12 사고의 뿌리를 없앤다. 그 사고는 로컬 SQLite / 운영
Postgres 라는 틈에서 났다. `DATABASE_URL` 이 빠지자 운영이 조용히 SQLite 로
떨어졌다. 양쪽을 Postgres 로 맞추면 그 틈 자체가 사라진다.

**지금이 가장 싸다.** 나중에 12명이 매일 쓰기 시작하면 못 한다.

### 한 줄이면 된다 — 실제로 해 보고 확인했다

`Base.metadata` 가 한 곳이라 스키마를 거기 박으면 표 전체가 따라간다.

```python
# app/models/base.py
metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="tb")
```

이 한 줄을 실제로 넣고 확인했다(확인 뒤 되돌림).

    표 28개 · tb 스키마 28개 · public 으로 샌 것 0개
    FK 52개 · 스키마 밖을 가리키는 것 0개
    DDL:  CREATE TABLE tb.tax_contents (
          ... REFERENCES tb.tenants (id)

FK 는 코드에 `ForeignKey("tenants.id")` 처럼 스키마 없이 적혀 있지만
**해석은 같은 스키마 안에서 된다.** 52개 전부 `tb` 를 가리켰다.

겹치던 `attachments` · `audit_logs` 도 `tb.attachments` · `tb.audit_logs` 가
되어 신정 것과 안 부딪힌다.

### 스키마가 접두어보다 나은 이유

- 표 29개 이름을 안 바꾼다 — 코드·시험·문서가 그대로다
- **통째로 떼거나 따로 백업할 수 있다** (`pg_dump --schema=tb`)
- 신정 `create_all()` 은 자기 Base 만 보므로 `tb` 를 안 건드린다
- Alembic 은 `version_table_schema="tb"` 로 자기 버전표도 안에 둔다

### create_all 충돌은 Base 를 갈라서 막는다

신정은 기동할 때마다 `init_db()` 가 돈다(`main.py:167`).

    Base.metadata.create_all()      database.py:1058
    _run_migrations()               database.py:825~   손으로 쓴 ALTER TABLE

Alembic 이 관리할 표를 SQLAlchemy 가 먼저 만들면 리비전과 실제 스키마가
어긋나고 다음 `upgrade` 가 깨진다.

**taxbriefing 은 자기 Base 를 쓴다.** 신정 `Base.metadata` 에 안 들어가므로
`create_all()` 대상이 아니다. 서로 안 만난다.

    신정 Base        → create_all + _run_migrations   (public, 그대로)
    taxbriefing Base → Alembic                        (tb)

### 버리는 표

- `users` (2건) — 신정 `employees` 로 대체
- `tenants` (0건) — 다중 사무소를 염두에 둔 것. 신정 한 곳만 쓰면 필요 없다

`corrections`(정정 이력)· `deliveries`(발송 기록)는 **비어 있어도 가져간다.**
아직 안 쓰였을 뿐 설계상 있어야 할 자리다.

## 2. DB 를 어디로 모으나 — Supabase 로

실제로 재 봤다 (TCP 왕복, 한국에서).

    Supabase ap-south-1 (뭄바이)    131 ms
    Neon     us-east-2  (오하이오)   189 ms

**합치면 오히려 가까워진다.** 자료를 한 곳에 모으는 것이 목적이므로 신정 쪽
Supabase 로 옮긴다.

둘 다 한국이 아니라는 것은 그대로 남는다. 화면 쪽은 응답 캐시(2분)로 이미
0.003초까지 내려와 있어서 당장 급하지는 않다. 나중에 ap-northeast 로 옮기는
절차는 `docs/MIGRATE-REGION.md` 에 적어 뒀다.

### 옮기는 법

`docs/MIGRATE-REGION.md` 의 절차를 그대로 쓴다. 이미 연습해서 검증한 것이다.

1. **쓰는 작업을 전부 멈춘다.** 20초 간격으로 두 번 세서 같은지 본다 —
   지난번에 요약 배치가 돌고 있어서 행 수가 어긋났다
2. `pg_dump --no-owner --no-privileges --format=custom`
3. **`tb` 스키마를 만들고 그 안에 복원한다.** 표 이름을 안 바꾸므로
   `pg_restore` 앞에 `search_path` 를 `tb` 로 두거나, 덤프를
   `--schema=public` 로 뜬 뒤 `sed` 로 스키마만 바꿔 넣는다.
   가장 안전한 길은 Alembic 으로 `tb` 에 빈 표를 만들고 데이터만 옮기는 것이다
4. **행 수와 값 지문을 대조한다** — `docs/sql/verify_counts.sql`,
   `docs/sql/verify_checksums.sql`
5. 접속 문자열 교체
6. 옛 DB 는 일주일 둔다

---

## 3. 인증 — 신정 것으로 갈아 끼운다

taxbriefing 은 자체 JWT + `users`. 신정은 JWT(HS256, 12시간) + `employees` +
`roles`/`role_permissions`.

- taxbriefing `app/core/security.py` · `app/api/deps.py` 의 의존성을 신정
  `auth.py:103 get_current_employee` 로 바꾼다
- 권한은 신정 방식(`require("taxbriefing.view")`)을 따른다.
  권한 키를 `permissions.py` 에 추가한다
- **공개 화면의 잠금(`middleware.ts`)은 없앤다.** 신정 안에서는 로그인한
  직원만 보므로 사이트 비밀번호가 필요 없다

`TAXBRIEFING_JWT_SECRET` 등 인증 관련 설정 3개가 필요 없어진다.

---

## 4. 배치 — 옮기지 않는다

`daily.yml` 은 **taxbriefing 공개 저장소에 그대로 둔다.** 옮기면 과금되고,
남기면 공짜다. 바꾸는 것은 하나뿐이다.

    TAXBRIEFING_DATABASE_URL  →  신정 Supabase (tb 스키마)

시크릿 7개도 그 저장소에 이미 들어 있으므로 손댈 것이 없다.

    TAXBRIEFING_LAW_API_OC / ASSEMBLY_API_KEY / LAWMAKING_OC
    TAXBRIEFING_NAVER_CLIENT_ID / SECRET
    TAXBRIEFING_AI_API_KEY
    TAXBRIEFING_TELEGRAM_BOT_TOKEN / CHAT_ID

**남는 문제 하나** — GitHub 예약이 시각을 못 지킨다. 07:17 인데 09~15시에
돌거나 아예 안 돈 날이 있었다. 무료 외부 스케줄러가 `workflow_dispatch` 를
정시에 부르게 하면 해결된다. 이것도 돈이 안 든다.

---

## 5. 코드를 어디에 두나 — 옮기지 않고 의존한다

처음에는 `backend/taxbriefing/` 로 통째로 옮기려 했다. 그러면 배치도 따라
가야 하고 과금이 시작된다.

**패키지로 쓴다.**

    taxbriefing 저장소   모델·수집기·요약·배치  (그대로, 공개)
    신정 저장소          routers_taxbriefing.py  (읽는 라우터만)
                        Vue 화면

신정 `main.py`(3,000줄)에는 `include_router` 한 줄만 는다. 그쪽 조언대로
거기 붙이지 않는다.

**모델 정의가 한 곳에만 있다.** 양쪽에 두면 언젠가 갈라지고, 갈라지면
한쪽이 조용히 틀린 값을 읽는다.

---

## 6. 사고를 되풀이하지 않기 위한 가드

2026-08-12 에 Render 대시보드에서 `DATABASE_URL` 이 빠져 **운영이 SQLite 로
돌다 데이터가 날아간 적**이 있다. `database.py:18` 이 값이 없으면 조용히
SQLite 로 떨어진다.

taxbriefing 자료까지 같은 DB 에 들어가면 그 사고가 더 커진다.

**기동할 때 막는다.** 운영 환경인데 접속 문자열이 sqlite 면 뜨지 않고 죽는다.
조용히 잘못된 곳에 쓰는 것보다 안 뜨는 편이 낫다.

---

## 7. 순서와 되돌리기

| | 하는 일 | 되돌리기 |
|---|---|---|
| 0 | 신정 로컬을 Postgres 로 (SQLite 틈 없애기) | 로컬만이라 위험 없음 |
| 1 | taxbriefing 에 `schema="tb"` 한 줄 + Alembic `version_table_schema` | 커밋 되돌리기 |
| 2 | 신정 Supabase 에 `tb` 스키마 만들고 Alembic 으로 표 생성 | 스키마 통째로 드롭 |
| 3 | 배치 멈춤 확인 → 덤프 → `tb` 로 데이터 이관 → **행수·지문 대조** | 옛 DB 그대로 |
| 4 | `daily.yml` 의 DB 주소만 신정 것으로 | **주소만 되돌림** |
| 5 | 신정에 패키지 의존성 + 읽는 라우터 하나 | 커밋 되돌리기 |
| 6 | 일주일 지켜보고 옛 Neon 정리 | — |

**화면은 이 단계에서 하나도 안 건드린다.** 기존 taxbriefing 사이트가 그대로
돌고 아침 텔레그램도 그대로 나간다. 자료만 한 곳으로 모인다.

---

## 8. 2단계에서 쓸 것 (미리 적어 둠)

화면을 Vue 로 옮길 때 지킬 것. 신정 쪽 회신에서 나온 규칙이다.

- **컴포넌트가 아니라 CSS 클래스다** — `.btn` `.btn-primary` `.card-base`
  `.badge` `.table` `.input` `.empty-state` (`assets/main.css`)
- **색은 CSS 변수 토큰** — `--c50~--c700`(주색 파랑), `--n0~--n800`(회색 10단계),
  `--g*`, `--bg`. taxbriefing 대응:

      ink → --n700    line → --n100    accent → --c500    danger → --r600

- **목록 총계는 `x-total-count` 헤더** — taxbriefing `feed` 는 본문 `total` 로
  준다. 맞춰야 한다
- **모바일 된다** — 640px 이하에서 표가 카드로 바뀌고 사이드바가 햄버거다.
  검사도 있다(`ui_mobile_check.mjs`)
- 메뉴 추가는 세 곳 — `router/index.js` · `App.vue:502-522` ·
  `lib/permission.js` 의 `ROUTE_PERMISSION`

---

## 9. 3단계를 막는 것 — 업종 칸

`clients` 에 업종 칸이 없다. `client_type` 은 법인/개인/기타뿐이다.
**이게 없으면 "음식점 3곳에 해당하는 개정" 이 성립하지 않는다.**

양쪽 조사가 같은 결론에 닿았다 — 여기가 3단계의 첫 번째 할 일이다.

채우는 사람이 결국 담당 직원이고 거래처가 99곳이다. 손으로 채우게 두면
안 채워진다. **드롭다운 + 엑셀 일괄 등록에 칸 추가**를 같이 해야 실제로 채워진다.

자유 입력으로 두면 안 된다 — "음식점" 과 "일반음식점" 이 다른 값이 되어
거를 수가 없다. `industry_code`(표준산업분류) + `industry_name` 으로 나눈다.

### 담당이 한 사람에게 몰려 있다

99곳 **전부 한 사람 담당**이다. 그러면 "김실장이 맡은 거래처 중 음식점" 이
아직 성립하지 않는다. 업종 채우기와 **담당 나누기가 같이 가야** 3단계가
값을 낸다.

---

## 10. 아직 값을 못 받은 것

신정 쪽에서 확인 못 한 것들. 1단계를 시작하기 전에 필요한 것은 ★ 표시.

- ★ **GitHub Actions 잔여 사용량** (Settings → Billing) — 0번 판단의 근거.
  계산으로는 1,644분을 쓰고 있는데 실측이 필요하다
- 카카오 채널 개설 여부 — 한참 뒤 일이라 급하지 않음

받은 값 (2차 회신):

    운영 DB   Supabase PostgreSQL · ap-south-1 · 14MB · public 표 30개
    재직 직원 3명 · 휴가 1 · 업무일지 1 · 지출·공지·도장 0 · 감사로그 4
    거래처 99건 (전부 한 사람 담당)

**아직 실사용 전이다.** 이 사실이 1절의 판단을 뒤집었다.
합쳐도 40MB 안쪽이라 Supabase 무료 한도(500MB)에 여유가 크다.
