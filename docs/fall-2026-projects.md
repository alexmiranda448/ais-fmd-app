# Fall 2026 projects

Eight projects for pairs and trios. The first three are the semester's core features and
get staffed first; the rest are ordered by how much they matter to treasury.
If there are fewer pairs than projects, drop from the bottom.

Read `CONTRIBUTING.md` before starting. Every project here is built and proven
in the sandbox — none of them needs real data or production access.

**Pick by talent, not by title.** Each brief lists the strengths it rewards.
A good pair mixes someone comfortable in Python with someone who brings the
other skill (design, finance, SQL, treasury knowledge).

| Code | Project | Core? | Best for |
| --- | --- | --- | --- |
| `vp` | VP landing page | Core | Front-end / design + Python |
| `cat` | Auto-categorization you can trust | Core | Python + data analysis |
| `model` | Financial modeling on historic data | Core | Finance / Excel modeling + pandas |
| `platform` | Production & security rehearsal | — | SQL / cloud / backend |
| `close` | Semester close & board pack | — | Accounting + design |
| `qa` | Write-path tests & bug bash | — | Detail-oriented, testing |
| `ux` | Usability, docs & treasury research | — | Writing, research, treasury ops (no coding required) |
| `ai` | AI assistant | — | Python + LLM APIs |

## Milestones (all teams)

Dates are proposals — adjust to the UF calendar.

| By | Milestone | Proof |
| --- | --- | --- |
| Sun Oct 4 | Everyone set up; each team fills in its goals worksheet | App runs locally; worksheet filled in |
| Sun Oct 11 | First working slice demoed in the sandbox | 2-minute demo at team meeting |
| Sun Nov 1 | Feature complete in the sandbox, PRs open | CI green, partner-reviewed |
| Sun Nov 15 | Merged; integration bug bash across all teams | Merged to `sandbox/mvp-rebuild` |
| Sat Nov 21 | **Code freeze** before Thanksgiving break | Only fixes after this |
| Sun Dec 6 | Final demo and handoff notes for the Spring treasurer | `docs/projects/<code>/handoff.md` |

The goals worksheet is a shared document the treasurer sends each team (not a
PR, and it stays out of this public repo). Each team writes its end-state goals
and how each one will be measured. Code PRs start after that.

---

## `vp` — VP landing page

**Goal.** A VP who signs in lands on one page that answers *"how is my
committee doing?"* — budget, spent, remaining, whether they are on pace, and
what was charged to them recently — without seeing any other committee's data.

**What already exists.** `views/Officer.py` ("My Committee") already scopes
budget-vs-actual and spending to one committee, and `auth.py` has Officer roles.
Google sign-in for VPs is written but not yet switched on in production
(`HANDOFF.md` §12.2). In the sandbox you get the Officer role from the sidebar
role switcher, so none of that blocks you.

**Build.**
1. Make the Officer landing experience the default page for the Officer role
   (today everyone lands on `Home`).
2. A glanceable header: remaining budget, % spent vs % of semester elapsed,
   projected end-of-term position (`domain/budgets.burn_rate_projection` exists).
3. Recent charges to the committee, with category and date.
4. **"This isn't ours"** — a VP can flag a charge they think was miscategorized,
   with a note. It lands in the treasurer's Review Queue; the VP never changes
   the booking themselves.
5. Mobile-friendly: VPs will open this on their phones.

**Files.** `views/Officer.py`, `views/Home.py`, `ui/shell.py` (add components),
`ui/charts.py`, `app.py` (`PAGES` — coordinate). Item 4 needs a new backend
method in `data/backend.py`, `sqlite_backend.py` and `supabase_backend.py`.

**Done means.** Headless tests in `tests/test_views.py` render the page as an
Officer for each committee **and assert no other committee's figures appear**;
a flagged charge shows up in the Review Queue as Treasurer; screenshots on a
phone-width window.

**Out of scope.** Registering the Google OAuth app, running the `profiles`
migration, and deciding when VPs get production logins — treasurer tasks.

---

## `cat` — Auto-categorization you can trust

**Goal.** Fewer rows reach a human, and we can *prove* the rows the app books
on its own are right. Today the app measures coverage, not accuracy.

**What already exists.** A tiered pipeline — card roster → deterministic
rules → scoring → (unused) model pass — in `domain/categorize/`. A spot-check
sampler (`spotcheck.py`, `scripts/spot_check.py`), an evaluation harness
(`learning.py`, `scripts/evaluate_categorizer.py`). Both are command-line
only, so nobody uses them.

**Build.**
1. **Spot-check in the app.** A Treasurer page (or Review Queue tab) that draws
   a sample of auto-applied rows, lets the treasurer mark each right or wrong,
   and shows the resulting accuracy. Wraps `spotcheck.py`.
2. **Re-categorize with a preview.** Run the current pipeline over stored rows,
   show a diff ("these 23 rows would move from Refunded to Membership, totalling
   $X"), and apply only what the treasurer confirms. This is what finally
   applies the reimbursement ruling to old rows.
3. **Card roster in the app.** A Treasurer view of `config/card_roster.json`:
   which cards are on it for the current cohort, which cards in recent
   statements are not, and how much money each unknown card carries. (Replaces
   the old merchant-proposals item: treasury took merchant rules out of
   categorization on 2026-09-23 -- the card now decides.)
4. **Accuracy report.** Accuracy by confidence band and by committee, from the
   spot-check labels. Use the weighted estimate `spotcheck.agreement` returns
   (`weighted_rate`, `margin`), not the raw share -- the sample over-picks rare
   committees and large amounts on purpose.
5. **Spend review.** Categorization answers *whose* purchase it is; this asks
   whether it *fits* that committee. Each merchant gets a type (hardware, gas
   station, restaurant...) and `config/spend_policy.json` says, per committee,
   which types are `expected`, `ask` (we'd like a one-line reason) or
   `not_allowed`. Plus checks that ignore merchant type: missing receipt,
   unknown card, a charge repeating across months, transfers to individuals
   with no reimbursement. Results land in a **Spend Review** tab in the Review
   Queue where the treasurer marks each one *Explained*, *Ask VP* or
   *Escalate*, with a note. A dry run of the draft policy on real history
   flags about 4-6% of categorized card purchases.
   - **Tone.** Every note reads as a friendly question ("Lowe's isn't usual for
     Membership -- what was this for?"), never an accusation.
   - **The model's job is narrow.** It may classify a merchant the keyword list
     does not know (cached per merchant, correctable) and word the question to
     the VP. It never decides whether a purchase is acceptable and never
     changes a category. Tests use a stub; the sandbox cannot call a model.
   - **Never writes a category.** Spend review and categorization stay
     separate: neither may change the other's output.

**Files.** `domain/categorize/*`, `views/ReviewQueue.py`, `scripts/`, new tests
beside `tests/test_scoring.py`, `test_learning.py`, `test_spotcheck.py`. Spend
review: a new `domain/spend_review.py` (pure pandas) with `tests/test_spend_review.py`,
reading `config/spend_policy.json`; review decisions need a new table, so a
numbered migration plus the matching sandbox SQLite change.

**Rules for this team especially.** Anything that changes where money is booked
is a proposal the treasurer confirms. Do not change weights, thresholds or
keyword tables to make a number go up — `tests/test_treasury_decisions.py` and
`docs/treasury-questions.md` explain why each one is what it is. Never add
`"membership"` to the memo keywords.
`config/spend_policy.json` is the treasurer's, like `card_roster.json`:
propose changes, don't make them.

**Done means.** Spot-check and re-categorize work end to end in the sandbox with
tests; nothing writes a category without an explicit confirm step (a test
proves it). Spend review runs on the sandbox seed, reports its flag
rate, and a test proves it never changes a category.

**Out of scope.** Turning on the LLM pass — the sandbox deliberately cannot call
one, and it only helps a small residual.

---

## `model` — Financial modeling on historic data

**Goal.** Set Spring 2027 budgets from evidence. Given past semesters, forecast
dues income and each committee's spend, with a range rather than a single
number, and show how much the forecast would have missed in past terms.

**What already exists.** `views/Planner.py` + `domain/scenarios.py` project a
term from **one** baseline semester (`build_baseline`, `project`,
`break_even_members`, `suggest_from_history`). `domain/budgets.py` has
historical budget-vs-actual; `domain/dues.py` has `collection_curve` and
`compare_semesters`.

**Build.**
1. **Multi-semester baseline.** Fall vs Spring behave differently (dues drive in
   August, Formal in spring). Model on several past terms of the same season,
   not just the last one.
2. **Committee forecasts with ranges.** Low / expected / high per committee.
3. **Dues forecast** from expected membership × rate, using the per-term rates
   in `terms.dues_rates`.
4. **Backtest.** Predict a term you already have from the terms before it, and
   report the error. A forecast without a backtest is a guess.
5. **Budget proposal export.** A table the treasurer can bring to the budget
   meeting.

**Files.** New `domain/forecast.py` (pure pandas, no Streamlit), `domain/scenarios.py`,
`views/Planner.py`, tests in a new `tests/test_forecast.py`.

**About the data.** Build and test entirely on the sandbox seed (several
semesters of generated activity). Real statements going back to 2021 exist,
but they stay with the treasurer, who runs your finished model on them and
shares only aggregate results. Write the model so that swap needs no code change.

**Done means.** Planner shows a multi-term forecast with ranges and a backtest
error on sandbox data; `domain/forecast.py` has tests including an empty term
and a term with no dues.

---

## `platform` — Production & security rehearsal

**Goal.** Make the real launch boring. The production backend
(`supabase_backend.py`, ~800 lines) has never run against a real Postgres
database. Run it against **your own free, throwaway Supabase project** with fake
data, and fix what breaks.

**Build.**
1. Create a personal Supabase project. Apply `data/schema_postgres.sql`, then
   migrations `001` and `003`, and record every error.
2. Point a local copy at it and exercise every write path: statement upload,
   transaction edit, budget save, term lock, roster replace, alias save.
   Keep a checklist of pass/fail in `docs/projects/platform/rehearsal.md`.
3. Write the security migration (`006_lock_down.sql`): enable row-level security
   with no permissive policy on every table, `REVOKE EXECUTE` on the two write
   RPCs from `PUBLIC, anon, authenticated`, and `SET search_path` on every
   `SECURITY DEFINER` function. Prove the app still works with the service key.
4. App-side hardening from the audit: a process-wide login throttle (not
   per-session), `.eq()` instead of `.ilike()` in `remove_profile`, and surface
   audit-write failures instead of swallowing them.
5. Pin upper bounds in the production requirements.

**Files.** `data/supabase_backend.py`, `data/migrations/`, `auth.py`,
`requirements-production.txt`.

**Hard rule.** You never receive the organization's Supabase keys or data. Your
throwaway project's keys go in your local `.streamlit/secrets.toml`, which is
gitignored — and never in a commit, screenshot or chat.

**Done means.** Every write path passes against Postgres; the lock-down migration
is written and rehearsed; the treasurer can follow your notes to do the real run.

---

## `close` — Semester close & board pack

**Goal.** Closing Fall 2026 in December takes an afternoon, not a week, and
produces a report the next treasurer and the board can read.

**What already exists.** Period locking (Treasury page), reconciliation
(`domain/reconcile.py`), data-quality checks (`domain/quality.py`) and a board
pack generator (`domain/report.py`, Alerts & Reports page).

**Build.**
1. **Close checklist.** One screen that answers "can we close this term?" — every
   statement period reconciled, review queue empty for the term, no
   high-severity quality findings, every card in the statement has a holder,
   board pack generated. Locking is offered only when all pass (or with an
   explicit override and a reason, which is audited).
2. **Board pack polish.** Semester-over-semester comparison, committee pages,
   print-to-PDF that looks presentable.
3. **Handoff export.** Everything the Spring treasurer needs in one download.

**Files.** New view (e.g. `views/Close.py`), `domain/report.py`,
`domain/quality.py`, `views/Reports.py`. `views/Treasury.py` is large and busy —
link to your page rather than growing it.

**Done means.** On sandbox data the checklist correctly blocks (the seed has an
unbalanced statement), passes after the fix, and the board pack prints cleanly.

---

## `qa` — Write-path tests & bug bash

**Goal.** Catch the bugs a green test suite has been missing. Every page is
rendered by tests, but nothing drives an upload, a budget save, a term lock or a
roster replace through the widgets.

**Build.**
1. Headless tests (`streamlit.testing.v1.AppTest`, see `tests/test_views.py`)
   for each write path: upload a statement, edit a transaction, save budgets,
   lock a term then try to edit inside it, replace a roster.
2. Week 1–2 only: the two small refactors from the audit — `shell.rule()` for
   the 27 hand-written dividers and `shell.semester_picker()` for the 6 copied
   pickers. These touch many views, so **merge them first**, before other teams
   are deep in those files.
3. Performance fixes: make the Treasury Export tab build CSVs on a button press,
   and hoist `committee_dropdown_options()` out of the Review Queue row loop.
4. Run the bug bash in November: a test script every team follows, bugs filed
   as GitHub issues.

**Files.** `tests/`, `ui/shell.py`, `views/Treasury.py`, `views/ReviewQueue.py`.

**Done means.** Every write path has at least one test that would fail if the
write silently did nothing.

---

## `ux` — Usability, docs & treasury research

**Goal.** Make the app usable by people who are not the treasurer, and settle
the open treasury questions with evidence. **No coding required** — ideal for
someone who knows treasury operations, writes well, or wants to learn the
codebase gradually.

**Build.**
1. **Usability tests.** Sit three officers who have never seen the app in front
   of the sandbox with five tasks ("how much does Marketing have left?"). Record
   where they get stuck. Turn findings into GitHub issues with screenshots.
2. **Copy review.** Page titles, empty states, error messages — plain language a
   VP understands. Small PRs.
3. **Runbook for the next treasurer.** Update `views/Runbook.py` and write a
   one-page "first week as treasurer" guide.
4. **Treasury research.** Use the VP Treasury Handbook and past records to bring
   the treasurer a recommendation — with evidence — on each open question in
   `docs/treasury-questions.md`: the disputed purpose mappings (§5a), headshot
   payments, the $35 exec rate, and the $1,000 of Venmo transfers.

**Files.** `docs/`, `views/Runbook.py`, page copy across `views/` (text only).

**Done means.** Usability findings filed; Runbook updated; a written
recommendation for each open question.

---

## `ai` — AI assistant

**Goal.** Anyone can ask a plain-English question about the finances and get a
correct answer from the live data, or be told where in the app to look.

**What already exists.** `views/Assistant.py` + `domain/assistant.py` answer
questions offline by running named, tested tools over the data, so every number
is checkable.

**Build.** Put a language model in front of those tools: it picks the tool and
its arguments, the tool computes the answer. Add tools for gaps rather than
letting the model write SQL; if free-form SQL is ever added, it is read-only,
runs on a copy, and shows the query. Choose the model by scoring candidates on a
fixed set of test questions (accuracy, speed, cost).

**Done means.** A test-question set with a measured pass rate; the assistant
never states a number no tool produced; a VP only ever gets their committee's
figures. The sandbox cannot call a model, so tests use a stub.
