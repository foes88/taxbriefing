/** 백엔드 계약과 1:1 대응. docs/contracts/openapi.yaml 이 정본이다. */

export type LegalStatus =
  | 'DISCUSSION'
  | 'BILL_PROPOSED'
  | 'PREANNOUNCED'
  | 'GOV_ANNOUNCED'
  | 'ASSEMBLY_PASSED'
  | 'PROMULGATED'
  | 'EFFECTIVE'
  | 'SUSPENDED'
  | 'ABOLISHED'
  | 'UNKNOWN';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type WorkflowStatus =
  | 'DETECTED'
  | 'UNVERIFIED'
  | 'SOURCE_CONFIRMED'
  | 'ANALYZED'
  | 'REVIEW_PENDING'
  | 'APPROVED'
  | 'SCHEDULED'
  | 'PUBLISHED'
  | 'MONITORING'
  | 'CORRECTED'
  | 'SUPERSEDED'
  | 'ARCHIVED';

export interface PublicContentSummary {
  id: string;
  title: string;
  one_line_summary: string | null;
  legal_status: LegalStatus;
  /** 서버가 확정한 표시 라벨. 프론트에서 다시 만들지 않는다 (§10.4). */
  status_label: string;
  /** "시행 확정 아님" 같은 경고. null 이면 경고 없음. */
  status_caveat: string | null;
  is_confirmed: boolean;
  risk_level: RiskLevel;
  effective_date: string | null;
  application_end: string | null;
  corrected: boolean;
  updated_at: string;
}

export interface PublicSource {
  publisher: string;
  title: string;
  url: string;
  authority: 'A' | 'B' | 'C' | 'D';
  role: 'PRIMARY' | 'SECONDARY' | 'REFERENCE';
  published_at: string | null;
}

export interface PublicContentDetail extends PublicContentSummary {
  announcement_date: string | null;
  promulgation_date: string | null;
  application_start: string | null;
  body: Record<string, unknown>;
  sources: PublicSource[];
  evidence_fields: string[];
  reviewed: boolean;
}

export interface PublicFeed {
  items: PublicContentSummary[];
  total: number;
  next_cursor: string | null;
}

/** 월별 아카이브. 공포월 기준 — 사업자는 "몇 월 개정"으로 기억한다. */
export interface MonthBucket {
  month: string;
  label: string;
  count: number;
  important: number;
}

/* ---------------------------------------------------------------- 관리자 */

export interface RawContent {
  id: string;
  source_id: string;
  canonical_url: string;
  title: string;
  publisher: string;
  published_at: string | null;
  first_collected_at: string;
  last_checked_at: string;
  current_version_id: string | null;
  status: string;
}

export interface SourceItem {
  id: string;
  display_name: string;
  canonical_domain: string;
  authority: 'A' | 'B' | 'C' | 'D';
  collector_type: string;
  status: string;
  last_success_at: string | null;
  failure_streak: number;
}

export interface GateResult {
  gate: string;
  passed: boolean;
  consequence: string | null;
  reason: string;
  details: Record<string, unknown>;
}

export interface GateReport {
  can_approve: boolean;
  can_schedule: boolean;
  can_personalize: boolean;
  requires_review: boolean;
  results: GateResult[];
}

export interface AdminContent {
  id: string;
  title: string;
  one_line_summary: string | null;
  workflow_status: WorkflowStatus;
  legal_status: LegalStatus;
  risk_level: RiskLevel;
  announcement_date: string | null;
  promulgation_date: string | null;
  effective_date: string | null;
  application_start: string | null;
  application_end: string | null;
  source_confidence: number;
  confidence_breakdown: {
    total?: number;
    max_total?: number;
    components?: { key: string; label: string; points: number; max_points: number; explanation: string }[];
  };
  version: number;
  current_version_id: string | null;
  tenant_id: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  tenant_id: string | null;
}

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
  trace_id: string;
}
