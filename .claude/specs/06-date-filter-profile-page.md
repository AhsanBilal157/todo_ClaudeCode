# Spec: Date Filter For Profile Page

## Overview
Step 6 adds a custom date-range filter to the `/profile` page transaction list.
Today the page only supports three preset windows ("This month", "Last month",
"All") via the `range` query string. Step 6 layers a `from` / `to` date picker
on top so a user can scope their recent transactions to any arbitrary window
(e.g. a single weekend, a quarter, a holiday trip). The filter is implemented
entirely as `GET` query parameters so it remains shareable, bookmarkable, and
back-button friendly. Summary stats and the category breakdown remain
unaffected — this step is scoped to the transaction list only — keeping the
data flow simple and the diff small.

## Depends on
- Step 1: Database setup (`expenses.date` column exists)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` is set)
- Step 4: Profile page static UI (template renders the transaction panel)
- Step 5: Backend routes for profile page (`queries.get_recent_transactions`
  already filters by `period`)

## Routes
No new routes. The existing `GET /profile` route is extended to accept two new
optional query parameters:

- `GET /profile?from=YYYY-MM-DD&to=YYYY-MM-DD` — logged-in only
  - When both `from` and `to` are present and valid, the transaction list is
    filtered to expenses with `date` between them (inclusive).
  - When only one is present, the missing bound is treated as open
    (`from` only → from that date onwards; `to` only → up to that date).
  - When `from` and `to` are both supplied, they take precedence over the
    `range` preset.
  - Invalid dates (wrong format or `from > to`) silently fall back to the
    default behaviour and an inline error message is shown above the table.

## Database changes
No database changes. The `expenses.date` column already stores `YYYY-MM-DD`.

## Templates
- **Modify:** `templates/profile.html`
  - Add a small inline `<form method="get" action="{{ url_for('profile') }}">`
    inside the existing `.panel-tools` block on the transactions panel.
  - Two `<input type="date" name="from">` and `<input type="date" name="to">`
    fields, plus an "Apply" submit button and a "Clear" link that returns to
    `url_for('profile')`.
  - When a custom range is active, the three preset pills must visually
    deactivate (no `is-active` class).
  - When the supplied range is invalid, render a `.filter-error` paragraph
    above the table with the message returned by the route.
- **Create:** none.

## Files to change
- `app.py` — read `from` and `to` from `request.args`, validate, and pass
  them through to `queries.get_recent_transactions`. Pass an optional
  `filter_error` string to the template when validation fails.
- `database/queries.py` — extend `get_recent_transactions` to accept
  `date_from` and `date_to` keyword arguments (both default `None`). When
  either is set, append parameterised `AND date >= ?` / `AND date <= ?`
  clauses. The existing `period` argument continues to work and is ignored
  when a custom range is active.
- `templates/profile.html` — see Templates section above.
- `static/css/style.css` (or wherever the profile panel styles live) — add
  styles for the date inputs and `.filter-error` using existing CSS variables
  only.

## Files to create
- `tests/test_date_filter.py` — unit and route tests (see Definition of done).

## New dependencies
No new dependencies. Use `datetime.strptime` for date validation.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`.
- Parameterised queries only — never string-format dates into SQL.
- Validate dates with `datetime.strptime(value, "%Y-%m-%d")` inside a
  `try/except ValueError`. Reject anything else.
- If `date_from > date_to`, treat it as invalid and show the error.
- Custom range takes precedence over the `range` preset; do not silently
  combine the two.
- When the custom range yields zero transactions, the existing empty state
  (`.tx-empty`) must still render — do not raise.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- No inline styles.
- Currency display continues to use `PKR` (matching the rest of the page).
- Keep `queries.TX_RANGES` and the preset behaviour unchanged so Step 5 tests
  still pass.

## Definition of done
- [ ] Logged in as the seed user, visiting `/profile?from=2026-04-05&to=2026-04-09`
      shows exactly 3 transactions (Bills, Health, Entertainment) and the
      preset pills are no longer highlighted.
- [ ] Visiting `/profile?from=2026-04-10` shows transactions on or after
      2026-04-10 only (Shopping, Other, Food on 2026-04-15).
- [ ] Visiting `/profile?to=2026-04-03` shows transactions up to and
      including 2026-04-03 only (Food, Transport).
- [ ] Visiting `/profile?from=2026-05-01&to=2026-04-01` (reversed) renders
      the page without crashing, falls back to the default transaction list,
      and shows an inline error above the table.
- [ ] Visiting `/profile?from=not-a-date` renders the page without crashing
      and shows the same inline error.
- [ ] Clicking "Clear" returns the user to `/profile` with no `from`/`to`
      query params and the "This month" preset pill active again.
- [ ] Submitting the form with both fields empty does not append empty
      `from=&to=` params (i.e. the form is submitted via GET but produces a
      clean URL — empty inputs are stripped or ignored on the server).
- [ ] All existing Step 5 route and unit tests still pass.
- [ ] New `tests/test_date_filter.py` covers: valid range, open-ended range
      (from only, to only), invalid format, reversed range, zero-result
      range, and that the preset `range=this_month` still works when no
      custom dates are supplied.
