# 7. 데이터 모델 및 ERD

> 원본: 통합개발명세서 §7 · 정본 DDL: [`docs/contracts/schema.sql`](../contracts/schema.sql)

## 7.1 테이블 책임

| 테이블 | 책임 |
| --- | --- |
| `sources` | 출처 레지스트리 |
| `source_runs` | 수집 실행 이력 |
| `raw_contents` | 원문 논리 항목 |
| `raw_content_versions` | 원문 버전과 해시 |
| `attachments` | 첨부파일 메타·저장경로 |
| `policy_clusters` | 동일 정책 묶음 |
| `content_sources` | 가공 콘텐츠와 원문 근거 관계 |
| `tax_contents` | 사업자용 콘텐츠 |
| `content_versions` | 편집·발송 버전 |
| `content_evidence` | 필드별 근거 위치 |
| `reviews` | 검수·승인·반려 |
| `corrections` | 정정과 영향범위 |
| `tags` / `content_tags` | 세목·업종·대상·지역 태그 |
| `users` | 계정 |
| `business_profiles` | 사업자 개인화 프로필 |
| `consents` | 수신·개인정보 동의 이력 |
| `campaigns` / `campaign_recipients` | 발송 캠페인과 대상 선정 스냅샷 |
| `deliveries` | 채널별 발송 결과 |
| `engagement_events` | 열람·클릭·저장 이벤트 |
| `consultation_requests` | 상담 요청 |
| `tenants` | B2B 테넌트 |
| `audit_logs` | 감사 이벤트 |

## 7.2 관계 요약

```
source           1:N  source_runs, raw_contents
raw_content      1:N  raw_content_versions, attachments
policy_cluster   N:M  raw_contents            (policy_cluster_items)
tax_content      N:M  raw_content_versions    (content_sources)
tax_content      1:N  content_versions, reviews, corrections, content_evidence
tax_content      N:M  tags                    (content_tags)
user             1:N  business_profiles, consents, deliveries
campaign         N:M  users                   (campaign_recipients)
delivery         N:1  campaign  +  message_snapshot(jsonb) 고정 저장
```

## 7.3 핵심 필드 규칙

| 엔터티 | 필드 | 규칙 |
| --- | --- | --- |
| `tax_contents` | `legal` | 정책 법적 상태 enum |
| `tax_contents` | `workflow` | 내부 처리 상태 enum |
| `tax_contents` | `risk` | LOW/MEDIUM/HIGH/CRITICAL |
| `tax_contents` | `effective_date` | **원문 확인 없으면 null** |
| `tax_contents` | `source_confidence` | 0~100 워크플로 점수 |
| `content_sources` | `role` | PRIMARY/SECONDARY/REFERENCE |
| `content_evidence` | `field_name` | `effective_date`, `affected_users` 등 구조화 필드명 |
| `content_evidence` | `locator` | 문단번호·페이지·텍스트 오프셋 |
| `reviews` | `decision` | APPROVE/APPROVE_WITH_EDIT/REJECT |
| `deliveries` | `idempotency_key` | 사용자·캠페인·채널 단위 유일 |
| `audit_logs` | `before_data`/`after_data` | 민감정보는 마스킹하고 변경 요약 보존 |

## 7.4 초안 DDL에서 확인된 이슈와 구현 결정

`schema.sql`은 v1.0 초안이며, 마이그레이션으로 옮기면서 아래를 보정했다.
원본 파일은 계약 기준으로 그대로 보존하고, 실제 DDL은 Alembic 마이그레이션이 정본이다.

| # | 초안 상태 | 구현 결정 |
| --- | --- | --- |
| D-01 | `deliveries.idempotency_key`가 전역 UNIQUE. §7.3은 "사용자·캠페인·채널 단위 유일" | 전역 UNIQUE 유지 + 키 생성 규칙을 `campaign_id:user_id:channel`로 고정해 두 정의를 일치시킴 |
| D-02 | `reviews.checked_source_version_ids`가 `uuid[]`로 FK 미보장 | MVP는 배열 유지 + 애플리케이션 레벨 존재 검증. 2단계에서 조인 테이블로 정규화 |
| D-03 | `raw_content_versions`에 `UNIQUE(raw_content_id, content_hash)` — 내용이 A→B→A로 되돌아가면 삽입 실패 | 되돌림은 새 버전이 아니라 `last_checked_at` 갱신으로 처리(AT-01/AT-02 의미와 일치). 제약 유지 |
| D-04 | `tax_contents.tenant_id` nullable — 공용 콘텐츠와 테넌트 전용 콘텐츠 구분 불명확 | `NULL` = 전체 공용, 값 있음 = 해당 테넌트 전용으로 정의. 조회 시 `tenant_id IS NULL OR tenant_id = :tid` |
| D-05 | `consents`의 UNIQUE에 `granted_at`이 포함되어 사실상 중복 방지가 안 됨 | 동의 이력은 append-only가 맞으므로 유지. "현재 유효 동의"는 `(user_id, consent_type, channel)`별 최신 행으로 조회 |
| D-06 | 멱등성 저장소 테이블 부재 (NFR-005) | `idempotency_records` 테이블 신규 추가 |
| D-07 | `campaigns`에 `campaign_message_snapshot` 언급(§11.3)되나 테이블 없음 | `deliveries.message_snapshot jsonb`가 그 역할. §11.3 문구를 이에 맞춰 해석 |
| D-08 | `source_confidence` 산정 내역 저장 위치 없음 (FR-VER-005 "점수 내역 조회") | `tax_contents.confidence_breakdown jsonb` 컬럼 추가 |

## 7.5 인덱스

`schema.sql` 하단 8개 인덱스를 그대로 사용한다.

```sql
idx_raw_contents_published     (published_at DESC)
idx_raw_versions_hash          (content_hash)
idx_tax_contents_status        (workflow, legal, risk)
idx_tax_contents_dates         (effective_date, application_end)
idx_content_evidence_content   (tax_content_id, field_name)
idx_deliveries_campaign_status (campaign_id, status)
idx_engagement_content_time    (tax_content_id, occurred_at DESC)
idx_audit_object               (object_type, object_id, occurred_at DESC)
```
