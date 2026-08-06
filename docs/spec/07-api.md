# 8. API 명세

> 원본: 통합개발명세서 §8 · 정본 계약: [`docs/contracts/openapi.yaml`](../contracts/openapi.yaml)
> 런타임 스펙: 서버 기동 후 `http://localhost:8000/openapi.json` · Swagger UI `http://localhost:8000/docs`

## 8.1 공통 규약

- 기본 경로 `/api/v1`
- JSON UTF-8, 시간은 **ISO 8601 UTC 저장**, 사용자 표시 시 `Asia/Seoul` 변환
- 목록 API는 cursor pagination
- 쓰기 요청은 `Idempotency-Key` 헤더 지원 (필수)
- 오류 응답은 `code`, `message`, `details`, `trace_id` 포함
- 관리자 API는 역할 기반 권한과 감사로그 필수
- 낙관적 잠금은 `version` 또는 `If-Match` 사용

### 오류 응답 형태

```json
{
  "code": "GATE_FAILED",
  "message": "공식 근거(A/B등급)가 연결되지 않아 승인할 수 없습니다.",
  "details": { "failed_gates": ["G1", "G5"] },
  "trace_id": "01JC9Z8YQ7K3T2R6X4N0M5"
}
```

## 8.2 엔드포인트 목록

| Method | Path | 설명 | 상태 |
| --- | --- | --- | --- |
| GET | `/sources` | 출처 목록·상태 | ✅ |
| POST | `/sources` | 출처 등록 | ✅ |
| POST | `/sources/{id}/runs` | 수집 실행 | ⬜ S2 |
| GET | `/raw-contents` | 원문 검색 | ✅ |
| GET | `/raw-contents/{id}` | 원문·버전·첨부 조회 | ✅ |
| POST | `/raw-contents/manual` | 수동 원문 등록 | ✅ |
| POST | `/policy-clusters` | 정책 클러스터 생성·병합 | ⬜ S2 |
| POST | `/analyses` | AI 분석 요청 | ✅ |
| GET | `/analyses/{id}` | 분석 결과·근거·경고 | ✅ |
| POST | `/contents` | 가공 콘텐츠 생성 | ✅ |
| PATCH | `/contents/{id}` | 콘텐츠 수정 | ✅ |
| POST | `/contents/{id}/submit-review` | 검수 요청 | ✅ |
| POST | `/contents/{id}/reviews` | 승인·반려 | ✅ |
| POST | `/contents/{id}/corrections` | 정정 생성 | ⬜ S3 |
| GET | `/feed` | 사용자 맞춤 브리핑 | ⬜ S3 |
| GET | `/contents/{id}/public` | 사용자 콘텐츠 상세 | ⬜ S3 |
| PUT | `/me/business-profile` | 사업자 프로필 수정 | ✅ |
| PUT | `/me/preferences` | 수신설정 수정 | ⬜ S3 |
| POST | `/campaigns` | 캠페인 생성 | ⬜ S3 |
| POST | `/campaigns/{id}/preview` | 대상·메시지 미리보기 | ⬜ S3 |
| POST | `/campaigns/{id}/schedule` | 예약 | ⬜ S3 |
| POST | `/campaigns/{id}/cancel` | 취소 | ⬜ S3 |
| GET | `/deliveries` | 발송결과 | ⬜ S3 |
| POST | `/consultations` | 상담신청 | ⬜ S3 |
| GET | `/admin/dashboard` | 운영 지표 | ⬜ S3 |

## 8.3 검수 요청 예시

```http
POST /api/v1/contents/{content_id}/reviews
Idempotency-Key: rev-01JC9Z8YQ7K3T2R6X4N0M5
```
```json
{
  "decision": "APPROVE_WITH_EDIT",
  "legal_status": "PROMULGATED",
  "risk_level": "HIGH",
  "review_note": "시행일과 경과조치 원문 확인 완료",
  "checked_source_version_ids": ["<uuid>", "<uuid>"]
}
```

## 8.4 초안 계약에서 확인된 불일치와 구현 결정

| # | 초안 상태 | 구현 결정 |
| --- | --- | --- |
| A-01 | 본문 §8.3 예시는 `checked_source_ids`, OpenAPI는 `checked_source_version_ids` | **`checked_source_version_ids`로 통일.** 검수자는 원문이 아니라 *원문 버전*을 확인해야 추적성이 성립한다 |
| A-02 | 본문 §8.2에 `/contents/{id}/submit-review`가 있으나 OpenAPI에 없음 | 엔드포인트 추가 구현 |
| A-03 | `Idempotency-Key`가 `required: true`인 공통 파라미터인데 GET에도 적용될 여지 | 쓰기(POST/PUT/PATCH)에만 강제 |
| A-04 | `ContentCreate`에 `legal_status`가 required — 원문 확인 전에는 알 수 없음 | 생성 시 `UNKNOWN` 허용을 명시. 확정은 검수 단계에서 |
| A-05 | `/analyses`는 `202`만 정의, 결과 조회 경로 미정의 | `POST /analyses` → `202 + {analysis_id}`, `GET /analyses/{id}`로 폴링 |
| A-06 | `PATCH /contents/{id}` 요청 본문이 `additionalProperties: true` | 수정 가능 필드를 명시적 스키마로 제한하고, 보호 필드 변경 시 승인 해제 (FR-CMS-004 / AT-07) |
| A-07 | 오류 응답 스키마가 `description`만 있고 본문 정의 없음 | `ErrorResponse` 스키마 정의 (§8.1) |

### 보호 필드 (변경 시 승인 해제 → `REVIEW_PENDING`)

`legal_status`, `risk_level`, `effective_date`, `promulgation_date`, `announcement_date`,
`application_start`, `application_end`, `title`, `one_line_summary`, `body`

구현: [`app/domain/workflow.py`](../../backend/app/domain/workflow.py) `PROTECTED_FIELDS`
