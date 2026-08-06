'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

/**
 * 접근 비밀번호 입력.
 *
 * useSearchParams 를 쓰므로 클라이언트 컴포넌트여야 한다.
 * 대신 주변 껍데기(제목·안내문)는 서버에서 그리도록 페이지를 나눠 두었다 —
 * 그러지 않으면 JS 가 로드될 때까지 흰 화면이 보인다.
 */
export function GateForm() {
  const router = useRouter();
  const params = useSearchParams();
  const from = params.get('from') ?? '/';

  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/gate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { message?: string };
        setError(data.message ?? '확인에 실패했습니다.');
        return;
      }
      router.replace(from);
      router.refresh();
    } catch {
      setError('네트워크 오류가 발생했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
      <label className="block">
        <span className="label">접근 비밀번호</span>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          autoFocus
          required
          className="mt-1.5 w-full rounded-sharp border border-rule-strong bg-surface px-3 py-2.5 text-[15px] text-ink focus:border-ink"
        />
      </label>

      {error ? (
        <p className="border-l-2 border-seal bg-surface-sunk px-3 py-2 text-[13px] text-seal">
          {error}
        </p>
      ) : null}

      <button type="submit" disabled={busy || !password} className="btn-primary mt-1">
        {busy ? '확인 중…' : '들어가기'}
      </button>
    </form>
  );
}

/** JS 로드 전에도 같은 자리를 차지하도록 모양을 맞춘 자리표시자. */
export function GateFormSkeleton() {
  return (
    <div className="mt-5 flex flex-col gap-3" aria-hidden>
      <div>
        <span className="label">접근 비밀번호</span>
        <div className="mt-1.5 h-[42px] w-full rounded-sharp border border-rule-strong bg-surface" />
      </div>
      <div className="mt-1 h-[42px] w-full rounded-sharp bg-surface-sunk" />
    </div>
  );
}
