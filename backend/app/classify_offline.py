"""업종 분류를 **밖에서 돌리고 결과만 받아 넣는다.**

    python -m app.classify_offline --export out/           내보내기
    python -m app.classify_offline --import out/답1.txt    넣기

--- 왜 필요한가 ---

분류 자체는 어렵지 않다. 병목은 GROQ 무료 한도다. 하루 20만 토큰이라
미분류 278건을 채우는 데 이레가 걸린다. 그동안 「요식·음식점」 은 0건이고,
음식점 사장님께 골라 보낼 것이 없다.

판단은 어느 모델이 해도 된다. 프롬프트를 파일로 내보내 붙여 넣고, 답만
받아 넣으면 이레가 몇 분이 된다.

--- 넣을 때가 위험하다 ---

밖에서 온 값을 그대로 믿으면 안 된다. 여기서 지키는 것은 넷이다.

1. **분류표에 없는 코드는 거절한다.** 조용히 버리지 않는다 — 버리면
   그 건은 "판단해보니 무관" 으로 남아 화면에서 사라진다. 무엇이
   잘못됐는지 말하고 통째로 멈춘다.

2. **하나라도 틀리면 아무것도 저장하지 않는다.** 반쯤 넣고 멈추면
   어디까지 들어갔는지 알 수 없다.

3. **INTERNAL 은 받지 않는다.** 그건 규칙(is_internal_document)만
   붙이는 숨김 표시다. 모델이 붙이면 진짜 세법이 화면에서 사라진다.
   실제로 증권거래세율 인상이 그렇게 사라진 적이 있다.

4. **빠진 항목은 건드리지 않는다.** 답에 없으면 그대로 둔다. 다시
   내보내면 나온다.

--- 열쇠 ---

프롬프트에 UUID 를 싣지 않는다. `A1`, `A2` 같은 짧은 열쇠를 쓰고 대응표는
`map.json` 으로 옆에 둔다. 긴 UUID 는 모델이 한 글자씩 흘리고, 흘린 값은
어느 건인지 알 수 없게 만든다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.domain.industry import Industry, is_internal_document, label
from app.models.tables import ContentVersion, TaxContent
from app.services.ai.classify import (
    SYSTEM_PROMPT,
    _taxonomy_block,
    build_search_text,
)

#: 한 파일에 담는 건수. 채팅창 한 번에 붙여 넣을 만한 크기다.
BATCH = 40

_VALID = {item.value for item in Industry}

#: 답에서 코드펜스를 걷어낸다. 붙여 오는 쪽이 감싸는 일이 잦다.
_FENCE = re.compile(r"```(?:json)?\s*(.+?)```", re.S)


def _judgement_rules() -> str:
    """판단 기준만 떼어 온다.

    SYSTEM_PROMPT 는 한 건씩 부를 때 쓰는 것이라 끝에 단건 출력 형식이
    붙어 있다.

        JSON 객체 하나만 출력한다. 설명·코드펜스를 붙이지 않는다.
        {"industries": ["코드", ...], "reason": "한 문장"}

    여기서는 마흔 건을 한 번에 물으므로 형식이 다르다. 두 형식을 같이
    주면 모델이 둘을 섞은 것을 내놓는다. 판단 기준까지만 쓰고 형식은
    아래에서 한 번만 말한다.
    """
    return SYSTEM_PROMPT.split("JSON 객체 하나만 출력한다")[0].rstrip()


def _body_of(db, content: TaxContent) -> dict:
    if not content.current_version_id:
        return {}
    version = db.get(ContentVersion, content.current_version_id)
    return version.body if version and isinstance(version.body, dict) else {}


def _item_block(key: str, content: TaxContent, body: dict) -> str:
    """한 건을 사람이 읽을 수 있는 덩어리로.

    제목만 주면 모델이 지어낸다. 요약·대상·바뀌는 것까지 준다 —
    화면에서 쓰는 것과 같은 자료다.
    """
    lines = [f"[{key}] {content.title}"]
    if content.one_line_summary:
        lines.append(f"  요약: {content.one_line_summary}")
    for name, field in (("대상", "affected_users"), ("바뀌는 것", "changes")):
        values = body.get(field)
        if not isinstance(values, list) or not values:
            continue
        picked = []
        for value in values[:3]:
            text = value.get("text") if isinstance(value, dict) else value
            if text:
                picked.append(str(text)[:100])
        if picked:
            lines.append(f"  {name}: {' / '.join(picked)}")
    return "\n".join(lines)


def _export(out_dir: Path, limit: int, retry_empty: bool) -> int:
    db = SessionLocal()
    try:
        # 기본은 아직 판단하지 않은 것(search_text 가 비어 있음).
        #
        # --retry-empty 는 **판단은 끝났는데 업종이 하나도 안 붙은 것**을
        # 다시 묻는다. 심판례 47건·해석례 40건이 전부 그랬는데, 음식점
        # 사장님께 골라 보낼 사례가 있다면 바로 거기에 있다. 분류가
        # 고장 나 있던 동안 붙은 값일 수도 있어서 한 번은 다시 봐야 한다.
        condition = (
            TaxContent.industries == []
            if retry_empty
            else TaxContent.search_text.is_(None)
        )
        stmt = (
            select(TaxContent)
            .where(condition)
            .order_by(TaxContent.updated_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = list(db.execute(stmt).scalars())

        # 제목만 봐도 아는 것은 내보내지 않는다. 밖에 물어볼 이유가 없다.
        rows = [c for c in rows if not is_internal_document(c.title)]
        if not rows:
            print("내보낼 것이 없습니다.")
            return 0

        out_dir.mkdir(parents=True, exist_ok=True)
        mapping: dict[str, str] = {}
        files = 0

        for start in range(0, len(rows), BATCH):
            chunk = rows[start : start + BATCH]
            files += 1
            prefix = chr(64 + files)
            keys: list[str] = []
            blocks: list[str] = []
            for offset, content in enumerate(chunk, start=1):
                key = f"{prefix}{offset}"
                mapping[key] = str(content.id)
                keys.append(key)
                blocks.append(_item_block(key, content, _body_of(db, content)))

            sample = '{"' + keys[0] + '": ["ALL"]'
            if len(keys) > 1:
                sample += ', "' + keys[1] + '": ["FOOD", "RETAIL"]'
            sample += "}"

            text = "\n".join(
                [
                    _judgement_rules(),
                    "",
                    "분류표",
                    _taxonomy_block(),
                    "",
                    f"아래 {len(chunk)}건을 각각 분류한다.",
                    "",
                    "\n\n".join(blocks),
                    "",
                    "출력 형식 — JSON 객체 하나만. 설명도 코드펜스도 붙이지 않는다.",
                    "열쇠는 위 대괄호 안 값을 그대로 쓴다. 한 건도 빠뜨리지 않는다.",
                    sample,
                ]
            )
            path = out_dir / f"{files:02d}.txt"
            path.write_text(text, encoding="utf-8")
            print(f"  {path}  {len(chunk)}건")

        (out_dir / "map.json").write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n{len(rows)}건을 {files}개 파일로 내보냈습니다.")
        print(f"대응표: {out_dir / 'map.json'} — 지우지 마세요.")
        print("\n파일 하나를 통째로 붙여 넣고, 받은 JSON 을 같은 폴더에 저장한 뒤:")
        print("  python -m app.classify_offline --import <답 파일>")
        return 0
    finally:
        db.close()


def _read_answer(path: Path) -> dict[str, object]:
    """답 파일을 읽는다. 코드펜스나 앞뒤 설명이 붙어 와도 받아 준다."""
    text = path.read_text(encoding="utf-8").strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        raise SystemExit("JSON 객체를 찾지 못했습니다. 답 전체를 붙여 넣었는지 보세요.")
    if end < start:
        # 긴 답이 채팅창에서 잘려 오는 일이 잦다. "JSON 을 못 찾았다" 고
        # 하면 붙여 넣기를 잘못한 줄 알고 같은 것을 또 붙인다.
        raise SystemExit(
            "JSON 이 닫히지 않았습니다. 답이 중간에서 끊긴 것 같습니다 — "
            "다시 받아 주세요."
        )
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise SystemExit("JSON 객체가 아닙니다.")
    return {str(k).strip(): v for k, v in data.items()}


def _validate(
    answers: dict[str, object], mapping: dict[str, str]
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """검사만 한다. 저장은 전부 통과한 뒤에.

    반환: (쓸 값, 잘못된 것, 대응표에 없는 열쇠)
    """
    unknown = [k for k in answers if k not in mapping]
    bad: list[str] = []
    cleaned: dict[str, list[str]] = {}

    for key, value in answers.items():
        if key not in mapping:
            continue
        if not isinstance(value, list):
            bad.append(f"{key}: 배열이 아닙니다 ({value!r})")
            continue
        codes = [str(c).strip().upper() for c in value if str(c).strip()]
        wrong = [c for c in codes if c not in _VALID]
        if wrong:
            bad.append(f"{key}: 분류표에 없는 코드 {wrong}")
            continue
        if Industry.INTERNAL.value in codes:
            bad.append(f"{key}: INTERNAL 은 규칙으로만 붙입니다")
            continue
        cleaned[key] = codes

    return cleaned, bad, unknown


def _import(answer_path: Path, dry_run: bool) -> int:
    map_path = answer_path.parent / "map.json"
    if not map_path.exists():
        raise SystemExit(f"대응표가 없습니다: {map_path}")
    mapping: dict[str, str] = json.loads(map_path.read_text(encoding="utf-8"))

    cleaned, bad, unknown = _validate(_read_answer(answer_path), mapping)

    if unknown:
        print(f"! 대응표에 없는 열쇠 {len(unknown)}개: {unknown[:8]}")
    if bad:
        print(f"\n! 잘못된 답 {len(bad)}건 — 아무것도 저장하지 않았습니다.")
        for line in bad[:12]:
            print(f"   {line}")
        return 1

    missing = [k for k in mapping if k not in cleaned]
    print(f"받은 답 {len(cleaned)}건 · 이 대응표에서 빠진 것 {len(missing)}건\n")

    db = SessionLocal()
    applied = 0
    try:
        for key, codes in cleaned.items():
            content = db.get(TaxContent, mapping[key])
            if content is None:
                print(f"   ! {key}: 콘텐츠가 없어졌습니다")
                continue
            content.industries = codes
            # search_text 는 여기서 채운다. 이 값이 "판단이 끝났다" 의 표지다.
            content.search_text = build_search_text(
                content.title, content.one_line_summary, _body_of(db, content)
            )
            applied += 1
            names = " · ".join(label(c) for c in codes) if codes else "(업종 없음)"
            print(f"   {key:4s} {content.title[:38]:40s} {names}")

        if dry_run:
            db.rollback()
            print("\n[dry-run] 저장하지 않았습니다.")
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\n{applied}건 반영했습니다.")
    if missing:
        print(f"빠진 {len(missing)}건은 그대로 뒀습니다. 다시 내보내면 나옵니다.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="업종 분류를 밖에서 돌리고 결과만 받아 넣는다"
    )
    parser.add_argument("--export", metavar="DIR", help="프롬프트 파일을 만들 폴더")
    parser.add_argument("--limit", type=int, default=0, help="내보낼 최대 건수 (0=전체)")
    parser.add_argument(
        "--retry-empty",
        action="store_true",
        help="업종이 하나도 안 붙은 것을 다시 묻는다",
    )
    parser.add_argument("--import", dest="answer", metavar="FILE", help="받은 JSON 파일")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않음")
    args = parser.parse_args(argv)

    if args.export:
        return _export(Path(args.export), args.limit, args.retry_empty)
    if args.answer:
        return _import(Path(args.answer), args.dry_run)
    parser.error("--export 또는 --import 중 하나가 필요합니다")
    return 2


if __name__ == "__main__":
    sys.exit(main())
