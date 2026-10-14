-- ===========================================================================
-- Migration 006 -- committee 6 becomes Operations.
--
-- Independent of 001-005.
--
-- WHY. Corporate Relations is defunct; the VP of Operations' committee took
-- its place (treasury, 2026-10-01). The app reads committee names from
-- `config/categories.py`, but this table holds the same list, so it has to
-- agree with it. The ID stays 6, so earlier terms' budgets and transactions
-- keep their committee and simply show the new name.
--
-- Mirrors the rename in `ais_fmd/config/categories.py`. A fresh sandbox
-- picks it up from `seed.py`; an existing one needs the same UPDATE.
--
--   Undo:  UPDATE public.committees SET "Committee_Name" = 'Corporate Relations'
--          WHERE "CommitteeID" = 6;
-- ===========================================================================

UPDATE public.committees
SET "Committee_Name" = 'Operations'
WHERE "CommitteeID" = 6;
