# Spec: Step 8 — Edit Expenses
#
# Behaviors under test (all derived from the spec, not the implementation):
#
#   AUTH GATE
#   - GET /expenses/<id>/edit without a session → 302 to /login
#   - POST /expenses/<id>/edit without a session → 302 to /login AND no row mutated
#
#   OWNERSHIP
#   - GET on a non-existent id → 404
#   - GET on another user's expense id → 404
#   - The 404 body must not leak the other user's expense values
#   - POST on another user's expense id → 404 AND target row unchanged
#
#   GET /expenses/<id>/edit (owner)
#   - Form is pre-filled with the row's current amount/category/date/description
#   - NULL description renders as empty string, never literal "None"
#
#   SUCCESSFUL POST
#   - Valid POST updates exactly one row (matching id + session user_id)
#   - Responds 302 → /profile
#   - stats.transaction_count is unchanged
#   - stats.total_spent changes by the delta
#   - Profile page shows the new values
#
#   AMOUNT / CATEGORY / DATE / DESCRIPTION VALIDATION
#   - Reuses the Step 7 contract; bad input → 200 re-render + auth-error + no change
#   - Empty / whitespace-only description stored as NULL
#   - Description > 200 chars rejected
#
#   FORM VALUE PRESERVATION
#   - On validation error, the previously typed values are echoed back,
#     NOT the original database values
#
#   USER_ID ATTRIBUTION
#   - A forged user_id form field is ignored — the row's user_id is unchanged
#
#   PROFILE PAGE
#   - GET /profile renders an edit link href="/expenses/<id>/edit" per row
#
#   get_recent_transactions
#   - Each per-row dict now includes an int "id" key

import pytest
from werkzeug.security import generate_password_hash

from database.db import get_db
from database import queries


# ---------------------------------------------------------------------------
# Isolation — snapshot rows before each test, restore/delete after
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(app):
    """Snapshot the existing expenses and users; restore them after the test.

    This protects seeded rows from mutation (UPDATE) and removes any rows
    inserted during the test (extra users, target expense rows).
    """
    with app.app_context():
        conn = get_db()
        try:
            expense_snapshot = conn.execute(
                "SELECT id, user_id, amount, category, date, description "
                "FROM expenses"
            ).fetchall()
            user_snapshot_ids = [
                row["id"]
                for row in conn.execute("SELECT id FROM users").fetchall()
            ]
            max_expense_id = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM expenses"
            ).fetchone()[0]
        finally:
            conn.close()

    yield

    with app.app_context():
        conn = get_db()
        try:
            conn.execute(
                "DELETE FROM expenses WHERE id > ?", (max_expense_id,)
            )
            for row in expense_snapshot:
                conn.execute(
                    "UPDATE expenses SET user_id = ?, amount = ?, "
                    "category = ?, date = ?, description = ? WHERE id = ?",
                    (
                        row["user_id"], row["amount"], row["category"],
                        row["date"], row["description"], row["id"],
                    ),
                )
            placeholders = ",".join("?" * len(user_snapshot_ids))
            conn.execute(
                f"DELETE FROM users WHERE id NOT IN ({placeholders})",
                user_snapshot_ids,
            )
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


def _make_user(app, email="other@spendly.com", name="Other User"):
    """Insert a second user and return their id."""
    with app.app_context():
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash("pw123456")),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def _make_expense(app, user_id, amount=10.0, category="Food",
                  date="2026-05-03", description="seed"):
    """Insert an expense row and return its id."""
    with app.app_context():
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, date, description),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def _get_expense_row(app, expense_id):
    with app.app_context():
        conn = get_db()
        try:
            return conn.execute(
                "SELECT id, user_id, amount, category, date, description "
                "FROM expenses WHERE id = ?",
                (expense_id,),
            ).fetchone()
        finally:
            conn.close()


def _expense_count(app, user_id):
    with app.app_context():
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        finally:
            conn.close()


VALID_FORM = {
    "amount": "99.99",
    "category": "Bills",
    "date": "2026-05-12",
    "description": "Updated",
}

ALLOWED_CATEGORIES = (
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
)


# ===========================================================================
# AUTH GATE
# ===========================================================================

class TestAuthGate:
    """Spec DoD: both GET and POST require an authenticated session."""

    def test_get_without_session_redirects_to_login(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_without_session_redirects_to_login(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        resp = client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_without_session_writes_no_change(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="original",
        )
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        row = _get_expense_row(app, expense_id)
        assert row["amount"] == pytest.approx(10.0)
        assert row["category"] == "Food"
        assert row["date"] == "2026-04-01"
        assert row["description"] == "original"


# ===========================================================================
# OWNERSHIP
# ===========================================================================

class TestOwnership:
    """Spec: an id that does not exist OR belongs to another user → 404."""

    def test_get_unknown_id_returns_404(self, client, seed_user_id):
        _authed(client, seed_user_id)
        resp = client.get("/expenses/999999/edit")
        assert resp.status_code == 404

    def test_post_unknown_id_returns_404(self, client, seed_user_id):
        _authed(client, seed_user_id)
        resp = client.post("/expenses/999999/edit", data=VALID_FORM)
        assert resp.status_code == 404

    def test_get_another_users_id_returns_404(self, client, app, seed_user_id):
        other_id = _make_user(app)
        other_expense = _make_expense(
            app, other_id, amount=42.42, category="Health",
            date="2026-03-15", description="other-user-secret-description",
        )
        _authed(client, seed_user_id)
        resp = client.get(f"/expenses/{other_expense}/edit")
        assert resp.status_code == 404

    def test_get_another_users_id_does_not_leak_values(self, client, app, seed_user_id):
        other_id = _make_user(app)
        other_expense = _make_expense(
            app, other_id, amount=42.42, category="Health",
            date="2026-03-15", description="other-user-secret-description",
        )
        _authed(client, seed_user_id)
        resp = client.get(f"/expenses/{other_expense}/edit")
        body = resp.data.decode()
        assert "other-user-secret-description" not in body
        assert "42.42" not in body

    def test_post_another_users_id_returns_404(self, client, app, seed_user_id):
        other_id = _make_user(app)
        other_expense = _make_expense(
            app, other_id, amount=42.42, category="Health",
            date="2026-03-15", description="other-user-secret-description",
        )
        _authed(client, seed_user_id)
        resp = client.post(f"/expenses/{other_expense}/edit", data=VALID_FORM)
        assert resp.status_code == 404

    def test_post_another_users_id_does_not_mutate_row(self, client, app, seed_user_id):
        other_id = _make_user(app)
        other_expense = _make_expense(
            app, other_id, amount=42.42, category="Health",
            date="2026-03-15", description="other-user-secret-description",
        )
        _authed(client, seed_user_id)
        client.post(f"/expenses/{other_expense}/edit", data=VALID_FORM)
        row = _get_expense_row(app, other_expense)
        assert row["amount"] == pytest.approx(42.42)
        assert row["category"] == "Health"
        assert row["date"] == "2026-03-15"
        assert row["description"] == "other-user-secret-description"
        assert row["user_id"] == other_id


# ===========================================================================
# GET /expenses/<id>/edit (owner)
# ===========================================================================

class TestGetForm:
    """Spec DoD: the form is pre-filled with the row's current values."""

    def test_get_returns_200(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 200

    def test_get_prefills_amount(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=12.50, category="Food",
            date="2026-02-01", description="lunch",
        )
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        assert "12.50" in body

    def test_get_prefills_category_selected(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Transport",
            date="2026-02-01", description="bus",
        )
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        assert 'value="Transport" selected' in body or \
               'selected>Transport' in body

    def test_get_prefills_date(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-02-01", description="x",
        )
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        assert 'value="2026-02-01"' in body

    def test_get_prefills_description(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-02-01", description="lunch at cafe",
        )
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        assert "lunch at cafe" in body

    def test_get_null_description_renders_empty_not_none(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-02-01", description=None,
        )
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        # The literal string "None" must not leak into the description input value.
        import re
        # Find the description input's value attribute and ensure it is empty.
        match = re.search(
            r'name="description"[^>]*value="([^"]*)"|value="([^"]*)"[^>]*name="description"',
            body,
        )
        assert match is not None, "description input not found"
        value = next(g for g in match.groups() if g is not None)
        assert value == "", f"Expected empty description, got {value!r}"

    def test_get_renders_all_seven_categories(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        for category in ALLOWED_CATEGORIES:
            assert category in body

    def test_get_renders_pkr_label(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        body = client.get(f"/expenses/{expense_id}/edit").data.decode()
        assert "PKR" in body


# ===========================================================================
# SUCCESSFUL POST
# ===========================================================================

class TestSuccessfulPost:
    """Spec DoD: valid POST updates exactly one row and redirects to /profile."""

    def test_valid_post_returns_302(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        assert resp.status_code == 302

    def test_valid_post_redirects_to_profile(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        assert "/profile" in resp.headers["Location"]

    def test_valid_post_updates_amount(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        row = _get_expense_row(app, expense_id)
        assert row["amount"] == pytest.approx(99.99)

    def test_valid_post_updates_category(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        row = _get_expense_row(app, expense_id)
        assert row["category"] == "Bills"

    def test_valid_post_updates_date(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        row = _get_expense_row(app, expense_id)
        assert row["date"] == "2026-05-12"

    def test_valid_post_updates_description(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        row = _get_expense_row(app, expense_id)
        assert row["description"] == "Updated"

    def test_valid_post_does_not_change_row_count(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        assert _expense_count(app, seed_user_id) == before

    def test_valid_post_does_not_change_user_id(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        client.post(f"/expenses/{expense_id}/edit", data=VALID_FORM)
        row = _get_expense_row(app, expense_id)
        assert row["user_id"] == seed_user_id

    def test_edited_values_visible_on_profile(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-05-12", description="orig",
        )
        _authed(client, seed_user_id)
        unique_desc = "Spec-marker-edited-expense-08"
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "55.55",
                "category": "Bills",
                "date": "2026-05-12",
                "description": unique_desc,
            },
        )
        body = client.get("/profile?range=all").data.decode()
        assert unique_desc in body


# ===========================================================================
# AMOUNT VALIDATION
# ===========================================================================

class TestAmountValidation:
    """Spec: reject zero, negative, non-numeric, empty, NaN, inf."""

    @pytest.mark.parametrize("bad_amount", ["0", "-5", "abc", "", "nan", "inf", "-inf"])
    def test_bad_amount_returns_200(self, client, app, seed_user_id, bad_amount):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-05-12",
                "description": "x",
            },
        )
        assert resp.status_code == 200, f"Expected 200 for amount={bad_amount!r}"

    @pytest.mark.parametrize("bad_amount", ["0", "-5", "abc", "", "nan", "inf"])
    def test_bad_amount_writes_no_change(self, client, app, seed_user_id, bad_amount):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Bills",
                "date": "2026-05-12",
                "description": "should-not-save",
            },
        )
        row = _get_expense_row(app, expense_id)
        assert row["amount"] == pytest.approx(10.0)
        assert row["category"] == "Food"
        assert row["date"] == "2026-04-01"
        assert row["description"] == "orig"

    @pytest.mark.parametrize("bad_amount", ["0", "-5", "abc", "", "nan", "inf"])
    def test_bad_amount_shows_inline_error(self, client, app, seed_user_id, bad_amount):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-05-12",
                "description": "x",
            },
        )
        assert "auth-error" in resp.data.decode()


# ===========================================================================
# CATEGORY VALIDATION
# ===========================================================================

class TestCategoryValidation:
    """Spec: only the seven allow-listed categories accepted."""

    @pytest.mark.parametrize("bad_category", [
        "Crypto", "crypto", "FOOD", "food", "Groceries", "",
        "'; DROP TABLE expenses; --",
    ])
    def test_disallowed_category_rejected(self, client, app, seed_user_id, bad_category):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": bad_category,
                "date": "2026-05-12",
                "description": "x",
            },
        )
        assert resp.status_code == 200
        assert "auth-error" in resp.data.decode()

    @pytest.mark.parametrize("good_category", ALLOWED_CATEGORIES)
    def test_each_allowed_category_accepted(self, client, app, seed_user_id, good_category):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "5.00",
                "category": good_category,
                "date": "2026-05-12",
                "description": f"category-acceptance-{good_category}",
            },
        )
        assert resp.status_code == 302
        row = _get_expense_row(app, expense_id)
        assert row["category"] == good_category


# ===========================================================================
# DATE VALIDATION
# ===========================================================================

class TestDateValidation:
    """Spec: date must parse as YYYY-MM-DD; anything else rejected."""

    @pytest.mark.parametrize("bad_date", [
        "not-a-date", "", "03/05/2026", "2026/05/03",
        "2026-13-01", "2026-05-32",
    ])
    def test_bad_date_rejected(self, client, app, seed_user_id, bad_date):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": bad_date,
                "description": "x",
            },
        )
        assert resp.status_code == 200
        assert "auth-error" in resp.data.decode()
        # Ensure no change.
        row = _get_expense_row(app, expense_id)
        assert row["date"] == "2026-04-01"


# ===========================================================================
# DESCRIPTION RULES
# ===========================================================================

class TestDescriptionRules:
    """Spec: optional; empty/whitespace → NULL; > 200 chars rejected."""

    def test_empty_description_stores_null(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-12",
                "description": "",
            },
        )
        row = _get_expense_row(app, expense_id)
        assert row["description"] is None

    def test_whitespace_only_description_stores_null(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-12",
                "description": "   \t  ",
            },
        )
        row = _get_expense_row(app, expense_id)
        assert row["description"] is None

    def test_description_over_200_chars_rejected(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-12",
                "description": "x" * 201,
            },
        )
        assert resp.status_code == 200
        assert "auth-error" in resp.data.decode()
        row = _get_expense_row(app, expense_id)
        assert row["description"] == "orig"

    def test_description_at_exactly_200_chars_accepted(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-12",
                "description": "a" * 200,
            },
        )
        assert resp.status_code == 302
        row = _get_expense_row(app, expense_id)
        assert row["description"] == "a" * 200


# ===========================================================================
# FORM VALUE PRESERVATION ON VALIDATION ERROR
# ===========================================================================

class TestFormPreservation:
    """Spec DoD: typed (invalid) values are echoed back, NOT the original DB values."""

    def test_typed_amount_preserved_not_db_amount(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "-5",          # invalid → trigger re-render
                "category": "Transport",
                "date": "2026-06-15",
                "description": "typed-desc",
            },
        )
        body = resp.data.decode()
        assert 'value="-5"' in body, "Typed amount must be echoed back"
        # The original DB amount (10.00 / 10.0) must NOT appear as the amount
        # value attribute.
        assert 'value="10.00"' not in body
        assert 'value="10.0"' not in body

    def test_typed_category_preserved(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "-5",
                "category": "Transport",
                "date": "2026-06-15",
                "description": "typed-desc",
            },
        )
        body = resp.data.decode()
        assert 'value="Transport" selected' in body or \
               'selected>Transport' in body
        # The DB's "Food" must NOT be marked selected.
        assert 'value="Food" selected' not in body
        assert 'selected>Food' not in body

    def test_typed_date_preserved(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "-5",
                "category": "Transport",
                "date": "2026-06-15",
                "description": "typed-desc",
            },
        )
        body = resp.data.decode()
        assert 'value="2026-06-15"' in body
        assert 'value="2026-04-01"' not in body

    def test_typed_description_preserved(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-04-01", description="orig",
        )
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "-5",
                "category": "Transport",
                "date": "2026-06-15",
                "description": "typed-desc",
            },
        )
        body = resp.data.decode()
        assert "typed-desc" in body
        assert 'value="orig"' not in body


# ===========================================================================
# USER_ID ATTRIBUTION
# ===========================================================================

class TestUserIdAttribution:
    """Spec: a forged user_id form field must be ignored."""

    def test_forged_user_id_field_does_not_change_owner(self, client, app, seed_user_id):
        other_id = _make_user(app)
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "33.33",
                "category": "Food",
                "date": "2026-05-12",
                "description": "forged-attribution",
                "user_id": str(other_id),     # forged — must be ignored
            },
        )
        assert resp.status_code == 302
        row = _get_expense_row(app, expense_id)
        assert row["user_id"] == seed_user_id, (
            f"Row owner must remain {seed_user_id}, got {row['user_id']}"
        )


# ===========================================================================
# PROFILE PAGE EDIT LINK
# ===========================================================================

class TestProfileEditLink:
    """Spec: /profile renders an edit link href='/expenses/<id>/edit' per row."""

    def test_profile_renders_edit_link_for_each_row(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-05-12", description="row-with-edit-link",
        )
        _authed(client, seed_user_id)
        body = client.get("/profile?range=all").data.decode()
        assert f'href="/expenses/{expense_id}/edit"' in body, (
            f"Profile must contain edit link for expense id {expense_id}"
        )


# ===========================================================================
# get_recent_transactions returns "id" key
# ===========================================================================

class TestRecentTransactionsIdKey:
    """Spec: each per-row dict now includes an int id key."""

    def test_get_recent_transactions_includes_id(self, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-05-12", description="id-key-test",
        )
        with app.app_context():
            rows = queries.get_recent_transactions(
                seed_user_id, limit=50, period="all",
            )
        match = next((r for r in rows if r.get("description") == "id-key-test"), None)
        assert match is not None, "Inserted row missing from get_recent_transactions"
        assert "id" in match
        assert isinstance(match["id"], int)
        assert match["id"] == expense_id


# ===========================================================================
# SQL INJECTION GUARD
# ===========================================================================

class TestSqlInjectionGuard:
    """Spec: parameterised queries only — injection in description is harmless text."""

    def test_sql_injection_in_description_does_not_drop_table(
        self, client, app, seed_user_id
    ):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "5.00",
                "category": "Food",
                "date": "2026-05-12",
                "description": "'; DROP TABLE expenses; --",
            },
        )
        # Table must still exist — a follow-up read must succeed.
        with app.app_context():
            conn = get_db()
            try:
                count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            finally:
                conn.close()
        assert count >= 1
