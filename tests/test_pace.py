"""Same-day comparison, pace and runway (domain.pace)."""

from __future__ import annotations

import pandas as pd
import pytest

from ais_fmd.config.categories import BUDGETED_COMMITTEE_IDS
from ais_fmd.domain import pace

COMMITTEE = sorted(BUDGETED_COMMITTEE_IDS)[0]


@pytest.fixture
def terms() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"TermID": "FA25", "Semester": "Fall 2025", "start_date": "2025-08-18", "end_date": "2025-12-19"},
            {"TermID": "SP26", "Semester": "Spring 2026", "start_date": "2026-01-05", "end_date": "2026-05-01"},
            {"TermID": "FA26", "Semester": "Fall 2026", "start_date": "2026-08-17", "end_date": "2026-12-18"},
        ]
    )


@pytest.fixture
def transactions() -> pd.DataFrame:
    rows = [
        ("2025-08-20", 500.0, None, "Dues"),
        ("2025-08-25", -100.0, COMMITTEE, "Supplies"),
        ("2025-11-01", 300.0, None, "Sponsorship"),
        ("2025-11-02", -400.0, COMMITTEE, "Event"),
        ("2026-08-19", 800.0, None, "Dues"),
        ("2026-08-24", -150.0, COMMITTEE, "Supplies"),
    ]
    return pd.DataFrame(
        [
            {"transaction_date": d, "amount": a, "budget_category": c, "purpose": p, "details": ""}
            for d, a, c, p in rows
        ]
    )


@pytest.fixture
def budgets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"termid": "FA25", "committeeid": COMMITTEE, "budget_amount": 1000.0},
            {"termid": "FA26", "committeeid": COMMITTEE, "budget_amount": 1000.0},
        ]
    )


def test_equivalent_prior_is_same_season_last_year(terms):
    assert pace.equivalent_prior(terms, "Fall 2026") == "Fall 2025"
    # No earlier spring: falls back to the previous term.
    assert pace.equivalent_prior(terms, "Spring 2026") == "Fall 2025"
    assert pace.equivalent_prior(terms, "Fall 2025") is None


def test_term_clock_clamps_to_the_term(terms):
    before = pace.term_clock(terms, "Fall 2026", as_of=pd.Timestamp("2026-01-01"))
    after = pace.term_clock(terms, "Fall 2026", as_of=pd.Timestamp("2027-03-01"))
    assert before.day == 0 and not before.finished
    assert after.finished and after.fraction == 1.0


def test_same_day_history_cuts_at_the_same_day(transactions, terms, budgets):
    history = pace.same_day_history(transactions, terms, ["Fall 2025", "Fall 2026"], 10, budgets)
    # Fall 2025 at day 10 excludes the November rows.
    assert history["Fall 2025"]["income"] == 500.0
    assert history["Fall 2025"]["expenses"] == 100.0
    assert history["Fall 2026"]["net"] == 650.0
    assert history["Fall 2026"]["used"] == pytest.approx(15.0)


def test_cumulative_by_day_has_one_row_per_day(transactions, terms):
    curve = pace.cumulative_by_day(transactions, terms, "Fall 2026", measure="expenses", through_day=20)
    assert list(curve["Day"]) == list(range(21))
    assert curve["Value"].iloc[-1] == 150.0
    assert curve["Value"].is_monotonic_increasing


def test_cash_runway_projects_from_today(transactions, terms, budgets):
    clock = pace.term_clock(terms, "Fall 2026", as_of=pd.Timestamp("2026-08-31"))
    runway = pace.cash_runway(transactions, budgets, terms, None, clock, prior="Fall 2025")
    assert not runway.anchored
    assert runway.actual["Day"].iloc[-1] == clock.day
    assert runway.projected["Day"].iloc[0] == clock.day
    assert runway.end_low <= runway.end_mid <= runway.end_high


def test_cash_runway_ties_to_a_statement(transactions, terms, budgets):
    clock = pace.term_clock(terms, "Fall 2026", as_of=pd.Timestamp("2026-08-31"))
    balances = pd.DataFrame(
        [{"account": "Checking", "period_start": "2026-08-01", "period_end": "2026-08-20",
          "opening_balance": 0.0, "closing_balance": 5000.0}]
    )
    runway = pace.cash_runway(transactions, budgets, terms, balances, clock)
    assert runway.anchored
    # 5000 at Aug 20, then -150 on Aug 24.
    assert runway.today_balance == pytest.approx(4850.0)


def test_flow_steps_sum_to_the_net(transactions, terms):
    steps = pace.flow_steps(transactions, terms, "Fall 2025")
    moves = sum(value for _, value, kind in steps if kind != "net")
    assert steps[-1][2] == "net"
    assert steps[-1][1] == pytest.approx(moves)


def test_committee_pace_is_worst_first(transactions, terms, budgets):
    clock = pace.term_clock(terms, "Fall 2026", as_of=pd.Timestamp("2026-08-31"))
    table = pace.committee_pace(transactions, budgets, terms, clock)
    assert not table.empty
    assert table["Pace"].is_monotonic_decreasing


def test_flow_waterfall_keeps_repeated_labels_apart():
    """'Formal' is both an income purpose and a committee; each needs its own bar."""
    from ais_fmd.ui import charts

    steps = [("Formal", 1550.0, "in"), ("Formal", -1560.0, "out"), ("Net", -10.0, "net")]
    trace = charts.flow_waterfall(steps).data[0]
    assert list(trace.x) == [0, 1, 2]
    assert list(trace.customdata) == ["Formal", "Formal", "Net"]
