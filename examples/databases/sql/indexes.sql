-- Індекси й EXPLAIN на 200 000 новин. PostgreSQL 16; після sql_basics.sql (потрібні таблиці sources і news).
--   docker exec -i part05-pg psql -U postgres < sql/indexes.sql

\set ON_ERROR_STOP 1
\timing off
SET client_min_messages = warning;
DROP INDEX IF EXISTS news_source_id_idx, news_lang_published_idx, news_lower_title_idx, news_title_trgm_idx;
RESET client_min_messages;
DELETE FROM news WHERE url LIKE 'https://gen/%';

INSERT INTO news (source_id, url, title, lang, category, views, published_at)
SELECT 1 + n % 4,
       'https://gen/' || n,
       'Згенерована новина ' || n,
       (ARRAY['uk', 'ru', 'en'])[1 + n % 3],
       (ARRAY['Економіка', 'Енергетика', 'Технології', 'Суспільство'])[1 + n % 4],
       n % 1000,
       timestamptz '2026-01-01' + n * interval '1 minute'
FROM generate_series(1, 200000) AS n;
ANALYZE news;

\echo '--- 1. UNIQUE (url) уже дає індекс'
EXPLAIN SELECT * FROM news WHERE url = 'https://gen/777';

\echo '--- 2. зовнішній ключ індексу НЕ отримує'
EXPLAIN SELECT count(*) FROM news WHERE source_id = 4;
CREATE INDEX news_source_id_idx ON news (source_id);
EXPLAIN SELECT count(*) FROM news WHERE source_id = 4;

\echo '--- 3. стрічка API: фільтр + сортування + LIMIT'
EXPLAIN ANALYZE SELECT id, title FROM news WHERE lang = 'uk' ORDER BY published_at DESC LIMIT 20;
CREATE INDEX news_lang_published_idx ON news (lang, published_at DESC);
EXPLAIN ANALYZE SELECT id, title FROM news WHERE lang = 'uk' ORDER BY published_at DESC LIMIT 20;

\echo '--- 4. пошук підрядка: B-tree не допомагає'
EXPLAIN SELECT id FROM news WHERE lower(title) LIKE '%новина 777%';
CREATE INDEX news_lower_title_idx ON news (lower(title));
EXPLAIN SELECT id FROM news WHERE lower(title) LIKE '%новина 777%';
EXPLAIN SELECT id FROM news WHERE lower(title) = 'згенерована новина 777';
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX news_title_trgm_idx ON news USING gin (lower(title) gin_trgm_ops);
EXPLAIN SELECT id FROM news WHERE lower(title) LIKE '%новина 777%';

\echo '--- 5. розмір таблиці й індексів'
SELECT relname AS name, pg_size_pretty(pg_relation_size(oid)) AS size
FROM pg_class
WHERE relname IN ('news', 'news_pkey', 'news_url_key', 'news_source_id_idx',
                  'news_lang_published_idx', 'news_lower_title_idx', 'news_title_trgm_idx')
ORDER BY pg_relation_size(oid) DESC;

DELETE FROM news WHERE url LIKE 'https://gen/%';
DROP INDEX news_source_id_idx, news_lang_published_idx, news_lower_title_idx, news_title_trgm_idx;
