'use client';

import { useEffect, useState } from 'react';

import { AuthorityTag } from '@/components/Authority';
import { adminApi } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { SourceItem } from '@/lib/types';

/** 출처 관리 (A-02, 부록 A). 출처는 코드가 아니라 DB에서 관리한다. */
export default function SourcesPage() {
  const [items, setItems] = useState<SourceItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .sources()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : '조회 실패'));
  }, []);

  return (
    <div>
      <h1 className="text-xl font-extrabold tracking-tight">출처 관리</h1>
      <p className="mt-1 text-sm text-ink-2">
        기관이 개편되어도 코드를 고치지 않습니다. 여기서 관리합니다.
      </p>

      {error ? <p className="border border-rule bg-surface mt-4 p-4 text-sm text-rose-700">{error}</p> : null}

      <div className="border border-rule bg-surface mt-4 overflow-x-auto">
        <table className="w-full min-w-[42rem] text-sm">
          <thead>
            <tr className="border-b border-rule text-left">
              <Th>출처</Th>
              <Th>등급</Th>
              <Th>수집방식</Th>
              <Th>상태</Th>
              <Th>최근 성공</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {items === null ? (
              <tr>
                <td colSpan={5} className="p-4 text-sm text-ink-3">
                  불러오는 중…
                </td>
              </tr>
            ) : (
              items.map((s) => (
                <tr key={s.id}>
                  <td className="p-3">
                    <p className="font-semibold">{s.display_name}</p>
                    <p className="text-xs text-ink-3">{s.canonical_domain}</p>
                  </td>
                  <td className="p-3">
                    <AuthorityTag grade={s.authority} />
                  </td>
                  <td className="p-3 text-xs text-ink-2">{s.collector_type}</td>
                  <td className="p-3">
                    <StatusPill status={s.status} failing={s.failure_streak > 0} />
                  </td>
                  <td className="p-3 text-xs text-ink-3">
                    {s.last_success_at ? formatDateTime(s.last_success_at) : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        <strong className="text-ink-2">PENDING_REVIEW</strong> 는 이용조건·자동수집 허용
        방식을 아직 확인하지 않은 상태입니다. robots.txt 우회·로그인 우회는 구현하지 않으며,
        확인 전에는 수집하지 않습니다.
      </p>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="p-3 text-xs font-semibold uppercase tracking-wide text-ink-3">{children}</th>;
}

function StatusPill({ status, failing }: { status: string; failing: boolean }) {
  if (failing) return <span className="tag bg-rose-100 text-rose-800">수집 실패</span>;
  if (status === 'ACTIVE') return <span className="tag bg-emerald-100 text-emerald-800">수집 중</span>;
  if (status === 'PENDING_REVIEW')
    return <span className="tag bg-amber-100 text-amber-900">확인 대기</span>;
  return <span className="tag bg-slate-100 text-slate-600">{status}</span>;
}

