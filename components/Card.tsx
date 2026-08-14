import Link from 'next/link';

import { daysUntil, effectiveLabel, formatDate, stripRevisionSuffix } from '@/lib/format';
import type { NewsItem, PublicContentSummary } from '@/lib/types';

/**
 * 목록에 놓이는 카드들.
 *
 * 예전에는 한 판 안에 스무 줄을 `divide-y` 로 넣었다. 줄과 줄 사이가
 * 1px 회색선 하나뿐이라 어디서 한 건이 끝나는지 눈이 못 잡았고,
 * 제목 아래 11~13px 회색 메타가 세 줄씩 붙어 화면의 절반을 먹었다.
 *
 * 카드 한 장에 한 건. 사이는 여백으로 벌린다. 그리고 **한 카드가
 * 말하는 것을 셋으로 줄인다** — 무엇이 바뀌나 / 언제부터 / 얼마나 급한가.
 * 나머지는 열면 나온다.
 */

/** 급한 정도를 알약 하나로. 안 급하면 아무것도 안 붙인다. */
function Urgency({ item }: { item: PublicContentSummary }) {
  const deadline = daysUntil(item.application_end);
  if (deadline !== null && deadline >= 0 && deadline <= 7) {
    return <span className="pill pill-danger">마감 D-{deadline}</span>;
  }
  if (item.risk_level === 'CRITICAL') return <span className="pill pill-danger">긴급</span>;
  if (item.risk_level === 'HIGH') return <span className="pill pill-accent">중요</span>;
  return null;
}

/**
 * 결론 알약 (심판례).
 *
 * 색만으로 구분하지 않는다 — 글자가 뜻을 다 말한다. 다만 "일부인용" 이
 * 납세자가 일부 이겼다는 뜻임을 모두가 아는 것은 아니라서, 상세에서는
 * 풀어 쓰고 목록에서는 색으로 갈래만 보여준다.
 */
export function OutcomePill({ outcome }: { outcome: string }) {
  const won = outcome === '인용' || outcome === '일부인용';
  return <span className={`pill ${won ? 'pill-good' : 'pill-calm'}`}>{outcome}</span>;
}

/**
 * 제목 정하기.
 *
 * 목록을 훑을 때 첫 줄이 "국세기본법 시행령 (일부개정)" 이면 자기와
 * 무슨 상관인지 알 수 없다. **법령명은 출처지 제목이 아니다.**
 * 무엇이 바뀌는지를 앞에 놓고, 법령명은 아래 메타로 내린다.
 *
 * 요약이 제목을 통째로 품고 있으면 제목을 그대로 쓴다 — AI 요약이 아직
 * 없는 건에 들어 있는 자동 생성 문구가 그렇다.
 */
function headlineOf(item: PublicContentSummary) {
  const name = stripRevisionSuffix(item.title);
  const summary = item.one_line_summary?.trim();
  if (!summary) return { headline: name, statute: null as string | null };

  // 입법예고는 법령안 이름이 곧 정보다. 「소득세법 일부개정법률안」을
  // 보는 순간 실무자는 무엇이 걸리는지 안다. 요약은 그 아래에서
  // 의견 마감을 말한다 — 두 개가 다른 것을 말하므로 둘 다 보여준다.
  if (item.legal_status === 'PREANNOUNCED') {
    return { headline: name, statute: null as string | null };
  }

  const strip = (s: string) => s.replace(/[「」·\s()]/g, '');
  if (strip(summary).includes(strip(item.title))) {
    return { headline: name, statute: null as string | null };
  }
  return { headline: summary, statute: name };
}

/** 법령·법안 한 건. */
export function PolicyCard({ item }: { item: PublicContentSummary }) {
  const { headline, statute } = headlineOf(item);
  const effective = effectiveLabel(item.effective_date);
  const urgency = <Urgency item={item} />;

  // 예고에는 시행일이라는 것이 아직 없다. 「시행일 미정」은 틀린 말은
  // 아니지만, 상태 배지와 경고 문구가 이미 확정이 아니라고 말한 뒤에
  // 세 번째로 같은 말을 하는 자리가 된다. 그 자리를 마감에 내준다.
  const preannounced = item.legal_status === 'PREANNOUNCED';

  return (
    <Link href={`/contents/${item.id}`} className="card-tap pad">
      <div className="flex flex-wrap items-center gap-1.5">
        {urgency}
        {item.corrected ? <span className="pill pill-warn">정정</span> : null}
        {item.status_label ? <span className="pill pill-calm">{item.status_label}</span> : null}
      </div>

            {/*
        두 줄에서 자른다. 목록에서 판단하는 것은 "열어볼까" 하나뿐이고,
        네 줄짜리 제목이 이어지면 카드 경계가 다시 흐려진다.
      */}
      <h3 className="mt-2.5 line-clamp-2 max-w-reading text-card text-ink">{headline}</h3>

      {preannounced ? null : (
        <p className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-meta">
          <span className={`font-bold ${effective.tone === 'soon' ? 'text-danger' : 'text-ink-2'}`}>
            {effective.text}
          </span>
          {statute ? <span className="text-ink-3">{statute}</span> : null}
        </p>
      )}

      {/*
        예고에서는 이 줄이 핵심이다. 의견을 낼 수 있는 기간이 언제까지인지.
        제목이 요약에 들어 있으면 요약을 버리는 규칙 때문에 이 문장이
        한동안 화면에서 사라져 있었다.
      */}
      {preannounced && item.one_line_summary ? (
        <p className="mt-2 text-meta font-bold text-ink-2">{item.one_line_summary}</p>
      ) : null}

      {item.status_caveat ? (
        <p className="mt-2 text-meta font-semibold text-warn">{item.status_caveat}</p>
      ) : null}
    </Link>
  );
}

/**
 * 심판례 한 건.
 *
 * 시행일도 정책 상태도 없다. 그 자리에 결론과 의결일이 온다 —
 * 비슷한 사안을 맡았을 때 다툴 만한지가 그 둘에서 갈린다.
 */
export function TribunalCard({ item }: { item: PublicContentSummary }) {
  return (
    <Link href={`/contents/${item.id}`} className="card-tap pad">
      <div className="flex flex-wrap items-center gap-1.5">
        {item.outcome ? <OutcomePill outcome={item.outcome} /> : null}
        <span className="pill pill-calm">조세심판원</span>
      </div>

      <h3 className="mt-2.5 line-clamp-2 max-w-reading text-card text-ink">{item.title}</h3>

      {item.promulgation_date ? (
        <p className="mt-2 text-meta text-ink-3">{formatDate(item.promulgation_date)} 결정</p>
      ) : null}
    </Link>
  );
}

/**
 * 언론 보도 한 건.
 *
 * 링크가 **바깥으로 나간다.** 우리 상세 페이지가 없다 — 만들면
 * "우리가 정리한 내용" 처럼 보이는데 정리한 적이 없다. 본문도 애초에
 * 저장하지 않았다 (§NFR-015).
 */
export function NewsCard({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="card-tap pad"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="pill pill-warn">확인 전</span>
        <span className="pill pill-calm">{item.publisher}</span>
      </div>

      <h3 className="mt-2.5 line-clamp-2 max-w-reading text-card text-ink">
        {item.title}
        <span aria-hidden className="ml-1 text-[13px] font-normal text-ink-3">
          ↗
        </span>
      </h3>

      {item.summary ? (
        <p className="mt-1.5 line-clamp-2 max-w-reading text-body text-ink-2">{item.summary}</p>
      ) : null}
    </a>
  );
}

/**
 * 법령해석 한 건.
 *
 * **본문이 없다.** 법제처 API 가 목록만 주고 상세는 안 준다. 그래서
 * 우리 상세 화면을 거치지 않고 원문으로 바로 보낸다 — 제목과 링크뿐인
 * 화면을 한 번 더 열게 하는 것은 헛걸음이다.
 *
 * 다만 뉴스와 다르다. 국가기관이 낸 공식 해석이라 등급이 A 다.
 * "확인 전" 이 아니라 "본문 미수록" 이라고 적는다 — 못 믿을 것이
 * 아니라 우리가 안 담은 것이다.
 */
export function InterpretationCard({ item }: { item: PublicContentSummary }) {
  // 판례는 법원 판결이고 해석은 과세관청 회신이다. 같은 알약을 붙이면
  // 법원이 답장을 보낸 것처럼 읽힌다.
  const isCourt = item.content_kind === 'PRECEDENT';
  return (
    <a
      href={item.source_url ?? '#'}
      target="_blank"
      rel="noopener noreferrer"
      className="card-tap pad"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="pill pill-good">{isCourt ? '법원 판결' : '공식 해석'}</span>
        <span className="pill pill-calm">본문 미수록</span>
      </div>

      <h3 className="mt-2.5 line-clamp-2 max-w-reading text-card text-ink">
        {item.title}
        <span aria-hidden className="ml-1 text-[13px] font-normal text-ink-3">
          ↗
        </span>
      </h3>

      <p className="mt-2 text-meta text-ink-3">
        {item.promulgation_date
          ? `${formatDate(item.promulgation_date)} ${isCourt ? '선고' : '회신'} · `
          : ''}
        {isCourt ? '법제처에서 원문 보기' : '국세법령정보시스템에서 원문 보기'}
      </p>
    </a>
  );
}

/** 종류를 보고 알아서 고른다. 화면마다 분기를 반복하지 않는다. */
export function ContentCard({ item }: { item: PublicContentSummary }) {
  if (item.content_kind === 'INTERPRETATION' || item.content_kind === 'PRECEDENT') {
    return <InterpretationCard item={item} />;
  }
  if (item.content_kind === 'TRIBUNAL') return <TribunalCard item={item} />;
  return <PolicyCard item={item} />;
}
