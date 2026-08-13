import { FactGrid } from '@/components/DetailParts';
import { formatDate } from '@/lib/format';
import type { PublicContentDetail, TribunalBody } from '@/lib/types';

/**
 * 심판례 상세.
 *
 * **법령 화면을 그대로 쓰면 거짓말이 된다.** 처음에는 한 화면으로 다
 * 처리했고, 그래서 심판례에 이런 것들이 붙었다.
 *
 *     시행 중              ← 심판례는 시행되지 않는다
 *     2024년 5월 1일부터 시행  ← 의결일을 시행일로 적었다
 *     지금 해야 할 일
 *       01 시행일 전에 해당 조문이 우리 사업장에 적용되는지 확인하세요
 *
 * 심판례는 제도가 아니라 **이미 끝난 남의 사건**이다. 할 일이 없다.
 * 대신 실무자가 알고 싶은 것은 따로 있다 — 누가 무엇을 다퉜고,
 * 심판원이 어느 쪽 손을 들어줬고, 그 근거가 무엇인가.
 *
 * 그래서 결론을 맨 위에 놓는다. 기각인지 인용인지를 먼저 봐야 이 사건을
 * 더 읽을지 말지 정할 수 있다.
 */

/**
 * 결론 표시.
 *
 * 색으로만 구분하지 않는다 (NFR-013). 인용은 채운 점, 기각은 빈 점이다.
 * 그리고 괄호에 그게 무슨 뜻인지 적는다 — "일부인용"이 납세자가 일부
 * 이겼다는 뜻임을 모두가 아는 것은 아니다.
 */
const OUTCOME: Record<string, { tone: string; hollow: boolean; gloss: string }> = {
  인용: { tone: 'text-state-effective', hollow: false, gloss: '납세자 주장이 받아들여짐' },
  일부인용: { tone: 'text-state-effective', hollow: true, gloss: '일부만 받아들여짐' },
  기각: { tone: 'text-state-halted', hollow: true, gloss: '납세자 주장이 받아들여지지 않음' },
  각하: { tone: 'text-ink-3', hollow: true, gloss: '본안 판단 없이 종료' },
  재조사: { tone: 'text-state-pending', hollow: true, gloss: '과세관청이 다시 조사' },
};

export function OutcomeMark({ outcome }: { outcome: string }) {
  const spec = OUTCOME[outcome];
  if (!spec) return null;
  return (
    <span className={`status ${spec.hollow ? 'status-hollow' : ''} ${spec.tone}`}>
      청구 {outcome}
    </span>
  );
}

const ORDINALS = '가나다라마바사아자차카타파하';

/**
 * 심판례 본문의 단계 표시. 넷이 사다리로 쓰인다.
 *
 *     1.  처분개요
 *     가.  청구인 주장
 *     (1)  …
 *     (가) …
 *
 * 항목 표시(`가.`)는 앞이 마침표인 경우와 글자인 경우를 나눠 잡는다 —
 * 뒤쪽은 "하였다." 의 끝 글자일 수 있어서 따로 걸러야 한다.
 */
const MARKER =
  /(?<!\d)(?<!\d\.)(\d{1,2})\.(?![0-9])|(?<=[.)\s])([가-힣])\.|([가-힣])\.|\((\d{1,2})\)|\(([가-힣])\)/g;

/**
 * 표제 바로 뒤에 붙은 첫 항목까지의 거리.
 *
 *     2.청구인 주장 및 처분청 의견가.청구인 주장
 *       └────────── 14자 ─────────┘
 *
 * 이 안쪽에서만 글자에 붙은 `가.` 를 항목으로 인정한다. 멀리 떨어진
 * 것은 "하였다." 처럼 문장 끝일 가능성이 높다.
 */
const HEADING_SPAN = 26;

/** 이보다 긴 덩어리는 문장 끝에서 한 번 더 끊는다. */
const WALL = 1200;

/**
 * 문단을 나눈다. **글자는 건드리지 않는다 — 줄바꿈만 넣는다.**
 *
 * 심판원 원문에는 줄바꿈이 하나도 없다. 판단 이유가 중앙값 13,495자,
 * 긴 것은 70,429자인데 전부 한 덩어리다. 그대로 흘리면 읽을 수 없다.
 *
 * 그래서 원문이 이미 갖고 있는 번호 표시 앞에서 끊는다. 다만 마침표를
 * 단서로 삼으면 날짜가 잘린다.
 *
 *     2025.5.20.  →  2025.5.
 *                    20.
 *
 * 그래서 마침표가 아니라 **순번**을 본다. 1 다음에 2, 가 다음에 나가
 * 올 때만 표시로 인정한다. 날짜 속의 숫자는 순번에 맞지 않아 그냥 지나간다.
 * 번호가 새로 나오면 항목 순번은 가부터 다시 센다.
 *
 * 글자 뒤에 바로 붙은 항목 표시(`1.처분개요가.청구인은`)는 표제 직후일
 * 때만 인정한다. 그러지 않으면 "하였다." 의 끝 글자를 항목으로 읽는다.
 *
 * 번호도 항목도 없는 원문이 하나 있었다. 그런 덩어리만 문장 끝에서
 * 추가로 끊는다 — 줄머리의 `다.` 는 항목 표시이므로 건드리지 않는다.
 */
function paragraphize(text: string): string {
  let out = '';
  let cut = 0;
  let numAt = -99;
  // 각 단계가 다음에 기대하는 값. 위 단계가 넘어가면 아래는 처음부터 다시 센다.
  let nextNum = 1;
  let nextOrd = 0;
  let nextSub = 1;
  let nextSubOrd = 0;

  for (const m of text.matchAll(MARKER)) {
    const at = m.index ?? 0;
    let lead: string;

    if (m[1] !== undefined) {
      if (Number(m[1]) !== nextNum) continue;
      nextNum += 1;
      nextOrd = 0;
      nextSub = 1;
      nextSubOrd = 0;
      numAt = at;
      lead = '\n\n';
    } else if (m[2] !== undefined || m[3] !== undefined) {
      const ch = m[2] ?? m[3];
      if (ch !== ORDINALS[nextOrd]) continue;
      if (m[3] !== undefined && !(nextOrd === 0 && at - numAt < HEADING_SPAN)) continue;
      nextOrd += 1;
      nextSub = 1;
      nextSubOrd = 0;
      lead = '\n';
    } else if (m[4] !== undefined) {
      if (Number(m[4]) !== nextSub) continue;
      nextSub += 1;
      nextSubOrd = 0;
      lead = '\n';
    } else {
      if (m[5] !== ORDINALS[nextSubOrd]) continue;
      nextSubOrd += 1;
      lead = '\n';
    }

    if (at <= cut) continue;
    out += text.slice(cut, at) + lead;
    cut = at;
  }

  return (out + text.slice(cut))
    .split('\n')
    .map((line) =>
      line.length > WALL ? line.replace(/(?<=[가-힣][다함음임])\.(?=\S)/g, '.\n') : line,
    )
    .join('\n')
    .trim();
}

/** 본문에 그대로 흘릴지, 접어 둘지. 긴 것만 접는다. */
const FOLD_OVER = 1500;

function Section({ label, text }: { label: string; text: string }) {
  const shaped = paragraphize(text);

  if (text.length <= FOLD_OVER) {
    return (
      <section className="prose-block">
        <h2 className="section-mark">{label}</h2>
        <p className="mt-3 whitespace-pre-wrap text-[16px] leading-loose text-ink-2">{shaped}</p>
      </section>
    );
  }

  /*
    접는 것은 숨기는 것과 다르다. 몇 자짜리인지 적어 두고, 열면 전문이
    그대로 나온다. 판단 요지를 읽고 더 볼지 정하는 사람이 대부분이고,
    끝까지 파는 사람에게는 한 번의 클릭이다.

    <details> 를 쓴 이유 — 자바스크립트 없이 동작하고, Ctrl+F 로 접힌
    내용까지 찾아 준다 (요즘 브라우저는 hidden=until-found 로 열어 준다).
  */
  return (
    <details className="group prose-block border-t border-rule pt-5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 [&::-webkit-details-marker]:hidden">
        <span className="section-mark">{label}</span>
        <span className="tabular shrink-0 text-[13px] font-semibold text-accent">
          전문 {text.length.toLocaleString('ko-KR')}자 <span className="group-open:hidden">펼치기</span>
          <span className="hidden group-open:inline">접기</span>
        </span>
      </summary>
      <p className="mt-4 whitespace-pre-wrap text-[15.5px] leading-loose text-ink-2">{shaped}</p>
    </details>
  );
}

export function TribunalArticle({
  content,
  tribunal,
}: {
  content: PublicContentDetail;
  tribunal: TribunalBody;
}) {
  const spec = OUTCOME[tribunal.outcome];
  const decided = content.promulgation_date ?? content.updated_at.slice(0, 10);

  // 사건명은 제목에 이미 들어 있다. 본문에서 한 번 더 보여줄 이유가 없다.
  const sections = tribunal.sections.filter((s) => s.label !== '사건명');

  return (
    <article className="min-w-0 border border-rule bg-surface">
      <header className="border-b border-rule px-5 py-7 sm:px-8">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="text-[13px] font-bold text-accent">조세심판원 결정</span>
          <OutcomeMark outcome={tribunal.outcome} />
        </div>

        <h1 className="mt-3.5 max-w-reading text-display text-ink">{content.title}</h1>

        {spec ? (
          <p className="mt-3 text-[14px] font-medium text-ink-3">{spec.gloss}</p>
        ) : null}
      </header>

      {/*
        시행일 자리에 의결일이 온다. 세목과 처분청은 "이게 우리 업체와
        비슷한 상황인가"를 가르는 첫 단서라 위에 둔다.
      */}
      <FactGrid
        cells={[
          { label: '세목', value: tribunal.tax_type || '원문 확인' },
          { label: '결론', value: tribunal.outcome ? `청구 ${tribunal.outcome}` : '원문 확인' },
          { label: '처분청', value: tribunal.disposition_agency || '원문 확인' },
          { label: '의결일', value: formatDate(decided) },
        ]}
      />

      <div className="max-w-reading px-5 py-7 sm:px-8">
        {/*
          원문을 그대로 쓴다. 요약하지 않는다 — 실무자는 이 문장을 근거로
          인용하고, 우리가 다시 쓴 문장은 인용할 수 없다.
        */}
        {sections.length > 0 ? (
          sections.map((section) => (
            <Section key={section.label} label={section.label} text={section.text} />
          ))
        ) : (
          <p className="text-[15px] leading-relaxed text-ink-2">
            본문을 불러오지 못했습니다. 아래 공식 원문을 확인해 주세요.
          </p>
        )}

        <p className="mt-9 border-t border-rule pt-4 text-[13.5px] leading-relaxed text-ink-3">
          개별 사건의 사실관계에 대한 판단입니다. 사실관계가 다르면 결론도 달라지므로 우리
          사업장에 그대로 적용된다고 볼 수 없습니다.
        </p>
      </div>
    </article>
  );
}
