# 5. 비기능 요구사항

> 원본: 통합개발명세서 §5

| ID | 영역 | 요구사항 |
| --- | --- | --- |
| NFR-001 | 가용성 | MVP 월 99.5% 이상. 계획 점검 제외. |
| NFR-002 | 성능 | 일반 API P95 800ms 이내, 검색 P95 1.5초 이내(외부 API 대기 제외). |
| NFR-003 | 수집 처리량 | 일 10,000건 원문 메타와 2,000건 첨부파일을 확장 가능하게 설계. |
| NFR-004 | 발송 처리량 | 시간당 50,000건까지 공급자 제한에 맞춘 배치·스로틀링 지원. |
| NFR-005 | 멱등성 | 수집, AI 분석, 캠페인 생성, 발송 요청은 idempotency key를 지원. |
| NFR-006 | 데이터 보존 | 원문·버전·감사로그·발송본 최소 5년을 기본안으로 하되 법률 검토 후 확정. |
| NFR-007 | 보안 | TLS, 저장 암호화, 비밀키 분리, 최소권한, 관리자 MFA. |
| NFR-008 | 개인정보 | 수집 최소화, 목적·보유기간 관리, 수신동의 이력, 파기·탈퇴 지원. |
| NFR-009 | 감사성 | 누가 언제 무엇을 변경·승인·발송했는지 추적 가능. |
| NFR-010 | 설명가능성 | 개인화 결과와 정책상태·신뢰도 산정 근거를 운영자에게 표시. |
| NFR-011 | 관측성 | 구조화 로그, 메트릭, 트레이스, 오류 알림, 비용 지표. |
| NFR-012 | 복구 | DB 일일 백업, 시점복구, 객체 스토리지 버전관리, 분기별 복구훈련. |
| NFR-013 | 접근성 | 웹 접근성 기본 준수, 키보드 탐색, 명확한 상태 라벨. |
| NFR-014 | 브라우저 | 최근 2개 주요 버전의 Chrome, Edge, Safari 모바일 웹. |
| NFR-015 | 저작권 | 뉴스 전문 재배포 금지. 제목·메타·짧은 요약과 원문 링크 중심. |

## 구현 매핑

| NFR | 현재 구현 위치 |
| --- | --- |
| NFR-005 멱등성 | [`app/core/idempotency.py`](../../backend/app/core/idempotency.py) — `Idempotency-Key` 헤더 → `idempotency_records` 테이블, 요청 해시 대조 |
| NFR-009 감사성 | [`app/core/audit.py`](../../backend/app/core/audit.py) — `audit_logs` append-only 기록 |
| NFR-010 설명가능성 | [`app/domain/confidence.py`](../../backend/app/domain/confidence.py) `score_breakdown()`, [`app/domain/personalization.py`](../../backend/app/domain/personalization.py) `match_reasons` |
| NFR-011 관측성 | [`app/core/logging.py`](../../backend/app/core/logging.py) — structlog JSON 로그 + `trace_id` 전파 |
| NFR-002 성능 | 인덱스는 [`docs/contracts/schema.sql`](../contracts/schema.sql) 하단 정의를 마이그레이션에 반영 |
