import type {
  AdminContent,
  ApiError,
  GateReport,
  MonthBucket,
  PublicContentDetail,
  PublicFeed,
  RawContent,
  SourceItem,
  TokenResponse,
} from './types';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/api/v1';

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly payload: ApiError,
  ) {
    super(payload.message);
    this.name = 'ApiRequestError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    let payload: ApiError;
    try {
      payload = (await response.json()) as ApiError;
    } catch {
      payload = {
        code: 'NETWORK_ERROR',
        message: `요청이 실패했습니다 (HTTP ${response.status})`,
        details: {},
        trace_id: '',
      };
    }
    throw new ApiRequestError(response.status, payload);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/* ---------------------------------------------------------------- 공개 */

export interface FeedFilters {
  q?: string;
  legal_status?: string[];
  risk_level?: string[];
  month?: string;
  deadline_within_days?: number;
  limit?: number;
  offset?: number;
}

function toQuery(filters: FeedFilters): string {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  filters.legal_status?.forEach((v) => params.append('legal_status', v));
  filters.risk_level?.forEach((v) => params.append('risk_level', v));
  if (filters.month) params.set('month', filters.month);
  if (filters.deadline_within_days) {
    params.set('deadline_within_days', String(filters.deadline_within_days));
  }
  params.set('limit', String(filters.limit ?? 20));
  if (filters.offset) params.set('offset', String(filters.offset));
  return params.toString();
}

export const publicApi = {
  feed: (filters: FeedFilters = {}) => request<PublicFeed>(`/public/feed?${toQuery(filters)}`),
  content: (id: string) => request<PublicContentDetail>(`/public/contents/${id}`),
  months: () => request<MonthBucket[]>('/public/months'),
};

/* ---------------------------------------------------------------- 관리자 */

const TOKEN_KEY = 'taxbriefing.admin.token';

export const auth = {
  save(token: string) {
    if (typeof window !== 'undefined') window.localStorage.setItem(TOKEN_KEY, token);
  },
  read(): string | null {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  clear() {
    if (typeof window !== 'undefined') window.localStorage.removeItem(TOKEN_KEY);
  },
  async login(email: string, password: string) {
    const result = await request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    auth.save(result.access_token);
    return result;
  },
};

function authed(init: RequestInit = {}): RequestInit {
  const token = auth.read();
  return {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
}

/** 쓰기 요청마다 새로 만든다 (§8.1 NFR-005). */
function idempotencyKey(): Record<string, string> {
  const value =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return { 'Idempotency-Key': value };
}

export const adminApi = {
  sources: () => request<SourceItem[]>('/sources', authed()),

  rawContents: (params: { q?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.q) query.set('q', params.q);
    query.set('limit', String(params.limit ?? 50));
    return request<RawContent[]>(`/raw-contents?${query}`, authed());
  },

  rawVersions: (id: string) =>
    request<{ id: string; version_no: number; content_hash: string; collected_at: string }[]>(
      `/raw-contents/${id}/versions`,
      authed(),
    ),

  content: (id: string) => request<AdminContent>(`/contents/${id}`, authed()),

  gates: (id: string) => request<GateReport>(`/contents/${id}/gates`, authed()),

  createContent: (body: {
    title: string;
    source_version_ids: string[];
    legal_status?: string;
    risk_level?: string;
    body?: Record<string, unknown>;
  }) =>
    request<AdminContent>('/contents', {
      ...authed({ method: 'POST', body: JSON.stringify(body) }),
      headers: { ...authed().headers, ...idempotencyKey(), 'Content-Type': 'application/json' },
    }),

  patchContent: (id: string, patch: Record<string, unknown>, version?: number) =>
    request<{
      content: AdminContent;
      approval_revoked: boolean;
      protected_fields_changed: string[];
      message: string | null;
    }>(`/contents/${id}`, {
      ...authed({ method: 'PATCH', body: JSON.stringify(patch) }),
      headers: {
        ...authed().headers,
        'Content-Type': 'application/json',
        ...(version !== undefined ? { 'If-Match': String(version) } : {}),
      },
    }),

  addEvidence: (
    id: string,
    body: { field_name: string; raw_content_version_id: string; locator: string },
  ) =>
    request<{ evidence_id: string }>(`/contents/${id}/evidence`, {
      ...authed({ method: 'POST', body: JSON.stringify(body) }),
      headers: { ...authed().headers, 'Content-Type': 'application/json' },
    }),

  submitReview: (id: string) =>
    request<{ content: AdminContent; gate_report: GateReport }>(
      `/contents/${id}/submit-review`,
      {
        ...authed({ method: 'POST' }),
        headers: { ...authed().headers, ...idempotencyKey() },
      },
    ),

  review: (
    id: string,
    body: {
      decision: 'APPROVE' | 'APPROVE_WITH_EDIT' | 'REJECT';
      review_note: string;
      checked_source_version_ids: string[];
      legal_status?: string;
      risk_level?: string;
    },
  ) =>
    request<{ content: AdminContent; gate_report: GateReport }>(`/contents/${id}/reviews`, {
      ...authed({ method: 'POST', body: JSON.stringify(body) }),
      headers: { ...authed().headers, ...idempotencyKey(), 'Content-Type': 'application/json' },
    }),

  audit: (id: string) =>
    request<
      {
        id: number;
        occurred_at: string;
        action: string;
        reason: string | null;
        after_data: Record<string, unknown> | null;
      }[]
    >(`/contents/${id}/audit`, authed()),
};
