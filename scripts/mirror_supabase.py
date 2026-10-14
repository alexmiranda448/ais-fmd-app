"""
Rebuild the SANDBOX database as a mirror of live Supabase, plus newer statements.

    python scripts/prod/inspect_supabase.py --export sandbox_data/supabase-export
    python scripts/mirror_supabase.py sandbox_data/supabase-export \\
        "<Checking (3).csv>" "<Checking (5).csv>"

Treasury's rule (2026-10-02): history already categorized in Supabase is the
record and must not change. So:

  * Every live transaction is copied as stored -- committee and purpose
    untouched, blanks left blank (they show up in the Review Queue). The
    categorizer never runs on them.
  * Live terms and budgets are copied as stored.
  * Statements are only used for what Supabase does not have yet: rows dated
    after the last live transaction on that account. Only those are
    categorized. Rows on the cut-off day itself are kept only if live has
    nothing with the same date, amount and account.

What it adds on top of the live data, and says so:

  * Committee names come from `config/categories.py` -- i.e. after migration
    006 (6 = Operations). IDs are unchanged.
  * A Fall 2026 term if live has none, following live's own convention of fall
    starting the day after spring ends.
  * Dues rates for the terms treasury confirmed. Live has no rates column
    until migration 001 runs.

Sandbox only: writes the local SQLite file, after copying the old one aside.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ais_fmd.config.categories import COMMITTEES, normalize_account
from ais_fmd.data.sqlite_backend import SqliteBackend
from ais_fmd.domain.categorize.pipeline import categorize_frame
from ais_fmd.domain.dedupe import split_new_and_duplicate
from ais_fmd.domain.dues import CONFIRMED_DUES_RATES, format_rates, schedule_from_terms
from ais_fmd.domain.parsers import venmo, wells_fargo

ACTOR = "mirror-supabase@sandbox.local"
FALL_2026_ENDS = date(2026, 12, 18)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("export_dir", help="output of inspect_supabase.py --export")
    parser.add_argument("statements", nargs="*", help="newer bank/Venmo exports")
    args = parser.parse_args()
    export = Path(args.export_dir)

    live = pd.read_csv(export / "transactions.csv")
    terms = pd.read_csv(export / "terms.csv")
    budgets = pd.read_csv(export / "committeebudgets.csv")

    backend = SqliteBackend()
    if backend.path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backend.path.with_name(f"{backend.path.stem}.{stamp}.bak.db")
        shutil.copy2(backend.path, backup)
        print(f"backed up        : {backup.name}")
    backend.reset()

    # --- reference data ------------------------------------------------------
    with backend._connect() as connection:  # noqa: SLF001
        connection.executemany(
            "INSERT OR REPLACE INTO committees (CommitteeID, Committee_Name, Committee_Type) "
            "VALUES (?, ?, ?)",
            [(c.id, c.name, c.kind) for c in COMMITTEES],
        )
        connection.commit()

    terms = terms.sort_values("start_date")
    for row in terms.itertuples():
        backend.insert_term(row.TermID, row.Semester, str(row.start_date)[:10], str(row.end_date)[:10], ACTOR)
    if "Fall 2026" not in set(terms["Semester"]):
        spring_end = pd.to_datetime(terms.loc[terms["Semester"] == "Spring 2026", "end_date"]).max()
        start = (spring_end + timedelta(days=1)).date() if pd.notna(spring_end) else date(2026, 5, 6)
        backend.insert_term("FA26", "Fall 2026", start.isoformat(), FALL_2026_ENDS.isoformat(), ACTOR)
        print(f"added term       : Fall 2026 ({start} .. {FALL_2026_ENDS}) -- not in live yet")
    for term_id, label in backend.fetch_terms()[["TermID", "Semester"]].itertuples(index=False):
        if label in CONFIRMED_DUES_RATES:
            backend.set_term_dues_rates(term_id, format_rates(CONFIRMED_DUES_RATES[label]), True, ACTOR)

    for term_id, group in budgets.groupby("termid"):
        backend.upsert_budgets(
            str(term_id),
            {int(c): float(a) for c, a in zip(group["committeeid"], group["budget_amount"]) if pd.notna(a)},
            ACTOR,
        )

    # --- live transactions, exactly as stored ------------------------------------
    live_rows = []
    for row in live.itertuples():
        category = None if pd.isna(row.budget_category) else int(row.budget_category)
        live_rows.append({
            "transaction_date": str(row.transaction_date)[:10],
            "amount": float(row.amount),
            "details": "" if pd.isna(row.details) else str(row.details),
            "budget_category": category,
            "purpose": None if pd.isna(row.purpose) else str(row.purpose),
            "account": normalize_account(str(row.account)) or str(row.account),
        })
    split = split_new_and_duplicate(live_rows, [])
    receipt = backend.insert_transactions(split.new, "supabase-export", ACTOR)
    if not receipt.ok:
        print(f"live copy failed: {receipt.error}")
        return 1
    print(f"live copied      : {receipt.inserted} of {len(live)} transactions, categories as stored")

    # --- statements: only what live does not have yet ----------------------------
    live_frame = pd.DataFrame(live_rows)
    live_frame["d"] = pd.to_datetime(live_frame["transaction_date"])
    cutoff = live_frame.groupby("account")["d"].max().to_dict()
    on_cutoff = {
        (r.account, r.transaction_date, round(r.amount, 2))
        for r in live_frame.itertuples() if r.d == cutoff.get(r.account)
    }
    schedule = schedule_from_terms(backend.fetch_terms())

    fresh = []
    for name in args.statements:
        source = Path(name)
        is_venmo = "venmo" in source.name.lower()
        raw = pd.read_csv(source, header=None, dtype=str, keep_default_na=False) if is_venmo \
            else pd.read_csv(source, header=None)
        result = (venmo if is_venmo else wells_fargo).parse(raw, source_file=source.name)
        if not result.ok:
            print(f"{source.name}: could not parse -- {'; '.join(result.errors)}")
            return 1
        rows = result.rows.copy()
        rows["account"] = rows["account"].map(lambda a: normalize_account(a) or a)
        dates = pd.to_datetime(rows["transaction_date"])
        limit = rows["account"].map(cutoff)
        newer = dates > limit
        same_day = (dates == limit) & pd.Series([
            (a, str(d)[:10], round(float(m), 2)) not in on_cutoff
            for a, d, m in zip(rows["account"], rows["transaction_date"], rows["amount"])
        ], index=rows.index)
        unseen_account = limit.isna()
        fresh.append(rows[newer | same_day | unseen_account].assign(_source=source.name))

    if fresh:
        new_rows = pd.concat(fresh, ignore_index=True)
        stored = backend.fetch_transactions()
        split = split_new_and_duplicate(new_rows.drop(columns="_source").to_dict("records"),
                                        stored.to_dict("records"))
        frame = pd.DataFrame(split.new)
        if not frame.empty:
            categorized, run = categorize_frame(frame.drop(columns=["natural_key"], errors="ignore"), dues=schedule)
            split2 = split_new_and_duplicate(categorized.to_dict("records"), stored.to_dict("records"))
            receipt = backend.insert_transactions(split2.new, "statements-after-live", ACTOR)
            print(f"newer statements : {receipt.inserted} transactions after "
                  + ", ".join(f"{a} {d:%Y-%m-%d}" for a, d in cutoff.items())
                  + f" | {run.summary_line()}")

    final = backend.fetch_transactions()
    print(f"\nsandbox now      : {len(final)} transactions, "
          f"{pd.to_datetime(final['transaction_date']).min():%Y-%m-%d} .. "
          f"{pd.to_datetime(final['transaction_date']).max():%Y-%m-%d}, "
          f"{final['budget_category'].isna().sum()} uncategorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
