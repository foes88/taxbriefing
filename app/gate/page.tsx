import { Suspense } from 'react';

import { GateForm, GateFormSkeleton } from '@/components/GateForm';
import { Wordmark } from '@/components/Logo';

/**
 * 접근 잠금 화면.
 *
 * 회원가입도 아이디도 없다. 공유 비밀번호 하나로 들어온다 (ADR-002 보완).
 *
 * 껍데기는 서버에서 그린다. 전체를 클라이언트 컴포넌트로 두면 JS 가 로드될 때까지
 * 흰 화면이 보이는데, 첫 화면이 흰 화면이면 사이트가 죽은 것처럼 보인다.
 */
export const metadata = {
  title: '접근 확인 — TaxBriefing',
  robots: { index: false, follow: false },
};

export default async function GatePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const unset = params.reason === 'unset';

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <Wordmark tone="dark" />
          <div aria-hidden className="mt-3 h-[3px] w-10 bg-accent" />
        </div>

        {unset ? (
          <div className="card mb-4 border-l-4 border-danger px-4 py-3">
            <p className="text-[13.5px] font-bold text-danger">접근 비밀번호가 설정되지 않았습니다</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">
              배포 환경의 환경변수에{' '}
              <code className="bg-surface-sunk px-1 py-0.5 font-mono text-[12px]">
                SITE_PASSWORD
              </code>{' '}
              를 설정한 뒤 다시 배포하세요.
            </p>
          </div>
        ) : null}

        <div className="border border-rule bg-surface p-6">
          <h1 className="text-[15px] font-bold text-ink">비공개 사이트입니다</h1>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">
            전달받으신 접근 비밀번호를 입력하세요.
          </p>

          <Suspense fallback={<GateFormSkeleton />}>
            <GateForm />
          </Suspense>
        </div>

        <p className="mt-4 text-[12px] leading-relaxed text-ink-3">
          이 사이트는 세무·정책 공식 발표를 정리해 전달합니다. 접근 권한이 필요하시면 담당자에게
          문의해 주세요.
        </p>
      </div>
    </div>
  );
}
