# Plan: Registration (Step 2)

## Context

`/register` in `app.py:15` currently only renders `templates/register.html` on GET. The template already has a POST form posting `name`, `email`, `password` and displays `{{ error }}` in an `.auth-error` block. The `users` table from Step 01 already has `id`, `name`, `email UNIQUE`, `password_hash`, `created_at`. No database work is required — the gap is the POST handler and session setup in `app.py`.

This unblocks Step 03 (login/logout) and Step 04 (profile), both of which require `session["user_id"]` to be set.

## Files to Modify

1. **`app.py`** — extend `/register` to handle POST, add session setup, set `app.secret_key`

No other files need to change. `templates/register.html`, `templates/base.html`, and `static/css/style.css` (with `.auth-error`, `--danger`, `--danger-light` already defined) are ready as-is.

## Implementation

### 1. Imports in `app.py`

Add to the existing `from flask import ...` line:
- `request`, `redirect`, `url_for`, `session`

Add new imports:
- `import sqlite3` (for catching `IntegrityError`)
- `import re` (for email regex validation — avoids new dependency)
- `from werkzeug.security import generate_password_hash`
- `from database.db import get_db` (already imported alongside `init_db`, `seed_db`)

### 2. Set `app.secret_key`

Right after `app = Flask(__name__)`, add:
```python
app.secret_key = "dev-secret-key-change-in-production"
```
Module-level constant is acceptable per the spec. A follow-up step can move it to env var.

### 3. Rewrite the `register` route

Change decorator to `@app.route("/register", methods=["GET", "POST"])`.

Handler flow:
- If `request.method == "GET"` → `return render_template("register.html")`
- On POST:
  1. Read `name = request.form.get("name", "").strip()`
  2. Read `email = request.form.get("email", "").strip().lower()`
  3. Read `password = request.form.get("password", "")`
  4. Validate in order, returning `render_template("register.html", error=...)` on first failure:
     - Blank name → "Please enter your name."
     - Blank email → "Please enter your email."
     - Email regex fail (simple `^[^@\s]+@[^@\s]+\.[^@\s]+$`) → "Please enter a valid email address."
     - `len(password) < 8` → "Password must be at least 8 characters."
  5. Pre-check duplicate email:
     ```python
     conn = get_db()
     existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
     if existing:
         conn.close()
         return render_template("register.html", error="An account with that email already exists.")
     ```
  6. Insert user with hashed password:
     ```python
     try:
         cursor = conn.execute(
             "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
             (name, email, generate_password_hash(password)),
         )
         conn.commit()
         new_user_id = cursor.lastrowid
     except sqlite3.IntegrityError:
         conn.close()
         return render_template("register.html", error="An account with that email already exists.")
     finally:
         conn.close()  # or handle via try/finally block around the whole conn usage
     ```
     (Connection cleanup can be simplified with one `finally` around the whole conn block — reuse the `get_db()` pattern from `seed_db` in `database/db.py:48`.)
  7. `session["user_id"] = new_user_id`
  8. `return redirect(url_for("profile"))` — the `/profile` placeholder already exists at `app.py:34`.

### 4. Reused existing code

- `get_db()` in `database/db.py:10` — the exact pattern used by `seed_db()` (get conn, execute, commit, close). No new helper needed.
- `.auth-error` CSS class in `static/css/style.css:456` — already styled with `--danger` / `--danger-light`, no template or CSS edits needed.
- `templates/register.html:16–18` — error block already wired to `{{ error }}`.
- `app.py:34` `profile` route — target for post-registration redirect.

## Verification

Run `python app.py` and use a browser (or `curl`) to verify the spec's Definition of Done checklist:

1. **GET still works:** visit `http://localhost:5005/register` → form renders.
2. **Happy path:** submit `Test User / test@example.com / password123` → browser lands on `/profile` (shows "Profile page — coming in Step 4") and `sqlite3 spendly.db "SELECT id, name, email, substr(password_hash,1,20) FROM users WHERE email='test@example.com';"` returns one row with a `scrypt:` / `pbkdf2:` prefixed hash.
3. **Session set:** in a Python shell, `from app import app; client = app.test_client(); client.post("/register", data={"name":"X","email":"x@y.com","password":"password123"}); with client.session_transaction() as s: print(s["user_id"])` → prints an int.
4. **Duplicate email:** re-submit the same email → form re-renders with visible error, no new row added (`SELECT COUNT(*)` unchanged).
5. **Validation errors:** submit blank name, blank email, `bademail`, and `short` password — each re-renders with the right error, no row added.
6. **DB constraint still enforced:** `sqlite3 spendly.db "INSERT INTO users (name,email,password_hash) VALUES ('a','test@example.com','x');"` → `UNIQUE constraint failed`.
7. **Parameterised SQL only:** `grep` `app.py` for `%` and f-string SQL → no hits in the new code.
8. **App startup clean:** `python app.py` prints no errors and serves `/`.
