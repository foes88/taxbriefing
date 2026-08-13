'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Wordmark } from '@/components/Logo';
import { ApiRequestError, auth } from '@/lib/api';

export default function AdminLoginPage() {
  const router = useRouter();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.login(id, password);
      router.push('/admin');
    } catch (e) {
      setError(
        e instanceof ApiRequestError ? e.payload.message : '로그인에 실패했습니다.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="border border-rule bg-surface w-full max-w-sm p-7">
        <h1>
          <Wordmark tone="dark" />
        </h1>
        <p className="mt-1 text-sm text-ink-2">관리자 로그인</p>

        <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="label">아이디</span>
            <input
              value={id}
              onChange={(e) => setId(e.target.value)}
              autoComplete="username"
              required
              className="rounded-lg border border-rule px-3 py-2 text-sm"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="label">비밀번호</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="rounded-lg border border-rule px-3 py-2 text-sm"
            />
          </label>

          {error ? (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-lg bg-ink px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-black disabled:opacity-50"
          >
            {busy ? '확인 중…' : '로그인'}
          </button>
        </form>

        {/*
          개발 계정 안내는 개발 빌드에서만 보여준다.
          배포된 화면에 기본 계정이 적혀 있으면 그 자체가 취약점이다.
          이 조건은 빌드 시점에 정적으로 평가되어 운영 번들에서 통째로 제거된다.
        */}
        {process.env.NODE_ENV !== 'production' ? (
          <div className="mt-5 bg-surface-sunk p-3 text-xs leading-relaxed text-ink-2">
            <p className="font-semibold text-ink">로컬 개발 계정</p>
            <p className="mt-1">
              운영자·관리자 <code className="bg-white px-1">admin / admin1234</code>
              <br />
              검수자 <code className="bg-white px-1">reviewer / reviewer1234</code>
            </p>
          </div>
        ) : null}

        <p className="mt-4 text-[12px] leading-relaxed text-ink-3">
          승인은 검수자만 할 수 있습니다. 최고관리자도 승인할 수 없습니다.
        </p>
      </div>
    </div>
  );
}
