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

-- ---------------------------------------------------------------------------
-- 2. Match the legs into pairs, one reference at a time
--
-- A clean intercompany pair is two legs that mirror each other: same
-- reference, A against B and B against A, same amount with opposite signs,
-- same currency, same month. Anything else is an exception, and the first
-- rule that fires decides the type. I number the legs of each reference
-- and put leg 1 and leg 2 side by side to compare them.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW recalc_pair_legs AS
WITH numbered AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY reference
            ORDER BY transaction_date, entity_code, counterparty_code
        ) AS leg_no
    FROM ic_ledger
)
SELECT
    reference,
    count(*) AS n_legs,
    -- rule 1: a leg booked against itself
    max(CASE WHEN entity_code = counterparty_code THEN 1 ELSE 0 END) AS self_dealing,
    -- leg 1
    max(CASE WHEN leg_no = 1 THEN entity_code END) AS e1,
    max(CASE WHEN leg_no = 1 THEN counterparty_code END) AS c1,
    max(CASE WHEN leg_no = 1 THEN amount END) AS a1,
    max(CASE WHEN leg_no = 1 THEN currency END) AS cur1,
    max(CASE WHEN leg_no = 1 THEN transaction_date END) AS d1,
    -- leg 2
    max(CASE WHEN leg_no = 2 THEN entity_code END) AS e2,
    max(CASE WHEN leg_no = 2 THEN counterparty_code END) AS c2,
    max(CASE WHEN leg_no = 2 THEN amount END) AS a2,
    max(CASE WHEN leg_no = 2 THEN currency END) AS cur2,
    max(CASE WHEN leg_no = 2 THEN transaction_date END) AS d2
FROM numbered
GROUP BY reference;

CREATE OR REPLACE VIEW recalc_pairs AS
SELECT
    reference,
    CASE
        WHEN self_dealing = 1 THEN 'self_dealing'
        WHEN n_legs = 1 THEN 'missing_counterparty'
        WHEN n_legs > 2 THEN 'duplicate_reference'
        -- rule 4: the two legs must point at each other
        WHEN e1 <> c2 OR e2 <> c1 THEN 'counterparty_mismatch'
        WHEN cur1 <> cur2 THEN 'currency_mismatch'
        -- rule 6: both legs the same sign, and neither is zero
        WHEN (a1 > 0 AND a2 > 0) OR (a1 < 0 AND a2 < 0) THEN 'sign_mismatch'
        -- rule 7: tolerance is the bigger of 1.00 and 0.01 % of the larger leg
        WHEN abs(a1 + a2) > greatest(1.00, 0.0001 * greatest(abs(a1), abs(a2)))
            THEN 'amount_mismatch'
        -- rule 8: booked in different months
        WHEN date_trunc('month', d1) <> date_trunc('month', d2) THEN 'timing_gap'
        ELSE 'clean'
    END AS outcome
FROM recalc_pair_legs
ORDER BY reference;

-- ---------------------------------------------------------------------------
-- 3. Total eliminated from the clean pairs only
--
-- For a clean pair the elimination is the receivable leg, the positive
-- one. The receivable of leg 1 is a1 when it is positive; a clean pair
-- always nets to ~zero, so the positive leg is what gets eliminated.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW recalc_eliminated AS
SELECT
    round(sum(CASE WHEN p.outcome = 'clean' THEN greatest(l.a1, l.a2) END), 2)
        AS total_eliminated_clean_pairs
FROM recalc_pairs p
JOIN recalc_pair_legs l USING (reference);
