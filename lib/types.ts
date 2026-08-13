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
  /**
   * 서버가 확정한 표시 라벨. 프론트에서 다시 만들지 않는다 (§10.4).
   *
   * **심판례·해석례는 null 이다.** 제도가 아니라 이미 끝난 한 건의
   * 판단이라 진행 상태라는 것이 없다. 예전에는 "상태 확인 필요 ·
   * 확정 아님" 이 붙어서, 확인할 것도 없는 확정된 결정문이 못 미더운
   * 것처럼 보였다.
   */
  status_label: string | null;
  /** "시행 확정 아님" 같은 경고. null 이면 경고 없음. */
  status_caveat: string | null;
  is_confirmed: boolean;
  risk_level: RiskLevel;
  effective_date: string | null;
  /** 공포일. 목록의 월 묶음이 이 값 기준이라 화면에도 같이 보여준다. */
  promulgation_date: string | null;
  application_end: string | null;
  corrected: boolean;
  updated_at: string;
  /** 업종 코드. 상담 참고용 색인이지 적용 판정이 아니다. */
  industries: string[];
  /** 화면용 업종 이름. 서버가 만든다 — 프론트에 분류표를 복사해두지 않는다. */
  industry_labels: string[];
  /**
   * POLICY / TRIBUNAL / INTERPRETATION / BILL / SUPPORT.
   *
   * 심판례에는 시행일도 정책 상태도 없다. 화면이 그 배지를 붙일지 말지를
   * 이 값으로 정한다. 없으면 POLICY 로 본다.
   */
  content_kind?: string;
  /**
   * 심판례 결론 — 인용 / 일부인용 / 기각 / 각하 / 재조사. 법령은 null.
   *
   * 예전에는 제목 끝의 "— 기각" 을 정규식으로 뽑아 썼다. 수집기 버전에
   * 따라 "(기각)" 도 섞이면서 결론 필터가 전부 0 이 됐다.
   */
  outcome?: string | null;
  /**
   * 달라지는 것이나 할 일이 하나라도 있는가. "먼저 볼 것" 선정에 쓴다.
   *
   * 선택 필드다 — 이 값을 내려주지 않는 예전 API 와도 동작해야 한다.
   * 없으면 "모른다"이지 "아니다"가 아니다.
   */
  actionable?: boolean;
}

export interface PublicSource {
  publisher: string;
  title: string;
  url: string;
  authority: 'A' | 'B' | 'C' | 'D';
  role: 'PRIMARY' | 'SECONDARY' | 'REFERENCE';
  published_at: string | null;
}

/**
 * 심판례 본문. 법령과 **구조가 다르다.**
 *
 * 법령은 "무엇이 바뀌고 무엇을 해야 하나"지만, 심판례는 "누가 무엇을
 * 다퉜고 심판원이 어떻게 판단했나"다. 후자에 "지금 해야 할 일"을 붙이면
 * 거짓이 된다 — 이미 끝난 남의 사건이다.
 *
 * 각 구획은 심판원이 쓴 원문 그대로다. 요약하지 않는다. 실무자는 이걸
 * 근거로 인용하므로 우리가 다시 쓴 문장이 끼어들 자리가 없다.
 */
export interface TribunalBody {
  tax_type: string;
  /** 인용 · 일부인용 · 기각 · 각하 · 재조사. 못 읽었으면 빈 문자열. */
  outcome: string;
  case_no: string;
  disposition_agency: string;
  related_laws: string;
  sections: { label: string; text: string }[];
}

/**
 * 조문 한 조각. `changed` 가 법제처가 표시한 변경 부분이다.
 *
 * HTML 이 아니라 조각으로 받는다 — 태그를 그대로 심으면 원문에 섞여
 * 들어온 것이 실행된다. 조각이면 글자로만 다룬다.
 */
export interface DiffSegment {
  text: string;
  changed: boolean;
}

/** 신구법 대조표. 법제처가 구/신 조문을 짝지어 준 것을 그대로 옮겼다. */
export interface ComparisonBody {
  rows: { no: string; old: DiffSegment[]; new: DiffSegment[] }[];
  /** 담지 못하고 자른 조문 수. 0 이 아니면 화면에 그 사실을 적는다. */
  dropped: number;
  law_name: string;
  revision_type: string;
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

/** 업종 필터 항목. 게시된 건이 있는 업종만 내려온다. */
export interface IndustryBucket {
  code: string;
  label: string;
  count: number;
}

/**
 * 언론 보도 한 건. **검수를 거치지 않았다.**
 *
 * `PublicContentSummary` 와 필드를 일부러 겹치지 않게 뒀다. 두 타입을 같은
 * 목록에 섞으면 타입 오류가 나야 한다 — 화면에서 섞이면 사업자가 보도를
 * 확정된 제도로 읽는다.
 */
export interface NewsItem {
  id: string;
  title: string;
  url: string;
  publisher: string;
  summary: string | null;
  published_at: string | null;
  authority: string;
  matched_query: string | null;
}

export interface NewsFeed {
  items: NewsItem[];
  total: number;
  caveat: string;
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

/** 검수자가 "무엇을 확인했는지" 고르는 목록 (AT-12). */
export interface ContentSourceRef {
  raw_content_version_id: string;
  version_no: number;
  title: string;
  publisher: string;
  authority: 'A' | 'B' | 'C' | 'D';
  role: 'PRIMARY' | 'SECONDARY' | 'REFERENCE';
  canonical_url: string;
  published_at: string | null;
  collected_at: string;
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

/**
 * 신고·납부 마감일 한 건.
 *
 * 날짜가 법에 정해져 있어 수집도 AI 도 쓰지 않는다. 기한을 하루 틀리면
 * 가산세가 붙으므로 지어낼 여지를 아예 두지 않았다.
 */
export interface Deadline {
  date: string;
  title: string;
  note: string;
  audience: string;
  audience_label: string;
  /** 근거 조문. 출처 없는 날짜는 싣지 않는다. */
  basis: string;
  /** 주말이라 다음 월요일로 민 것인가. */
  shifted: boolean;
  days_left: number;
}
