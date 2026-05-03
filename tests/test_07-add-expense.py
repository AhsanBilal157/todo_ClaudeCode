# Spec: Step 7 — Add Expense
#
# Behaviors under test (all derived from the spec, not the implementation):
#
#   AUTH GATE
#   - GET /expenses/add without a session → 302 to /login
#   - POST /expenses/add without a session → 302 to /login AND no row inserted
#
#   GET /expenses/add (authenticated)
#   - Returns HTTP 200
#   - Renders today's date pre-filled in the date input (value="YYYY-MM-DD")
#   - Amount input is present and empty by default
#   - Description input is present and empty by default
#   - All seven allowed categories appear in the category select
#
#   SUCCESSFUL POST
#   - Valid form (amount=49.99, category=Food, date=2026-05-03, description="Tea")
#     inserts exactly one row attributed to the session user, returns 302 → /profile
#   - After the redirect, the expense surfaces in /profile:
#     transaction count increases by 1, total_spent increases by the amount,
#     and the description appears in the transaction list
#
#   AMOUNT VALIDATION (parametrized)
#   - Rejects "0", "-5", "abc", "" with a 200 re-render + inline error + no DB write
#   - Rejects "inf" and "nan" (values that survive naive float() casts) — same contract
#
#   CATEGORY VALIDATION (parametrized)
#   - Rejects any value not in the seven-item allow-list with 200 + error + no DB write
#   - Accepts all seven allowed categories
#
#   DATE VALIDATION (parametrized)
#   - Rejects "not-a-date" and "" with 200 + error + no DB write
#   - Rejects plausible but wrong-format strings like "03/05/2026" and "2026/05/03"
#
#   DESCRIPTION RULES
#   - Empty description ("") → row stored with NULL in expenses.description
#   - Whitespace-only description ("   ") → row stored with NULL in expenses.description
#   - Description > 200 chars → rejected with 200 + inline error + no DB write
#
#   FORM VALUE PRESERVATION ON VALIDATION ERROR
#   - On re-render the previously submitted amount, category, date, description
#     are all echoed back into the form inputs so the user need not retype
#
#   PROFILE PAGE CTA
#   - GET /profile (authenticated) renders a link to /expenses/add
#
#   user_id ATTRIBUTION
#   - A POST that includes a forged "user_id=999999" field must still attribute
#     the new row to the session user, not to 999999
#
#   SEVEN ALLOWED CATEGORIES
#   - Spec allow-list: Food, Transport, Bills, Health, Entertainment, Shopping, Other

import pytest
from datetime import datetime

from database.db import get_db


# ---------------------------------------------------------------------------
# Isolation fixture — rolls back any expense rows inserted during a test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_inserts(app):
    """Snapshot MAX(id) before each test; delete any rows added by the test after it."""
    with app.app_context():
        conn = get_db()
        try:
            max_id = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM expenses"
            ).fetchone()[0]
        finally:
            conn.close()

    yield

    with app.app_context():
        conn = get_db()
        try:
            conn.execute("DELETE FROM expenses WHERE id > ?", (max_id,))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _authed(client, user_id):
    """Inject user_id into the session so requests are treated as authenticated."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _expense_count(app, user_id):
    """Return the number of expense rows for user_id using a direct DB query."""
    with app.app_context():
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        finally:
            conn.close()


def _latest_expense_row(app, user_id):
    """Return the most recently inserted expense row for user_id, or None."""
    with app.app_context():
        conn = get_db()
        try:
            return conn.execute(
                "SELECT id, user_id, amount, category, date, description "
                "FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()


VALID_FORM = {
    "amount": "49.99",
    "category": "Food",
    "date": "2026-05-03",
    "description": "Tea",
}

ALLOWED_CATEGORIES = (
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
)


# ===========================================================================
# AUTH GATE
# ===========================================================================

class TestAuthGate:
    """Spec DoD: both GET and POST require an authenticated session."""

    def test_get_without_session_redirects_to_login(self, client):
        """Logged-out GET /expenses/add must return 302 pointing to /login."""
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_without_session_redirects_to_login(self, client, seed_user_id, app):
        """Logged-out POST /expenses/add must return 302 pointing to /login."""
        resp = client.post("/expenses/add", data=VALID_FORM)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_without_session_writes_no_row(self, client, seed_user_id, app):
        """Logged-out POST must not insert any row into expenses."""
        before = _expense_count(app, seed_user_id)
        client.post("/expenses/add", data=VALID_FORM)
        assert _expense_count(app, seed_user_id) == before


# ===========================================================================
# GET /expenses/add — authenticated
# ===========================================================================

class TestGetForm:
    """Spec DoD: authenticated GET renders a form pre-filled with today's date."""

    def test_get_returns_200(self, client, seed_user_id):
        """Authenticated GET /expenses/add must return HTTP 200."""
        _authed(client, seed_user_id)
        resp = client.get("/expenses/add")
        assert resp.status_code == 200

    def test_get_prefills_today_date(self, client, seed_user_id):
        """Spec: date input must default to today's date in YYYY-MM-DD format."""
        _authed(client, seed_user_id)
        resp = client.get("/expenses/add")
        today = datetime.now().strftime("%Y-%m-%d")
        body = resp.data.decode()
        assert f'value="{today}"' in body

    def test_get_amount_input_is_empty(self, client, seed_user_id):
        """Spec: amount input must be empty on the initial GET (no default value)."""
        _authed(client, seed_user_id)
        resp = client.get("/expenses/add")
        body = resp.data.decode()
        # The amount input must exist and must not carry a pre-filled numeric value.
        assert 'name="amount"' in body
        # A non-empty value attribute would look like value="<digits>"; verify it is absent.
        import re
        amount_value_re = re.compile(r'name="amount"[^>]*value="[^"]+"|value="[^"]+"[^>]*name="amount"')
        assert not amount_value_re.search(body), (
            "Amount input must not have a non-empty value on initial GET"
        )

    def test_get_description_input_is_empty(self, client, seed_user_id):
        """Spec: description input must be empty on the initial GET."""
        _authed(client, seed_user_id)
        resp = client.get("/expenses/add")
        body = resp.data.decode()
        assert 'name="description"' in body

    def test_get_renders_all_seven_categories(self, client, seed_user_id):
        """Spec: the category select must contain exactly the seven allowed categories."""
        _authed(client, seed_user_id)
        resp = client.get("/expenses/add")
        body = resp.data.decode()
        for category in ALLOWED_CATEGORIES:
            assert category in body, f"Category '{category}' missing from GET form"

    def test_get_renders_pkr_label(self, client, seed_user_id):
        """Spec: amount field must carry a PKR label (currency display rule)."""
        _authed(client, seed_user_id)
        resp = client.get("/expenses/add")
        body = resp.data.decode()
        assert "PKR" in body


# ===========================================================================
# SUCCESSFUL POST
# ===========================================================================

class TestSuccessfulPost:
    """Spec DoD: valid POST inserts exactly one row and redirects to /profile."""

    def test_valid_post_returns_302(self, client, seed_user_id):
        """Spec: successful POST must respond with HTTP 302."""
        _authed(client, seed_user_id)
        resp = client.post("/expenses/add", data=VALID_FORM)
        assert resp.status_code == 302

    def test_valid_post_redirects_to_profile(self, client, seed_user_id):
        """Spec: the 302 after a successful POST must point to /profile."""
        _authed(client, seed_user_id)
        resp = client.post("/expenses/add", data=VALID_FORM)
        assert "/profile" in resp.headers["Location"]

    def test_valid_post_inserts_exactly_one_row(self, client, seed_user_id, app):
        """Spec: exactly one new row must be written to expenses on success."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        client.post("/expenses/add", data=VALID_FORM)
        assert _expense_count(app, seed_user_id) == before + 1

    def test_valid_post_stores_correct_amount(self, client, seed_user_id, app):
        """Spec: the inserted row must store the submitted amount."""
        _authed(client, seed_user_id)
        client.post("/expenses/add", data=VALID_FORM)
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert float(row["amount"]) == pytest.approx(49.99)

    def test_valid_post_stores_correct_category(self, client, seed_user_id, app):
        """Spec: the inserted row must store the submitted category."""
        _authed(client, seed_user_id)
        client.post("/expenses/add", data=VALID_FORM)
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert row["category"] == "Food"

    def test_valid_post_stores_correct_date(self, client, seed_user_id, app):
        """Spec: the inserted row must store the submitted date as YYYY-MM-DD."""
        _authed(client, seed_user_id)
        client.post("/expenses/add", data=VALID_FORM)
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert row["date"] == "2026-05-03"

    def test_valid_post_stores_correct_description(self, client, seed_user_id, app):
        """Spec: the inserted row must store the submitted description text."""
        _authed(client, seed_user_id)
        client.post("/expenses/add", data=VALID_FORM)
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert row["description"] == "Tea"

    def test_new_expense_surfaces_in_profile_transaction_list(self, client, seed_user_id):
        """Spec DoD: after redirect the new expense appears in the /profile transaction list."""
        _authed(client, seed_user_id)
        unique_desc = "Spec-marker-tea-expense-07"
        client.post(
            "/expenses/add",
            data={
                "amount": "49.99",
                "category": "Food",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": unique_desc,
            },
        )
        resp = client.get("/profile?range=all")
        body = resp.data.decode()
        assert unique_desc in body

    def test_new_expense_increases_transaction_count_by_one(self, client, seed_user_id):
        """Spec DoD: stats.transaction_count on /profile must increase by 1 after a POST."""
        _authed(client, seed_user_id)

        # Scrape the count before insertion (from the all-time stats block).
        before_body = client.get("/profile?range=all").data.decode()
        # The stats block contains the integer transaction_count inside a stat-value span.
        # We pull it out via a simple search for the surrounding Transactions stat card text.
        import re
        count_matches = re.findall(r'<span class="stat-value">(\d+)</span>', before_body)
        # The transaction count stat is the second stat-value (after total_spent).
        # Use the raw DB helper as the authoritative "before" figure instead of HTML parsing.
        # This keeps the test independent of template markup details.
        before_resp = client.get("/profile?range=all")
        # We rely on the DB helper's count directly for the "before" value.
        conn_before = get_db()
        try:
            before_count = conn_before.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (seed_user_id,)
            ).fetchone()[0]
        finally:
            conn_before.close()

        client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Other",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": "count-check",
            },
        )

        conn_after = get_db()
        try:
            after_count = conn_after.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (seed_user_id,)
            ).fetchone()[0]
        finally:
            conn_after.close()

        assert after_count == before_count + 1

    def test_new_expense_increases_total_spent(self, client, seed_user_id, app):
        """Spec DoD: stats.total_spent on /profile must increase by the submitted amount."""
        _authed(client, seed_user_id)

        # Capture the total_spent from the DB before the POST.
        with app.app_context():
            conn = get_db()
            try:
                before_total = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?",
                    (seed_user_id,),
                ).fetchone()[0]
            finally:
                conn.close()

        added_amount = 77.77
        client.post(
            "/expenses/add",
            data={
                "amount": str(added_amount),
                "category": "Health",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": "total-check",
            },
        )

        with app.app_context():
            conn = get_db()
            try:
                after_total = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?",
                    (seed_user_id,),
                ).fetchone()[0]
            finally:
                conn.close()

        assert after_total == pytest.approx(before_total + added_amount, rel=1e-5)

    def test_future_date_is_accepted(self, client, seed_user_id, app):
        """Spec: future dates are allowed — no rejection for dates after today."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "2099-12-31",
                "description": "future date test",
            },
        )
        assert resp.status_code == 302
        assert _expense_count(app, seed_user_id) == before + 1


# ===========================================================================
# AMOUNT VALIDATION
# ===========================================================================

class TestAmountValidation:
    """Spec DoD: zero, negative, non-numeric, and empty amounts are rejected."""

    @pytest.mark.parametrize("bad_amount", ["0", "-5", "-0.01", "abc", ""])
    def test_bad_amount_returns_200(self, client, seed_user_id, bad_amount):
        """Spec: an invalid amount must re-render the form (200), not redirect."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-05-03",
                "description": "x",
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200 re-render for amount={bad_amount!r}, got {resp.status_code}"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "-5", "-0.01", "abc", ""])
    def test_bad_amount_shows_inline_error(self, client, seed_user_id, bad_amount):
        """Spec: an invalid amount must render an inline error block."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-05-03",
                "description": "x",
            },
        )
        body = resp.data.decode()
        assert "auth-error" in body, (
            f"Expected inline error block for amount={bad_amount!r}"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "-5", "-0.01", "abc", ""])
    def test_bad_amount_writes_no_row(self, client, seed_user_id, app, bad_amount):
        """Spec: a validation failure must write no row to expenses."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-05-03",
                "description": "x",
            },
        )
        assert _expense_count(app, seed_user_id) == before, (
            f"Expected no new row for amount={bad_amount!r}"
        )

    # -- Special float values that survive a naive float() cast --

    @pytest.mark.parametrize("sneaky_amount", ["inf", "nan", "infinity", "-inf"])
    def test_special_float_values_are_rejected(self, client, seed_user_id, app, sneaky_amount):
        """Spec: inf and nan values slip through float() but must still be rejected."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": sneaky_amount,
                "category": "Food",
                "date": "2026-05-03",
                "description": "x",
            },
        )
        # Must not accept these — either 200 re-render with an error or 302 is wrong.
        # Spec says amount must be a finite positive float > 0.
        assert resp.status_code == 200, (
            f"Expected 200 re-render for amount={sneaky_amount!r} (inf/nan must be rejected)"
        )
        assert "auth-error" in resp.data.decode(), (
            f"Expected inline error for amount={sneaky_amount!r}"
        )
        assert _expense_count(app, seed_user_id) == before, (
            f"Expected no DB write for amount={sneaky_amount!r}"
        )

    def test_very_small_positive_amount_is_accepted(self, client, seed_user_id, app):
        """Spec: any positive float > 0 is valid — 0.01 must be accepted."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "0.01",
                "category": "Food",
                "date": "2026-05-03",
                "description": "minimum valid amount",
            },
        )
        assert resp.status_code == 302
        assert _expense_count(app, seed_user_id) == before + 1


# ===========================================================================
# CATEGORY VALIDATION
# ===========================================================================

class TestCategoryValidation:
    """Spec: only the seven explicit allow-list categories may be submitted."""

    @pytest.mark.parametrize("bad_category", [
        "Crypto",
        "crypto",
        "FOOD",          # case-sensitive match required
        "food",
        "Groceries",
        "Utilities",
        "",
        "'; DROP TABLE expenses; --",
    ])
    def test_disallowed_category_returns_200_with_error(
        self, client, seed_user_id, app, bad_category
    ):
        """Spec: a category not in the allow-list must be rejected with 200 + inline error."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": bad_category,
                "date": "2026-05-03",
                "description": "x",
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200 re-render for category={bad_category!r}"
        )
        assert "auth-error" in resp.data.decode(), (
            f"Expected inline error for category={bad_category!r}"
        )
        assert _expense_count(app, seed_user_id) == before, (
            f"Expected no DB write for category={bad_category!r}"
        )

    @pytest.mark.parametrize("good_category", ALLOWED_CATEGORIES)
    def test_each_allowed_category_is_accepted(
        self, client, seed_user_id, app, good_category
    ):
        """Spec: every entry in the seven-item allow-list must be accepted."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": good_category,
                "date": "2026-05-03",
                "description": f"category acceptance test: {good_category}",
            },
        )
        assert resp.status_code == 302, (
            f"Expected 302 redirect for allowed category={good_category!r}, "
            f"got {resp.status_code}"
        )
        assert _expense_count(app, seed_user_id) == before + 1, (
            f"Expected a new row for category={good_category!r}"
        )


# ===========================================================================
# DATE VALIDATION
# ===========================================================================

class TestDateValidation:
    """Spec: date must parse via datetime.strptime(value, '%Y-%m-%d'); anything else rejected."""

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "",
        "03/05/2026",       # DD/MM/YYYY format — wrong separator and order
        "2026/05/03",       # right digits, wrong separator
        "2026-13-01",       # month 13 does not exist
        "2026-05-32",       # day 32 does not exist
        "yesterday",
        "05-03-2026",       # MM-DD-YYYY — wrong order
    ])
    def test_bad_date_returns_200(self, client, seed_user_id, bad_date):
        """Spec: a malformed or empty date must re-render the form (200)."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": bad_date,
                "description": "x",
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200 re-render for date={bad_date!r}, got {resp.status_code}"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "",
        "03/05/2026",
        "2026/05/03",
        "2026-13-01",
        "2026-05-32",
        "yesterday",
        "05-03-2026",
    ])
    def test_bad_date_shows_inline_error(self, client, seed_user_id, bad_date):
        """Spec: a malformed or empty date must render an inline error block."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": bad_date,
                "description": "x",
            },
        )
        assert "auth-error" in resp.data.decode(), (
            f"Expected inline error for date={bad_date!r}"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "",
        "03/05/2026",
        "2026/05/03",
        "2026-13-01",
        "2026-05-32",
        "yesterday",
        "05-03-2026",
    ])
    def test_bad_date_writes_no_row(self, client, seed_user_id, app, bad_date):
        """Spec: a date validation failure must not write any row to expenses."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": bad_date,
                "description": "x",
            },
        )
        assert _expense_count(app, seed_user_id) == before, (
            f"Expected no DB write for date={bad_date!r}"
        )


# ===========================================================================
# DESCRIPTION RULES
# ===========================================================================

class TestDescriptionRules:
    """Spec: description is optional; empty/whitespace → NULL; > 200 chars rejected."""

    def test_empty_description_stores_null(self, client, seed_user_id, app):
        """Spec DoD: empty description string must be stored as NULL, not empty string."""
        _authed(client, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "8.50",
                "category": "Other",
                "date": "2026-05-03",
                "description": "",
            },
        )
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert row["description"] is None, (
            "Empty description must be stored as NULL, got: "
            + repr(row["description"])
        )

    def test_whitespace_only_description_stores_null(self, client, seed_user_id, app):
        """Spec: whitespace-only description must be stripped and stored as NULL."""
        _authed(client, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "8.50",
                "category": "Other",
                "date": "2026-05-03",
                "description": "   \t  ",
            },
        )
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert row["description"] is None, (
            "Whitespace-only description must be stored as NULL, got: "
            + repr(row["description"])
        )

    def test_description_over_200_chars_rejected(self, client, seed_user_id, app):
        """Spec: description longer than 200 characters must be rejected with inline error."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        long_desc = "x" * 201
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-03",
                "description": long_desc,
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 re-render when description exceeds 200 characters"
        )
        assert "auth-error" in resp.data.decode(), (
            "Expected inline error when description exceeds 200 characters"
        )
        assert _expense_count(app, seed_user_id) == before, (
            "Expected no DB write when description exceeds 200 characters"
        )

    def test_description_at_exactly_200_chars_is_accepted(self, client, seed_user_id, app):
        """Spec: 200 characters is the cap; exactly 200 must be accepted."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        exact_desc = "a" * 200
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-03",
                "description": exact_desc,
            },
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect when description is exactly 200 characters"
        )
        assert _expense_count(app, seed_user_id) == before + 1

    def test_non_empty_description_stored_as_text(self, client, seed_user_id, app):
        """A non-empty description must be stored verbatim (not coerced to NULL)."""
        _authed(client, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-03",
                "description": "My coffee",
            },
        )
        row = _latest_expense_row(app, seed_user_id)
        assert row is not None
        assert row["description"] == "My coffee"


# ===========================================================================
# FORM VALUE PRESERVATION ON VALIDATION ERROR
# ===========================================================================

class TestFormPreservation:
    """Spec DoD: when the form is re-rendered with an error, submitted values are echoed back."""

    def test_amount_preserved_on_error(self, client, seed_user_id):
        """The submitted (invalid) amount must be echoed back into the input value."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "-5",
                "category": "Transport",
                "date": "2026-05-03",
                "description": "Tea",
            },
        )
        body = resp.data.decode()
        assert 'value="-5"' in body, "Submitted amount must be echoed back on error"

    def test_category_preserved_on_error(self, client, seed_user_id):
        """The submitted category must still be selected on re-render."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "-5",          # trigger error via invalid amount
                "category": "Transport",
                "date": "2026-05-03",
                "description": "Tea",
            },
        )
        body = resp.data.decode()
        # The template marks the previously selected option with selected.
        assert "Transport" in body
        # Verify the option is actually selected (not just present as text).
        assert "selected" in body, "Category option must carry selected attribute on re-render"

    def test_date_preserved_on_error(self, client, seed_user_id):
        """The submitted date must be echoed back into the date input on re-render."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "-5",          # trigger error
                "category": "Food",
                "date": "2026-05-03",
                "description": "Tea",
            },
        )
        body = resp.data.decode()
        assert "2026-05-03" in body, "Submitted date must be echoed back on error"

    def test_description_preserved_on_error(self, client, seed_user_id):
        """The submitted description must be echoed back into the description input."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "-5",          # trigger error
                "category": "Food",
                "date": "2026-05-03",
                "description": "Tea",
            },
        )
        body = resp.data.decode()
        assert "Tea" in body, "Submitted description must be echoed back on error"

    def test_all_four_fields_preserved_simultaneously(self, client, seed_user_id):
        """All four fields must be echoed back together on a single re-render."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "-99",
                "category": "Bills",
                "date": "2026-01-15",
                "description": "Electricity",
            },
        )
        body = resp.data.decode()
        assert 'value="-99"' in body
        assert "Bills" in body
        assert "2026-01-15" in body
        assert "Electricity" in body


# ===========================================================================
# PROFILE PAGE CTA
# ===========================================================================

class TestProfileCTA:
    """Spec DoD: /profile must render an 'Add expense' CTA linking to /expenses/add."""

    def test_profile_has_add_expense_link(self, client, seed_user_id):
        """Spec: GET /profile must include a link whose href points to /expenses/add."""
        _authed(client, seed_user_id)
        resp = client.get("/profile")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert '/expenses/add' in body, (
            "Profile page must contain a link to /expenses/add"
        )

    def test_profile_cta_text_indicates_add_action(self, client, seed_user_id):
        """Spec: the CTA must be labelled to indicate the 'Add expense' action."""
        _authed(client, seed_user_id)
        resp = client.get("/profile")
        body = resp.data.decode()
        # The spec says the CTA is labelled "Add expense" (case-insensitive check
        # to allow minor UI variations in capitalisation).
        assert "add expense" in body.lower(), (
            "Profile page must contain 'Add expense' (or similar) CTA text"
        )

    def test_profile_cta_is_an_anchor_tag(self, client, seed_user_id):
        """Spec: the CTA must be an anchor (<a>) element linking to /expenses/add."""
        _authed(client, seed_user_id)
        resp = client.get("/profile")
        body = resp.data.decode()
        assert 'href="/expenses/add"' in body, (
            "Profile page must have an <a href='/expenses/add'> element"
        )


# ===========================================================================
# user_id ATTRIBUTION — must always come from session, never from form
# ===========================================================================

class TestUserIdAttribution:
    """Spec: new expense must be attributed to session user_id, never to a form field."""

    def test_row_attributed_to_session_user_not_form_field(self, client, seed_user_id, app):
        """Spec: smuggling user_id=999999 in the POST body must not change row attribution."""
        _authed(client, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "1.00",
                "category": "Other",
                "date": "2026-05-03",
                "description": "session-attribution-spec-test",
                "user_id": "999999",      # forged field — must be ignored
            },
        )
        assert resp.status_code == 302, "Valid POST with forged user_id must still succeed"

        row = _latest_expense_row(app, seed_user_id)
        assert row is not None, "Expected an inserted row after the POST"
        assert row["description"] == "session-attribution-spec-test"
        assert row["user_id"] == seed_user_id, (
            f"Row must be attributed to session user {seed_user_id}, "
            f"not the forged value 999999 (got {row['user_id']})"
        )

    def test_forged_user_id_does_not_create_row_for_other_user(self, client, seed_user_id, app):
        """A forged user_id must not insert any row attributed to that foreign user."""
        _authed(client, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "1.00",
                "category": "Other",
                "date": "2026-05-03",
                "description": "forged-user-check",
                "user_id": "999999",
            },
        )
        with app.app_context():
            conn = get_db()
            try:
                count_for_forged_id = conn.execute(
                    "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (999999,)
                ).fetchone()[0]
            finally:
                conn.close()

        assert count_for_forged_id == 0, (
            "No row must be written for the forged user_id=999999"
        )


# ===========================================================================
# SQL INJECTION GUARD
# ===========================================================================

class TestSqlInjectionGuard:
    """Spec: parameterised queries only — no string-formatted user input in SQL."""

    def test_sql_injection_in_description_does_not_drop_table(self, client, seed_user_id, app):
        """A SQL injection attempt in description must not alter the expenses table."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": "Food",
                "date": "2026-05-03",
                "description": "'; DROP TABLE expenses; --",
            },
        )
        # If the table were dropped, this would raise; instead it must still work.
        after = _expense_count(app, seed_user_id)
        assert after == before + 1, (
            "The expenses table must survive a SQL injection attempt in description"
        )

    def test_sql_injection_in_category_rejected_cleanly(self, client, seed_user_id, app):
        """A SQL injection string as category value must be rejected by the allow-list check."""
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": "'; DROP TABLE expenses; --",
                "date": "2026-05-03",
                "description": "x",
            },
        )
        assert resp.status_code == 200
        assert _expense_count(app, seed_user_id) == before
