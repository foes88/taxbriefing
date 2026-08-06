import type { Metadata, Viewport } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'TaxBriefing — 공식 원문으로 확인한 세무 브리핑',
  description:
    '국세·지방세·노무·4대보험·지원사업 관련 공식 발표를 법령·관보 원문으로 확인하고, 세무전문가 검수를 거쳐 사업자에게 전달합니다.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#f5f6f8',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // colorScheme: light — 브라우저가 폼 컨트롤을 임의로 어둡게 바꾸지 못하게 한다.
    <html lang="ko" style={{ colorScheme: 'light' }}>
      <head>
        {/*
          Pretendard. 한국어 화면 가독성의 실질 표준이다.
          명조 계열은 관보 느낌에는 맞지만 화면에서 획이 얇아 흐려지므로 쓰지 않는다.
          개성은 레이아웃(일자 거터·도장·헤어라인·인주색)이 나르고, 글꼴은 읽기에만 집중한다.

          dynamic-subset 은 실제로 쓰인 글자만 내려받는다 — 한글 전체를 받으면 수 MB다.
        */}
        <link rel="preconnect" href="https://cdn.jsdelivr.net" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
