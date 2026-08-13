import type { Config } from 'tailwindcss';

/**
 * 색·간격은 globals.css 의 토큰이 정본이다. 여기서는 이름만 연결한다.
 * 다크 모드까지 토큰 한 곳에서 뒤집히므로 컴포넌트는 테마를 몰라도 된다.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Pretendard Variable',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'Apple SD Gothic Neo',
          'Malgun Gothic',
          'sans-serif',
        ],
      },
      colors: {
        paper: 'var(--paper)',
        surface: {
          DEFAULT: 'var(--surface)',
          sunk: 'var(--surface-sunk)',
        },
        band: {
          DEFAULT: 'var(--band)',
          2: 'var(--band-2)',
        },
        ink: {
          DEFAULT: 'var(--ink)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
        },
        rule: {
          DEFAULT: 'var(--rule)',
          strong: 'var(--rule-strong)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          soft: 'var(--accent-soft)',
        },
        seal: 'var(--seal)',
        state: {
          effective: 'var(--state-effective)',
          confirmed: 'var(--state-confirmed)',
          pending: 'var(--state-pending)',
          halted: 'var(--state-halted)',
          unknown: 'var(--state-unknown)',
        },
      },
      /*
       * 큰 글자는 화면 폭을 따라간다.
       *
       * 36px 로 고정해 뒀더니 360px 짜리 휴대폰에서 제목 한 줄이
       * "2026년 7월 1일부터 학원 사업장의 4대보험 가입 기준이 바뀝니다"
       * 다섯 줄로 흘렀다. 데스크톱에서 존재감을 주던 크기가 휴대폰에서는
       * 그냥 화면을 다 먹는다.
       *
       * 작은 글자(record 18px, 본문 16px)는 고정한다. 그 아래로 줄이면
       * 읽기 힘들어지지, 공간이 절약되지 않는다.
       */
      fontSize: {
        display: [
          'clamp(1.625rem, 5.4vw, 2.25rem)',
          { lineHeight: '1.24', letterSpacing: '-0.028em', fontWeight: '800' },
        ],
        headline: [
          'clamp(1.1875rem, 3.4vw, 1.375rem)',
          { lineHeight: '1.4', letterSpacing: '-0.018em', fontWeight: '700' },
        ],
        /** 목록 제목. 훑을 때 가장 먼저 읽히는 크기다. */
        record: ['1.125rem', { lineHeight: '1.44', letterSpacing: '-0.014em', fontWeight: '700' }],
      },
      maxWidth: {
        /** 페이지 골격. 데스크톱에서 양옆이 비지 않을 만큼 넓다. */
        page: '78rem',
        /**
         * 본문 measure. 한국어는 이 폭을 넘으면 줄 끝에서 눈이 길을 잃는다.
         * 뉴스 탭은 사이드바가 없어 요약이 1200px 를 가로질렀다 — 한 줄에
         * 120자가 넘었고, 그게 "가독성이 떨어진다"의 실체였다.
         */
        reading: '42rem',
      },
      borderRadius: {
        sharp: '2px',
        soft: '3px',
      },
    },
  },
  plugins: [],
};

export default config;
