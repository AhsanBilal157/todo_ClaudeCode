# Spec: Delete Expense

## Overview
Step 9 turns the placeholder `/expenses/<id>/delete` route into a real
feature: a logged-in user can permanently remove one of their own expenses
directly from the transactions table on `/profile`. Each row already carries
an Edit pencil (Step 8); this step adds a Delete (trash) action beside it.
Clicking it submits a small per-row POST form, guarded by a JavaScript
`confirm()` prompt so an accidental click cannot silently destroy data. On
success the row is removed and the user is redirected back to `/profile`,
where the summary stats, transaction list, and category breakdown all
recompute from the live `expenses` table. This completes the expense
lifecycle (Step 7 created, Step 8 edited, Step 9 deletes) and reuses the
exact ownership-enforcement pattern established by the edit feature so a user
cannot delete another user's expense by guessing the `id`.

## Depends on
- Step 1: Database setup (`expenses` table with `id`, `user_id`, `amount`,
  `category`, `date`, `description`)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` is set)
- Step 4: Profile page static UI
- Step 5: Backend routes for profile page (after a delete, the row must
  disappear from `get_recent_transactions`, and `get_summary_stats` /
  `get_category_breakdown` must recompute)
- Step 8: Edit expenses (defines the `get_expense(id, user_id)` ownership
  helper this step reuses, and the per-row `.tx-actions` cell the Delete
  button is placed into)

## Routes
- `POST /expenses/<int:id>/delete` — delete one expense owned by the current
  user, then redirect to `/profile` — **logged-in only, owner-only**

This replaces the existing GET placeholder at `app.py:329-331`. The route is
**POST-only** — a destructive action must never be reachable by a GET (link
prefetch, crawler, or address-bar visit). Flask returns `405 Method Not
Allowed` for a GET to this path; that is the correct behaviour and must not
be special-cased. If `session["user_id"]` is missing, the route redirects to
`url_for("login")` (matching `/profile`, `/expenses/add`, `/expenses/<id>/edit`).
If the row does not exist, or exists but belongs to a different user, the
route responds with HTTP 404 — never reveal whether the id is real but
unauthorised vs. missing.

## Database changes
No database changes. The `expenses` table at `database/db.py:28-37` already
holds everything needed. The delete is a single `DELETE` statement; there is
no soft-delete column and none is being added in this step.

## Templates
- **Create:** none.
- **Modify:** `templates/profile.html`
  - Inside the existing per-row `.tx-actions` cell (currently holding only
    the Edit pencil at `templates/profile.html:137-141`), add a Delete
    control after the Edit link. The Delete control is a small inline
    `<form method="POST" action="{{ url_for('delete_expense', id=e.id) }}">`
    containing a single icon `<button type="submit">` with a `trash-2`
    Lucide icon and `aria-label="Delete expense"`.
  - The form carries an `onsubmit="return confirm('Delete this expense?')"`
    attribute so the browser shows a native confirm dialog; returning
    `false` cancels the submit. This is a UX guard only — the server does
    not depend on it.
  - The two controls (Edit link + Delete form) sit side by side in the
    `.tx-actions` cell; wrap them so the cell layout (right-aligned, narrow
    column) is preserved on desktop and at the ≤ 760px breakpoint.
  - The empty-state block (`templates/profile.html:145-149`) is unchanged —
    it renders no rows, so there is nothing to delete.

## Files to change
- `app.py`
  - Replace the placeholder `delete_expense(id)` view (currently
    `app.py:329-331`) with a `methods=["POST"]` handler that:
    1. Redirects to `/login` if `session["user_id"]` is missing.
    2. Loads the row via `queries.get_expense(id, session["user_id"])`
       (the helper added in Step 8). If `None`, `abort(404)`.
    3. Calls the new `queries.delete_expense(id, session["user_id"])` helper.
    4. Redirects to `url_for("profile")`.
  - `abort` is already imported (added in Step 8); no new imports.
- `database/queries.py`
  - Add `delete_expense(expense_id, user_id) -> bool`. Runs a single
    parameterised `DELETE FROM expenses WHERE id = ? AND user_id = ?`.
    Returns `True` if `rowcount == 1`, else `False`. Commits, closes the
    connection in a `finally` block, mirroring `update_expense`.
    The `user_id` filter in the `WHERE` clause is the ownership guard and
    is mandatory — the route must not be able to delete another user's row
    even if the pre-check is somehow bypassed.
- `templates/profile.html`
  - Add the per-row Delete form described under Templates → Modify.
- `static/css/style.css`
  - Add a `.tx-delete` rule for the trash button, mirroring the existing
    `.tx-edit` rule (`static/css/style.css`, the `.tx-edit` block) but with
    a danger-coloured hover. Reuse `--danger`, `--danger-light`,
    `--ink-muted`, `--border`, `--radius-sm`. The trash `<button>` must be
    reset to look like the `.tx-edit` icon link (transparent background,
    no default button border/padding). **No new hex values, no new colour
    variables.**

## Files to create
- `tests/test_delete_expense.py` — covers the behaviour in Definition of
  done. Mirrors the structure of `tests/test_edit_expense.py` (class-based,
  reuses the `app` / `client` / `seed_user_id` fixtures from
  `tests/conftest.py` and the same snapshot-restore isolation fixture).

## New dependencies
No new dependencies. No CSRF library is introduced — the delete form carries
no CSRF token, consistent with the existing Step 7 add-expense and Step 8
edit-expense POST forms. (If CSRF protection is added later it must be added
uniformly across all POST forms, which is out of scope for this step.)

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`.
- Parameterised queries only — never string-format user input into SQL. The
  `id` is typed `<int:id>` by Flask but still passes through a `?`
  placeholder.
- Passwords hashed with werkzeug (general rule; not exercised here).
- Use CSS variables — never hardcode hex values. Reuse existing variables
  and existing classes; the trash control reuses the `.tx-edit` sizing and
  only differs in hover colour via `--danger`.
- All templates extend `base.html` (no new templates in this step).
- The route is **POST-only**. Do not add a GET handler, a confirmation
  page, or a query-string `?confirm=1` scheme. The only confirmation is the
  client-side `confirm()` dialog, which is a UX guard and must not be relied
  on server-side.
- Ownership: the view must first call
  `queries.get_expense(id, session["user_id"])` and `abort(404)` if `None`.
  "Not found" and "not yours" must both return 404 — never a different
  status — so the route does not leak the existence of other users' rows.
  The `DELETE` statement additionally carries `WHERE id = ? AND user_id = ?`.
- The delete must be scoped to `session["user_id"]` — never trust a
  `user_id` from the form (no such field should exist).
- The view always redirects on completion: `redirect(url_for("profile"))`.
  It never renders a template directly.
- Deleting an expense must not affect any other user's rows and must not
  affect the current user's other rows — exactly one row is removed.
- Inline `if not session.get("user_id"): return redirect(url_for("login"))`
  at the top of the view — do not introduce a `@login_required` decorator
  in this step (consistent with Steps 5–8).

## Definition of done
- [ ] Logged out, `POST /expenses/<existing_id>/delete` redirects to
      `/login` (HTTP 302) and deletes no row.
- [ ] `GET /expenses/<existing_id>/delete` responds with HTTP 405 (the
      route is POST-only) and deletes no row.
- [ ] Logged in as the owner, `POST /expenses/<my_id>/delete` removes
      exactly that one row from `expenses` and responds with
      `302 → /profile`.
- [ ] After the redirect, the deleted expense no longer appears in the
      recent transactions list; `stats.transaction_count` decreases by 1
      and `stats.total_spent` decreases by the deleted amount; the category
      breakdown recomputes.
- [ ] Logged in, `POST /expenses/999999/delete` (id that does not exist)
      responds with HTTP 404 and deletes no row.
- [ ] Logged in as user A, `POST /expenses/<user_B_id>/delete` responds
      with HTTP 404 and user B's row still exists unchanged in the database.
- [ ] A delete of one expense leaves all the current user's other expenses
      intact (exactly one row removed, verified by a direct SQL count).
- [ ] Each row of `/profile`'s transactions table renders a Delete control
      that is a `<form method="POST">` posting to
      `/expenses/<that_row_id>/delete` (verifiable in the page HTML).
- [ ] The Delete control carries an `onsubmit` `confirm(...)` guard so a
      click shows a browser confirmation prompt before the POST is sent.
- [ ] The Edit and Delete controls sit side by side in the `.tx-actions`
      cell without breaking the transactions table layout on desktop or at
      the ≤ 760px mobile breakpoint.
- [ ] `tests/test_delete_expense.py` covers: POST requires login, GET is
      405, successful POST removes the row and redirects, non-existent id
      is 404, another user's id is 404 and that row survives, only one row
      is removed, and `/profile` renders a POST delete form per row.
- [ ] All existing Step 5, 6, 7, and 8 tests still pass.
