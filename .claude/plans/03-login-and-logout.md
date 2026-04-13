# Plan: Login and Logout (Step 3)

## Context

`/login` in `app.py:77` currently only renders `templates/login.html` on GET. `/logout` at `app.py:87` is a string placeholder. Step 02 already shipped `session["user_id"]`, `app.secret_key`, and the `get_db()`/`try/finally` connection pattern in the `register` route (`app.py:29–74`). The `login.html` template already POSTs `email` and `password` to `/login` and shows `{{ error }}` in an `.auth-error` block — no template or CSS work is needed.

The goal is to complete the auth loop: verify credentials against `users.password_hash` via `werkzeug.security.check_password_hash`, set the session, redirect to `/profile`, and make `/logout` actually clear the session. To prevent user enumeration, all failure cases (blank fields, unknown email, wrong password) must return the exact same error message.

## Files to Modify

1. **`app.py`** — extend `/login` to handle POST, replace the `/logout` placeholder with a real handler.

No other files need to change. `templates/login.html`, `templates/base.html`, and `static/css/style.css` are ready as-is.

## Implementation

### 1. Imports

Update the existing werkzeug import at `app.py:5`:
```python
from werkzeug.security import generate_password_hash, check_password_hash
```
No other imports are needed — `request`, `redirect`, `url_for`, `session` are already imported for registration (`app.py:4`).

### 2. Rewrite the `login` route (`app.py:77`)

Change decorator to `@app.route("/login", methods=["GET", "POST"])`.

Handler flow:
- If `request.method == "GET"` → `return render_template("login.html")`
- On POST:
  1. `email = request.form.get("email", "").strip().lower()`
  2. `password = request.form.get("password", "")`
  3. Define one error constant inside the function: `error = "Invalid email or password."`
  4. If either field is blank → `return render_template("login.html", error=error)`
  5. Look up the user:
     ```python
     conn = get_db()
     try:
         user = conn.execute(
             "SELECT id, password_hash FROM users WHERE email = ?", (email,)
         ).fetchone()
     finally:
         conn.close()
     ```
  6. If `user is None` **or** `not check_password_hash(user["password_hash"], password)` → `return render_template("login.html", error=error)` (same message for both — no enumeration hint)
  7. `session["user_id"] = user["id"]`
  8. `return redirect(url_for("profile"))`

### 3. Rewrite the `logout` route (`app.py:86`)

Replace the placeholder entirely:
```python
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("landing"))
```
`session.pop` with a default is safe to call when already logged out. `landing` is the name of the `/` route at `app.py:24`.

### 4. Reused existing code

- `get_db()` in `database/db.py:10` — same pattern already used in `register` (`app.py:47–71`).
- `templates/login.html:16–18` — error block already wired to `{{ error }}`.
- `templates/login.html:20` — form already POSTs to `/login` with `email` + `password`.
- `app.py:91` `profile` route — redirect target after login.
- `app.py:24` `landing` route — redirect target after logout.
- `app.secret_key` already set at `app.py:10`.

## Verification

Run `python app.py` and use Flask's test client + a browser/curl to cover the spec's Definition of Done:

1. **GET still works:** `curl -s http://localhost:5005/login | grep -c '<form'` → 1.
2. **Happy path:** POST `email=demo@spendly.com`, `password=demo123` → 302 to `/profile`; inspect session via `app.test_client()` → `user_id == 1` (or whatever the demo user's id is per `seed_db`).
3. **Case-insensitive email:** POST `email=DEMO@SPENDLY.COM`, `password=demo123` → still 302 to `/profile`.
4. **Wrong password:** POST `email=demo@spendly.com`, `password=wrong` → 200, response body contains `Invalid email or password.`, session has no `user_id`.
5. **Unknown email:** POST `email=nobody@spendly.com`, `password=whatever` → 200, same error string as (4), no `user_id`.
6. **Blank fields:** POST with empty `email` and empty `password` → 200, same error, no `user_id`.
7. **Logout:** with a logged-in client, GET `/logout` → 302 to `/`; session no longer has `user_id`.
8. **Idempotent logout:** with a fresh (logged-out) client, GET `/logout` → still 302 to `/`, no exception.
9. **Parameterised SQL only:** grep `app.py` for `%` and f-string SQL in the new code → no hits.
10. **App boots clean:** `python app.py` starts without errors; registration (Step 02) still works end-to-end.

One consolidated Python harness using `app.test_client()` can cover items 2–8 without launching the live server.
