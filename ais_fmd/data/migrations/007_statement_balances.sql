-- ===========================================================================
-- Migration 007 -- the statement_balances table.
--
-- Independent of 001-006.
--
-- WHY. The Reconciliation and Alerts & Reports pages read and write
-- `statement_balances` (opening/closing balance per account per statement
-- period), but the table's DDL only ever lived in `schema_postgres.sql` -- no
-- migration created it, so on the live project those pages would fail on first
-- use. Found in the 2026-09-23 launch audit. Copied verbatim from
-- `schema_postgres.sql`; the sandbox creates the same table in
-- `sqlite_backend.py`.
--
-- ADDITIVE. Creates one table if it is missing; touches nothing else.
--
--   Undo:  DROP TABLE public.statement_balances;
-- ===========================================================================

CREATE TABLE IF NOT EXISTS public.statement_balances (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account         text NOT NULL,
    period_start    date NOT NULL,
    period_end      date NOT NULL,
    opening_balance numeric NOT NULL,
    closing_balance numeric NOT NULL,
    source_file     text,
    recorded_at     timestamptz DEFAULT now(),
    CONSTRAINT statement_balances_period_key UNIQUE (account, period_start, period_end)
);
