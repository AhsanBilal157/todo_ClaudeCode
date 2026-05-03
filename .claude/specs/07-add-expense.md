# Spec: Add Expense

## Overview
Step 7 turns the placeholder `/expenses/add` route into a real feature: a
logged-in user can record a new expense via a small form (amount, category,
date, description), the row is persisted to the `expenses` table, and the
user is redirected back to `/profile` where the new transaction immediately
shows up in the summary stats, transaction list, and category breakdown that
Step 5 already wired to live data. This is the first write path Spendly
exposes for transactional data — login/registration write to `users`, but no
prior step writes to `expenses` — so it sets the validation, error-handling,
and Post/Redirect/Get conventions that the edit and delete steps will reuse.

## Depends on
- Step 1: Database setup (`expenses` table exists with `user_id`, `amount`,
  `category`, `date`, `description` columns)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` is set)
- Step 4: Profile page static UI (target page after redirect)
- Step 5: Backend routes for profile page (new expense must show up in the
  recent transactions, summary stats, and category breakdown)

## Routes
- `GET  /expenses/add` — render the empty add-expense form — **logged-in only**
- `POST /expenses/add` — validate the form, insert one row into `expenses`
  for the current user, and redirect to `/profile` on success — **logged-in only**

Both methods replace the existing placeholder string at `app.py:212`. If
`session["user_id"]` is missing, both methods redirect to `url_for("login")`
(matching the pattern established by `/profile` and `/analytics`).

## Database changes
No database changes. The `expenses` table created in `database/db.py:28-37`
already has every column this feature writes (`user_id`, `amount`, `category`,
`date`, `description`, plus `created_at` defaulted by SQLite).

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`. Single-column form card centered on the page,
    reusing the existing auth-form styling (`.form-group`, `.form-input`,
    `.btn-primary` from `static/css/style.css:466-491` and `:306-321`) so
    the visual style matches login / register.
  - Fields, in order:
    1. **Amount** — `<input type="number" name="amount" step="0.01" min="0.01" required>` with a `PKR` prefix label
    2. **Category** — `<select name="category" required>` populated from the
       fixed list below, with no placeholder option (browser-default first item)
    3. **Date** — `<input type="date" name="date" required value="{{ today }}">`
       defaulting to today's date in `YYYY-MM-DD`
    4. **Description** — `<input type="text" name="description" maxlength="200">`
       (optional)
  - Submit button labelled "Add expense" plus a "Cancel" link back to
    `url_for('profile')`.
  - When the route renders the template with an `error` string, show it in a
    `.form-error` block above the form (same pattern as `login.html` /
    `register.html`).
  - When `error` is set, the previously submitted values must be preserved in
    the inputs so the user does not have to retype.
- **Modify:** `templates/profile.html`
  - Add an "Add expense" CTA button in the existing transactions panel
    `.panel-tools` block (next to the preset filter pills), linking to
    `url_for('add_expense')`. Use the existing `.btn-primary` class (or a
    sibling pill-style class that already exists in the stylesheet — pick
    one and reuse, do not introduce a new variant).

## Files to change
- `app.py`
  - Replace the placeholder `add_expense()` view (currently `app.py:212-214`)
    with a `methods=["GET", "POST"]` handler that performs the auth check,
    validates input on POST, calls the new `queries.add_expense(...)` helper,
    and redirects to `url_for("profile")` on success.
  - Reuse the existing `EMAIL_RE`-style top-of-file pattern: keep validation
    inline in the view (no new modules) since the rules are short.
- `database/queries.py`
  - Add a single helper:
    `add_expense(user_id, amount, category, date, description) -> int`
    that opens one connection via `get_db()`, runs a parameterised
    `INSERT INTO expenses (...) VALUES (?, ?, ?, ?, ?)`, commits, and
    returns the new `id` from `last_insert_rowid()`. Closes the connection
    in a `finally` block, mirroring the existing helpers.
- `templates/profile.html` — add the "Add expense" CTA inside `.panel-tools`
  (see Templates → Modify above). No other markup changes.
- `static/css/style.css` — only if the chosen CTA placement needs a small
  spacing tweak inside `.panel-tools`. Use existing CSS variables; no new
  hex values, no new colour ramp.

## Files to create
- `templates/add_expense.html` — see Templates → Create above.
- `tests/test_add_expense.py` — covers GET/POST behaviour and validation
  (see Definition of done).

## New dependencies
No new dependencies. `datetime.strptime` covers date validation; the standard
`float()` cast covers amount parsing.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`.
- Parameterised queries only — never string-format user input into SQL.
- Passwords hashed with werkzeug (not directly relevant here, but the rule
  stands: never store sensitive values in plaintext if any are added later).
- Use CSS variables — never hardcode hex values. Reuse `--accent`, `--ink`,
  `--paper-card`, `--border`, etc.
- All templates extend `base.html`.
- Categories are a fixed allow-list — must exactly match the seed data and
  the icon map already in `templates/profile.html:6-14`:
  `Food`, `Transport`, `Bills`, `Health`, `Entertainment`, `Shopping`, `Other`.
  A POST with any other category value is rejected with a form error.
- Amount validation: must parse as a positive `float` and be `> 0`. Reject
  zero, negative, non-numeric, and empty values with an inline error.
- Date validation: must parse as `datetime.strptime(value, "%Y-%m-%d")`.
  Reject anything else with an inline error. Future dates are allowed
  (matches the existing seed which uses past dates but is not enforced).
- Description is optional. Strip whitespace, store `NULL` (not empty string)
  when empty after stripping. Cap at 200 characters; truncate or reject
  longer input — pick one and document the choice in the view comment if
  any. Default: reject with an inline error (consistent with the other
  validations).
- The view always uses Post/Redirect/Get on success: respond with
  `redirect(url_for("profile"))`, never re-render the form on success.
- Currency display continues to use `PKR` in the form's amount label and
  anywhere amounts are echoed back, matching `templates/profile.html`.
- The new expense must be attributed to `session["user_id"]` only — never
  trust a `user_id` field from the form (no such field should exist).
- No JavaScript-only validation. Server-side validation is mandatory; HTML5
  `required` / `min` / `step` attributes are acceptable as a UX hint only.
- Inline `if not session.get("user_id"): return redirect(url_for("login"))`
  at the top of the view — do not introduce a `@login_required` decorator
  in this step.

## Definition of done
- [ ] Logged out, `GET /expenses/add` redirects to `/login` (HTTP 302).
- [ ] Logged out, `POST /expenses/add` redirects to `/login` and writes
      no row to `expenses`.
- [ ] Logged in, `GET /expenses/add` renders the form with today's date
      pre-filled in the date input and an empty amount/description.
- [ ] Logged in, submitting a valid form
      (`amount=49.99 category=Food date=2026-05-03 description="Tea"`)
      inserts exactly one row in `expenses` for the current `user_id` and
      responds with `302 → /profile`.
- [ ] After the redirect, the new expense appears in the recent
      transactions list, `stats.transaction_count` increases by 1, and
      `stats.total_spent` increases by the submitted amount.
- [ ] Submitting `amount=0`, `amount=-5`, `amount=abc`, or no amount at
      all re-renders the form with an inline error and writes no row.
- [ ] Submitting `category=Crypto` (not in the allow-list) re-renders the
      form with an inline error and writes no row.
- [ ] Submitting `date=not-a-date` or `date=` re-renders the form with
      an inline error and writes no row.
- [ ] Submitting an empty description stores `NULL` in
      `expenses.description` (verifiable via a direct SQL select).
- [ ] When the form is re-rendered with an error, the previously typed
      amount, category, date, and description are preserved in the inputs.
- [ ] The "Add expense" CTA on `/profile` links to `/expenses/add` and
      renders without breaking the existing `.panel-tools` layout on
      desktop and mobile (≤ 760px breakpoint).
- [ ] `tests/test_add_expense.py` covers: GET requires login, POST
      requires login, successful POST inserts and redirects, each
      validation failure path (amount, category, date, description),
      empty description stores NULL, and the new row is attributed to
      the session user (not a form-supplied user_id).
- [ ] All existing Step 5 and Step 6 tests still pass.
