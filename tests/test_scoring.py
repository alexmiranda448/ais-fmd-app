"""
Weighted evidence scoring (M18), the confidence gate, and the card's place above both.

Treasury's ruling of 2026-09-23 decides the shape of these tests: **the card is
the most highly valued evidence there is.** A purchase on a card confirmed for
the current officer cohort is that card's committee, whatever the merchant, the
weekday or the amount suggest -- so the pipeline books it before scoring runs,
and a directly-scored confirmed card still outweighs everything else scoring
can say. Merchant memory is gone from categorization entirely.

What scoring still does is weigh the evidence on purchases whose card is *not*
on the roster, and route the uncertain ones to a human instead of booking them.
"""

from __future__ import annotations

import inspect

import pytest

from ais_fmd.domain.categorize import pipeline
from ais_fmd.domain.categorize.pipeline import categorize_records
from ais_fmd.domain.categorize.scoring import (
    AUTO_APPLY_THRESHOLD,
    CARD_DEFAULT_CONFIDENCE,
    MAX_NON_CARD_EVIDENCE,
    W_CARD_VERIFIED,
    CardAssignment,
    CardRegistry,
    ScoredResult,
    card_number,
    score,
)


def wells(merchant: str, purchase: str = "09/16", card: str = "1234") -> str:
    """A realistic Wells Fargo line, with the run-of-spaces padding real ones have."""
    return (
        f"PURCHASE                      AUTHORIZED ON   {purchase} {merchant}"
        f"              GAINESVILLE   FL  S304257782821355   CARD {card}"
    )


def record(details: str, amount: float, date: str = "2025-09-18") -> dict:
    return {"details": details, "amount": amount, "transaction_date": date, "account": "Wells Fargo"}


# A roster fixed in the test, so these tests say what the categorizer does with
# a card -- not which cards happen to be in config/card_roster.json this year.
ROSTER = CardRegistry(
    {
        "5718": CardAssignment(5, "Membership VP", verified=True),
        "3568": CardAssignment(4, "President", verified=True),
    }
)

# 09/16/2025 is a Tuesday: food + meeting weekday + catering-sized is the
# strongest reading scoring can produce without a card.
FULL_MEETING_FOOD = ("PUBLIX #1560", "09/16", -159.80)


# --- Card extraction ---------------------------------------------------------

def test_card_number_reads_the_last_four():
    assert card_number(wells("PUBLIX", card="5718")) == "5718"


def test_card_number_absent_is_none():
    assert card_number("ZELLE FROM JANE DOE ON 07/08 REF # ABC123") is None


# --- The card outranks everything --------------------------------------------

def test_a_confirmed_card_outweighs_everything_scoring_can_say():
    """
    The 2026-09-23 ruling, at the level of weights. Before it, a card only
    *contested* a Tuesday food run (4.0 against 6.5) and Meeting Food won. The
    card now wins that contest outright, by enough margin to clear the gate.
    """
    merchant, purchase, amount = FULL_MEETING_FOOD
    result = score(record(wells(merchant, purchase, card="5718"), amount), cards=ROSTER)
    assert result.winner == 5, "the card must beat a full meeting-food reading"
    assert result.is_confident, f"and win it decisively, got {result.confidence}"


def test_the_card_weight_is_derived_so_it_cannot_fall_behind():
    """If someone adds or raises a signal, the card weight moves with it."""
    assert W_CARD_VERIFIED >= 2 * MAX_NON_CARD_EVIDENCE


def test_the_pipeline_books_a_confirmed_card_by_default():
    run = categorize_records([record(wells("DICKS SPORTING GOODS", "10/14", card="5718"), -60.00)],
                             cards=ROSTER)
    booked = run.classifications[0]
    assert booked.committee_id == 5
    assert booked.source == "rule"
    assert booked.confidence == CARD_DEFAULT_CONFIDENCE
    assert "Card 5718" in booked.rule, "the reason must name the card"
    assert 0 not in run.proposals, "nothing argued with the card"


def test_the_pipeline_lets_every_other_signal_overrule_the_card():
    """Treasury, 2026-10-01: the card is the default, not a verdict."""
    merchant, purchase, amount = FULL_MEETING_FOOD
    run = categorize_records([record(wells(merchant, purchase, card="5718"), amount)], cards=ROSTER)
    assert run.classifications[0].committee_id == 8
    assert 0 in run.proposals, "the queue can still show the evidence that overruled it"


def test_a_card_booking_names_its_holder():
    run = categorize_records([record(wells("SOMEWHERE", "10/14", card="3568"), -50.00)], cards=ROSTER)
    assert "President" in run.classifications[0].rule


# --- Merchant memory is out of categorization --------------------------------

def test_categorization_no_longer_takes_merchant_memory():
    """
    Treasury, 2026-09-23: merchant rules come out -- Consulting food and Meeting
    Food come from the same restaurants, so a merchant's history says nothing
    reliable about the next purchase, and it was able to override the card.
    """
    for function in (pipeline.categorize_records, pipeline.categorize_frame):
        parameters = inspect.signature(function).parameters
        assert "merchants" not in parameters, function.__name__


def test_scoring_no_longer_weighs_merchant_history():
    parameters = inspect.signature(score).parameters
    assert "merchant_history" not in parameters
    assert "remembered_committee" not in parameters


# --- Scoring, for cards that are not on the roster ---------------------------

def test_confident_rows_are_applied_and_carry_their_confidence():
    # Card 1113 has no known holder, so nothing competes with the meeting-food
    # reading and it applies cleanly.
    merchant, purchase, amount = FULL_MEETING_FOOD
    run = categorize_records([record(wells(merchant, purchase, card="1113"), amount)], cards=ROSTER)
    assert run.classifications[0].committee_id == 8
    assert run.classifications[0].source == "scored"
    assert run.classifications[0].confidence >= AUTO_APPLY_THRESHOLD


def test_uncorroborated_weak_evidence_does_not_clear_the_gate():
    """A lone food-merchant keyword is not enough to book money on."""
    result = score(
        record(wells("PUBLIX #1560", "09/20", card="1113"), -40.00, "2025-09-22"),  # Saturday
        cards=ROSTER,
    )
    assert not result.is_confident


def test_low_confidence_rows_are_held_back_but_keep_their_proposal():
    """Don't book the uncertain ones, but don't throw the reasoning away either."""
    rows = [record(wells("PUBLIX #1560", "09/20", card="1113"), -40.00, "2025-09-20")]
    run = categorize_records(rows, cards=ROSTER)
    assert not run.classifications[0].is_assigned, "a weak row must not be booked"
    assert 0 in run.held_for_review
    assert run.held_for_review[0].winner == 8, "the proposal must survive"


def test_no_signal_yields_no_winner():
    result = score(record(wells("SOMEPLACE ODD", "10/14", card="1113"), -50.00), cards=ROSTER)
    assert result.winner is None
    assert result.confidence == 0.0
    assert not result.is_confident


def test_confidence_never_exceeds_one():
    """Piling on agreeing signals must saturate, not run away."""
    stacked = score(record(wells("PUBLIX #1560", "09/16", card="5718"), -500.00), cards=ROSTER)
    assert 0.0 <= stacked.confidence <= 1.0


def test_threshold_is_tunable_per_run():
    """Raising the bar must move rows into review, not change what wins."""
    rows = [record(wells("PUBLIX #1560", "09/20", card="1113"), -40.00, "2025-09-20")]
    lenient = categorize_records(rows, cards=ROSTER, threshold=0.5)
    strict = categorize_records(rows, cards=ROSTER, threshold=0.99)
    assert lenient.classifications[0].is_assigned
    assert not strict.classifications[0].is_assigned


# --- Confidence mechanics ----------------------------------------------------

def test_a_tie_collapses_confidence():
    """Two exactly balanced readings must not clear the gate."""
    tied = ScoredResult(totals={5: 3.0, 7: 3.0})
    assert tied.dominance == pytest.approx(0.5)
    assert not tied.is_confident


def test_conflict_is_visible_in_the_explanation():
    """An inferred card disagreeing with a food reading shows up as a named rival."""
    registry = ROSTER.with_unverified("7193", 7, "unknown")
    result = score(record(wells("PUBLIX #1560", "09/20", card="7193"), -40.00, "2025-09-20"), cards=registry)
    assert result.conflicting(), "a contested result must name its rival"
    explanation = result.explain()
    assert "contested by" in explanation
    assert "%" in explanation, "a treasurer needs the confidence figure, not just a label"


# --- Provenance: confirmed beats inferred ------------------------------------

def test_an_unverified_card_cannot_outweigh_a_verified_one():
    """
    History-derived card affinities are inferred from this database's own
    labels, which were themselves written by the categorizer. They must never
    carry the authority of treasury's documented assignments.
    """
    registry = ROSTER.with_unverified("7193", 8, "unknown")
    verified = score(record(wells("SOMEWHERE", "10/14", card="5718"), -50.00), cards=registry)
    inferred = score(record(wells("SOMEWHERE", "10/14", card="7193"), -50.00), cards=registry)
    assert verified.top_score > inferred.top_score
    assert verified.is_confident
    assert not inferred.is_confident, "an inferred card alone must not auto-apply"


def test_an_unverified_card_is_never_booked_as_certain():
    registry = ROSTER.with_unverified("7193", 8, "unknown")
    run = categorize_records([record(wells("SOMEWHERE", "10/14", card="7193"), -50.00)], cards=registry)
    assert not run.classifications[0].is_assigned


def test_with_unverified_never_overwrites_a_confirmed_assignment():
    registry = ROSTER.with_unverified("5718", 99, "bogus")
    assignment = registry.get("5718")
    assert assignment.committee_id == 5, "treasury's documented owner must win"
    assert assignment.verified


# --- Exact rules still short-circuit scoring ---------------------------------

def test_dues_still_resolve_exactly():
    dues = {
        "details": "ZELLE FROM JANE DOE ON 07/08 REF # A1",
        "amount": 35.00,
        "transaction_date": "2025-09-18",
        "account": "Wells Fargo",
    }
    run = categorize_records([dues], cards=ROSTER)
    assert run.classifications[0].committee_id == 1
