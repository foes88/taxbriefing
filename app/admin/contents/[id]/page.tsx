'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { ApiRequestError, adminApi } from '@/lib/api';
import type {
  AdminContent,
  ContentSourceRef,
  GateReport,
  LegalStatus,
  RiskLevel,
} from '@/lib/types';

const LEGAL_OPTIONS: { value: LegalStatus; label: string }[] = [
  { value: 'UNKNOWN', label: '상태 확인 필요' },
  { value: 'DISCUSSION', label: '검토·논의' },
  { value: 'BILL_PROPOSED', label: '법안 발의' },
  { value: 'PREANNOUNCED', label: '입법·행정예고' },
  { value: 'GOV_ANNOUNCED', label: '정부안 발표' },
  { value: 'ASSEMBLY_PASSED', label: '국회 통과' },
  { value: 'PROMULGATED', label: '공포' },
  { value: 'EFFECTIVE', label: '시행' },
  { value: 'SUSPENDED', label: '유예·효력정지' },
  { value: 'ABOLISHED', label: '폐지' },
];

const RISK_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: 'LOW', label: '참고' },
  { value: 'MEDIUM', label: '안내' },
  { value: 'HIGH', label: '중요' },
  { value: 'CRITICAL', label: '긴급' },
];

/**
 * 검수 편집기 (A-05).
 *
 * 이 화면의 핵심은 **왜 발송할 수 없는지 보여주는 것**이다.
 * 게이트 판정을 숨기고 승인 버튼만 두면 검수자가 이유를 모른 채 막히거나,
 * 더 나쁘게는 우회 방법을 찾게 된다.
 */
export default function ContentEditorPage() {
  const { id } = useParams<{ id: string }>();

  const [content, setContent] = useState<AdminContent | null>(null);
  const [gates, setGates] = useState<GateReport | null>(null);
  const [sources, setSources] = useState<ContentSourceRef[]>([]);
  /** 검수자가 실제로 대조한 원문 버전. 승인 기록에 그대로 남는다 (AT-12). */
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [legal, setLegal] = useState<LegalStatus>('UNKNOWN');
  const [risk, setRisk] = useState<RiskLevel>('MEDIUM');
  const [summary, setSummary] = useState('');
  const [effective, setEffective] = useState('');
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    const [c, g, s] = await Promise.all([
      adminApi.content(id),
      adminApi.gates(id),
      adminApi.contentSources(id),
    ]);
    setContent(c);
    setGates(g);
    setSources(s);
    setLegal(c.legal_status);
    setRisk(c.risk_level);
    setSummary(c.one_line_summary ?? '');
    setEffective(c.effective_date ?? '');
  }, [id]);

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : '조회 실패'));
  }, [load]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof ApiRequestError ? describeError(e) : '요청 실패');
    } finally {
      setBusy(false);
    }
  }

  const save = () =>
    act(async () => {
      if (!content) return;
      const result = await adminApi.patchContent(
        id,
        {
          legal_status: legal,
          risk_level: risk,
          one_line_summary: summary || null,
          effective_date: effective || null,
        },
        content.version,
      );
      setMessage(
        result.approval_revoked ? `저장했습니다. ${result.message ?? ''}` : '저장했습니다.',
      );
    });

  const submit = () =>
    act(async () => {
      await adminApi.submitReview(id);
      setMessage('검수 요청했습니다. 검수자 계정으로 로그인해 승인하세요.');
    });

  const approve = () =>
    act(async () => {
      if (checked.size === 0) {
        throw new ApiRequestError(422, {
          code: 'NO_CHECKED_SOURCE',
          message: '대조한 원문을 하나 이상 선택하세요. 무엇을 보고 승인했는지가 기록됩니다.',
          details: {},
          trace_id: '',
        });
      }
      await adminApi.review(id, {
        decision: 'APPROVE',
        review_note: note || '원문 대조 확인 완료',
        checked_source_version_ids: Array.from(checked),
        legal_status: legal,
        risk_level: risk,
      });
      setChecked(new Set());
      setMessage('승인했습니다.');
    });

  const reject = () =>
    act(async () => {
      if (!note.trim()) {
        throw new ApiRequestError(422, {
          code: 'NO_REASON',
          message: '반려 사유를 적어주세요.',
          details: {},
          trace_id: '',
        });
      }
      await adminApi.review(id, {
        decision: 'REJECT',
        review_note: note,
        checked_source_version_ids: Array.from(checked).length
          ? Array.from(checked)
          : sources.slice(0, 1).map((s) => s.raw_content_version_id),
      });
      setMessage('반려했습니다.');
    });

  const toggleChecked = (versionId: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(versionId)) next.delete(versionId);
      else next.add(versionId);
      return next;
    });

  if (error && !content) {
    return <p className="border border-rule bg-surface p-4 text-sm text-state-halted">{error}</p>;
  }
  if (!content) return <p className="text-sm text-ink-3">불러오는 중…</p>;

  return (
    <div>
      <Link href="/admin/raw" className="text-[13px] font-semibold text-ink-3 hover:text-ink">
        ← 목록
      </Link>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="tag border border-ink text-ink">{content.workflow_status}</span>
        <span className="tabular text-[12px] text-ink-3">
          신뢰도 {content.source_confidence}/100 · v{content.version}
        </span>
      </div>

      <h1 className="mt-2 text-headline text-ink">{content.title}</h1>

      {gates ? <GatePanel report={gates} /> : null}

      <section className="mt-4 border border-rule bg-surface p-5">
        <h2 className="label">콘텐츠 편집</h2>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-2">
          승인 후 보호 필드를 수정하면 승인이 자동 해제되고 재검수 큐로 돌아갑니다.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="정책 법적 상태">
            <select
              value={legal}
              onChange={(e) => setLegal(e.target.value as LegalStatus)}
              className="w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink"
            >
              {LEGAL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="위험도">
            <select
              value={risk}
              onChange={(e) => setRisk(e.target.value as RiskLevel)}
              className="w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink"
            >
              {RISK_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="시행일 (원문에 없으면 비워 두세요)">
            <input
              type="date"
              value={effective}
              onChange={(e) => setEffective(e.target.value)}
              className="w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink"
            />
          </Field>

          <Field label="한 줄 요약">
            <input
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              maxLength={250}
              placeholder="무엇이 어떻게 달라지는지 한 문장"
              className="w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink placeholder:text-ink-3"
            />
          </Field>
        </div>

        {/*
          AT-12: "누가 어떤 근거를 확인하고 승인했는가"가 남아야 한다.
          체크 없이 승인 버튼만 두면 그 기록이 형식이 된다.
        */}
        <fieldset className="mt-5 border-t border-rule pt-4">
          <legend className="label">대조한 원문 (승인 시 기록됨)</legend>
          {sources.length === 0 ? (
            <p className="mt-2 text-[13px] text-ink-3">연결된 원문이 없습니다.</p>
          ) : (
            <ul className="mt-2.5 flex flex-col gap-1.5">
              {sources.map((s) => (
                <li key={s.raw_content_version_id}>
                  <label className="flex cursor-pointer items-start gap-2.5 border border-rule px-3 py-2.5 transition-colors hover:border-ink-3">
                    <input
                      type="checkbox"
                      checked={checked.has(s.raw_content_version_id)}
                      onChange={() => toggleChecked(s.raw_content_version_id)}
                      className="mt-[3px] h-4 w-4 shrink-0 accent-[color:var(--ink)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`seal ${
                            s.authority === 'A' || s.authority === 'B'
                              ? 'border-ink text-ink'
                              : 'border-rule-strong text-ink-3'
                          }`}
                        >
                          {s.authority}등급
                        </span>
                        <span className="text-[12px] font-semibold text-ink-2">
                          {s.publisher}
                        </span>
                        <span className="tabular text-[11px] text-ink-3">v{s.version_no}</span>
                      </span>
                      <span className="mt-1 block text-[14px] font-semibold leading-snug text-ink">
                        {s.title}
                      </span>
                      <a
                        href={s.canonical_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="mt-0.5 inline-block text-[12px] text-ink-3 underline underline-offset-2 hover:text-ink"
                      >
                        원문 열기 ↗
                      </a>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>

        <label className="mt-4 block">
          <span className="label">검수 메모</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="무엇을 확인했는지, 무엇이 미확인인지 남기세요"
            className="mt-1.5 w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink placeholder:text-ink-3"
          />
        </label>

        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={save} disabled={busy} className="btn-primary">
            저장
          </button>
          <button type="button" onClick={submit} disabled={busy} className="btn-quiet">
            검수 요청
          </button>
          <button
            type="button"
            onClick={approve}
            disabled={busy || !gates?.can_approve || checked.size === 0}
            title={
              !gates?.can_approve
                ? '게이트를 통과하지 못했습니다'
                : checked.size === 0
                  ? '대조한 원문을 선택하세요'
                  : undefined
            }
            className="btn text-white disabled:opacity-40"
            style={{ background: 'var(--state-effective)' }}
          >
            승인 {checked.size > 0 ? `(원문 ${checked.size}건 확인)` : '(검수자만)'}
          </button>
          <button
            type="button"
            onClick={reject}
            disabled={busy}
            className="btn border text-state-halted"
            style={{ borderColor: 'var(--state-halted)' }}
          >
            반려
          </button>
        </div>

        {message ? (
          <p className="mt-4 border-l-2 border-state-effective bg-surface-sunk px-3 py-2 text-[13px] text-ink">
            {message}
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 whitespace-pre-line border-l-2 border-state-halted bg-surface-sunk px-3 py-2 text-[13px] text-state-halted">
            {error}
          </p>
        ) : null}
      </section>

      <ConfidencePanel content={content} />
    </div>
  );
}

function describeError(e: ApiRequestError): string {
  if (e.payload.code === 'GATE_FAILED') {
    const failed = (e.payload.details.failed_gates as string[] | undefined) ?? [];
    return `${e.payload.message}\n실패한 게이트: ${failed.join(', ')}`;
  }
  return e.payload.message;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function GatePanel({ report }: { report: GateReport }) {
  const failed = report.results.filter((r) => !r.passed);
  return (
    <section
      className={`mt-4 border-l-2 bg-surface p-4 ${
        report.can_approve ? 'border-state-effective' : 'border-state-pending'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="label">검증 게이트</h2>
        <Flag ok={report.can_approve} label="승인" />
        <Flag ok={report.can_schedule} label="발송" />
        <Flag ok={report.can_personalize} label="개인화" />
      </div>

      {failed.length === 0 ? (
        <p className="mt-2.5 text-[13px] text-state-effective">모든 게이트를 통과했습니다.</p>
      ) : (
        <ul className="mt-2.5 flex flex-col gap-2.5">
          {failed.map((r) => (
            <li key={r.gate}>
              <p className="text-[12px] font-bold text-ink">
                {r.gate}
                {r.consequence ? (
                  <span className="ml-2 font-semibold text-state-halted">{r.consequence}</span>
                ) : null}
              </p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">{r.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Flag({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`seal ${
        ok ? 'border-state-effective text-state-effective' : 'border-state-halted text-state-halted'
      }`}
    >
      {ok ? '가능' : '불가'} {label}
    </span>
  );
}

function ConfidencePanel({ content }: { content: AdminContent }) {
  const components = content.confidence_breakdown?.components ?? [];
  if (components.length === 0) return null;

  return (
    <section className="mt-4 border border-rule bg-surface p-5">
      <h2 className="label">신뢰도 산정 내역</h2>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-2">
        사실의 확률이 아니라 내부 처리 우선순위 점수입니다. 점수만으로 확정하지 않습니다.
      </p>
      <ul className="mt-3 divide-y divide-rule border-y border-rule">
        {components.map((c) => (
          <li key={c.key} className="flex items-baseline justify-between gap-3 py-2.5 text-[13px]">
            <span className="text-ink-2">
              <span className="font-semibold text-ink">{c.label}</span>
              <span className="ml-2 text-[12px] text-ink-3">{c.explanation}</span>
            </span>
            <span className="tabular shrink-0 font-bold text-ink">
              {c.points}/{c.max_points}
            </span>
          </li>
        ))}
      </ul>
      <p className="tabular mt-3 text-right text-[13px] font-bold text-ink">
        합계 {content.source_confidence}/100
      </p>
    </section>
  );
}
