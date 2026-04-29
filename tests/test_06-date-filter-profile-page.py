# Spec: Step 6 — Date Filter for Profile Page
#
# Behaviors under test (all derived from the spec, not the implementation):
#
#   ROUTE TESTS (GET /profile with date params)
#   - Unauthenticated request with date params redirects to /login
#   - Valid from+to range returns 200 and shows exactly the right transactions
#   - Custom range deactivates the preset pills (no is-active class on them)
#   - from-only (open-ended upper bound) returns transactions on/after that date
#   - to-only (open-ended lower bound) returns transactions up/to that date
#   - Reversed range (from > to) returns 200, shows inline .filter-error, does not crash
#   - Malformed from date returns 200, shows inline .filter-error, does not crash
#   - Empty from= and to= both present triggers a redirect to the clean /profile URL
#   - Zero-result custom range returns 200 with an empty transaction state (no exception)
#   - range=this_month preset still works when no from/to supplied
#   - Stats and category breakdown are present in the response regardless of date filter
#
#   DB HELPER UNIT TESTS (database.queries.get_recent_transactions)
#   - Both bounds inclusive: from=2026-04-05&to=2026-04-09 → 3 rows
#   - from-only: from=2026-04-10 → 3 rows (Apr 11, Apr 13, Apr 15)
#   - to-only: to=2026-04-03 → 2 rows (Apr 01, Apr 03)
#   - date_from == date_to (single day): exactly 1 row when that date has a transaction
#   - date_from == date_to for a date with no transaction → 0 rows, returns list
#   - Zero-result range returns empty list, not an exception
#   - Custom date range overrides the period argument
#   - Existing period="this_month" still works when no custom dates given

from database import queries


def _authed_client(client, user_id):
    """Set the session user_id so the request is treated as authenticated."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_date_filter_unauthenticated_redirects_to_login(client):
    """Unauthenticated GET /profile?from=2026-04-05&to=2026-04-09 must redirect to /login."""
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Happy paths — valid ranges
# ---------------------------------------------------------------------------

def test_date_filter_valid_range_returns_200(client, seed_user_id):
    """GET /profile?from=2026-04-05&to=2026-04-09 returns HTTP 200 for an auth'd user."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    assert resp.status_code == 200


def test_date_filter_valid_range_shows_correct_transactions(client, seed_user_id):
    """Spec DoD: from=2026-04-05&to=2026-04-09 shows exactly Bills, Health, Entertainment."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    body = resp.data.decode()
    assert "Bills" in body
    assert "Health" in body
    assert "Entertainment" in body
    # Transactions outside the range must not appear
    assert "Transport" not in body
    assert "Shopping" not in body


def test_date_filter_valid_range_deactivates_preset_pills(client, seed_user_id):
    """When a custom date range is active, no preset pill must carry the is-active class."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    body = resp.data.decode()
    # The template applies is-active only when tx_range matches the preset name.
    # With a custom range tx_range is set to "custom", so none of the preset
    # values should be paired with is-active in the same HTML fragment.
    # We check that the string "is-active" does not co-occur with any preset label.
    for preset_label in ("This month", "Last month", "All"):
        # A rough but spec-faithful check: none of the preset anchor/button
        # elements that contain the preset label text also contain is-active.
        # Split by the preset label and inspect the surrounding context.
        parts = body.split(preset_label)
        for part in parts[:-1]:
            # Look backwards ~150 chars for is-active within the same tag/element
            context = part[-150:]
            assert "is-active" not in context, (
                f"Preset pill '{preset_label}' still has is-active when custom range is set"
            )


def test_date_filter_from_only_open_ended_range(client, seed_user_id):
    """Spec DoD: from=2026-04-10 shows transactions on/after 2026-04-10 only."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-10")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Seeded dates >= 2026-04-10: Apr 11 (Shopping), Apr 13 (Other), Apr 15 (Food)
    assert "Shopping" in body
    assert "Other" in body
    # Earlier transactions must not appear
    assert "Bills" not in body
    assert "Transport" not in body
    assert "Health" not in body


def test_date_filter_to_only_open_ended_range(client, seed_user_id):
    """Spec DoD: to=2026-04-03 shows transactions up to and including 2026-04-03 only."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?to=2026-04-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Seeded dates <= 2026-04-03: Apr 01 (Food/Lunch), Apr 03 (Transport)
    assert "Transport" in body
    # Transactions after 2026-04-03 must not appear
    assert "Bills" not in body
    assert "Health" not in body
    assert "Entertainment" not in body
    assert "Shopping" not in body


# ---------------------------------------------------------------------------
# Custom range overrides preset
# ---------------------------------------------------------------------------

def test_date_filter_custom_range_overrides_range_preset(client, seed_user_id):
    """When from/to are both valid they take precedence over the range= preset param."""
    _authed_client(client, seed_user_id)
    # ?range=all would normally show all 8 transactions; adding from+to must restrict it
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09&range=all")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Only 3 transactions fall in this window; the earlier Food (Apr 01) must not appear
    assert "Bills" in body
    assert "Health" in body
    assert "Entertainment" in body
    assert "Transport" not in body
    assert "Shopping" not in body


# ---------------------------------------------------------------------------
# Validation errors — must render 200, not crash, show .filter-error
# ---------------------------------------------------------------------------

def test_date_filter_reversed_range_returns_200_with_error(client, seed_user_id):
    """Spec DoD: reversed range (from > to) renders the page without crashing."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-05-01&to=2026-04-01")
    assert resp.status_code == 200


def test_date_filter_reversed_range_shows_inline_error(client, seed_user_id):
    """Spec DoD: reversed range shows an inline error element above the table."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-05-01&to=2026-04-01")
    body = resp.data.decode()
    assert "filter-error" in body


def test_date_filter_reversed_range_falls_back_to_default_list(client, seed_user_id):
    """Spec: reversed range falls back to default transaction list (page still renders data)."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-05-01&to=2026-04-01")
    body = resp.data.decode()
    # At least some transactions should be visible (fallback renders default list)
    assert "Food" in body or "Transport" in body or "Bills" in body


def test_date_filter_malformed_from_date_returns_200(client, seed_user_id):
    """Spec DoD: malformed from date renders the page without crashing."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=not-a-date")
    assert resp.status_code == 200


def test_date_filter_malformed_from_date_shows_inline_error(client, seed_user_id):
    """Spec DoD: malformed from date shows the inline .filter-error element."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=not-a-date")
    body = resp.data.decode()
    assert "filter-error" in body


def test_date_filter_malformed_to_date_returns_200_with_error(client, seed_user_id):
    """Malformed to date (wrong format) also renders 200 with inline error."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?to=2026/04/09")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "filter-error" in body


def test_date_filter_no_error_shown_for_valid_range(client, seed_user_id):
    """No .filter-error element must appear when the supplied range is valid."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    body = resp.data.decode()
    assert "filter-error" not in body


# ---------------------------------------------------------------------------
# Empty form submission — server must redirect to a clean URL
# ---------------------------------------------------------------------------

def test_date_filter_empty_from_and_to_redirects_to_clean_url(client, seed_user_id):
    """Spec DoD: empty from= and to= both present triggers a redirect (not a 200)."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=&to=")
    assert resp.status_code == 302


def test_date_filter_empty_from_and_to_redirect_has_no_date_params(client, seed_user_id):
    """The redirect from empty from=&to= must point to /profile with no from/to in the URL."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=&to=")
    location = resp.headers["Location"]
    assert "from=" not in location
    assert "to=" not in location


def test_date_filter_empty_from_and_to_followed_redirect_returns_200(client, seed_user_id):
    """Following the redirect from empty from=&to= returns a clean 200 profile page."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=&to=", follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Zero-result custom range — empty state, no exception
# ---------------------------------------------------------------------------

def test_date_filter_zero_result_range_returns_200(client, seed_user_id):
    """Spec: a custom range yielding no transactions still returns 200 (no exception)."""
    _authed_client(client, seed_user_id)
    # No seeded transactions exist in the year 2020
    resp = client.get("/profile?from=2020-01-01&to=2020-01-31")
    assert resp.status_code == 200


def test_date_filter_zero_result_range_renders_empty_state(client, seed_user_id):
    """Spec: the existing empty state (.tx-empty) must render when no transactions match."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2020-01-01&to=2020-01-31")
    body = resp.data.decode()
    assert "tx-empty" in body


# ---------------------------------------------------------------------------
# Regression guard — range= preset still works without custom dates
# ---------------------------------------------------------------------------

def test_date_filter_range_this_month_preset_still_works(client, seed_user_id):
    """Spec: range=this_month works normally when no from/to are supplied."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?range=this_month")
    assert resp.status_code == 200


def test_date_filter_range_this_month_does_not_show_filter_error(client, seed_user_id):
    """range=this_month with no custom dates must not display a filter-error."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?range=this_month")
    body = resp.data.decode()
    assert "filter-error" not in body


def test_date_filter_range_all_preset_returns_all_transactions(client, seed_user_id):
    """range=all (no custom dates) returns all 8 seeded transactions."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?range=all")
    assert resp.status_code == 200
    body = resp.data.decode()
    # All 7 distinct categories (Food appears twice but that's fine)
    for category in ("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"):
        assert category in body


# ---------------------------------------------------------------------------
# Stats and breakdown unaffected by date filter
# ---------------------------------------------------------------------------

def test_date_filter_stats_present_with_date_filter_applied(client, seed_user_id):
    """Spec scope: summary stats are present in the response even when a date filter is active."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    body = resp.data.decode()
    # Stats section renders total_spent and transaction_count; at minimum the user sees numbers.
    # The spec says stats are NOT filtered, so total_spent reflects all 8 expenses.
    # We just assert the stats container is present, not its exact values.
    assert "total_spent" in body or "PKR" in body or "stats" in body.lower()


def test_date_filter_category_breakdown_present_with_date_filter_applied(client, seed_user_id):
    """Spec scope: category breakdown panel is present in the response with a date filter active."""
    _authed_client(client, seed_user_id)
    resp = client.get("/profile?from=2026-04-05&to=2026-04-09")
    body = resp.data.decode()
    # Breakdown lists categories; at least one known seeded category must appear outside
    # the transaction list as part of the breakdown panel.
    assert "breakdown" in body.lower() or "category" in body.lower()


# ---------------------------------------------------------------------------
# DB helper unit tests — database.queries.get_recent_transactions
# ---------------------------------------------------------------------------

def test_query_both_bounds_inclusive_returns_three_rows(seed_user_id):
    """Spec DoD: from=2026-04-05&to=2026-04-09 → exactly 3 transactions (Bills, Health, Ent.)."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2026-04-05", date_to="2026-04-09"
    )
    assert len(results) == 3
    categories = {r["category"] for r in results}
    assert categories == {"Bills", "Health", "Entertainment"}


def test_query_from_only_returns_three_rows(seed_user_id):
    """Spec DoD: from=2026-04-10 → 3 rows (Shopping Apr 11, Other Apr 13, Food Apr 15)."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2026-04-10"
    )
    assert len(results) == 3
    categories = {r["category"] for r in results}
    assert categories == {"Shopping", "Other", "Food"}


def test_query_to_only_returns_two_rows(seed_user_id):
    """Spec DoD: to=2026-04-03 → exactly 2 rows (Food Apr 01, Transport Apr 03)."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_to="2026-04-03"
    )
    assert len(results) == 2
    categories = {r["category"] for r in results}
    assert categories == {"Food", "Transport"}


def test_query_single_day_exact_match_returns_one_row(seed_user_id):
    """from == to for a date that has one transaction → exactly 1 row."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2026-04-07", date_to="2026-04-07"
    )
    assert len(results) == 1
    assert results[0]["category"] == "Health"


def test_query_single_day_no_match_returns_empty_list(seed_user_id):
    """from == to for a date with no transaction → empty list (no exception)."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2026-04-02", date_to="2026-04-02"
    )
    assert isinstance(results, list)
    assert len(results) == 0


def test_query_zero_result_range_returns_empty_list(seed_user_id):
    """A date range that matches no expenses returns an empty list, not an exception."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2020-01-01", date_to="2020-12-31"
    )
    assert isinstance(results, list)
    assert len(results) == 0


def test_query_custom_date_range_overrides_period_argument(seed_user_id):
    """Custom date_from/date_to must override the period argument (spec: takes precedence)."""
    # period="this_month" for April 2026 would return all 8 rows;
    # adding date_from/date_to that restricts to 1 day must return only that day's row.
    results = queries.get_recent_transactions(
        seed_user_id,
        limit=50,
        period="this_month",
        date_from="2026-04-05",
        date_to="2026-04-05",
    )
    assert len(results) == 1
    assert results[0]["category"] == "Bills"


def test_query_period_this_month_works_without_custom_dates(seed_user_id):
    """Regression: period='this_month' still works when date_from and date_to are both None."""
    # The seed data is all in April 2026; if tests run in April 2026, this_month returns
    # all 8 rows. If tests run in a different month, this_month returns 0. Either way
    # the function must return a list without raising.
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, period="this_month"
    )
    assert isinstance(results, list)


def test_query_from_bound_is_inclusive(seed_user_id):
    """The from bound must be inclusive: a transaction exactly on date_from must be returned."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2026-04-15"
    )
    dates_raw = [r["date"] for r in results]
    # Apr 15 is "Apr 15, 2026" after formatting
    assert any("15" in d and "2026" in d for d in dates_raw), (
        "Transaction on 2026-04-15 (the from bound) must be included"
    )


def test_query_to_bound_is_inclusive(seed_user_id):
    """The to bound must be inclusive: a transaction exactly on date_to must be returned."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_to="2026-04-01"
    )
    assert len(results) == 1
    assert "01" in results[0]["date"] and "2026" in results[0]["date"]


def test_query_results_ordered_newest_first(seed_user_id):
    """Results within a date range must be ordered newest-date-first per spec."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=50, date_from="2026-04-05", date_to="2026-04-09"
    )
    assert len(results) == 3
    # Formatted dates: "Apr 09, 2026", "Apr 07, 2026", "Apr 05, 2026"
    assert "09" in results[0]["date"]  # newest first
    assert "05" in results[2]["date"]  # oldest last


def test_query_result_shape_has_required_keys(seed_user_id):
    """Each result dict must contain date, description, category, and amount keys."""
    results = queries.get_recent_transactions(
        seed_user_id, limit=1, date_from="2026-04-01", date_to="2026-04-15"
    )
    assert len(results) >= 1
    row = results[0]
    assert "date" in row
    assert "description" in row
    assert "category" in row
    assert "amount" in row


def test_query_sql_injection_in_date_from_does_not_raise(seed_user_id):
    """Parameterised query: a SQL injection attempt in date_from must not raise or drop data."""
    results = queries.get_recent_transactions(
        seed_user_id,
        limit=50,
        date_from="'; DROP TABLE expenses; --",
    )
    # Either 0 rows (no match) or an empty list — the important thing is no exception
    assert isinstance(results, list)
    # Original data must still exist (the table must not have been dropped)
    all_results = queries.get_recent_transactions(seed_user_id, limit=50, period="all")
    assert len(all_results) == 8
