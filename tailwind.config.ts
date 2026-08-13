import type { Config } from 'tailwindcss';

/**
 * 색·간격은 globals.css 의 토큰이 정본이다. 여기서는 이름만 연결한다.
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
        bg: 'var(--bg)',
        surface: {
          DEFAULT: 'var(--surface)',
          sunk: 'var(--surface-sunk)',
        },
        ink: {
          DEFAULT: 'var(--ink)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
        },
        line: {
          DEFAULT: 'var(--line)',
          strong: 'var(--line-strong)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          weak: 'var(--accent-weak)',
          ink: 'var(--accent-ink)',
        },
        danger: {
          DEFAULT: 'var(--danger)',
          weak: 'var(--danger-weak)',
        },
        warn: {
          DEFAULT: 'var(--warn)',
          weak: 'var(--warn-weak)',
        },
        good: {
          DEFAULT: 'var(--good)',
          weak: 'var(--good-weak)',
        },

        /*
         * 관리자 화면 전용 별칭.
         *
         * 공개 화면은 위 이름으로 다시 짰지만 관리자 화면은 그대로 둔다 —
         * 검수자 한 사람이 쓰는 내부 도구라 손볼 이유가 없고, 여섯 페이지를
         * 같이 뜯으면 정작 사장님이 보는 화면을 확인할 시간이 준다.
         *
         * **공개 화면에는 쓰지 않는다.** 새 이름(line·bg·danger)을 쓴다.
         */
        rule: {
          DEFAULT: 'var(--line)',
          strong: 'var(--line-strong)',
        },
        paper: 'var(--bg)',
        seal: 'var(--danger)',
        band: {
          DEFAULT: '#191f28',
          2: '#4e5968',
        },
        state: {
          effective: 'var(--good)',
          confirmed: 'var(--accent)',
          pending: '#b45309',
          halted: 'var(--danger)',
          unknown: 'var(--ink-3)',
        },
      },
      /*
       * 큰 글자는 화면 폭을 따라간다. 36px 로 고정해 뒀더니 360px 짜리
       * 휴대폰에서 제목 한 줄이 다섯 줄로 흘렀다.
       *
       * 작은 글자는 고정하고, **바닥을 올렸다.** 예전 화면은 11~13px
       * 회색 메타가 절반이었다. 그게 "가독성이 별로" 의 실체였다.
       */
      fontSize: {
        display: [
          'clamp(1.5rem, 4.6vw, 1.875rem)',
          { lineHeight: '1.3', letterSpacing: '-0.03em', fontWeight: '700' },
        ],
        /** 카드 제목. 목록에서 가장 먼저 읽히는 크기 */
        card: ['1.0625rem', { lineHeight: '1.47', letterSpacing: '-0.02em', fontWeight: '700' }],
        /** 본문 */
        body: ['0.9375rem', { lineHeight: '1.65', letterSpacing: '-0.01em' }],
        /** 보조 정보. 이 아래로는 쓰지 않는다 */
        meta: ['0.8125rem', { lineHeight: '1.5', letterSpacing: '-0.005em' }],
      },
      maxWidth: {
        /** 화면 골격. 예전 78rem 은 데스크톱에서 한 줄이 너무 길었다 */
        page: '66rem',
        /** 본문 measure. 한국어는 이 폭을 넘으면 줄 끝에서 눈이 길을 잃는다 */
        reading: '40rem',
      },
      borderRadius: {
        card: '16px',
        field: '12px',
        /* 관리자 화면 전용 */
        sharp: '2px',
        soft: '3px',
      },
    },
  },
  plugins: [],
};

export default config;
