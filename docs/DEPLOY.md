# 배포 가이드 (무료 구성)

> 관련: [ADR-004 배포 분리](DECISIONS.md)

```
Vercel (웹)  ──HTTPS──▶  Render (API)  ──▶  Neon (PostgreSQL)
   무료                    무료                무료
```

셋 다 **카드 없이** 시작할 수 있다.

| | 서비스 | 무료 조건 |
| --- | --- | --- |
| 웹 | Vercel | Hobby 플랜. 개인 프로젝트 무료 |
| API | Render | 월 750 인스턴스시간. 15분 무요청 시 절전 |
| DB | Neon | 영구 무료 티어. 저장 용량·컴퓨트 제한 있음 |

> **Render 무료의 절전이 유일한 실질 제약이다.** 15분간 요청이 없으면 잠들고,
> 다음 요청에서 깨어나는 데 30~60초가 걸린다. 아침에 첫 방문자가 기다리게 된다.
> 아래 keep-alive 워크플로로 해결한다.
>
> Render 무료 Postgres 는 **90일 후 만료**된다. 그래서 DB 는 Neon 을 쓴다.

---

## 1. Neon — 데이터베이스

1. https://neon.tech 가입 → 프로젝트 생성 (리전은 `Asia Pacific (Singapore)`)
2. 대시보드에서 **Connection string** 복사
3. **접두어를 바꾼다.** Neon 은 `postgresql://` 을 주는데 이 프로젝트는 psycopg 드라이버를 쓴다.

```
받은 값 : postgresql://user:pw@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
넣을 값 : postgresql+psycopg://user:pw@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
                      ^^^^^^^ 이 부분을 추가
```

접두어를 빠뜨리면 기동 시 드라이버를 찾지 못해 실패한다.

---

## 2. Render — API

1. https://render.com 가입
2. **New → Blueprint** → 이 저장소 선택 → `render.yaml` 자동 인식
3. 아래 값을 입력한다.

| 환경변수 | 값 |
| --- | --- |
| `TAXBRIEFING_DATABASE_URL` | 위에서 만든 Neon 문자열 (`postgresql+psycopg://…`) |
| `TAXBRIEFING_CORS_ORIGINS` | `https://taxbriefing.vercel.app` |
| `TAXBRIEFING_LAW_API_OC` | `taxbriefing` |
| `TAXBRIEFING_SEED_ADMIN_PASSWORD` | 관리자 비밀번호 (기본값 금지) |

`TAXBRIEFING_JWT_SECRET` 은 Render 가 자동 생성한다.

4. 첫 배포에서 **`RUN_SEED` 를 `1`** 로 바꿔 출처·태그·관리자 계정을 만든다.
   배포가 끝나면 **다시 `0`** 으로 되돌린다.

5. 배포된 주소를 확인한다 — `https://taxbriefing-api.onrender.com`

```bash
curl https://taxbriefing-api.onrender.com/health
# {"status":"ok","environment":"production"}
```

### CORS 를 잊지 말 것

`TAXBRIEFING_CORS_ORIGINS` 에 Vercel 주소가 없으면 웹에서 API 호출이 브라우저에 막힌다.
증상은 "정보를 불러오지 못했습니다" 이고, 서버 로그에는 아무것도 남지 않는다.

여러 주소를 쓸 때는 쉼표로 나열한다. 와일드카드(`*`)는 쓰지 않는다.

```
https://taxbriefing.vercel.app,https://taxbriefing-git-main-foes88.vercel.app
```

---

## 3. Vercel — 웹

웹 앱은 **저장소 루트**에 있으므로 Root Directory 설정이 필요 없다.

**Settings → Environment Variables**

| 이름 | 값 |
| --- | --- |
| `SITE_PASSWORD` | 사이트 접근 비밀번호 |
| `NEXT_PUBLIC_API_BASE` | `https://taxbriefing-api.onrender.com/api/v1` |

> `SITE_PASSWORD` 를 넣지 않으면 운영에서 사이트가 열리지 않는다.
> 설정을 깜빡했을 때 아무나 들어오는 것보다 낫다고 판단해 그렇게 만들었다.

`NEXT_PUBLIC_` 접두어가 붙은 값은 **브라우저에 노출된다.** API 주소는 공개돼도 되지만,
비밀은 절대 이 접두어로 넣지 않는다.

환경변수를 바꾸면 **재배포해야** 반영된다.

---

## 4. 자동화 — GitHub Actions

`.github/workflows/` 에 세 개가 있다. 저장소 **Settings → Secrets and variables → Actions** 에 등록한다.

| Secret | 용도 |
| --- | --- |
| `API_BASE_URL` | `https://taxbriefing-api.onrender.com` |
| `API_ADMIN_ID` | 관리자 아이디 |
| `API_ADMIN_PASSWORD` | 관리자 비밀번호 |

| 워크플로 | 주기 | 하는 일 |
| --- | --- | --- |
| `keep-alive.yml` | 10분 | `/health` 호출로 절전 방지 |
| `collect.yml` | 평일 09·13·17시(KST) | 법령 원문 수집 |

수집은 API 를 통해 트리거하지 않고 Render 의 **Cron Job** 으로 돌리는 편이 낫지만,
무료 티어에는 Cron Job 이 없다. 그래서 GitHub Actions 에서 호출한다.

---

## 순서 요약

```
1. Neon 프로젝트 생성 → 접속 문자열 (postgresql+psycopg:// 로 수정)
2. Render Blueprint 배포 → 환경변수 입력 → RUN_SEED=1 로 1회 → 0 으로 복귀
3. Render 주소 확인 (/health 200)
4. Vercel 환경변수에 SITE_PASSWORD, NEXT_PUBLIC_API_BASE 입력 → 재배포
5. Render 의 TAXBRIEFING_CORS_ORIGINS 에 Vercel 주소 입력 → 재배포
6. GitHub Secrets 등록
```

4번과 5번은 서로를 참조하므로 **양쪽 주소가 다 나온 뒤에** 채워야 한다.

---

## 흔한 실패

| 증상 | 원인 |
| --- | --- |
| Vercel `Deployment Blocked` — 커밋 이메일을 GitHub 계정과 매칭할 수 없음 | 아래 참조 |
| Vercel 404 `DEPLOYMENT_NOT_FOUND` | 빌드 실패 또는 배포 차단으로 배포본이 없음 |
| 사이트는 뜨는데 "정보를 불러오지 못했습니다" | `NEXT_PUBLIC_API_BASE` 미설정 또는 CORS 누락 |
| 환경변수를 넣었는데 반영이 안 됨 | 아래 참조 |
| 첫 요청이 1분 걸림 | Render 무료 절전. keep-alive 워크플로 확인 |
| API 기동 실패 `could not load driver` | DB URL 에 `+psycopg` 누락 |
| API 기동 실패 `JWT_SECRET must be at least 32 bytes` | 운영에서 짧은 비밀키 사용 |
| 관리자 로그인 실패 | `RUN_SEED=1` 로 1회 배포했는지 확인 |

### 환경변수를 넣었는데 반영되지 않을 때

두 가지를 순서대로 확인한다.

**1. Environments 범위**

변수 추가 화면의 체크박스에서 **Production** 이 빠지면 실서비스에는 들어가지 않는다.
Preview 에만 걸려 있으면 미리보기 URL 에서만 동작한다.

**2. 재배포**

Vercel 환경변수는 **이미 돌아가는 배포에 소급 적용되지 않는다.** 새 배포부터 적용된다.
`Deployments → 맨 위 항목 ⋯ → Redeploy` 또는 커밋을 하나 더 올린다.

증상으로 구분하는 법:

```
GET /            → 307 → /gate?reason=unset    변수를 못 봄
POST /api/gate   → 503                          변수를 못 봄

GET /            → 307 → /gate                  정상
POST /api/gate   → 401 (틀린 비밀번호)          정상
```

`/gate` 에 직접 들어가 입력 화면이 보이는 것은 판단 근거가 되지 않는다.
경고 문구는 `?reason=unset` 이 붙었을 때만 나오기 때문이다.

### 커밋 이메일이 GitHub 계정과 매칭되지 않을 때

Vercel 은 배포하려는 커밋의 작성자 이메일이 GitHub 계정에 등록돼 있는지 확인한다.
등록되지 않은 주소로 커밋하면 빌드조차 시작하지 않고 차단한다.

```
Deployment Blocked
The deployment was blocked because the commit email ... could not be matched
to a GitHub account.
```

**이 저장소의 커밋 신원을 계정 이메일로 맞춘다.**

```bash
git config user.name  "Jinhan Bae"
git config user.email "foes88@gmail.com"     # GitHub 계정에 등록된 주소
```

전역이 아니라 저장소 단위(`--global` 없이)로 두면 다른 프로젝트에 영향이 없다.

이미 잘못된 이메일로 쌓인 커밋이 있으면, 올바른 이메일로 **새 커밋을 하나 더 올리면**
그 커밋 기준으로 배포가 진행된다. 과거 커밋까지 정리하려면 히스토리 재작성이 필요하므로
협업자가 없을 때만 한다.

GitHub 에 여러 이메일을 쓰고 있다면 **Settings → Emails** 에서 해당 주소를 추가·인증하는
방법도 있다. 공개하고 싶지 않으면 `{id}+{login}@users.noreply.github.com` 를 쓰면 된다.
