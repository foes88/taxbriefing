# 신정 결재시스템에 심기 — 문서 안내

taxbriefing 을 신정세무회계법인 통합관리 시스템 안으로 합친다.
**어디부터 읽을지**만 여기 적는다.

---

## 신정 쪽에서 작업한다면

세션에 이 한 줄을 넣는다.

    C:\dev\taxbriefing\docs\HANDOFF-SHINJUNG.md 를 읽고 그대로 진행해.
    로직은 REFERENCE-FOR-SHINJUNG.md 를 보고, 막히면 ROADMAP.md 의
    「확인된 한계」 를 먼저 읽어.

읽는 순서:

| | 무엇 |
|---|---|
| **HANDOFF-SHINJUNG.md** | **무엇을 만들지.** 6단계 + 확인 목록 |
| **REFERENCE-FOR-SHINJUNG.md** | **어떤 소스를 보고 무엇을 지킬지.** API 필드·종류별 규칙 |
| MERGE-STEP1.md | 스키마·DB·배치를 어떻게 합치나 |
| MIGRATE-TO-SHINJUNG.md | 옮길 것 전체 목록과 부딪히는 곳 |
| ROADMAP.md | 확인된 한계 — 이미 파 본 막다른 길 |

---

## 한 장으로 요약

**돈을 쓰지 않는 것이 목표다.** 그래서 이렇게 나눈다.

    코드·배치   taxbriefing 공개 저장소에 그대로  (Actions 무료·무제한)
    DB          신정 Supabase 의 tb 스키마        ← 여기서 합쳐진다
    API·화면    신정에서 새로

taxbriefing 을 신정 저장소로 **옮기지 않는다.** 옮기면 비공개 저장소라
Actions 가 과금된다(월 600~900분). 대신 파이썬 패키지로 설치해 쓴다.

    taxbriefing-backend @ git+https://github.com/foes88/taxbriefing@main#subdirectory=backend

모델 정의가 한 곳에만 있어야 한다. 양쪽에 두면 언젠가 갈라지고, 갈라지면
한쪽이 조용히 틀린 값을 읽는다.

---

## 순서

    0  신정 로컬을 Postgres 로 (SQLite 틈 없애기)      신정
    1  신정 Supabase 에 CREATE SCHEMA tb               신정
    2  TAXBRIEFING_DB_SCHEMA=tb 로 alembic upgrade     taxbriefing
    3  데이터 이관 → 행수·값 지문 대조                  taxbriefing
    4  daily.yml 의 DB 주소만 신정 것으로               taxbriefing
    5  읽는 라우터 하나 + 화면(오늘·찾기)               신정
    6  거래처 업종 칸 + 담당 나누기                     신정

**0~1 과 2~3 을 동시에 하지 않는다.** 한쪽이 DB 를 갈아엎는 동안 다른 쪽이
데이터를 넣으면 어디까지 들어갔는지 알 수 없다.

---

## 준비된 것 (taxbriefing 쪽)

- **스키마 스위치** — `TAXBRIEFING_DB_SCHEMA=tb` 를 켜면 표 28개가 통째로
  `tb` 로 간다. 꺼 두면 지금까지와 같다. 양쪽 다 시험으로 못 박혀 있다
- **Alembic 이 따라간다** — `version_table_schema` · `include_schemas`
- **이관 절차** — `MIGRATE-REGION.md` 에 덤프·복원·대조가 적혀 있고 한 번
  연습해서 검증했다. `docs/sql/verify_counts.sql` · `verify_checksums.sql`

## 아직 안 된 것

- 신정 로컬 Postgres 전환 (신정 쪽 작업)
- `tb` 스키마 생성 (신정 쪽 작업)
- 화면 (신정 쪽 작업)
- 거래처 업종 칸 — **이게 없으면 합치는 이유가 성립하지 않는다**
