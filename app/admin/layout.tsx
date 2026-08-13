'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Logo } from '@/components/Logo';
import { auth } from '@/lib/api';

const NAV = [
  { href: '/admin', label: '대시보드' },
  { href: '/admin/raw', label: '수집 원문' },
  { href: '/admin/sources', label: '출처 관리' },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === '/admin/login';
  const [ready, setReady] = useState(isLogin);

  useEffect(() => {
    if (isLogin) {
      setReady(true);
      return;
    }
    if (!auth.read()) router.replace('/admin/login');
    else setReady(true);
  }, [isLogin, pathname, router]);

  if (isLogin) return <>{children}</>;
  if (!ready) return null;

  return (
    <div className="min-h-screen">
      <header className="border-b border-rule bg-surface">
        <div className="mx-auto flex max-w-page flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
          <Link
            href="/admin"
            className="flex items-center gap-2 text-base font-extrabold tracking-tight text-ink"
          >
            <Logo size={20} />
            TaxBriefing<span className="ml-0.5 text-xs font-medium text-ink-3">관리자</span>
          </Link>

          <nav className="flex gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  pathname === item.href
                    ? 'bg-surface-sunk text-ink'
                    : 'text-ink-2 hover:bg-surface-sunk'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <Link href="/" className="text-xs text-ink-3 hover:text-ink">
              공개 사이트 ↗
            </Link>
            <button
              type="button"
              onClick={() => {
                auth.clear();
                router.replace('/admin/login');
              }}
              className="text-xs font-medium text-ink-3 hover:text-rose-600"
            >
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-page px-4 py-6">{children}</main>
    </div>
  );
}
