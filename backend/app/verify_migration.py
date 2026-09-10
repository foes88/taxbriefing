"""이관 전후를 표별로 대조한다. 이관이 끝났다고 말하기 전에 이걸 돌린다.

    python -m app.verify_migration <원본URL파일> <이관본URL파일> [원본스키마] [이관본스키마]

URL 을 인자로 직접 받지 않고 **파일 경로로 받는다.** 명령줄에 적으면
셸 기록과 프로세스 목록에 비밀번호가 남는다.

**건수만 맞춰 보면 「같은 수의 다른 데이터」를 못 잡는다.** 그래서 기본키를
정렬해 md5 로 묶은 값도 같이 본다. 실제로 로컬 이관을 이걸로 확인했고,
14개 표가 건수·내용 모두 같았다. 빠진 것은 audit_logs 하나였는데 그건
씨앗에서 일부러 뺀 것이었다 — **세어 보지 않았으면 몰랐다.**

기본키가 없는 표는 순서를 정할 수 없어 체크섬을 건너뛴다. 그 사실을
「(기본키 없음)」으로 적는다. 조용히 통과시키지 않는다.
"""

from __future__ import annotations

import sys

import psycopg

SEP = chr(39) + "|" + chr(39)  # SQL 문자열 리터럴 '|'

if len(sys.argv) < 3:
    sys.exit(__doc__)

def _url(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


src_url = _url(sys.argv[1])
dst_url = _url(sys.argv[2])
SRC = sys.argv[3] if len(sys.argv) > 3 else "public"
DST = sys.argv[4] if len(sys.argv) > 4 else "tb"


def tables(cur, schema):
    cur.execute(
        "select table_name from information_schema.tables "
        "where table_schema=%s and table_type='BASE TABLE' order by 1",
        (schema,),
    )
    return [r[0] for r in cur.fetchall()]


def pkey(cur, schema, t):
    cur.execute(
        "select a.attname from pg_index i "
        "join pg_attribute a on a.attrelid=i.indrelid and a.attnum=any(i.indkey) "
        "where i.indrelid = %s::regclass and i.indisprimary order by a.attnum",
        (schema + '."' + t + '"',),
    )
    return [r[0] for r in cur.fetchall()]


def digest(cur, schema, t, cols):
    order = ", ".join('"' + c + '"' for c in cols)
    first = '"' + cols[0] + '"'
    sql = (
        "select md5(string_agg(" + first + "::text, " + SEP + " order by " + order + ")) "
        "from " + schema + '."' + t + '"'
    )
    cur.execute(sql)
    return cur.fetchone()[0]


with psycopg.connect(src_url, connect_timeout=20) as s, psycopg.connect(dst_url, connect_timeout=20) as d:
    sc, dc = s.cursor(), d.cursor()
    src_t = set(tables(sc, SRC))
    dst_t = set(tables(dc, DST)) - {"alembic_version"}
    src_t -= {"alembic_version"}
    if src_t - dst_t:
        print("원본에만 있는 표:", sorted(src_t - dst_t))
    if dst_t - src_t:
        print("이관본에만 있는 표:", sorted(dst_t - src_t))

    bad = []
    print("{:28s} {:>7s} {:>7s}  {}".format("표", SRC, DST, "체크섬"))
    for t in sorted(src_t & dst_t):
        sc.execute('select count(*) from ' + SRC + '."' + t + '"')
        n1 = sc.fetchone()[0]
        dc.execute('select count(*) from ' + DST + '."' + t + '"')
        n2 = dc.fetchone()[0]
        if n1 == 0 and n2 == 0:
            continue
        ck = "―"
        if n1 != n2:
            bad.append(t + " (건수)")
        else:
            cols = pkey(sc, SRC, t)
            if cols:
                h1 = digest(sc, SRC, t, cols)
                h2 = digest(dc, DST, t, cols)
                ck = "같음" if h1 == h2 else "★다름"
                if h1 != h2:
                    bad.append(t + " (내용)")
            else:
                ck = "(기본키 없음)"
        mark = "일치" if n1 == n2 else "★불일치"
        print(f"{t:28s} {n1:7d} {n2:7d}  {mark} {ck}")

    print()
    print("어긋난 표:", bad if bad else "없음")
    sys.exit(1 if bad else 0)
