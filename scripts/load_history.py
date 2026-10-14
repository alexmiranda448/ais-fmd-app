"""
Load real bank statements into the SANDBOX database, replacing the demo data.

    python scripts/load_history.py "<Checking (3).csv>" "<Checking (5).csv>"         "<VenmoStatement_December_2025.csv>" "<transactions_20260325_000407.csv>"

Same path as the Treasury page's upload -- parse, categorize, deduplicate,
insert -- for several files at once, oldest first. Overlapping exports are safe:
rows already loaded from an earlier file are recognised as duplicates.

Three kinds of file are accepted, told apart by their contents:

  * Wells Fargo checking exports (the 5-column CSV).
  * Venmo monthly statements.
  * An export of the OLD live app's `transactions` table. Only its **Venmo**
    rows are taken, and only from the earliest bank date onward. That export is
    the one place the Venmo account's history before December 2025 survives.
    Its checking rows are skipped (the bank's own exports are the better
    source), and so are its categories: every row is re-categorized by the
    current rules, like everything else.

What it sets up, and what it deliberately does not:

  * Committees from `config/categories.py`.
  * Terms on the real UF calendar (`TERMS` below), each running up to the day
    before the next starts, so every transaction belongs to some term.
  * Dues rates only where treasury confirmed them (`dues.CONFIRMED_DUES_RATES`).
    Other terms carry none and are reported as unconfirmed on Data Quality --
    which is true.
  * NO BUDGETS. `load_real_statement.py` invents $1,500 per committee per term so
    its pages have something to draw; here that would put fake numbers beside
    real spending. Enter real allocations on the Treasury page.

Sandbox only: it writes the local SQLite file and nothing else. The previous
file is copied aside first. Personal names are never printed.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ais_fmd.config.categories import COMMITTEES
from ais_fmd.data.sqlite_backend import SqliteBackend
from ais_fmd.domain.categorize.pipeline import categorize_frame
from ais_fmd.domain.dedupe import split_new_and_duplicate
from ais_fmd.domain.dues import CONFIRMED_DUES_RATES, format_rates, schedule_from_terms
from ais_fmd.domain.parsers import venmo, wells_fargo

ACTOR = "load-history@sandbox.local"

# Real term starts (the seed's calendar). Each term ends the day before the next
# begins; the last ends on its own date.
TERMS = [
    ("SU24", "Summer 2024", date(2024, 5, 3)),
    ("FA24", "Fall 2024", date(2024, 8, 21)),
    ("SP25", "Spring 2025", date(2025, 1, 6)),
    ("SU25", "Summer 2025", date(2025, 5, 3)),
    ("FA25", "Fall 2025", date(2025, 8, 20)),
    ("SP26", "Spring 2026", date(2026, 1, 5)),
    ("SU26", "Summer 2026", date(2026, 5, 2)),
    ("FA26", "Fall 2026", date(2026, 8, 15)),
]
LAST_TERM_ENDS = date(2026, 12, 18)


def bootstrap(backend: SqliteBackend) -> None:
    with backend._connect() as connection:  # noqa: SLF001
        connection.executemany(
            "INSERT OR REPLACE INTO committees (CommitteeID, Committee_Name, Committee_Type) "
            "VALUES (?, ?, ?)",
            [(c.id, c.name, c.kind) for c in COMMITTEES],
        )
        connection.commit()
    for position, (term_id, label, start) in enumerate(TERMS):
        if position + 1 < len(TERMS):
            end = TERMS[position + 1][2] - pd.Timedelta(days=1)
            end = end.date() if hasattr(end, "date") else end
        else:
            end = LAST_TERM_ENDS
        backend.insert_term(term_id, label, start.isoformat(), end.isoformat(), ACTOR)
        rates = CONFIRMED_DUES_RATES.get(label)
        if rates:
            backend.set_term_dues_rates(term_id, format_rates(rates), True, ACTOR)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="+", help="statement exports, any order")
    args = parser.parse_args()

    backend = SqliteBackend()
    if backend.path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backend.path.with_name(f"{backend.path.stem}.{stamp}.bak.db")
        shutil.copy2(backend.path, backup)
        print(f"backed up       : {backup.name}")
    backend.reset()
    bootstrap(backend)
    schedule = schedule_from_terms(backend.fetch_terms())

    parsed, app_exports = [], []
    for name in args.csv:
        source = Path(name)
        raw = pd.read_csv(source, header=None, dtype=str, keep_default_na=False)
        header = {str(v).strip().lower() for v in raw.iloc[0]}
        if {"transaction_date", "amount", "details", "account"} <= header:
            app_exports.append(source)
            continue
        is_venmo = "venmo" in source.name.lower()
        result = (venmo if is_venmo else wells_fargo).parse(
            raw if is_venmo else pd.read_csv(source, header=None), source_file=source.name
        )
        if not result.ok:
            print(f"{source.name}: could not parse -- {'; '.join(result.errors)}")
            return 1
        first = pd.to_datetime(result.rows["transaction_date"]).min()
        parsed.append((first, source, result.rows))

    bank_start = min((first for first, _, _ in parsed), default=None)
    for source in app_exports:
        export = pd.read_csv(source)
        export["transaction_date"] = pd.to_datetime(export["transaction_date"], errors="coerce")
        keep = export["account"].astype(str).str.lower().eq("venmo")
        if bank_start is not None:
            keep &= export["transaction_date"] >= bank_start
        rows = export.loc[keep, ["transaction_date", "amount", "details", "account"]].copy()
        rows["transaction_date"] = rows["transaction_date"].dt.strftime("%Y-%m-%d")
        rows["amount"] = pd.to_numeric(rows["amount"])
        parsed.append((pd.to_datetime(rows["transaction_date"]).min(), source, rows.reset_index(drop=True)))
    parsed.sort(key=lambda item: item[0])

    for _, source, rows in parsed:
        categorized, run = categorize_frame(rows, dues=schedule)
        existing = backend.fetch_transactions()
        split = split_new_and_duplicate(
            categorized.to_dict("records"),
            existing.to_dict("records") if not existing.empty else [],
        )
        receipt = backend.insert_transactions(split.new, source.name, ACTOR)
        if not receipt.ok:
            print(f"{source.name}: insert failed -- {receipt.error}")
            return 1
        print(
            f"{source.name:<20}: {len(rows):>4} rows, {receipt.inserted:>4} new, "
            f"{len(split.duplicates):>4} already loaded | {run.summary_line()}"
        )

    stored = backend.fetch_transactions()
    amounts = pd.to_numeric(stored["amount"])
    print(
        f"\nloaded          : {len(stored)} transactions, "
        f"{pd.to_datetime(stored['transaction_date']).min():%Y-%m-%d} .. "
        f"{pd.to_datetime(stored['transaction_date']).max():%Y-%m-%d}"
    )
    print(f"categorized     : {stored['budget_category'].notna().sum()} "
          f"({stored['budget_category'].isna().sum()} in the Review Queue)")
    print(f"net             : ${amounts.sum():,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
