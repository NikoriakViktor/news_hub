-- SQL, яке потрібне API: ключі, обмеження, SELECT, GROUP BY, JOIN, підзапити, транзакції.
-- PostgreSQL 16. Запуск (контейнер з README):
--   docker exec -i part05-pg psql -U postgres < sql/sql_basics.sql
-- Скрипт можна запускати багато разів: на початку він видаляє свої таблиці.

\set ON_ERROR_STOP 0
SET client_min_messages = warning;
DROP TABLE IF EXISTS news, sources, balances CASCADE;
RESET client_min_messages;

\echo '--- 1. CREATE TABLE'
CREATE TABLE sources (
    id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    url  text NOT NULL UNIQUE
);

CREATE TABLE news (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id    integer NOT NULL REFERENCES sources (id),
    url          text NOT NULL UNIQUE,
    title        text NOT NULL CHECK (length(title) >= 5),
    lang         text NOT NULL CHECK (lang IN ('uk', 'ru', 'en')),
    category     text NOT NULL,
    views        integer NOT NULL DEFAULT 0 CHECK (views >= 0),
    sentiment    text CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    published_at timestamptz NOT NULL DEFAULT now()
);

\echo '--- 2. INSERT ... RETURNING'
INSERT INTO sources (name, url) VALUES
    ('rbc.ua', 'https://www.rbc.ua'),
    ('ukrinform', 'https://www.ukrinform.ua'),
    ('pravda', 'https://www.pravda.com.ua'),
    ('suspilne', 'https://suspilne.media');

INSERT INTO news (source_id, url, title, lang, category, views, sentiment, published_at) VALUES
    (1, 'https://www.rbc.ua/ukr/news/1', 'Гривня зміцнилася на міжбанку',       'uk', 'Економіка',   540, 'positive', '2026-11-09 09:10+02'),
    (1, 'https://www.rbc.ua/rus/news/2', 'Курс евро снизился',                  'ru', 'Економіка',   320, 'negative', '2026-11-09 10:05+02'),
    (2, 'https://www.ukrinform.ua/3',    'Укрзалізниця призначила нові поїзди', 'uk', 'Суспільство', 980, 'positive', '2026-11-09 19:40+02'),
    (3, 'https://www.pravda.com.ua/4',   'Енергетики відновили живлення',       'uk', 'Енергетика',  760, 'positive', '2026-11-10 18:15+02'),
    (1, 'https://www.rbc.ua/rus/news/5', 'Цены на топливо выросли',             'ru', 'Економіка',   450, 'negative', '2026-11-10 20:30+02'),
    (2, 'https://www.ukrinform.ua/6',    'Kyiv hosts a tech summit',            'en', 'Технології',  610, 'neutral',  '2026-11-11 12:45+02'),
    (3, 'https://www.pravda.com.ua/7',   'Графіки відключень на тиждень',       'uk', 'Енергетика', 1250, 'negative', '2026-11-11 19:20+02'),
    (1, 'https://www.rbc.ua/ukr/news/8', 'Нацбанк зберіг облікову ставку',      'uk', 'Економіка',   280, NULL,       '2026-11-12 13:00+02'),
    (2, 'https://www.ukrinform.ua/9',    'Стартап зі Львова залучив інвестиції','uk', 'Технології',  390, NULL,       '2026-11-12 13:10+02')
RETURNING id, title, views;

\echo '--- 3. обмеження: CHECK, FOREIGN KEY, UNIQUE, NOT NULL'
INSERT INTO news (source_id, url, title, lang, category) VALUES (1, 'https://x/10', 'Новина', 'pl', 'Світ');
INSERT INTO news (source_id, url, title, lang, category) VALUES (99, 'https://x/11', 'Новина', 'uk', 'Світ');
INSERT INTO news (source_id, url, title, lang, category) VALUES (1, 'https://www.rbc.ua/ukr/news/1', 'Дубль', 'uk', 'Світ');
INSERT INTO news (source_id, url, lang, category) VALUES (1, 'https://x/12', 'uk', 'Світ');

\echo '--- 4. UPDATE і DELETE'
UPDATE news SET views = views + 1 WHERE id = 8 RETURNING id, views;
DELETE FROM sources WHERE name = 'rbc.ua';

\echo '--- 5. SELECT ... WHERE ... ORDER BY'
SELECT id, title, views FROM news WHERE views >= 500 ORDER BY views DESC;

SELECT id, title, lang, sentiment
FROM news
WHERE lang IN ('ru', 'en') OR title LIKE 'Г%'
ORDER BY id;

SELECT count(*) AS by_equals FROM news WHERE sentiment = NULL;
SELECT count(*) AS by_is FROM news WHERE sentiment IS NULL;

\echo '--- 6. псевдонім з SELECT у WHERE'
SELECT id, views * 2 AS double_views FROM news WHERE double_views > 2000;

\echo '--- 7. агрегати, GROUP BY, HAVING'
SELECT count(*) AS news, sum(views) AS views, round(avg(views), 2) AS avg_views FROM news WHERE lang = 'uk';

SELECT category, count(*) AS news, sum(views) AS views
FROM news
GROUP BY category
ORDER BY views DESC, category;

SELECT category, sum(views) AS views
FROM news
GROUP BY category
HAVING sum(views) > 1500
ORDER BY category;

SELECT category, title, sum(views) FROM news GROUP BY category;

\echo '--- 8. JOIN і LEFT JOIN'
SELECT n.id, s.name AS source, n.title
FROM news AS n
JOIN sources AS s ON s.id = n.source_id
WHERE n.lang = 'uk'
ORDER BY n.id;

SELECT s.name, count(n.id) AS negative_news
FROM sources AS s
LEFT JOIN news AS n ON n.source_id = s.id AND n.sentiment = 'negative'
GROUP BY s.id, s.name
ORDER BY negative_news DESC, s.name;

SELECT s.name, count(n.id) AS negative_news
FROM sources AS s
LEFT JOIN news AS n ON n.source_id = s.id
WHERE n.sentiment = 'negative'
GROUP BY s.id, s.name
ORDER BY negative_news DESC, s.name;

\echo '--- 9. підзапити і WITH'
SELECT id, title, views FROM news WHERE views > (SELECT avg(views) FROM news) ORDER BY views DESC;

WITH source_views AS (
    SELECT source_id, sum(views) AS views
    FROM news
    GROUP BY source_id
)
SELECT s.name, sv.views
FROM source_views AS sv
JOIN sources AS s ON s.id = sv.source_id
WHERE sv.views > (SELECT avg(views) FROM source_views)
ORDER BY sv.views DESC;

\echo '--- 10. транзакції'
CREATE TABLE balances (owner text PRIMARY KEY, amount numeric(10, 2) NOT NULL CHECK (amount >= 0));
INSERT INTO balances VALUES ('фонд', 1000), ('автор', 0);

BEGIN;
UPDATE balances SET amount = amount - 300 WHERE owner = 'фонд';
UPDATE balances SET amount = amount + 300 WHERE owner = 'автор';
COMMIT;
SELECT * FROM balances ORDER BY owner;

BEGIN;
UPDATE balances SET amount = amount + 900 WHERE owner = 'автор';
UPDATE balances SET amount = amount - 900 WHERE owner = 'фонд';
SELECT * FROM balances;
ROLLBACK;
SELECT * FROM balances ORDER BY owner;
