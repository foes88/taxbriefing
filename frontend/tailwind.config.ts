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
        ink: {
          DEFAULT: 'var(--ink)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
        },
        rule: {
          DEFAULT: 'var(--rule)',
          strong: 'var(--rule-strong)',
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
      fontSize: {
        display: ['1.9375rem', { lineHeight: '1.28', letterSpacing: '-0.022em', fontWeight: '800' }],
        headline: ['1.1875rem', { lineHeight: '1.42', letterSpacing: '-0.014em', fontWeight: '700' }],
        record: ['1.0313rem', { lineHeight: '1.48', letterSpacing: '-0.011em', fontWeight: '700' }],
      },
      maxWidth: {
        /** 페이지 골격. 데스크톱에서 양옆이 비지 않을 만큼 넓다. */
        page: '78rem',
        /** 본문 measure. 한국어는 이 폭을 넘으면 줄 끝에서 눈이 길을 잃는다. */
        reading: '46rem',
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
