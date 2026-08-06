'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { adminApi } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { RawContent } from '@/lib/types';

/** 수집 원문 목록 (A-03). 여기서 콘텐츠 작성으로 넘어간다. */
export default function RawContentsPage() {
  const [items, setItems] = useState<RawContent[] | null>(null);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = (query?: string) => {
    setItems(null);
    adminApi
      .rawContents({ q: query, limit: 100 })
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : '조회 실패'));
  };

  useEffect(() => load(), []);

  return (
    <div>
      <h1 className="text-xl font-extrabold tracking-tight">수집 원문</h1>
      <p className="mt-1 text-sm text-ink-2">
        법령·행정규칙 원문입니다. 사업자용 콘텐츠로 가공하려면 항목을 선택하세요.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(q || undefined);
        }}
        className="mt-4 flex gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="법령명 검색 (예: 부가가치세)"
          className="min-w-0 flex-1 rounded-lg border border-rule px-3 py-2 text-sm"
        />
        <button
          type="submit"
          className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white"
        >
          검색
        </button>
      </form>

      {error ? <p className="border border-rule bg-surface mt-4 p-4 text-sm text-rose-700">{error}</p> : null}

      <div className="border border-rule bg-surface mt-4 divide-y divide-rule">
        {items === null ? (
          <p className="p-4 text-sm text-ink-3">불러오는 중…</p>
        ) : items.length === 0 ? (
          <p className="p-6 text-center text-sm text-ink-3">결과가 없습니다.</p>
        ) : (
          items.map((item) => (
            <Link
              key={item.id}
              href={`/admin/raw/${item.id}`}
              className="block p-4 transition hover:bg-surface-sunk"
            >
              <p className="text-sm font-semibold">{item.title}</p>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
                <span>{item.publisher}</span>
                <span>공포 {item.published_at?.slice(0, 10) ?? '미상'}</span>
                <span>최종 확인 {formatDateTime(item.last_checked_at)}</span>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
