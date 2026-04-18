# Spec: Profile Page Design

## Overview
Replace the `/profile` placeholder string with a real, designed profile page — the first authenticated landing surface a user sees after signing in or registering. This step is *design-first*: the page reads the current user's `name`, `email`, and `created_at` from the `users` table and presents them inside a styled "account" card that matches the visual language already established by the landing and auth pages (DM Serif Display headings, DM Sans body, paper-warm palette, soft borders, rounded cards). It also lays down the layout shell (page header, profile card, an empty "Activity" placeholder section) that later steps — expense list, add/edit/delete — will plug content into. No expense CRUD yet; this is purely the profile surface, the auth gate around it, and the CSS to make it feel like part of Spendly.

## Depends on
- Step 01 — Database Setup (`users` table, `get_db()`)
- Step 02 — Registration (creates accounts; sets `session["user_id"]`)
- Step 03 — Login and Logout (sets / clears `session["user_id"]`; the navbar's "Logout" link already points here when logged in)

## Routes
- `GET /profile` — render the profile page for the currently logged-in user — logged-in (replaces the existing `"Profile page — coming in Step 4"` string)

If the request has no `session["user_id"]`, redirect to `/login` (302). No POST handler in this step.

No other new routes.

## Database changes
No database changes. Everything needed is already on the `users` table from Step 01:
- `name`
- `email`
- `created_at` (used to render a "Member since" line)

## Templates
- **Create:**
  - `templates/profile.html` — extends `base.html`, renders the profile card and an empty "Recent activity" placeholder section
- **Modify:**
  - none (the navbar in `base.html` already shows the "Logout" link when `session.user_id` is set, which is the only nav surface this page needs)

## Files to change
- `app.py`
  - Replace the placeholder `/profile` handler with a real one
  - On entry: if `session.get("user_id")` is falsy → `redirect(url_for("login"))`
  - Otherwise: open `get_db()`, `SELECT id, name, email, created_at FROM users WHERE id = ?` with `(session["user_id"],)`, close the connection in a `finally`, then `render_template("profile.html", user=user)`
  - If the lookup returns `None` (stale session pointing at a deleted row): `session.pop("user_id", None)` then redirect to `/login`
- `static/css/style.css`
  - Append a new `/* Profile */` section at the end of the file with all classes used by `profile.html` — see "Rules for implementation" below for the required class names and design constraints

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use `sqlite3` via `get_db()`
- Parameterised queries only — never f-string or `%`-format SQL
- Passwords are never read or rendered on this page (no `password_hash` in the SELECT, no display of any credential)
- All templates extend `base.html`
- **Use CSS variables — never hardcode hex values.** Every color must come from the `:root` palette already defined in `style.css` (`--ink`, `--ink-soft`, `--ink-muted`, `--ink-faint`, `--paper`, `--paper-warm`, `--paper-card`, `--accent`, `--accent-light`, `--accent-2`, `--accent-2-light`, `--danger`, `--danger-light`, `--border`, `--border-soft`). Reuse `--font-display` / `--font-body`, `--max-width`, and the `--radius-*` tokens.
- Close the DB connection in a `finally` block, same pattern as the login/register routes
- Auth gate: a logged-out user hitting `/profile` must get a 302 to `/login` — never a 500, never a leaked stack trace, never a partial render
- Stale session (user_id no longer exists in `users`): clear the session key and redirect to `/login`
- The page must not break if `created_at` is `NULL` (older rows seeded before the default landed) — fall back to a dash or `"—"`
- No JavaScript is required for this step; do not add a new JS file

### Required template structure (`profile.html`)
- Block `title` → `"Profile — Spendly"`
- Block `content` contains, in order:
  1. `<section class="profile-section">` wrapping a `<div class="profile-container">` (max-width container, similar to `.auth-container` but wider — target ~720px)
  2. A page header `<div class="profile-header">` with:
     - `<h1 class="profile-title">` — DM Serif Display, e.g. `Your account`
     - `<p class="profile-subtitle">` — short DM Sans line in `--ink-muted`, e.g. `Manage your Spendly profile and review your activity.`
  3. A profile card `<article class="profile-card">` containing:
     - An avatar block `<div class="profile-avatar">` showing the **first letter** of `user.name` uppercased, on an `--accent-light` circle with `--accent`-colored serif text
     - A details block with three rows (`<div class="profile-row">` × 3): one each for `Name`, `Email`, `Member since`. Each row has a `<span class="profile-row-label">` (small, `--ink-muted`, uppercase or tracked) and a `<span class="profile-row-value">` (regular weight, `--ink`)
     - Format `Member since` from `user.created_at` as a human-friendly date in the template (e.g. `April 17, 2026`). If you need date parsing, do it in the route and pass a pre-formatted string into the template — keep the template logic-light.
     - A footer action row `<div class="profile-actions">` with a single secondary-styled `<a>` linking to `/logout`, label `Sign out`. (No edit-profile button in this step — that comes later.)
  4. A second card `<section class="profile-activity">` titled `Recent activity` (DM Serif Display) with an empty state inside: a muted line such as `You haven't logged any expenses yet.` and a primary `<a class="btn-primary">` to `/expenses/add` labelled `Add your first expense`. This section is design scaffolding for Step 07; it must render cleanly even though the link target is still a placeholder.

### Required CSS additions (append to `static/css/style.css`)
Define exactly these classes (no more, no fewer) so the template above renders correctly:
- `.profile-section` — top padding ~3rem, horizontal padding 2rem, centered
- `.profile-container` — `max-width: 720px; margin: 0 auto;`
- `.profile-header` — bottom margin ~2rem
- `.profile-title` — `font-family: var(--font-display)`, large (~2.4rem), `color: var(--ink)`
- `.profile-subtitle` — `color: var(--ink-muted)`, ~1rem
- `.profile-card` — `background: var(--paper-card)`, `border: 1px solid var(--border)`, `border-radius: var(--radius-lg)`, padding ~2rem, soft shadow consistent with `.mock-browser`
- `.profile-avatar` — circle ~64px, `background: var(--accent-light)`, `color: var(--accent)`, `font-family: var(--font-display)`, centered letter
- `.profile-row` — flex row, label left, value right, separator `1px solid var(--border-soft)` between rows (last row has no border)
- `.profile-row-label` — `color: var(--ink-muted)`, small (~0.8rem), letter-spacing ~0.05em, uppercase
- `.profile-row-value` — `color: var(--ink)`, regular weight
- `.profile-actions` — top margin, right-aligned
- `.profile-activity` — second card sharing the same surface treatment as `.profile-card` (you may reuse via a shared selector, e.g. `.profile-card, .profile-activity { ... }`), with its own internal title styling for `Recent activity`
- Reuse the existing `.btn-primary` (already defined around line 306 of `style.css`) — do not redefine it

The page must look at home next to the existing landing and auth pages — same fonts, same rounded-corner language, same paper-warm palette, same restraint.

## Definition of done
- [ ] Logged-out user visiting `/profile` is redirected (302) to `/login` — no stack trace, no partial render
- [ ] Logged-in demo user (`demo@spendly.com` / `demo123`) sees a fully-styled profile page at `/profile`
- [ ] The page shows the demo user's `name` ("Demo User"), `email` ("demo@spendly.com"), and a human-formatted `Member since` date derived from `created_at`
- [ ] The avatar circle shows the letter `D` (first letter of `Demo User`) on an `--accent-light` background
- [ ] The "Recent activity" card renders with the empty-state copy and a working `Add your first expense` button (target may still be the Step 07 placeholder — that is acceptable)
- [ ] Clicking `Sign out` from the profile page logs the user out and lands on `/`
- [ ] Navbar "Logout" link from any other page lands on `/profile` only when logged in (this already works via Step 03 — verify it has not regressed)
- [ ] A user whose `session["user_id"]` no longer exists in the database (e.g. row deleted manually via sqlite) is redirected to `/login` and their session key is cleared
- [ ] `templates/profile.html` extends `base.html` and contains no inline `<style>` blocks and no inline color hex values
- [ ] `static/css/style.css` contains the new `/* Profile */` section, uses only CSS variables for colors, and does not redefine any existing class
- [ ] `app.py` uses only parameterised queries for the new logic (no f-string or `%` SQL)
- [ ] `python app.py` starts without errors and all previously-passing routes (`/`, `/register`, `/login`, `/logout`, `/terms`, `/privacy`) still work
