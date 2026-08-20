-- 표별 행 수. 원본과 새 DB 에서 각각 돌려 diff 로 비교한다.
-- 한 줄도 달라선 안 된다. 다르면 그 사이에 쓰는 작업이 돌았다는 뜻이다.
select table_name || ' ' || (xpath('/row/c/text()',
  query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name),
  false, true, '')))[1]::text::int
from information_schema.tables
where table_schema = 'public' and table_type = 'BASE TABLE'
order by table_name;
