# TaxBriefing 개발패키지 v1.0

## 파일 구성
1. **TaxBriefing_통합개발명세서_v1.0.docx** — PRD, 기능명세, 아키텍처, 데이터, API, AI, 화면, 보안, 테스트, 일정
2. **TaxBriefing_Claude검증프롬프트.md** — Claude에 문서와 함께 넣을 검증 지시문
3. **TaxBriefing_schema.sql** — PostgreSQL 데이터 모델 초안
4. **TaxBriefing_openapi_draft.yaml** — 핵심 API 계약 초안
5. **TaxBriefing_ai_output_schema.json** — AI 구조화 출력 JSON Schema

## 사용 순서
1. Claude에 5개 파일을 모두 첨부합니다.
2. `TaxBriefing_Claude검증프롬프트.md` 내용을 입력합니다.
3. Claude의 치명적 문제와 스키마 불일치를 먼저 수정합니다.
4. 제품책임자와 세무전문가가 MVP 범위, 공식 출처, 검수 SLA, 발송 동의를 승인합니다.
5. 수정된 OpenAPI·SQL·JSON Schema를 Git 저장소의 계약 기준으로 등록합니다.
6. 인수 시나리오 AT-01~AT-15를 테스트 기준으로 사용합니다.

## 주의
- 이 패키지는 개발 착수용 설계 초안이며, 개별 세무 판단을 자동화하는 문서가 아닙니다.
- 공식 사이트의 이용조건·자동수집 허용 방식·조직명·URL은 구현 직전에 다시 확인해야 합니다.
- 개인정보, 광고성 정보 발송, 저작권, 전자상거래·결제 요건은 출시 전 전문가 검토가 필요합니다.
