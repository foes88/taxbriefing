# 이관 절차서 — 세무브리핑을 신정 결재시스템으로

이 문서 하나로 이관이 끝나야 한다. 빠진 것이 있으면 여기에 적는다.

한 줄 요약: **배치를 먼저 세우고, 뽑고, 넣고, 세어 보고, 주소를 바꾸고,
손으로 한 번 돌려 본다.** 세어 보기 전에는 끝났다고 말하지 않는다.

---

# 1. 지금 상태

| 단계 | 무엇 | 누가 | 상태 |
|---|---|---|---|
| 0 | 신정 로컬을 Postgres 로 | 신정 | **끝** |
| 1 | `CREATE SCHEMA tb` | 신정 | 로컬 끝 · **운영 아직** |
| 2 | `TAXBRIEFING_DB_SCHEMA=tb` 로 alembic | taxbriefing | 로컬 끝 · **운영 아직** |
| 3 | 데이터 이관 + 대조 | taxbriefing | 로컬 끝 · **운영 아직** |
| 4 | 배치 DB 주소 교체 | taxbriefing | 아직 |
| 5 | 읽는 라우터 + 화면 | 신정 | **지금 시작 가능** |
| 6 | 거래처 업종 칸 + 담당 나누기 | 신정 | 아직 |

로컬(`127.0.0.1:5434/shinjung`, 스키마 `tb`)은 원본과 **글자 단위로 같다.**

```
표                            원본   이관본
ai_analyses                    259    259   일치 같음
content_evidence              2133   2133   일치 같음
content_sources                427    427   일치 같음
content_versions               427    427   일치 같음
idempotency_records              5      5   일치 같음
raw_content_versions          1133   1133   일치 같음
raw_contents                  1025   1025   일치 같음
reviews                        427    427   일치 같음
source_runs                    213    213   일치 같음
sources                         23     23   일치 같음
tags                            23     23   일치 같음
tax_contents                   427    427   일치 같음
users                            2      2   일치 같음
audit_logs                       6      0   ★불일치 ← 씨앗에서 일부러 뺐다
```

로컬 `tb.users` 두 계정은 비밀번호 해시를 무효값(`DISABLED-SEED-NOT-A-HASH`)
으로 덮어 놨다. **그 계정으로는 로그인 못 한다.** 로컬에서 세무브리핑
관리자 화면을 열 일이 생기면 해시를 새로 넣어야 한다. 운영 덤프는 안 덮는다.

---

# 2. 옮기는 것은 세 덩어리다

```
  ① 데이터            ② 배치               ③ 웹
  Neon                GitHub Actions       Render API
    → Supabase tb     (그대로 둔다)         Vercel 화면 → 신정 화면
```

**② 배치는 옮기지 않는다.** taxbriefing 리포에 그대로 둔다. 이유는 돈이다 —
**공개 리포는 Actions 가 무료·무제한이고, 신정은 비공개라 월 2,000분으로
계량된다.** (현재 사용량 30분 / 2,000분) 배치를 신정으로 옮기면 매일
20~30분씩 그 한도를 갉아먹는다.

바뀌는 것은 **배치가 바라보는 DB 주소 하나뿐이다.**

**③ Vercel 화면은 당장 안 끈다.** 신정 화면이 자리 잡을 때까지 둘 다
같은 DB 를 본다. 신정 화면이 대체하면 그때 정리한다.

---

# 3. 지금 막고 있는 것

이것들이 오기 전에는 운영 이관을 시작할 수 없다.

## 3-1. Supabase 접속 문자열 — **두 개 다** 필요하다

지금 신정 `.env` 의 `DATABASE_URL` 은 로컬(`127.0.0.1:5434`)을 가리킨다.
운영 주소는 내게 없다.

```
:5432  직결(direct)     ← Alembic · pg_dump · psql 은 이쪽
:6543  풀러(pooler)     ← 앱 런타임(Render)은 이쪽
```

풀러로 Alembic 을 돌리면 준비된 구문(prepared statement)이 엉켜 중간에
깨진다. 그리고 **풀러는 접속 옵션의 `search_path` 를 버린다** — 그래서
`env.py` 안에서 `SET search_path` 를 직접 건다(아래 5-2).

## 3-2. 업종 칸 — 이관을 막지는 않지만 **합치는 이유**가 여기 있다

거래처에 `industry_code` 가 없으면 6단계(담당 나누기)가 성립하지 않는다.
세무브리핑을 신정에 넣는 이유가 "내가 맡은 사장님한테 필요한 것만" 인데,
거래처가 무슨 업종인지 모르면 그 말이 성립하지 않는다.

---

# 4. 배치와 수집 — 옮기기 전에 알아야 하는 전부

## 4-1. 언제 도나

| 워크플로 | cron (UTC) | 한국 시각 | 하는 일 |
|---|---|---|---|
| `daily.yml` 매일 브리핑 | `17 22 * * *` | 07:17 | 수집 → 초안 → 요약 → 분류 → 발송 |
| `keep-alive.yml` API 깨워두기 | `*/14 21-23,0-10 * * *` | 06:00~19:59 · 14분마다 | Render 절전 방지 |

**정각을 피해 17분에 둔 이유**: `0 22` 였을 때 8월 17일·20일 실행이 통째로
빠졌다. GitHub 예약은 보장이 아니라 여유 있을 때 돌려주는 것이고, 정각은
전 세계가 몰린다.

**그래도 밀린다.** 07:17 예약인데 실제로는 09:2x 에 돈다. 최근 실행 기록이
전부 그렇다. 이건 고칠 수 없는 것이고, 받아들이고 쓰는 것이다.
**"시간 맞춰 온다" 고 약속하지 않는다.**

`keep-alive` 를 하루 종일 안 돌리는 이유: Render 무료는 월 750 인스턴스시간
이라 24시간 깨워두면 730시간을 혼자 쓴다. 14시간 × 30일 = 420시간으로 맞췄다.

## 4-2. 하루 한 번 무엇이 도나 — 6단계

```
  1 수집        python -m app.collect --days 14 --limit 120
                   원문(raw_contents)까지만 만든다
  2 초안·게시    python -m app.bulk_draft --auto-approve
                   ★ 이게 없으면 사이트에 아무것도 안 올라간다
  3 요약        python -m app.summarize --limit 40 --pace 12
  4 업종 분류    python -m app.classify --limit 40 --pace 8
  5 미리보기     python -m app.notify --hours 26
  6 발송        python -m app.notify --hours 26 --send   (예약 실행일 때만)
```

**2단계가 빠져서 사흘 동안 아무것도 안 올라간 적이 있다.** 수집은 원문까지만
만들고, 사람이 보는 콘텐츠는 `bulk_draft` 가 만든다. 8월 18~19일 여섯 건이
원문으로만 남았고, 보낼 것이 없으니 발송은 조용히 끝났다 — **고장 난 것처럼
보이지도 않았다.**

`--auto-approve` 로 바로 게시한다. 매일 아침 승인할 사람이 없으면 아무것도
안 나간다. 대신 감사 기록에 "사람이 원문과 대조하지 않았습니다" 를 그대로
남긴다(`AUTO_REVIEW_NOTE`).

발송은 **예약 실행일 때만** 한다. 수동 실행은 `send` 를 명시적으로 켜야
나간다. 발송은 되돌릴 수 없다.

## 4-3. 실패를 어떻게 다루나

- 각 단계는 `continue-on-error: true` 다. 출처 하나가 죽어도 나머지는 돈다.
- **하지만 `continue-on-error` 는 실패를 감춘다.** 네 단계가 전부 exit 1
  이었는데 셋이 초록으로 보인 적이 있다. 그래서 「결과 정리」 단계가 각 단계
  결과를 요약에 적고, **수집과 발송이 둘 다 실패하면 실행 자체를 실패로
  만든다.** 일부 실패는 정상 운영이지만 전부 실패는 고장이다.
- 시크릿이 없으면 **실패가 아니라 건너뜀**이다. 준비 안 된 단계 때문에 매일
  실패 메일이 오면 진짜 실패를 놓친다.

## 4-4. 시크릿 — 이관 때 손대는 것은 딱 하나

| 이름 | 없으면 | 이관 때 |
|---|---|---|
| `TAXBRIEFING_DATABASE_URL` | 전부 멈춤 | **★ 이것만 바꾼다** |
| `TAXBRIEFING_DB_SCHEMA` | `public` | **★ `tb` 로 새로 추가** |
| `TAXBRIEFING_LAW_API_OC` | 법령 수집만 건너뜀 | 그대로 |
| `TAXBRIEFING_LAWMAKING_OC` | 입법예고 수집만 건너뜀 | 그대로 |
| `TAXBRIEFING_ASSEMBLY_API_KEY` | 법안 수집만 건너뜀 | 그대로 |
| `TAXBRIEFING_AI_API_KEY` | 요약·분류만 건너뜀 | 그대로 |
| `TAXBRIEFING_NAVER_CLIENT_ID` / `_SECRET` | 뉴스 수집만 건너뜀 | 그대로 |
| `TAXBRIEFING_TELEGRAM_BOT_TOKEN` / `_CHAT_ID` | 발송만 건너뜀 | 그대로 |

`TAXBRIEFING_DATABASE_URL` 은 **드라이버 접두어를 포함한다**:
`postgresql+psycopg://...` — `postgresql://` 로 넣으면 앱이 안 뜬다.
(반면 `pg_dump`·`psql` 은 접두어 없는 `postgresql://` 을 받는다.)

## 4-5. 출처 23개 — 지금 실제로 도는 것은 7개다

**ACTIVE — 매일 돈다**

| 출처 | 종류 | 최근 성공 |
|---|---|---|
| 조세심판원 (`law.go.kr/조세심판원`) | API | 09-10 |
| 국민참여입법센터 입법예고 (`lawmaking.go.kr`) | API | 09-10 |
| 국회 의안정보 (`open.assembly.go.kr`) | API | 09-10 |
| 국세청·기재부 법령해석 (`law.go.kr/법령해석`) | API | 09-10 (부분) |

**`PENDING_REVIEW` 인데 실제로 도는 것** — 국가법령정보센터(`law.go.kr`),
국세신문(`intn.co.kr`), 세정일보(`sejungilbo.com`). 상태 칸과 실제가
어긋나 있다. 상태를 보고 판단하면 틀린다.

**DISABLED** — 네이버 뉴스(`openapi.naver.com`), 연속실패 4.

나머지 13개(국세청·재정경제부·위택스·소상공인24·건보·연금·근로복지공단·
기업마당·전자관보·정책브리핑·고용노동부·국세법령정보시스템·4대사회보험)는
`PENDING_REVIEW` 로 등록만 돼 있고 **한 번도 안 돌았다.** 어댑터가 없다.
늘리려면 `app/collect.py` 의 `ADAPTERS` 에 추가하거나 RSS 주소를
`sources.settings.feed_url` 에 넣는다.

**크롤링 차단은 우회하지 않는다.** robots.txt·CAPTCHA·로그인·IP 우회 전부
안 한다. 수집기는 `TaxBriefing/1.0 (+tax briefing aggregator)` 로 정직하게
밝힌다. 막힌 출처는 막힌 채로 두고 그 사실을 적는다.

## 4-6. 지금 살아 있는 문제 두 개

**① 법령해석 `failure_streak` 6** — 겁먹을 것 없다. 114건 중 1건
(`ntsCgmExpc:법인세`)에서 SSL 핸드셰이크 시간초과가 났고 나머지는 들어왔다.
상태는 `PARTIAL` 인데 연속실패로 세어져 6이 됐다. **부분 실패를 완전 실패로
세고 있다** — 이관과는 무관하지만 언젠가 고칠 것.

**② 예약인지 손인지 기록에 안 남았다** — `source_runs` 213건이 전부 `MANUAL`
이다. 워크플로가 `--run-type` 을 안 넘겨서 CLI 기본값이 그대로 들어갔다.
예약이 밀린 건지 아예 안 돈 건지 DB 만 봐서는 알 수 없었다.
**이번에 고쳤다** — 예약 실행은 `SCHEDULED` 로 기록된다. 이관 후 5-7 에서
이걸로 확인한다.

---

# 5. 운영 이관 순서

## 5-0. 배치를 세운다 — **이걸 안 하면 데이터가 샌다**

뽑는 동안 배치가 돌면 그 사이에 들어온 행은 **원본에만 남고 이관본에는
없다.** 주소를 바꾸는 순간 그 행들은 아무도 안 보는 곳에 남는다.

```
GitHub → Actions → 매일 브리핑  → ⋯ → Disable workflow
GitHub → Actions → API 깨워두기 → ⋯ → Disable workflow
```

세워 둔 것을 **눈으로 확인한다.** "예약된 것이 없겠지" 로 넘어가지 않는다.

## 5-1. `tb` 스키마와 표를 만든다

```
psql "postgresql://<Supabase 직결>" -c "create schema if not exists tb;"

cd backend
set TAXBRIEFING_DB_SCHEMA=tb
set TAXBRIEFING_DATABASE_URL=postgresql+psycopg://<Supabase 직결>
alembic upgrade head
```

확인 — `public` 으로 새지 않았는지 본다.

```sql
select table_schema, count(*)
  from information_schema.tables
 where table_schema in ('tb','public') and table_type='BASE TABLE'
 group by 1;
-- tb 28 + alembic_version · public 은 신정 것 그대로(30)
```

`public` 이 30보다 커졌으면 **거기서 멈춘다.** 신정 표 사이에 우리 표가
섞인 것이다.

## 5-2. 왜 `env.py` 가 `search_path` 를 직접 거는가 — **여기서 한 번 틀렸다**

내가 처음에 "`TAXBRIEFING_DB_SCHEMA` 를 켜면 표 28개가 통째로 `tb` 로 간다"
고 확인했다고 적었다. **모델(`Base.metadata`)만 보고 한 말이었다.**

표를 실제로 만드는 것은 마이그레이션 파일이고, 거기엔
`op.create_table("audit_logs", ...)` 처럼 **스키마가 안 적혀 있다.** 그래서
`DB_SCHEMA` 를 켜도 표는 `search_path` 대로 `public` 에 만들어졌고, 신정의
같은 이름 표(`audit_logs`)와 부딪혀 멈췄다.

지금 `alembic/env.py` 는 접속 직후에 이렇게 한다.

```python
if DB_SCHEMA:
    connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"')
    connection.exec_driver_sql(f'SET search_path TO "{DB_SCHEMA}", public')
    connection.commit()
```

세 가지가 다 이유가 있다.

- **접속 문자열의 `options=-csearch_path=` 로는 안 된다.** Supabase 풀러가
  그 시작 옵션을 버린다.
- **`, public` 을 뒤에 붙인다.** 표는 맨 앞(`tb`)에 만들어지고, 이미 있는
  타입·확장 함수(`gen_random_uuid` 등)는 뒤에서 찾는다. `tb` 만 두면 그것들을
  못 찾아 멈춘다.
- **`connection.commit()` 이 있어야 한다.** SQLAlchemy 2.0 은 첫 실행에서
  트랜잭션을 연다. 안 닫으면 alembic 이 그 위에서 돌고 커넥션이 닫힐 때
  통째로 롤백된다 — **alembic 은 exit 0 을 내는데 표는 하나도 안 생긴다.**

## 5-3. 원문을 뽑는다 — 배치를 세운 **뒤에**

```
pg_dump --dbname="postgresql://<Neon>" --data-only --no-owner --no-privileges \
        --disable-triggers --file=cutover.sql
```

`--disable-triggers` 가 필요한 이유: `tags` 에 자기참조가 있어 행 순서를
맞출 수 없다. 넣을 때도 superuser 로 넣는다.

**빼는 표는 없다.** 씨앗과 달리 `audit_logs` 도 넣는다.

그다음 `public.` 을 `tb.` 로 바꾼다. **문장 줄만 바꾼다** — COPY 블록 안의
값에 "public." 이라는 글자가 있을 수 있고, 통째로 치환하면 본문을 조용히
고쳐 놓게 된다. 바꿀 줄머리는 셋뿐이다.

```
COPY public.                        → COPY tb.
ALTER TABLE public.                 → ALTER TABLE tb.
SELECT pg_catalog.setval('public.   → SELECT pg_catalog.setval('tb.
```

로컬 씨앗을 만들 때 쓴 방식 그대로다. `.local/seed_tb.sql` 이 그 결과물이고,
바꾸는 코드는 그 파일을 만든 스크립트에 남아 있다.

## 5-4. 넣는다

```
psql "postgresql://<Supabase 직결>" -v ON_ERROR_STOP=1 -f cutover.sql
```

`ON_ERROR_STOP=1` 없이 돌리면 중간에 실패한 COPY 를 건너뛰고 끝까지 가서
**성공한 것처럼 끝난다.**

## 5-5. 센다 — 여기가 끝인지 아닌지를 정하는 자리

```
python -m app.verify_migration <원본URL파일> <이관본URL파일> public tb
```

URL 은 **파일 경로로 넘긴다.** 명령줄에 적으면 셸 기록과 프로세스 목록에
비밀번호가 남는다.

건수뿐 아니라 기본키를 정렬해 md5 로 묶은 지문까지 본다. **건수만 맞춰 보면
「같은 수의 다른 데이터」를 못 잡는다.** 어긋난 표가 하나라도 있으면
**종료코드 1** 이다. 0 이 아니면 다음으로 가지 않는다.

기본키 없는 표는 순서를 정할 수 없어 지문을 건너뛴다. 그 사실을
「(기본키 없음)」으로 적는다 — 조용히 통과시키지 않는다.

## 5-6. 주소를 바꾼다

| 어디 | 이름 | 값 |
|---|---|---|
| GitHub Actions 시크릿 | `TAXBRIEFING_DATABASE_URL` | `postgresql+psycopg://<Supabase **직결**>` |
| GitHub Actions 시크릿 | `TAXBRIEFING_DB_SCHEMA` | `tb` |
| Render 환경변수 | `TAXBRIEFING_DATABASE_URL` | `postgresql+psycopg://<Supabase **풀러**>` |
| Render 환경변수 | `TAXBRIEFING_DB_SCHEMA` | `tb` |

Render 는 저장하면 다시 뜬다. 뜨고 나서 확인한다.

```
curl "https://taxbriefing-api.onrender.com/api/v1/public/feed?limit=1"
```

`total` 이 이관 건수와 같은지 본다. **`limit` 이다 — `size` 를 보내면
FastAPI 가 조용히 무시하고 기본값 20건을 준다.**

## 5-7. 배치를 다시 켠다 — **한 번은 손으로**

```
GitHub → Actions → 매일 브리핑  → Enable → Run workflow (days=14, send=false)
GitHub → Actions → API 깨워두기 → Enable
```

예약이 돌아오기를 기다리지 않는다. **예약은 밀린다** (07:17 이 09:2x 에
뜬다). 손으로 한 번 돌려 Supabase 에 쓰는 것을 눈으로 본다.

`send=false` 로 돌린다 — 발송은 되돌릴 수 없다. 미리보기까지만 보고,
내용이 멀쩡하면 다음 날 예약 발송에 맡긴다.

돌고 나서 다시 센다. **늘어난 만큼만 늘었는지** 본다.

```
python -m app.verify_migration <원본> <이관본> public tb
```

그리고 예약이 정말 돌았는지는 이걸로 본다.

```sql
select run_type, count(*), max(started_at at time zone 'Asia/Seoul')
  from tb.source_runs group by 1;
-- 이관 후 예약 실행이면 SCHEDULED 가 찍힌다
```

## 5-8. Neon 은 바로 지우지 않는다

2주는 그대로 둔다. 쓰지 않을 뿐이다. 무료 티어라 돈이 안 든다. 지우는 건
되돌릴 수 없고, 되돌릴 수 없는 일을 급하게 할 이유가 없다.

---

# 6. 되돌리기

| 어디까지 갔나 | 되돌리는 법 |
|---|---|
| 5-1 까지 | `drop schema tb cascade;` — 신정 `public` 은 안 건드린다 |
| 5-4 까지 | 위와 같다. 원본 Neon 은 그대로다 |
| 5-6 까지 | 주소를 Neon 으로 되돌린다. 그 사이 쓰인 것이 있으면 그것만 옮긴다 |
| 5-7 이후 | Supabase 가 원본이다. 되돌리려면 반대 방향으로 같은 절차 |

**5-6 전까지는 언제든 그냥 멈추면 된다.** 원본이 안 바뀌기 때문이다.

---

# 7. 이관해도 안 바뀌는 것

신정 쪽에서 "이것도 옮겨야 하나" 하고 물을 만한 것들이다. 안 옮긴다.

| | 그대로 두는 이유 |
|---|---|
| GitHub Actions 배치 | 공개 리포라 무료·무제한. 신정은 비공개라 월 2,000분 계량 |
| 수집기 코드 | 세무브리핑 리포에 산다. 신정은 `pip install git+…` 로 가져다 쓴다 |
| 텔레그램 발송 | 챗봇·채팅방 그대로. DB 주소만 바뀐다 |
| GROQ 키 · 법제처 OC · 국회 키 | 전부 그대로 |
| Vercel 화면 | 신정 화면이 자리 잡을 때까지 둘 다 같은 DB 를 본다 |
| Render API | 주소만 바뀐다. 신정 화면도 이 API 를 부른다 |

---

# 8. 이관 후 신정이 해야 하는 것 (5·6단계)

## 8-1. 읽는 라우터 하나

세무브리핑 API 를 그대로 부르거나, `tb` 스키마를 직접 읽는 라우터를 만든다.
어느 쪽이든 **모델 정의는 한 곳에만 둔다.** 양쪽에 두면 언젠가 갈라지고,
갈라지면 한쪽이 조용히 틀린 값을 읽는다.

```
pip install git+https://github.com/foes88/taxbriefing@main#subdirectory=backend
```

## 8-2. 화면 — 오늘 · 찾기 부터

화면이 지켜야 하는 것은 `REFERENCE-FOR-SHINJUNG.md` 에 있다.
**서버가 막아주지 못하는 것**만 여기 다시 적는다.

- `body._ai` 가 true 면 AI 가 쓴 요약이다(124건). **「검수 필요」를 표시한다.**
- POLICY 11건은 `changes`·`required_actions` 가 전부 비어 있다.
  **빈 섹션을 그리지 말고 숨긴다.**
- 시행일 없는 것이 303건. **"미정" 이라 쓰지 말고 비워 둔다.**
- 업종 없는 것이 21건. **"전체" 로 보이게 하지 않는다.**
- `one_line_summary` 가 null 일 수 있다. **제목만 보여준다.**
- `body` 모양이 종류마다 다르다. 없는 키를 빈 배열로 가정하고 섹션을 그리면
  심판례 상세가 텅 빈다.

서버가 이미 정해서 주는 것 — 화면이 못 깬다. **다시 거르지 않는다.**

- `status_label` · `status_caveat` 는 심판례·해석례·판례에 `null` 로 온다
- `risk_level` 은 법안·입법예고·해석례·판례·심판례에 `LOW` 로 온다
- 총계는 응답의 `total` 이다

## 8-3. 거래처 업종 칸

`industry_code` · `industry_name` 을 거래처에 넣고, 세무브리핑의
`industries` 와 맞춘다. **이것이 합치는 진짜 이유다.**

---

# 9. 이 문서가 있는 이유

로컬 이관은 아무도 절차를 안 적고 했다. 끝나고 세어 보니 `audit_logs` 6건이
빠져 있었다. **세어 보지 않았으면 몰랐다.** 로컬이라 아무 일도 아니었지만,
운영에서 같은 일이 나면 감사 기록이 말없이 사라진다.

그리고 나는 "표 28개가 통째로 `tb` 로 간다"고 확인했다고 적었는데, 확인한
것은 모델이었고 표를 만드는 것은 마이그레이션 파일이었다. **틀린 것을
확인했다고 적으면, 다음 사람이 그걸 믿고 안 본다.**
