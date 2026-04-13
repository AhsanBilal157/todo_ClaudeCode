# Spec: Registration

## Overview
Enable users to create a Spendly account by submitting the existing registration form. The `/register` route currently only renders the template — this spec adds the POST handler that validates input, hashes the password with werkzeug, inserts a new user row, logs the user in via Flask's session, and redirects to the profile page. Registration is the first user-facing feature after the database layer and unblocks every subsequent feature that depends on an authenticated user (login, profile, expense CRUD).

## Depends on
- Step 01 — Database Setup (users table, `get_db()`, `init_db()`, `seed_db()`)

## Routes
- `GET /register` — render the registration form — public (already exists, keep unchanged)
- `POST /register` — validate input, create user, log them in, redirect to `/profile` — public

No other new routes.

## Database changes
No database changes. The `users` table from Step 01 already has `id`, `name`, `email` (UNIQUE), `password_hash`, and `created_at`.

## Templates
- **Create:** none
- **Modify:** none — `templates/register.html` already:
  - extends `base.html`
  - posts to `/register` with fields `name`, `email`, `password`
  - renders `{{ error }}` in an `.auth-error` block when set

## Files to change
- `app.py`
  - Update the existing `register` route to accept `GET` and `POST` methods
  - Import `request`, `redirect`, `url_for`, `session` from Flask
  - Import `get_db` from `database.db`
  - Import `generate_password_hash` from `werkzeug.security`
  - On POST: read name/email/password, validate, insert user, set `session["user_id"]`, redirect to `/profile`
  - On GET or validation failure: render `register.html` with optional `error`
  - Set `app.secret_key` (required for `session`) — use a module-level constant for now

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug` is already installed via Flask.

## Rules for implementation
- No SQLAlchemy or ORMs — use `sqlite3` via `get_db()`
- Parameterised queries only — never build SQL with string formatting or f-strings
- Passwords hashed with `werkzeug.security.generate_password_hash` before insert
- Use CSS variables for any styling adjustments — never hardcode hex values
- All templates extend `base.html` (already the case)
- Normalise `email` to lowercase and `.strip()` before querying or inserting
- Trim `name` with `.strip()`
- Enforce minimum password length of 8 characters (matches the placeholder in the form)
- Reject blank `name`, `email`, or `password`
- Detect duplicate email before insert by catching `sqlite3.IntegrityError` **and** by pre-check with a `SELECT` — show a friendly error in the template rather than a 500
- On success, store `session["user_id"]` so subsequent steps can read the logged-in user
- Return status 200 when re-rendering the form with an error; 302 on successful redirect
- Do not log or echo the raw password anywhere

## Definition of done
- [ ] `GET /register` still renders the form exactly as before
- [ ] Submitting the form with valid new details creates a row in the `users` table with a hashed `password_hash` (verifiable via `sqlite3 spendly.db "SELECT id, name, email, substr(password_hash,1,20) FROM users;"`)
- [ ] After successful registration the browser is redirected to `/profile` and `session["user_id"]` matches the new row's `id`
- [ ] Submitting the form with an email that already exists re-renders `register.html` with a visible error message and no new row is inserted
- [ ] Submitting with a blank name, blank email, invalid email, or password shorter than 8 chars re-renders the form with an error and no row is inserted
- [ ] `spendly.db` users table still enforces the UNIQUE email constraint (attempting duplicate insert at the SQL layer still fails)
- [ ] `app.py` uses only parameterised queries for the new logic (no f-string or `%` SQL)
- [ ] App starts without errors: `python app.py`
