# DB를 가까운 리전으로 옮기기

## 왜

측정값이다.

```
select 1  →  393ms
```

DB가 미국 오하이오(Neon `us-east-2`)에 있고 화면을 여는 사람은 한국에 있다.
**왕복 한 번이 393ms다.** 쿼리를 몇 번 던지느냐가 그대로 초 단위로 화면에
나온다.

목록 화면을 다섯 번 왕복에서 한 번으로 줄이고(2.0초 → 0.40초), 응답을 2분
들고 있게 해서(0.40초 → 0.003초) 여기까지 왔다. 그런데 **캐시가 안 먹는
경우는 그대로다** — 아침 배치, 관리자 화면, 캐시가 식은 뒤 첫 방문.

393ms는 코드로 못 줄인다. 거리를 줄여야 한다.

## 먼저 확인한 것

옮기기 전에 덤프·복원이 온전한지 로컬에서 연습했다. 결과:

| | |
|---|---|
| 크기 | 25 MB (덤프 2.2 MB) |
| 표 | 29개 |
| 인덱스 51 · FK 50 | 원본과 복원본 동일 |
| 확장 | `pg_trgm`, `plpgsql` |
| 덤프 시간 | 31초 |
| 복원 시간 | 1.2초 |

`raw_contents`·`reviews`·`sources`는 값 지문(md5)까지 **완전 일치**했다.

## 여기서 한 번 걸렸다

행 수를 대조했더니 `ai_analyses`가 하나 어긋났다. 20초 뒤 다시 세니 또
하나 늘어 있었다.

```
지금 원본 ai_analyses: 209
20초 뒤       ai_analyses: 210
```

**요약 배치가 돌고 있었다.** 데이터가 깨진 게 아니라 과녁이 움직이고
있었던 것이다.

> **쓰는 작업이 하나라도 돌고 있으면 덤프를 뜨지 않는다.**
> 어긋난 행이 나와도 그게 손실인지 그 사이에 들어온 것인지 구분할 수 없다.

같은 이유로 `tax_contents`·`content_versions`의 값 지문도 달랐다. 배치가
바로 그 두 표를 고쳐 쓰는 중이었다.

## 절차

### 0. 쓰는 것을 전부 멈춘다

- GitHub Actions `매일 브리핑` 이 도는 시간(07:17 KST)을 피한다
- 로컬에서 `app.collect` / `app.summarize` / `app.classify` / `app.bulk_draft` 를
  돌리고 있지 않은지 확인한다
- 관리자 화면에서 승인·정정하지 않는다

멈춘 것을 **눈으로 확인**한다. 20초 간격으로 두 번 세서 같은지 본다.

```bash
psql -d "$SRC" -Atc "select count(*) from ai_analyses;"
sleep 20
psql -d "$SRC" -Atc "select count(*) from ai_analyses;"
```

### 1. Neon 콘솔에서 새 프로젝트를 만든다

리전은 **한국에서 가장 가까운 것**을 고른다. Neon 콘솔의 리전 목록에서
아시아 쪽(싱가포르 등)을 확인한다.

같은 프로젝트 안에서는 리전을 못 바꾼다. 새 프로젝트를 만들어야 한다.

만들고 나면 접속 문자열을 받는다. 그 값으로 **왕복을 먼저 재 본다.**

```bash
psql -d "$NEW" -Atc "select 1;"   # time 으로 감싸서 잰다
```

**여기서 393ms보다 크게 안 줄면 옮길 이유가 없다.** 옮기기 전에 잰다.

### 2. 덤프

```bash
export PATH="/c/Program Files/PostgreSQL/16/bin:$PATH"
pg_dump -d "$SRC" --no-owner --no-privileges --format=custom -f taxbriefing.dump
```

`--no-owner --no-privileges` 를 붙인다. Neon은 프로젝트마다 역할 이름이
달라서, 안 붙이면 복원할 때 없는 역할을 찾다 멈춘다.

### 3. 복원

```bash
psql -d "$NEW" -Atc "create extension if not exists pg_trgm;"
pg_restore -d "$NEW" --no-owner --no-privileges taxbriefing.dump
```

확장은 먼저 만든다. 덤프에 `CREATE EXTENSION` 이 들어 있어도 권한 문제로
건너뛰는 일이 있고, 그러면 인덱스를 만들다 멈춘다.

### 4. 대조 — 세고, 지문을 찍는다

행 수만 보지 않는다. **값까지 본다.**

```bash
psql -d "$SRC" -Atf docs/sql/verify_counts.sql > src.txt
psql -d "$NEW" -Atf docs/sql/verify_counts.sql > new.txt
diff src.txt new.txt        # 한 줄도 달라선 안 된다

psql -d "$SRC" -Atf docs/sql/verify_checksums.sql | sort > src_sum.txt
psql -d "$NEW" -Atf docs/sql/verify_checksums.sql | sort > new_sum.txt
diff src_sum.txt new_sum.txt
```

인덱스와 FK 개수도 본다.

```bash
psql -d "$U" -Atc "select count(*) from pg_indexes where schemaname='public';"
psql -d "$U" -Atc "select count(*) from information_schema.table_constraints
                   where constraint_type='FOREIGN KEY' and table_schema='public';"
```

### 5. 바꿔 끼운다 — 네 군데

한 군데라도 빠뜨리면 **일부는 새 DB, 일부는 옛 DB를 보게 된다.** 그 상태가
제일 나쁘다. 화면에는 새 것이 안 보이는데 배치는 옛 것에 계속 쓴다.

| 어디 | 무엇 |
|---|---|
| Render | `TAXBRIEFING_DATABASE_URL` (백엔드 API) |
| GitHub Secrets | `TAXBRIEFING_DATABASE_URL` (매일 브리핑) |
| 로컬 `backend/.env` | `TAXBRIEFING_DATABASE_URL` |
| Vercel | DB를 직접 안 본다 — 확인만 하고 넘어간다 |

접두어를 잊지 않는다: `postgresql+psycopg://`

### 6. 확인

```bash
curl -s -o /dev/null -w "%{time_total}s\n" \
  "https://<render>/api/v1/public/feed?limit=1"
```

`X-Cache: MISS` 인 응답으로 잰다. HIT는 DB를 안 본다.

### 7. 옛 DB는 일주일 둔다

바로 지우지 않는다. 뭔가 어긋나 있으면 그때야 알게 되고, 그때 돌아갈
곳이 있어야 한다.

## 되돌리기

접속 문자열 네 군데를 옛 값으로 되돌린다. 그게 전부다 — 옛 DB는 그대로
있고, 새 DB에 쓴 것만 잃는다. 그래서 옮긴 직후에는 배치를 한 번 돌려
보고 이상이 없는지부터 본다.
