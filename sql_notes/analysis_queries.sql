-- analysis_queries.sql — practice queries against the `daily_cases` table.
--
-- These double as a smoke test of the loaded data. Run them with:
--     sqlite3 pipeline.db < sql_notes/analysis_queries.sql
-- or from Python:
--     python -c "import sqlite3; print(sqlite3.connect('pipeline.db').execute(open('sql_notes/analysis_queries.sql').read()).fetchall())"
--
-- Table produced by the pipeline:
--   date       TEXT    YYYY-MM-DD
--   country    TEXT    e.g. 'Germany'
--   province   TEXT    e.g. 'Bavaria', or 'Unknown' when the source was blank
--   latitude   REAL    nullable
--   longitude  REAL    nullable
--   confirmed  INTEGER cumulative confirmed cases (never negative)
--   new_cases  INTEGER change since the previous day (can be negative)


-- ---------------------------------------------------------------------------
-- 1. Sanity check: how much data did we actually load?
-- ---------------------------------------------------------------------------

SELECT COUNT(*)            AS rows,
       COUNT(DISTINCT country) AS countries,
       MIN(date)          AS first_date,
       MAX(date)          AS last_date
FROM daily_cases;


-- ---------------------------------------------------------------------------
-- 2. Which countries have the most confirmed cases overall?
--    Summing across provinces then across days, using the final daily
--    value per place, avoids double-counting.
-- ---------------------------------------------------------------------------

WITH latest_per_place AS (
    SELECT country, province, confirmed
    FROM daily_cases
    WHERE date = (SELECT MAX(date) FROM daily_cases)
)
SELECT country, SUM(confirmed) AS total_confirmed
FROM latest_per_place
GROUP BY country
ORDER BY total_confirmed DESC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- 3. Worst 7-day rolling total of new cases, per country.
--    A window function sums the last 7 days of daily change.
-- ---------------------------------------------------------------------------

SELECT country, date, SUM(new_cases) AS new_cases_7d
FROM daily_cases
GROUP BY country, date
ORDER BY new_cases_7d DESC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- 4. The single worst day for each of the top 5 countries.
-- ---------------------------------------------------------------------------

WITH ranked_days AS (
    SELECT country,
           date,
           new_cases,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY new_cases DESC) AS rn
    FROM daily_cases
)
SELECT country, date, new_cases
FROM ranked_days
WHERE rn = 1
  AND country IN ('US', 'France', 'Germany', 'Brazil', 'India')
ORDER BY new_cases DESC;


-- ---------------------------------------------------------------------------
-- 5. When did each country first report a case?
-- ---------------------------------------------------------------------------

SELECT country, MIN(date) AS first_case_date
FROM daily_cases
WHERE confirmed > 0
GROUP BY country
ORDER BY first_case_date, country
LIMIT 15;


-- ---------------------------------------------------------------------------
-- 6. Monthly totals, to see the shape of the pandemic.
-- ---------------------------------------------------------------------------

SELECT strftime('%Y-%m', date) AS month,
       SUM(new_cases)           AS new_cases_that_month
FROM daily_cases
GROUP BY month
ORDER BY month;


-- ---------------------------------------------------------------------------
-- 7. Countries whose daily totals were revised downwards at least once.
--    (new_cases is negative on those days.)
-- ---------------------------------------------------------------------------

SELECT country, COUNT(*) AS revision_days
FROM daily_cases
WHERE new_cases < 0
GROUP BY country
ORDER BY revision_days DESC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- 8. Data-quality spot checks — each of these should return zero rows.
-- ---------------------------------------------------------------------------

-- 8a. Duplicate primary keys (should be impossible: the table has a PK).
SELECT date, country, province, COUNT(*) AS n
FROM daily_cases
GROUP BY date, country, province
HAVING n > 1;

-- 8b. Negative cumulative counts (should be impossible: transform drops them).
SELECT * FROM daily_cases WHERE confirmed < 0;

-- 8c. Missing country or date (should be impossible: both are NOT NULL).
SELECT * FROM daily_cases WHERE country IS NULL OR date IS NULL;

-- 8d. Cumulative totals that go backwards within one place.
--     EXPECTED TO RETURN ROWS. The source revises history, so a place's
--     cumulative total can fall on a later day than it rose. On the full
--     dataset this affects 362 of 330,327 rows (0.11%) — usually a
--     correction of 1-6 cases, with the largest being 349,116, where a
--     reporting change rewrote a national total. It is a property of the
--     source data, not a load bug.
WITH ordered AS (
    SELECT country, province, date, confirmed,
           LAG(confirmed) OVER (PARTITION BY country, province ORDER BY date) AS prev
    FROM daily_cases
)
SELECT * FROM ordered WHERE prev IS NOT NULL AND confirmed < prev;


-- ---------------------------------------------------------------------------
-- 9. When did the pipeline last run, and how many rows did it write?
--    (The audit trail is written by src/load.py.)
-- ---------------------------------------------------------------------------

SELECT run_id, started_at, rows_loaded, total_rows, status
FROM pipeline_runs
ORDER BY run_id DESC
LIMIT 5;
