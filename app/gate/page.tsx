'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

/**
 * 접근 잠금 화면.
 *
 * 회원가입도 아이디도 없다. 공유 비밀번호 하나로 들어온다.
 * "무엇을 입력해야 하는지"가 바로 보여야 하므로 설명을 숨기지 않는다.
 */
function GateForm() {
  const router = useRouter();
  const params = useSearchParams();
  const from = params.get('from') ?? '/';
  const unset = params.get('reason') === 'unset';

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
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <p className="text-[19px] font-extrabold tracking-[-0.02em] text-ink">TaxBriefing</p>
          <div aria-hidden className="mt-2 h-[2px] w-10 bg-seal" />
        </div>

        {unset ? (
          <div className="mb-4 border-l-2 border-seal bg-surface px-4 py-3">
            <p className="text-[13px] font-bold text-seal">접근 비밀번호가 설정되지 않았습니다</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">
              배포 환경에서{' '}
              <code className="bg-surface-sunk px-1 py-0.5 font-mono text-[12px]">
                SITE_PASSWORD
              </code>{' '}
              환경변수를 설정한 뒤 다시 배포하세요.
            </p>
          </div>
        ) : null}

        <div className="border border-rule bg-surface p-6">
          <h1 className="text-[15px] font-bold text-ink">비공개 사이트입니다</h1>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">
            전달받으신 접근 비밀번호를 입력하세요.
          </p>

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
        </div>

        <p className="mt-4 text-[12px] leading-relaxed text-ink-3">
          이 사이트는 세무·정책 공식 발표를 정리해 전달합니다. 접근 권한이 필요하시면 담당자에게
          문의해 주세요.
        </p>
      </div>
    </div>
  );
}

export default function GatePage() {
  return (
    <Suspense fallback={null}>
      <GateForm />
    </Suspense>
  );
}
