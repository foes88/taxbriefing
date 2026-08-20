-- 값 지문. 행 수만 보면 "같은 개수의 다른 내용" 을 못 잡는다.
--
-- 정렬을 id 로 못 박는다. 정렬이 없으면 서버마다 순서가 달라 지문도
-- 달라지고, 멀쩡한 것을 깨진 것으로 읽는다.
select 'tax_contents ' || md5(string_agg(
         id::text || coalesce(title,'') || coalesce(one_line_summary,'')
         || coalesce(industries::text,''), '|' order by id)) from tax_contents
union all
select 'content_versions ' || md5(string_agg(
         id::text || coalesce(body::text,''), '|' order by id)) from content_versions
union all
select 'raw_contents ' || md5(string_agg(
         id::text || coalesce(title,'') || coalesce(canonical_url,''), '|' order by id)) from raw_contents
union all
select 'raw_content_versions ' || md5(string_agg(
         id::text || coalesce(content_hash,''), '|' order by id)) from raw_content_versions
union all
select 'sources ' || md5(string_agg(
         id::text || display_name, '|' order by id)) from sources
union all
select 'reviews ' || md5(string_agg(
         id::text || coalesce(review_note,''), '|' order by id)) from reviews;
