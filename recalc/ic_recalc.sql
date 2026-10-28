-- ic_recalc.sql
-- My independent recalculation of the sample intercompany close, in plain
-- SQL over the three CSVs in data/synthetic/. I wrote this file; see
-- recalc/README.md for what it checks and how to run it.
--
-- Run from the repo root:
--   duckdb -c ".read recalc/ic_recalc.sql" -c "SELECT * FROM recalc_tieout"

-- ---------------------------------------------------------------------------
-- 0. Load the three files
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TABLE entities AS
    SELECT * FROM read_csv('data/synthetic/entities.csv', header = true);

CREATE OR REPLACE TABLE trial_balance AS
    SELECT * FROM read_csv('data/synthetic/trial_balance.csv', header = true);

CREATE OR REPLACE TABLE ic_ledger AS
    SELECT * FROM read_csv('data/synthetic/ic_ledger.csv', header = true);

-- ---------------------------------------------------------------------------
-- 1. Tie-out per entity: subledger vs control accounts in the trial balance
--
-- The subledger total is just the sum of ic_ledger for the entity. In the
-- TB, the intercompany position sits in two control accounts:
--   1000-IC-REC (receivable) and 2000-IC-PAY (payable, credit balance).
-- If the two don't agree within 1.00, the entity does not tie out and I want
-- to know before matching anything.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW recalc_tieout AS
WITH ledger_totals AS (
    SELECT
        entity_code,
        round(sum(amount), 2) AS ledger_total
    FROM ic_ledger
    GROUP BY entity_code
),
tb_totals AS (
    SELECT
        entity_code,
        round(sum(balance), 2) AS tb_total
    FROM trial_balance
    WHERE account_code IN ('1000-IC-REC', '2000-IC-PAY')
    GROUP BY entity_code
)
SELECT
    t.entity_code,
    l.ledger_total,
    t.tb_total,
    round(l.ledger_total - t.tb_total, 2) AS variance,
    abs(l.ledger_total - t.tb_total) > 1.00 AS is_break
FROM tb_totals t
JOIN ledger_totals l USING (entity_code)
ORDER BY t.entity_code;
