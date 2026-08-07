import type { NewsItem } from '@/lib/types';

/**
 * 언론 보도 한 건.
 *
 * 정책 항목과 세 가지가 다르고, 셋 다 의도한 것이다.
 *
 * 1. 링크가 **바깥으로 나간다.** 우리 상세 페이지가 없다. 상세를 만들면
 *    "우리가 정리한 내용"처럼 보이는데, 정리한 적이 없다.
 * 2. 도장도 시행일도 없다. 확인한 게 없으니 확인한 척하는 표시를 못 붙인다.
 * 3. 제목 앞에 **점선 표시**가 붙는다. 확정 기록의 실선과 눈으로 구분된다.
 *
 * 본문은 애초에 저장하지 않았으므로(§NFR-015) 보여줄 수 있는 것은
 * 제목·요약 한두 줄·링크뿐이다.
 */
export function NewsRecord({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="group flex gap-3 px-4 py-3.5 transition-colors hover:bg-surface-sunk"
    >
      <span
        aria-hidden
        className="mt-[11px] h-0 w-3 shrink-0 border-t border-dashed border-rule-strong"
      />

      <div className="min-w-0 flex-1">
        <h3 className="text-record text-ink decoration-1 underline-offset-4 group-hover:underline">
          {item.title}
          <span aria-hidden className="ml-1.5 text-[12px] font-normal text-ink-3">
            ↗
          </span>
        </h3>

        {item.summary ? (
          <p className="mt-1 line-clamp-2 max-w-reading text-[14px] leading-relaxed text-ink-2">
            {item.summary}
          </p>
        ) : null}

        <p className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] text-ink-3">
          <span className="break-all font-medium">{hostOf(item.url)}</span>
          {item.matched_query ? (
            <>
              <span aria-hidden className="text-rule-strong">
                ·
              </span>
              <span>{item.matched_query}</span>
            </>
          ) : null}
        </p>
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
