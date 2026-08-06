# 14. 테스트·인수 기준

> 원본: 통합개발명세서 §14

## 14.1 테스트 레벨

| 레벨 | 대상 |
| --- | --- |
| 단위 | 파서, 해시, 상태 전이, 점수, 개인화 규칙, 템플릿 |
| 통합 | 수집→저장→AI→검수→발송 흐름, 공급자 샌드박스 |
| 계약 | OpenAPI와 JSON Schema, 채널 변수 |
| E2E | 관리자 승인과 사용자 수신·조회·수신거부 |
| 데이터 품질 | 날짜·기관·문서번호·상태·근거 정확성 |
| 보안 | RBAC, 테넌트 격리, SSRF, 업로드, 인증 |
| 성능 | 수집 배치, 피드 조회, 대량 대상 선정·발송 |
| 복구 | 백업 복원, 큐 재처리, 중복 발송 방지 |

## 14.2 인수 시나리오 AT-01 ~ AT-15

| ID | 인수 조건 | 테스트 위치 | 상태 |
| --- | --- | --- | --- |
| AT-01 | 동일 게시물을 3회 수집해도 `raw_content`는 1개이고 실행이력만 증가한다. | `tests/acceptance/test_at01_idempotent_collect.py` | ✅ |
| AT-02 | 원문 본문이 변경되면 새 `raw_content_version`과 diff가 생성된다. | `tests/acceptance/test_at02_versioning.py` | ✅ |
| AT-03 | 뉴스만 연결된 콘텐츠는 승인·발송할 수 없다. | `tests/acceptance/test_at03_news_only_blocked.py` | ✅ |
| AT-04 | 입법예고 콘텐츠가 "시행 중"으로 표시되지 않는다. | `tests/acceptance/test_at04_status_display.py` | ✅ |
| AT-05 | 시행일 근거가 없으면 AI 출력 `effective_date`는 `null`이다. | `tests/acceptance/test_at05_null_dates.py` | ✅ |
| AT-06 | `HIGH` 위험도 콘텐츠는 `REVIEWER` 승인 없이는 캠페인에 포함되지 않는다. | `tests/acceptance/test_at06_high_risk_gate.py` | ✅ |
| AT-07 | 승인 후 본문 수정 시 승인상태가 해제되고 재검수 큐로 이동한다. | `tests/acceptance/test_at07_reapproval.py` | ✅ |
| AT-08 | 명시적 제외 대상 사용자는 캠페인 대상에서 제거된다. | `tests/acceptance/test_at08_exclusion.py` | ✅ |
| AT-09 | 동일 idempotency key로 발송 요청해도 사용자당 1건만 전송된다. | `tests/acceptance/test_at09_idempotent_delivery.py` | ✅ |
| AT-10 | 수신철회 사용자는 예약 캠페인 실행 시 최종 대상에서 제외된다. | `tests/acceptance/test_at10_consent_revoked.py` | ✅ |
| AT-11 | 정정본 승인 후 기존 수신자 중 영향 대상에게만 재발송된다. | — | ⬜ S3 |
| AT-12 | 관리자는 누가 어떤 근거를 확인하고 승인했는지 조회할 수 있다. | `tests/acceptance/test_at12_audit_trail.py` | ✅ |
| AT-13 | 테넌트 관리자는 다른 테넌트의 사용자·발송정보를 볼 수 없다. | — | ⬜ S2 |
| AT-14 | 수집 대상 URL이 사설 IP로 리다이렉트되면 차단된다. | `tests/acceptance/test_at14_ssrf.py` | ✅ |
| AT-15 | DB 복원 후 최근 승인 콘텐츠와 발송 이력이 일치한다. | — | ⬜ S3 (운영 훈련) |

## 14.3 실행

```bash
cd backend
pytest                      # 전체
pytest tests/acceptance -v  # 인수 시나리오만
pytest -m "not integration" # DB 없이 도메인 단위 테스트만
```

## 14.4 골든셋 케이스

전문가가 라벨링할 최소 100건은 아래 유형을 모두 포함해야 한다.

1. 세법 개정 공포 사례
2. 법안 발의만 된 사례
3. 입법예고 후 내용이 변경된 사례
4. 발표일과 시행일이 다른 사례
5. 경과조치가 있는 사례
6. 지원사업 조기마감 사례
7. 뉴스와 공식자료 제목이 다른 사례
8. 서로 충돌하는 정부 설명자료 사례
9. 적용대상과 제외대상이 복잡한 사례
10. **원문에 시행일이 없는 사례**

측정 축: 날짜 / 상태 / 대상 / 행동사항 / 근거 정밀도를 **각각 별도로** 측정한다.
자동 점수 외에 전문가 오류등급을 기록한다.

## 14.5 개발 완료 정의 (Definition of Done)

- [ ] MUST 요구사항과 AT-01~AT-15가 스테이징 환경에서 통과한다.
- [ ] 고위험 콘텐츠가 공식 원문과 전문가 승인 없이 발송되지 않는다.
- [ ] 동일 요청 재실행 시 중복 원문·캠페인·발송이 생성되지 않는다.
- [ ] 정정 모의훈련에서 영향 대상 추출, 승인, 재발송, 기존 콘텐츠 표시가 확인된다.
- [ ] 개인정보·수신동의·테넌트 격리·SSRF·업로드 보안 테스트가 통과한다.
- [ ] 운영자가 출처 장애, AI 실패, 발송 실패를 대시보드와 알림으로 확인할 수 있다.
