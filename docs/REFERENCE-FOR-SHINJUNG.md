# 신정에서 세무 브리핑을 개발할 때 보는 문서

**로직은 그대로 가져가고 화면은 새로 짠다.** 화면은 더 나아져도 된다.
다만 아래 판단들은 바꾸면 안 된다 — 전부 겪고 나서 알게 된 것이고, 바꾸면
사장님에게 거짓이 나간다.

여기 적힌 값은 전부 실제 코드와 DB 에서 뽑았다. 짐작한 것은 없다.

---

# 1. 어디를 보고 개발하나

taxbriefing 은 **파이썬 패키지로 설치해서 쓴다.** 신정 저장소로 옮기지 않는다.

```
taxbriefing-backend @ git+https://github.com/foes88/taxbriefing@main#subdirectory=backend
```

## 신정이 실제로 쓸 것

| 무엇 | 어디 | 신정에서 |
|---|---|---|
| 표 28개 (모델) | `app/models/tables.py` | 그대로 씀 |
| 목록·상세 조회 | `app/api/v1/public.py` | **라우터만 새로** |
| 마감 일정 13개 | `app/domain/tax_calendar.py` | 그대로 씀 (DB 안 봄) |
| 사장님께 보낼 글 | `app/domain/share.py` | 그대로 씀 |
| 업종 분류표 | `app/domain/industry.py` | 거래처 업종과 이음 |
| 상태 문구 | `app/services/render/telegram.py` | `STATUS_LABEL`·`STATUS_CAVEAT` |

## 신정이 안 건드릴 것

수집·요약·분류·발송은 **taxbriefing 저장소의 배치가 계속 돈다.**
공개 저장소라 GitHub Actions 가 무료이기 때문이다. 신정은 **읽기만** 한다.

```
app/collect.py  app/bulk_draft.py  app/summarize.py
app/classify.py  app/notify.py
```

---

# 2. 자료가 어떻게 생겼나

## 종류 (`content_kind`) — 6가지

```
POLICY          법령 (시행령·시행규칙 포함)
TRIBUNAL        조세심판원 결정
INTERPRETATION  국세청·기재부 법령해석
PRECEDENT       법원 판례
BILL            국회 발의 법안
SUPPORT         지원사업
```

## 상태 (`legal_status`) — 10가지, 화면 문구는 서버가 준다

| 상태 | `status_label` | `status_caveat` |
|---|---|---|
| `DISCUSSION` | 검토·논의 | 확정 아님 |
| `BILL_PROPOSED` | 법안 발의 | 시행 확정 아님 |
| `PREANNOUNCED` | 입법·행정예고 | 시행 확정 아님 · 최종안 변경 가능 |
| `GOV_ANNOUNCED` | 정부안 발표 | 시행 확정 아님 |
| `ASSEMBLY_PASSED` | 국회 통과 | 공포·시행일 확인 필요 |
| `PROMULGATED` | 공포 | 시행일 확인 |
| `EFFECTIVE` | 시행 중 | (없음) |
| `SUSPENDED` | 유예·효력정지 | 적용 중단 |
| `ABOLISHED` | 폐지 | 폐지일·경과조치 확인 |
| `UNKNOWN` | 상태 확인 필요 | 확정 아님 |

**화면에서 이 표를 다시 만들지 마라.** API 가 `status_label` · `status_caveat`
로 내려준다. 심판례·해석례·판례에는 **둘 다 `null`** 로 온다 — 진행 단계라는
것이 없기 때문이다. `null` 이면 안 그리면 된다.

**`PROMULGATED` 인데 시행일을 아는 건에는 경고가 안 붙는다.** 날짜를 보여
주면서 그 날짜를 확인하라고 하는 셈이라서다. 서버가 이미 판단해서 `null` 로
준다.

## 위험도 (`risk_level`) — 4단계

```
CRITICAL  긴급    HIGH  중요    MEDIUM  안내    LOW  참고
```

**법안 · 입법예고 · 해석례 · 판례 · 심판례는 무조건 `LOW` 다.**
(`app/bulk_draft.py` 의 `KINDS_ALWAYS_LOW` + `preannounced`) 확정 안 된 것과
남의 사건에 [중요] 를 달면, 정작 확정된 개정이 그 아래 묻힌다. 세법 열
건이 같은 날 예고된 적이 있다.

**이 문서를 처음 쓸 때 심판례가 빠져 있었다.** 형제인 해석례·판례는 목록에
있는데 심판례만 없어서 제목 낱말("가산세" 같은)로 판정됐고, 33건 중 30건에
[중요] 가 붙어 있었다. 코드를 고치고 70건(법안 37 · 심판례 33)을 `LOW` 로
되돌렸다. 지금은 어긋난 건이 0 이다.

**그러니 화면에서 종류로 다시 거르지 마세요.** 서버가 정한 값을 그대로
쓰면 됩니다. 대신 이관 후 아래 한 줄로 어긋남이 0 인지 확인해 주세요.

```sql
select content_kind, risk::text, count(*)
  from tb.tax_contents
 where content_kind in ('BILL','TRIBUNAL','INTERPRETATION','PRECEDENT')
   and risk::text <> 'LOW'
 group by 1,2;   -- 0 행이어야 합니다
```

---

# 3. API — 무엇이 오나

## 목록 `GET /public/feed`

한 건에 20개 필드가 온다.

```
id · title · one_line_summary
legal_status · status_label · status_caveat · is_confirmed
risk_level · content_kind · outcome
effective_date · promulgation_date · application_end · comment_deadline
industries · industry_labels
corrected · actionable · source_url · updated_at
```

**총계는 본문 `total` 로 온다.** 신정 목록 규칙은 `x-total-count` 헤더이므로
**헤더로 바꾸고 본문에서는 빼라.** 둘 다 두면 어긋날 때 어느 쪽이 맞는지
알 수 없다.

거를 수 있는 것:

```
q                 제목·요약·본문 전체 검색 (search_text)
content_kind[]    종류
legal_status[]    상태
risk_level[]      위험도
industries[]      업종 (하나라도 겹치면 나온다)
outcome           심판례 결론
month             공포월 YYYY-MM
promulgated_from / promulgated_to
effective_from / effective_to
deadline_within_days
limit (1~100, 기본 20) / offset
```

**`next_cursor` 는 그냥 다음 `offset` 을 문자열로 담은 것이다.**
(`str(offset + limit)`, 끝이면 `null`) 커서 토큰이 아니다.

**모르는 파라미터는 조용히 무시된다.** FastAPI 가 그렇다. 신정 목록 규칙이
`page` · `size` 라면 `?size=50` 을 보내도 오류 없이 **기본값 20건이 온다.**
실제로 이관 점검 중에 이걸로 한 번 속았다. `limit` · `offset` 으로 보내고,
받은 건수가 요청한 수와 같은지 한 번은 확인하세요.

## 상세 `GET /public/contents/{id}`

목록 20개에 7개가 더 붙는다.

```
announcement_date · application_start · body
share_text · sources · evidence_fields · reviewed
```

### `body` 는 종류마다 다르다 — 실제로 확인한 것

```
POLICY          affected_users, excluded_users, changes,
                business_impact, required_actions, needs_expert, _ai
TRIBUNAL        tribunal, needs_expert
INTERPRETATION  changes, required_actions, needs_expert
BILL            changes, required_actions, needs_expert
```

`_ai: true` 면 AI 가 쓴 요약이다. **화면에 「검수 필요」 를 표시하라.**
사람이 원문과 대조하지 않았다.

`changes` · `business_impact` · `required_actions` 는
`[{text, locator}]` 꼴이다. `locator` 는 근거 위치("제개정이유 2문단")다.

`tribunal` 은 심판례 전용 묶음 — 청구번호·세목·처분청·결론·판단 요지·
판단 이유·주문이 들어 있다.

## 마감 일정 `GET /public/calendar`

**DB 를 안 본다.** 날짜가 법에 정해져 있어 수집할 것도 물어볼 것도 없다.

```
date · title · note · audience · audience_label · basis · shifted · days_left
```

`basis` 는 근거 조문이다. **반드시 같이 보여라** — 날짜가 법에 정해져 있다는
것이 이 화면의 값이고, 어디에 정해져 있는지 안 보이면 그냥 남의 달력이다.

`shifted` 는 주말이라 다음 월요일로 민 것이다. **밝혀야 한다.** 원래 25일인
줄 아는 사람이 "왜 27일이지" 하고 멈추지 않도록.

## 사장님께 돌릴 글 `GET /public/share/deadlines`

```
text · deadline_count · change_count · industry_count
```

`text` 를 그대로 복사해 카톡에 붙이면 된다. **화면에서 다시 조립하지 마라.**

---

# 4. 바꾸면 안 되는 판단들

## 4.1 종류에 따라 말을 바꾼다

하나로 뭉치면 이런 것이 나온다.

    「…심판청구가 적법한지 여부 — 기각」이(가) 개정되어
    시행일은 원문 확인이 필요합니다.

심판례는 개정된 것이 아니고 시행일도 없다.

| 종류 | 보여줄 것 | **보여주면 안 되는 것** |
|---|---|---|
| 법령 | 공포일·시행일·달라지는 점·할 일 | — |
| 심판례 | 결론·의결일·판단 요지 | 시행일 · 상태 배지 |
| 해석례·판례 | 회신일/선고일·원문 링크 | 시행일 · 상태 배지 · 「할 일」 |
| 법안 | 발의자·소관위원회·처리결과 | **시행일 · 「할 일」** |
| 입법예고 | 의견 제출 마감 | **시행일 · 「할 일」** |

법안에 「할 일」을 만들면 사업자가 안 해도 될 일을 하고, 확정된 개정과
구분이 안 된다.

## 4.2 본문이 없으면 AI 를 안 돌린다

심판례·해석례·판례·법안·입법예고는 원문이 없거나 이미 구획이 나뉘어 있다.
**제목만 주고 요지를 쓰라고 하면 지어낸다.** 세 번 겪었다.

법안 86건에 돌렸더니 결과가 전부 빈 배열이었고, 한 줄 요약은 이렇게 덮였다.

    구체적인 내용이 확정되지 않아 사업자에게 직접적인 변화는 없습니다.

**내용은 확정돼 있다.** 국회가 조문을 안 줄 뿐이다.

## 4.3 모르는 값은 비운다

「확인 필요」로 채우지 마라. **확인할 것이 없는데 있는 것처럼 읽힌다.**
시행일이 없으면 시행일 줄이 없다.

## 4.4 건수는 서버에 묻는다

화면에 그려진 것을 세지 마라. 예전에 목록에 15라고 떴는데 실제로는 34건이었다.

## 4.5 자른 것은 자른 사실을 적는다

    이 밖에 3건이 더 있습니다.

조용히 자르면 오늘 나온 게 그게 전부라고 믿는다.

## 4.6 예고를 확정된 것과 섞지 않는다

**이 화면에서 가장 위험한 오해다.** 같은 모양의 카드로 이어 붙이면
스크롤하다 「소득세법 일부개정법률안」을 이미 바뀐 것으로 읽는다.

「예고 단계」를 「최근 확정된 것」 **위**에 따로 둔다. 공포는 이미 끝난
일이고 예고는 아직 의견을 낼 수 있다 — 지금 움직일 수 있는 쪽이 위다.

## 4.7 실질 변경이 없는 건을 위에 올리지 않는다

`actionable: false` 로 온다. 자구 정리나 인용 조문만 바뀐 개정이다.
「먼저 볼 것」 1번이 "사업자에게 실질적인 변경사항은 없습니다" 였던 적이 있다.

## 4.8 사장님께 나가는 글에서는 AI 를 다시 돌리지 않는다

`share_text` 는 이미 검증된 필드를 **고르고 자른 것**이다. "쉬운 말로 바꿔"를
한 번 더 시키면 검수를 통과한 문장이 검수 안 거친 문장으로 바뀌고, 그게
사무소를 떠나 사장님 카톡으로 들어간다. 거기서는 정정할 방법이 없다.

---

# 5. 화면은 새로 짜도 된다 — 다만 이건 유지

taxbriefing 화면 넷을 참고하되 더 나아져도 좋다.
`app/page.tsx`(오늘) · `app/search/page.tsx`(찾기) · `app/upcoming/page.tsx`(일정) ·
`app/contents/[id]/page.tsx`(상세), 컴포넌트는 `components/Card.tsx` 등.

## 유지할 구조

**오늘** — 순서가 판단이다.

```
지금 확인          위험도 CRITICAL·HIGH 이면서 곧 시행 (actionable=true)
예고 단계          PREANNOUNCED — 아직 의견 낼 수 있다
최근 확정된 것      나머지
비슷한 사안         심판례
확인 전 소식        뉴스 ← 경계를 눈에 보이게. 위는 검수를 거쳤고 아래는 아니다
```

**찾기** — 종류 칩 8 + 업종 칩 11. **칩은 가로로 밀지 말고 줄바꿈하라.**
스크롤바를 감춘 가로 줄은 마우스로 밀 방법이 없어서, 화면 오른쪽에서 잘린
칩은 없는 것과 같다.

**일정** — 마감 / 시행 예정 두 갈래. 남은 날짜(D-day)를 왼쪽에 크게.
**세 자리(D-131)가 한 줄에 들어가는 폭을 줘라.** 48px 로 뒀다가 두 줄로
깨졌다.

**상세** — 급한 정도 → 무엇이 바뀌나 → 한눈 표 → 할 일 → 대상 → 조문 대조.

## 화면에 반드시 남길 것

- **출처와 검수 표시** — 신뢰는 여기서 온다. `sources` 와 `reviewed`
- **`_ai: true` 면 「검수 필요」**
- **면책 한 줄** — "개별 사업자의 적용 여부는 사실관계에 따라 달라집니다"
- **정정(`corrected`) 표시** — 이전에 안내한 내용이 바뀌었다는 사실

---

# 6. 업종 — 거래처와 잇는 열쇠

taxbriefing 업종 13개. 거래처(`clients`)에 이 코드를 붙이면
**"김실장이 맡은 거래처 중 음식점에 해당하는 개정"** 이 나온다.

```
ALL           전 업종 공통     신고절차·가산세·4대보험처럼 업종 무관
FOOD          요식·음식점      의제매입세액공제, 배달앱
EDU           학원·교육
RETAIL        도소매·유통      신용카드 매출, 현금영수증
BEAUTY        미용·서비스
LODGING       숙박
TRANSPORT     운수·배달
FREELANCE     프리랜서·인적용역  3.3% 원천징수
MEDICAL       의료·약국
CONSTRUCTION  건설
REALESTATE    부동산임대
MANUFACTURING 제조
CORPORATE     법인 일반        법인세·주주·배당
```

**`INTERNAL` 이라는 값이 하나 더 있는데 업종이 아니다.** 화면에서 숨긴다는
표시이고 규칙만 붙인다. 목록에 보이면 안 된다.

**자유 입력으로 두지 마라.** "음식점" 과 "일반음식점" 이 다른 값이 되면
거를 수가 없다.

---

# 7. 확인된 한계 — 여기는 이미 파 봤다

같은 데를 다시 파지 않도록. 자세한 것은 `docs/ROADMAP.md` 의 「확인된 한계」.

- **해석례·심판례·판례 134건은 제목과 링크뿐이다.** 국세법령정보시스템이
  본문을 안 준다. 화면에서 "본문 미수록" 을 밝히고 원문으로 보낸다
- **국회는 법안 조문을 안 준다.** 의안명·발의자·처리결과가 전부다
- **크롤링 차단을 우회하지 않는다.** 막힌 곳은 막힌 대로 두고 한계로 적는다
- **GROQ 무료 티어** — 분당 8,000 토큰 / 하루 20만. 하루 40건이 한계다

---

# 8. 막히면

```
docs/HANDOFF-SHINJUNG.md      단계별 작업 지시
docs/MERGE-STEP1.md           스키마·DB·배치 계획
docs/MIGRATE-TO-SHINJUNG.md   옮길 것 전체 목록
docs/ROADMAP.md               확인된 한계
```

코드에 **왜 그렇게 했는지가 주석으로 적혀 있다.** 바꾸기 전에 그 주석을
읽어라. 대부분은 한 번 겪고 고친 자리다.
