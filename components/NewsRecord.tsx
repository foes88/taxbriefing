import { formatDateCompact } from '@/lib/format';
import type { NewsItem } from '@/lib/types';

/**
 * 언론 보도 한 건.
 *
 * `ContentRecord` 와 두 가지가 다르고, 둘 다 의도한 것이다.
 *
 * 1. 링크가 **바깥으로 나간다.** 우리 상세 페이지가 없다. 상세 페이지를 만들면
 *    "우리가 정리한 내용"처럼 보이는데, 정리한 적이 없다.
 * 2. 거터 구분선이 **점선**이다. 확정된 정보의 실선과 눈으로 구분된다.
 *
 * 본문은 애초에 저장하지 않았으므로(§NFR-015) 여기서 보여줄 수 있는 것은
 * 제목·요약 한두 줄·링크뿐이다.
 */
export function NewsRecord({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="group -mx-3 block rounded-soft px-3 py-3 transition-colors hover:bg-surface-sunk"
    >
      <div className="flex gap-3 sm:gap-4">
        <div className="w-[3.5rem] shrink-0 pt-[2px] sm:w-[4rem]">
          <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-ink-3">보도</div>
          <div className="tabular mt-0.5 text-[13px] font-bold leading-tight text-ink-2">
            {item.published_at ? formatDateCompact(item.published_at) : '미상'}
          </div>
        </div>

        {/* 점선 — 이 항목은 확정되지 않았다는 표시 */}
        <div
          aria-hidden
          className="w-px shrink-0 border-l border-dashed border-rule-strong"
        />

        <div className="min-w-0 flex-1">
          <h3 className="text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
            {item.title}
            <span aria-hidden className="ml-1.5 text-[13px] font-normal text-ink-3">
              ↗
            </span>
          </h3>

          {item.summary ? (
            <p className="mt-1.5 line-clamp-2 max-w-reading text-[15px] leading-relaxed text-ink-2">
              {item.summary}
            </p>
          ) : null}

          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-ink-3">
            <span className="break-all">{hostOf(item.url)}</span>
            {item.matched_query ? (
              <>
                <span aria-hidden>·</span>
                <span>{item.matched_query}</span>
              </>
            ) : null}
          </p>
        </div>
      </div>
    </a>
  );
}

/**
 * 언론사 이름 대신 도메인을 보여준다.
 *
 * 검색 API 가 주는 것은 링크뿐이고 언론사명은 따로 오지 않는다.
 * 없는 값을 지어내느니 주소를 그대로 보여주는 편이 정직하다.
 */
function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}
