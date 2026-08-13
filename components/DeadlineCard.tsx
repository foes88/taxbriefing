import { formatDate } from '@/lib/format';
import type { Deadline } from '@/lib/types';

/**
 * 신고·납부 마감일 한 건.
 *
 * **남은 날짜가 제목보다 먼저다.** 실무자가 이 화면에서 찾는 것은
 * "무슨 신고가 있나" 가 아니라 "며칠 남았나" 다. 그래서 D-day 를
 * 왼쪽에 크게 놓고 제목을 옆에 붙인다.
 *
 * 근거 조문을 같이 적는다. 날짜가 법에 정해져 있다는 것이 이 화면의
 * 값이고, 어디에 정해져 있는지 보이지 않으면 그냥 남의 달력이다.
 */
export function DeadlineCard({ deadline }: { deadline: Deadline }) {
  const days = deadline.days_left;
  // 일주일 안이면 붉게. 그 밖에는 조용히 둔다 — 세 달치를 다 붉게 칠하면
  // 급한 것이 안 보인다.
  const urgent = days <= 7;

  return (
    <div className="card flex gap-4 px-5 py-4">
      <div className="w-12 shrink-0 text-center">
        <div
          className={`tabular text-[19px] font-extrabold leading-none ${
            urgent ? 'text-danger' : 'text-ink'
          }`}
        >
          {days === 0 ? '오늘' : `D-${days}`}
        </div>
        <div className="tabular mt-1 text-[11.5px] text-ink-3">
          {deadline.date.slice(5).replace('-', '.')}
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`pill ${urgent ? 'pill-danger' : 'pill-calm'}`}>
            {deadline.audience_label}
          </span>
          {/*
            주말이라 민 것은 밝힌다. 원래 25일인 줄 아는 사람이
            "왜 27일이지" 하고 멈추지 않도록.
          */}
          {deadline.shifted ? <span className="pill pill-calm">주말 이월</span> : null}
        </div>

        <h3 className="mt-2 text-card text-ink">{deadline.title}</h3>
        <p className="mt-1 text-body text-ink-2">{deadline.note}</p>
        <p className="mt-1.5 text-meta text-ink-3">{deadline.basis}</p>
      </div>
    </div>
  );
}
