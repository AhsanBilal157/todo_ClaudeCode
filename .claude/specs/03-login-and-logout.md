# Spec: Login and Logout

## Overview
Complete the authentication loop started in Step 02 by allowing existing users to sign in and sign out. `/login` currently only renders the form; this spec adds a POST handler that verifies credentials against the `users` table, sets `session["user_id"]`, and redirects to `/profile`. `/logout` is currently a placeholder string — it becomes a real route that clears the session and redirects to the landing page. Together with Step 02, this unlocks every protected feature that follows (profile, expense CRUD).

## Depends on
- Step 01 — Database Setup (`users` table, `get_db()`)
- Step 02 — Registration (creates accounts to sign into; `session["user_id"]` convention; `app.secret_key` already set)

## Routes
- `GET /login` — render the sign-in form — public (already exists, keep unchanged)
- `POST /login` — validate credentials, start session, redirect to `/profile` — public
- `GET /logout` — clear session, redirect to `/` — public (replaces the current placeholder string)

No other new routes.

## Database changes
No database changes. The `users` table already has `email` (UNIQUE) and `password_hash` — everything needed to authenticate.

## Templates
- **Create:** none
- **Modify:** none — `templates/login.html` already:
  - extends `base.html`
  - POSTs to `/login` with fields `email` and `password`
  - renders `{{ error }}` inside an `.auth-error` block

## Files to change
- `app.py`
  - Change the `/login` decorator to `methods=["GET", "POST"]` and add POST handling
  - Import `check_password_hash` from `werkzeug.security` (alongside the existing `generate_password_hash`)
  - On POST: read `email` and `password`, look up user, verify hash, set `session["user_id"]`, redirect to `/profile`; on failure re-render `login.html` with a generic error
  - Replace the `/logout` placeholder with a real handler that calls `session.clear()` (or `session.pop("user_id", None)`) and redirects to `url_for("landing")`

## Files to create
None.

## New dependencies
No new dependencies — `werkzeug.security.check_password_hash` ships with Flask.

## Rules for implementation
- No SQLAlchemy or ORMs — use `sqlite3` via `get_db()`
- Parameterised queries only — never build SQL with string formatting or f-strings
- Passwords verified with `werkzeug.security.check_password_hash` (never compare plain text)
- Use CSS variables for any styling adjustments — never hardcode hex values
- All templates extend `base.html` (already the case)
- Normalise `email` to lowercase and `.strip()` before querying
- Reject blank `email` or blank `password` with the same generic error used for bad credentials — do not reveal whether the email exists in the database
- Error message on bad credentials: `"Invalid email or password."` (identical for unknown email and wrong password — prevents user enumeration)
- Close the DB connection in a `finally` block, same pattern as the registration route
- On successful login: `session["user_id"] = user["id"]`, then `redirect(url_for("profile"))` (302)
- Logout must clear `user_id` from the session and return a redirect to `/`
- Logout must be safe to hit when already logged out (no KeyError)
- Do not log or echo the raw password anywhere

## Definition of done
- [ ] `GET /login` still renders the form exactly as before
- [ ] Submitting valid credentials for the demo user (`demo@spendly.com` / `demo123`) redirects to `/profile` and sets `session["user_id"]` to that user's id
- [ ] Submitting a **wrong password** for an existing email re-renders `login.html` with the error `"Invalid email or password."` and leaves `session["user_id"]` unset
- [ ] Submitting an **unknown email** re-renders with the same error (wording identical — no enumeration hint)
- [ ] Submitting a blank email or blank password re-renders with the same error
- [ ] Email is matched case-insensitively: `DEMO@SPENDLY.COM` with the correct password still logs in
- [ ] `GET /logout` clears `session["user_id"]` and redirects (302) to `/`
- [ ] Hitting `/logout` while already logged out still returns a 302 to `/` with no error
- [ ] `app.py` uses only parameterised queries for the new logic (no f-string or `%` SQL)
- [ ] `python app.py` starts without errors and all existing routes still work
