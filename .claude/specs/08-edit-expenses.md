# Spec: Edit Expenses

## Overview
Step 8 turns the placeholder `/expenses/<id>/edit` route into a real feature:
a logged-in user can edit one of their existing expenses via a pre-filled
form (amount, category, date, description), the row is updated in the
`expenses` table, and the user is redirected back to `/profile` where the
change is reflected immediately in the summary stats, transaction list, and
category breakdown. This is the first update path Spendly exposes and reuses
the validation rules, allow-lists, and Post/Redirect/Get conventions
established by Step 7 (Add Expense). It must also enforce row-level ownership
so a user cannot read or modify another user's expense by guessing the `id`.

## Depends on
- Step 1: Database setup (`expenses` table with `id`, `user_id`, `amount`,
  `category`, `date`, `description`)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` is set)
- Step 4: Profile page static UI
- Step 5: Backend routes for profile page (the edited row must show up
  correctly in `get_recent_transactions`, `get_summary_stats`, and
  `get_category_breakdown`)
- Step 7: Add expense (defines the validation rules, the allow-list of
  categories, and the form/template patterns this step reuses)

## Routes
- `GET  /expenses/<int:id>/edit` — render the edit form pre-filled with the
  row's current values — **logged-in only, owner-only**
- `POST /expenses/<int:id>/edit` — validate the form, update the row, and
  redirect to `/profile` on success — **logged-in only, owner-only**

Both methods replace the existing placeholder string at `app.py:269-271`. If
`session["user_id"]` is missing, both methods redirect to `url_for("login")`
(matching `/profile`, `/analytics`, `/expenses/add`). If the row does not
exist, or exists but belongs to a different user, both methods respond with
HTTP 404 — never reveal whether the id is real but unauthorised vs. missing.

## Database changes
No database changes. The `expenses` table at `database/db.py:28-37` already
has every column this feature reads and writes. No new indexes are needed
for this volume of data.

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html`. Reuses the same single-column form-card layout as
    `templates/add_expense.html` (the `.auth-section` / `.auth-container` /
    `.auth-card` stack with `.form-group` rows), so visual style matches the
    add form and the auth pages.
  - Page title: "Edit expense — Spendly". Header text: "Edit expense" with
    subtitle "Update this transaction".
  - Fields, in order, pre-filled from the row being edited:
    1. **Amount** — `<input type="number" name="amount" step="0.01" min="0.01" required>`
       with a `PKR` label, value from the row (or the previously submitted
       value when re-rendering after a validation error).
    2. **Category** — `<select name="category" required>` with the same fixed
       option list as `add_expense.html`; the row's current category is
       pre-selected via `{% if form.category == c %}selected{% endif %}`.
    3. **Date** — `<input type="date" name="date" value="{{ form.date }}" required>`
       — pre-filled with the row's existing `YYYY-MM-DD` date (not today).
    4. **Description** — `<input type="text" name="description" maxlength="200">`
       — pre-filled with the row's description or empty if `NULL`.
  - Submit button labelled "Save changes". Cancel link below the card linking
    to `url_for('profile')` — matches the add-expense form's cancel pattern.
  - When the route renders the template with an `error` string, show it in
    the same `.auth-error` block used by `add_expense.html`.
  - When `error` is set, the previously submitted (invalid) values must be
    preserved in the inputs — do not fall back to the database values on a
    failed POST, or the user will lose what they typed.
  - The form's `action` attribute posts to
    `url_for('edit_expense', id=expense.id)` so the row id is implicit in
    the URL and never duplicated in a hidden form field.
- **Modify:** `templates/profile.html`
  - In the transactions table (`app.py:182-189` data, table at
    `templates/profile.html:111-140`), add an "Edit" action per row that
    links to `url_for('edit_expense', id=e.id)`. Two acceptable shapes —
    pick one and reuse the existing CSS rather than inventing a new variant:
    - A small "Edit" text link in a new trailing `<th>/`<td>` action column, or
    - A pencil icon button (`<i data-lucide="pencil"></i>`) wrapped in an
      `<a>` placed inside the existing description or amount cell.
  - The current `get_recent_transactions` query at
    `database/queries.py:114-119` selects `id` but does not return it. The
    helper's per-row dict (`database/queries.py:131-138`) must add `"id":
    row["id"]` so the template can build the edit link. No other rows in
    that result dict change.

## Files to change
- `app.py`
  - Replace the placeholder `edit_expense(id)` view (currently
    `app.py:269-271`) with a `methods=["GET", "POST"]` handler that:
    1. Redirects to `/login` if `session["user_id"]` is missing.
    2. Loads the row via the new `queries.get_expense(id, user_id)` helper.
       If `None`, `abort(404)`.
    3. On `GET`, renders `edit_expense.html` with `expense=<row>`,
       `categories=ALLOWED_CATEGORIES`, and an empty `form` dict (the
       template falls back to the row values when `form.amount` etc. are
       empty).
    4. On `POST`, reads the same four form fields as `add_expense`, runs the
       exact same validation chain (amount > 0 finite float, category in
       `ALLOWED_CATEGORIES`, date parses as `YYYY-MM-DD`, description
       optional and ≤ `DESCRIPTION_MAX`), and on success calls the new
       `queries.update_expense(...)` helper before
       `redirect(url_for("profile"))`.
    5. Reuses `ALLOWED_CATEGORIES` and `DESCRIPTION_MAX` from the top of
       `app.py`; do not redefine them.
  - The validation logic is structurally identical to `add_expense`. Extract
    a small helper *only* if the duplication exceeds ~25 lines — otherwise
    inline both views and keep them parallel. No premature abstraction.
  - Import `abort` from `flask` alongside the existing imports at
    `app.py:6`.
- `database/queries.py`
  - Add `get_expense(expense_id, user_id) -> dict | None`. Selects
    `id, user_id, amount, category, date, description` from `expenses` where
    `id = ? AND user_id = ?` (the `user_id` filter is the ownership check
    and must be in the SQL, not done in Python after the fact). Returns the
    row as a plain dict, or `None` if no match. Closes the connection in a
    `finally` block.
  - Add `update_expense(expense_id, user_id, amount, category, date, description) -> bool`.
    Runs a single parameterised `UPDATE expenses SET amount=?, category=?,
    date=?, description=? WHERE id=? AND user_id=?`. Returns `True` if
    `rowcount == 1`, else `False`. Commits, closes in a `finally` block.
    The `user_id` filter in the `WHERE` clause is mandatory — the route
    must not be able to update another user's row even if it somehow
    bypasses the ownership pre-check.
  - Modify `get_recent_transactions` (at `database/queries.py:83-140`) so
    each result dict also includes the row's `id` (see Templates above).
    No other behaviour changes — ordering, filtering, formatting, and
    return shape for the other keys stay identical.
- `templates/profile.html`
  - Add the per-row Edit affordance described above.
  - If the transaction table layout adds a new header column, also adjust
    the empty-state markup (`templates/profile.html:141-145`) if any
    colspan assumption breaks. (At a glance, the empty state is a sibling
    `<div>`, not a `<tr colspan>`, so no change should be needed — verify
    during implementation.)
- `static/css/style.css`
  - Only if a small spacing/colour rule is needed for the new edit action
    inside `.tx-table` / `.tx-desc`. Reuse `--accent`, `--ink`,
    `--paper-card`, `--border`. **No new hex values. No new colour
    variables.**

## Files to create
- `templates/edit_expense.html` — see Templates → Create.
- `tests/test_edit_expense.py` — see Definition of done. Mirrors the
  structure of `tests/test_add_expense.py` (already in the repo).

## New dependencies
No new dependencies. Validation reuses `datetime.strptime`, `float()`, and
`math.isnan`/`math.isinf` — all already imported at `app.py:1-4`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`.
- Parameterised queries only — never string-format user input into SQL. The
  `id` from the URL is typed as `<int:id>` by Flask, but still passes
  through `?` placeholders.
- Passwords hashed with werkzeug (general rule; not directly exercised here).
- Use CSS variables — never hardcode hex values. Reuse existing variables
  and existing classes (`.btn-primary`, `.tx-table`, `.form-input`,
  `.auth-card`, `.auth-error`, `.form-group`). Do not introduce a new
  colour ramp for the edit action.
- All templates extend `base.html`.
- Categories are the same fixed allow-list as Step 7:
  `Food`, `Transport`, `Bills`, `Health`, `Entertainment`, `Shopping`,
  `Other`. A POST with any other category value is rejected with a form
  error and re-renders with the user's typed values preserved.
- Amount validation: must parse as a finite positive `float` (`> 0`,
  not NaN, not inf). Reject zero, negative, non-numeric, NaN, inf, and
  empty values with an inline error.
- Date validation: must parse as `datetime.strptime(value, "%Y-%m-%d")`.
  Reject anything else with an inline error.
- Description is optional. Strip whitespace, store `NULL` (not empty
  string) when empty after stripping. Cap at `DESCRIPTION_MAX` (200);
  reject longer input with an inline error — same policy as Step 7.
- The view always uses Post/Redirect/Get on success: respond with
  `redirect(url_for("profile"))`, never re-render the form on success.
- Currency display continues to use `PKR` in the amount label, matching
  `add_expense.html` and `profile.html`.
- The update must be attributed to `session["user_id"]` — the row's
  `user_id` is **never** read from the form, even as a hidden field, and
  the `UPDATE` always carries `WHERE id = ? AND user_id = ?`.
- Ownership pre-check: every `GET` and every `POST` must first call
  `queries.get_expense(id, session["user_id"])` and `abort(404)` if `None`.
  Do not return a different status for "not found" vs. "not yours" — both
  must be 404, otherwise the route leaks the existence of other users'
  rows.
- No JavaScript-only validation. Server-side validation is mandatory; HTML5
  `required` / `min` / `step` attributes are acceptable as UX hints only.
- Inline `if not session.get("user_id"): return redirect(url_for("login"))`
  at the top of the view — do not introduce a `@login_required` decorator
  in this step (consistent with Steps 5–7).
- Do not allow PATCH/PUT or any non-GET/POST method. Flask returns 405 by
  default for the unlisted methods — do not handle this explicitly.

## Definition of done
- [ ] Logged out, `GET /expenses/<existing_id>/edit` redirects to `/login`
      (HTTP 302) and reads no row to the response body.
- [ ] Logged out, `POST /expenses/<existing_id>/edit` redirects to `/login`
      and writes no change to `expenses`.
- [ ] Logged in as the owner, `GET /expenses/<my_id>/edit` renders the form
      pre-filled with the row's amount, category, date (`YYYY-MM-DD`), and
      description.
- [ ] Logged in as the owner, `GET /expenses/<my_id>/edit` with a row whose
      `description` is `NULL` renders an empty description input (not the
      literal string "None").
- [ ] Logged in, `GET /expenses/999999/edit` (id that does not exist)
      responds with HTTP 404.
- [ ] Logged in as user A, `GET /expenses/<user_B_id>/edit` responds with
      HTTP 404 — and the response body must not reveal any of user B's
      expense values.
- [ ] Logged in as the owner, `POST` with
      `amount=99.99 category=Bills date=2026-05-12 description="Updated"`
      updates exactly one row (matching `id` and `session["user_id"]`)
      and responds with `302 → /profile`.
- [ ] After the redirect, the edited expense's new amount, category, date,
      and description appear in the recent transactions list; the
      `stats.total_spent`, `stats.transaction_count`, and category
      breakdown are recomputed from the live `expenses` table (the count
      stays the same; total and breakdown reflect the new amount/category).
- [ ] Submitting `amount=0`, `amount=-5`, `amount=abc`, `amount=` (empty),
      `amount=NaN`, or `amount=inf` re-renders the form with an inline
      error and writes no change to `expenses`.
- [ ] Submitting `category=Crypto` (not in the allow-list) re-renders the
      form with an inline error and writes no change.
- [ ] Submitting `date=not-a-date` or `date=` re-renders the form with an
      inline error and writes no change.
- [ ] Submitting a description longer than 200 characters re-renders the
      form with an inline error and writes no change.
- [ ] Submitting an empty (whitespace-only) description stores `NULL` in
      `expenses.description` (verifiable via a direct SQL select).
- [ ] When the form is re-rendered with an error, the previously typed
      amount, category, date, and description are preserved — the
      template does not fall back to the original database values on a
      failed POST.
- [ ] A `POST` that includes an unexpected `user_id` form field is ignored
      — the row's `user_id` in the database is unchanged (the column is
      not in the `UPDATE` statement at all).
- [ ] The "Edit" affordance on each row of `/profile`'s transactions table
      links to `/expenses/<that_row_id>/edit` and does not break the
      table layout on desktop or the ≤ 760px mobile breakpoint.
- [ ] `queries.get_recent_transactions` still returns the same keys it did
      before, plus a new `id` integer key per row; existing Step 5 and
      Step 6 tests that read `date`, `description`, `category`, `amount`
      still pass unchanged.
- [ ] `tests/test_edit_expense.py` covers: GET requires login, POST
      requires login, GET of a non-existent id is 404, GET of another
      user's id is 404, POST of another user's id is 404 and writes no
      change, successful POST updates the row and redirects, each
      validation failure path (amount, category, date, description),
      empty description stores NULL, the row's `user_id` is unchanged
      after a successful update, and a `user_id` field in the form body
      is ignored.
- [ ] All existing Step 5, 6, and 7 tests still pass.
