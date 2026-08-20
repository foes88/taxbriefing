'use client';

import { useState } from 'react';

/**
 * 사장님에게 보낼 짧은 글.
 *
 * 세무사무소 직원이 이 화면을 보고 고객에게 카톡으로 옮겨 적는다.
 * 그 옮겨 적는 일을 대신한다.
 *
 * **글은 서버가 만든다.** 여기서 조립하면 화면마다 문구가 갈리고,
 * 무엇이 나갔는지 시험으로 확인할 방법이 없어진다. 이 글은 우리
 * 화면보다 멀리 가서 — 사무소를 떠나 사장님 카톡으로 들어가서 —
 * 거기서는 정정할 방법이 없다. 한 자리에서 만들고 한 자리에서 검사한다.
 *
 * **보내기 전에 보여준다.** 눌러야 나오는 상자에 넣으면 확인 없이
 * 복사하게 된다. 펼쳐 두고, 무엇이 나가는지 읽은 다음 누르게 한다.
 */
export function ShareCard({
  text,
  title = '사장님께 보내기',
  note = '핵심만',
  bare = false,
}: {
  text: string;
  title?: string;
  note?: string;
  /** 이미 카드 안에 있을 때. 머리말과 테두리를 그리지 않는다. */
  bare?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  if (!text.trim()) return null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // 클립보드를 막아 둔 브라우저가 있다. 그때는 아무 일도 없었던 것처럼
      // 두지 않고, 글을 직접 고를 수 있게 선택 상태로 만든다.
      const box = document.getElementById('share-text');
      if (box) {
        const range = document.createRange();
        range.selectNodeContents(box);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const body = (
    <>
      <pre
        id="share-text"
        className="mt-2.5 max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-field bg-surface-sunk p-3 font-sans text-[13.5px] leading-relaxed text-ink-2"
      >
        {text}
      </pre>

      <button
        type="button"
        onClick={copy}
        className="btn-primary mt-3 w-full"
        aria-live="polite"
      >
        {copied ? '복사했습니다' : '복사'}
      </button>
    </>
  );

  if (bare) return body;

  return (
    <section className="card pad">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="section-title">{title}</h2>
        <span className="shrink-0 text-meta text-ink-3">{note}</span>
      </div>
      {body}
    </section>
  );
}
