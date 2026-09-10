# 1단계 — 백엔드를 신정으로 합치기 (실행 계획)

신정 쪽 조사 답변(`docs/ASK-SHINJUNG.md` 에 대한 회신)을 받고 정한 것.
화면은 안 건드린다. 자료와 배치만 옮긴다. **되돌리려면 접속 문자열만 되돌린다.**

---

## 0. 먼저 — 막는 것이 하나 있다

**GitHub Actions 무료분이 모자란다.**

    신정 keep-awake   평일 07~19시 10분마다 = 하루 72회 × 22일 = 1,584분/월
    신정 db-backup    매일 1회 × 2분              =    60분/월
    ─────────────────────────────────────────────────────────
    지금 쓰는 것                                  = 1,644분/월
    무료 한도                                     = 2,000분/월
    남는 것                                       =   356분/월

taxbriefing 아침 배치는 하루 20~30분이다. 월 600~900분. **356분에 안 들어간다.**

### 해법 — Render 백엔드를 유료로 ($7/월)

keep-awake 는 무료 플랜이 15분 놀면 잠들기 때문에 도는 것이다. 유료로 올리면
**그 워크플로가 통째로 필요 없어진다.**

    1,584분 확보  →  taxbriefing 배치 900분을 넣고도 1,000분 넘게 남는다

덤으로 아침 첫 접속 1분 대기가 사라진다. 지금도 매일 겪고 있는 것이다.

**다른 길**

- `--pace` 를 줄인다 — summarize 12초 × 40건 = 8분, classify 8초 × 40건 = 5분.
  **하루 13분을 자는 데 쓰고 그 시간에 과금된다.** 다만 GROQ 분당 한도(TPM 8,000)
  때문에 둔 것이라 줄이면 429 가 늘고, 재시도 대기도 결국 시간이다. 아껴야
  월 400분이고 그것만으로는 모자란다.
- keep-awake 간격을 10분 → 15분 — 528분 절약. 이것도 모자라고, 잠드는 위험만
  커진다.

**유료 전환이 유일하게 깔끔하다.** 1단계를 시작하기 전에 정해야 한다.

---

## 1. 표를 어떻게 넣나 — 별도 Base + `tb_` 접두어

### 왜 스키마가 아니라 접두어인가

스키마(`taxbriefing.*`)가 깔끔해 보이지만 **신정 로컬은 SQLite 다.**
SQLite 는 스키마를 지원하지 않는다. 스키마로 가르면 로컬에서 개발이 안 된다.

접두어는 양쪽에서 다 돈다.

    tax_contents      →  tb_tax_contents
    raw_contents      →  tb_raw_contents
    attachments       →  tb_attachments     ← 신정 것과 충돌하던 것
    audit_logs        →  tb_audit_logs      ← 신정 것과 충돌하던 것
    ...  29개 전부

### create_all 충돌은 Base 를 갈라서 막는다

신정은 기동할 때마다 `init_db()` 가 돈다(`main.py:167`).

    Base.metadata.create_all()      database.py:1058
    _run_migrations()               database.py:825~   손으로 쓴 ALTER TABLE

여기서 Alembic 이 관리하는 표를 SQLAlchemy 가 먼저 만들어 버리면 리비전과 실제
스키마가 어긋나고 그다음 `upgrade` 가 깨진다.

**taxbriefing 모델은 자기 Base 를 쓴다.** 신정 `Base.metadata` 에 안 들어가므로
`create_all()` 대상이 아니다. taxbriefing 표는 Alembic 이 만들고, 신정 표는
지금 방식 그대로 둔다. 서로 안 만난다.

    신정 Base       → create_all + _run_migrations   (그대로)
    taxbriefing Base → Alembic                        (그대로)

두 방식이 한 DB 에 있지만 **각자 자기 표만 건드린다.**

### 버리는 표

- `users` (2건) — 신정 `employees` 로 대체
- `tenants` (0건) — 다중 사무소를 염두에 둔 것. 신정 한 곳만 쓰면 필요 없다

`corrections`(정정 이력)· `deliveries`(발송 기록)는 **비어 있어도 가져간다.**
아직 안 쓰였을 뿐 설계상 있어야 할 자리다.

---

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
3. 표 이름에 `tb_` 를 붙여 복원 (덤프 뒤 `pg_restore --list` 로 이름을 바꾸거나,
   빈 스키마에 Alembic 으로 표를 만들고 데이터만 `COPY`)
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

## 4. 배치 — 자리는 이미 있다

신정도 GitHub Actions 를 쓴다(`db-backup.yml`, `keep-awake.yml`). taxbriefing
`daily.yml` 을 그대로 옮기고 시크릿 7개를 신정 저장소에 넣는다.

    TAXBRIEFING_LAW_API_OC / ASSEMBLY_API_KEY / LAWMAKING_OC
    TAXBRIEFING_NAVER_CLIENT_ID / SECRET
    TAXBRIEFING_AI_API_KEY
    TAXBRIEFING_TELEGRAM_BOT_TOKEN / CHAT_ID

`TAXBRIEFING_DATABASE_URL` 은 신정 `DATABASE_URL` 과 같은 값이 되므로 하나로
합친다.

**keep-awake 는 지운다** (Render 유료 전환 뒤). 그게 이 단계의 예산을 만든다.

---

## 5. 코드를 어디에 두나

신정 `main.py` 는 3,000줄이고 라우터 분리가 안 돼 있다. 그쪽 조언대로 **거기
붙이지 않는다.**

    backend/taxbriefing/          taxbriefing app/ 을 통째로
    backend/routers_taxbriefing.py   공개 API 7개 + 관리자
    backend/alembic/                 taxbriefing 표만 관리

`main.py` 에는 `include_router` 한 줄만 늘린다.

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
| 0 | Render 백엔드 유료 전환 · keep-awake 삭제 | 플랜 되돌리고 워크플로 복구 |
| 1 | 코드를 `backend/taxbriefing/` 로 옮기고 라우터 하나 붙임 | 커밋 되돌리기 |
| 2 | 표 이름에 `tb_` 접두어, 별도 Base, Alembic 분리 | 아직 운영에 안 씀 |
| 3 | 배치 멈춤 확인 → 덤프 → Supabase 복원 → 대조 | 옛 DB 그대로 있음 |
| 4 | 접속 문자열 교체 (Render · GitHub Secrets · 로컬) | **문자열만 되돌림** |
| 5 | 배치를 신정 저장소에서 돌림 | 워크플로 끄기 |
| 6 | 일주일 지켜보고 옛 DB 정리 | — |

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

채우는 사람이 결국 담당 직원이고 거래처가 100곳쯤 된다. 손으로 채우게 두면
안 채워진다. **드롭다운(표준산업분류 또는 taxbriefing 업종 12개) + 엑셀 일괄
등록에 칸 추가**를 같이 해야 실제로 채워진다.

---

## 10. 아직 값을 못 받은 것

신정 쪽에서 확인 못 한 것들. 1단계를 시작하기 전에 필요한 것은 ★ 표시.

- ★ **GitHub Actions 잔여 사용량** (Settings → Billing) — 0번 판단의 근거
- 운영 표별 행 수 (Supabase 대시보드 SQL 편집기)
- 거래처 건수 (거래처 화면 상단 "전체 N건")
- 카카오 채널 개설 여부 — 5단계 이후라 급하지 않음
- 하루 접속량 — 급하지 않음
