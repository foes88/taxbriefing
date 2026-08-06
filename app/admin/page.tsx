'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { adminApi } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { RawContent, SourceItem } from '@/lib/types';

/** 운영 대시보드 (A-01). MVP는 수집 현황 중심이다. */
export default function AdminDashboard() {
  const [sources, setSources] = useState<SourceItem[] | null>(null);
  const [raw, setRaw] = useState<RawContent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([adminApi.sources(), adminApi.rawContents({ limit: 8 })])
      .then(([s, r]) => {
        setSources(s);
        setRaw(r);
      })
      .catch((e) => setError(e instanceof Error ? e.message : '조회 실패'));
  }, []);

  const active = sources?.filter((s) => s.status === 'ACTIVE').length ?? 0;
  const pending = sources?.filter((s) => s.status === 'PENDING_REVIEW').length ?? 0;
  const failing = sources?.filter((s) => s.failure_streak > 0).length ?? 0;

  return (
    <div>
      <h1 className="text-xl font-extrabold tracking-tight">운영 대시보드</h1>

      {error ? (
        <p className="border border-rule bg-surface mt-4 p-4 text-sm text-rose-700">{error}</p>
      ) : null}

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="등록 출처" value={sources?.length} />
        <Stat label="수집 활성" value={active} tone={active === 0 ? 'warn' : undefined} />
        <Stat label="이용조건 확인 대기" value={pending} tone={pending > 0 ? 'warn' : undefined} />
        <Stat label="수집 실패 중" value={failing} tone={failing > 0 ? 'bad' : undefined} />
      </div>

      {pending > 0 ? (
        <div className="border border-rule bg-surface mt-4 border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-bold text-amber-900">
            출처 {pending}곳이 이용조건 확인 대기 상태입니다.
          </p>
          <p className="mt-1 text-sm text-amber-800">
            자동수집 허용 방식을 확인한 뒤 ACTIVE 로 전환하세요. robots.txt·이용약관 확인 전에는
            수집하지 않습니다.
          </p>
        </div>
      ) : null}

      <section className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-bold">최근 수집 원문</h2>
          <Link href="/admin/raw" className="text-xs font-medium text-ink hover:underline">
            전체 보기 →
          </Link>
        </div>

        <div className="border border-rule bg-surface divide-y divide-rule">
          {raw === null ? (
            <p className="p-4 text-sm text-ink-3">불러오는 중…</p>
          ) : raw.length === 0 ? (
            <div className="p-6 text-center">
              <p className="text-sm font-medium">수집된 원문이 없습니다.</p>
              <p className="mt-1 text-xs text-ink-3">
                <code className="rounded bg-surface-sunk px-1">python -m app.collect</code> 를
                실행하세요.
              </p>
            </div>
          ) : (
            raw.map((item) => (
              <Link
                key={item.id}
                href={`/admin/raw/${item.id}`}
                className="flex items-center gap-3 p-3 transition hover:bg-surface-sunk"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{item.title}</p>
                  <p className="mt-0.5 text-xs text-ink-3">
                    {item.publisher} · 공포 {item.published_at?.slice(0, 10) ?? '미상'}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-ink-3">
                  {formatDateTime(item.last_checked_at)}
                </span>
              </Link>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone?: 'warn' | 'bad';
}) {
  const color =
    tone === 'bad' ? 'text-rose-600' : tone === 'warn' ? 'text-amber-600' : 'text-ink';
  return (
    <div className="border border-rule bg-surface p-4">
      <p className="label">{label}</p>
      <p className={`mt-1 text-2xl font-extrabold tabular-nums ${color}`}>
        {value ?? '—'}
      </p>
    </div>
  );
}
