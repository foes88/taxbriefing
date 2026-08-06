'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ApiRequestError, adminApi } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { RawContent } from '@/lib/types';

/**
 * 원문 상세 → 콘텐츠 생성 (A-04 → A-05 진입).
 *
 * 여기서 만든 콘텐츠는 UNVERIFIED 또는 SOURCE_CONFIRMED 로 시작한다.
 * 공식 근거(A/B등급)가 붙어 있어야 검수 요청이 가능하다 (게이트 G1, AT-03).
 */
export default function RawDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [raw, setRaw] = useState<RawContent | null>(null);
  const [versions, setVersions] = useState<
    { id: string; version_no: number; collected_at: string }[]
  >([]);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      adminApi.rawContents({ limit: 200 }).then((all) => all.find((r) => r.id === id) ?? null),
      adminApi.rawVersions(id),
    ])
      .then(([r, v]) => {
        setRaw(r);
        setVersions(v);
        if (r) setTitle(r.title);
      })
      .catch((e) => setError(e instanceof Error ? e.message : '조회 실패'));
  }, [id]);

  async function createContent() {
    const latest = versions.at(-1);
    if (!latest) {
      setError('원문 버전이 없습니다.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const content = await adminApi.createContent({
        title: title.slice(0, 120),
        source_version_ids: [latest.id],
        // 상태는 검수 단계에서 확정한다 (A-04). 생성 시점에는 UNKNOWN 이 정직하다.
        legal_status: 'UNKNOWN',
        risk_level: 'MEDIUM',
      });
      router.push(`/admin/contents/${content.id}`);
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.payload.message : '생성 실패');
      setBusy(false);
    }
  }

  if (error && !raw) {
    return <p className="border border-rule bg-surface p-4 text-sm text-state-halted">{error}</p>;
  }
  if (!raw) return <p className="text-sm text-ink-3">불러오는 중…</p>;

  return (
    <div>
      <Link href="/admin/raw" className="text-[13px] font-semibold text-ink-3 hover:text-ink">
        ← 수집 원문
      </Link>

      <article className="mt-3 border border-rule bg-surface p-5">
        <h1 className="text-headline text-ink">{raw.title}</h1>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-3">
          <span>{raw.publisher}</span>
          <span className="tabular">공포 {raw.published_at?.slice(0, 10) ?? '미상'}</span>
          <span className="tabular">최초 수집 {formatDateTime(raw.first_collected_at)}</span>
          <span className="tabular">최종 확인 {formatDateTime(raw.last_checked_at)}</span>
        </div>
        <a
          href={raw.canonical_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2.5 inline-block text-[15px] font-semibold text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
        >
          공식 원문 보기 ↗
        </a>

        <section className="mt-5 border-t border-rule pt-4">
          <h2 className="label">버전 이력 ({versions.length})</h2>
          <ul className="mt-2 flex flex-col gap-1 text-[12px] text-ink-2">
            {versions.map((v) => (
              <li key={v.id} className="flex gap-3">
                <span className="tabular font-semibold text-ink">v{v.version_no}</span>
                <span className="tabular">{formatDateTime(v.collected_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </article>

      <section className="mt-4 border border-rule bg-surface p-5">
        <h2 className="label">사업자용 콘텐츠 만들기</h2>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-2">
          최신 버전이 주 근거(PRIMARY)로 연결됩니다. 정책 상태와 시행일은 검수 단계에서 원문을
          대조해 확정합니다.
        </p>

        <label className="mt-4 block">
          <span className="label">사업자용 제목 (120자 이내)</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            className="mt-1.5 w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2 text-[15px] text-ink focus:border-ink"
          />
        </label>

        {error ? (
          <p className="mt-3 border-l-2 border-state-halted bg-surface-sunk px-3 py-2 text-[13px] text-state-halted">
            {error}
          </p>
        ) : null}

        <button
          type="button"
          onClick={createContent}
          disabled={busy || !title.trim()}
          className="btn-primary mt-4"
        >
          {busy ? '생성 중…' : '콘텐츠 초안 만들기'}
        </button>
      </section>
    </div>
  );
}
