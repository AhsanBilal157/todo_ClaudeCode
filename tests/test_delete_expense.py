# Spec: Step 9 — Delete Expense
#
# Behaviors under test (all derived from the spec, not the implementation):
#
#   AUTH GATE
#   - POST /expenses/<id>/delete without a session → 302 to /login,
#     and the target row still exists
#
#   METHOD
#   - GET /expenses/<id>/delete → 405 (route is POST-only), row still exists
#
#   OWNERSHIP
#   - POST on a non-existent id → 404
#   - POST on another user's expense id → 404 AND that row survives unchanged
#
#   SUCCESSFUL DELETE
#   - Owner POST → 302 to /profile
#   - The target row is removed; the user's expense count drops by exactly 1
#   - The user's other rows are untouched
#
#   PROFILE PAGE
#   - After a delete, /profile no longer shows the deleted row's description
#   - Each transactions row renders a POST delete form guarded by confirm()

import pytest
from werkzeug.security import generate_password_hash

from database.db import get_db


# ---------------------------------------------------------------------------
# Isolation — snapshot rows before each test, restore after (delete-safe)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(app):
    """Snapshot expenses and users; fully restore them after the test.

    Unlike a plain insert-rollback fixture this one is delete-safe: any
    snapshotted expense row that the test removed is re-inserted with its
    original id, so a DELETE in one test cannot leak into the next.
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
            # Drop any rows the test inserted.
            conn.execute(
                "DELETE FROM expenses WHERE id > ?", (max_expense_id,)
            )
            # Restore every snapshotted row: re-insert it if the test deleted
            # it, otherwise reset its columns to the original values.
            for row in expense_snapshot:
                conn.execute(
                    "INSERT INTO expenses "
                    "(id, user_id, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "user_id = excluded.user_id, amount = excluded.amount, "
                    "category = excluded.category, date = excluded.date, "
                    "description = excluded.description",
                    (
                        row["id"], row["user_id"], row["amount"],
                        row["category"], row["date"], row["description"],
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


# ===========================================================================
# AUTH GATE
# ===========================================================================

class TestAuthGate:
    """Spec DoD: POST requires an authenticated session."""

    def test_post_without_session_redirects_to_login(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_without_session_deletes_no_row(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        client.post(f"/expenses/{expense_id}/delete")
        assert _get_expense_row(app, expense_id) is not None


# ===========================================================================
# METHOD — route is POST-only
# ===========================================================================

class TestMethodNotAllowed:
    """Spec DoD: a GET to the delete route must return 405 and delete nothing."""

    def test_get_returns_405(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.get(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 405

    def test_get_deletes_no_row(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        client.get(f"/expenses/{expense_id}/delete")
        assert _get_expense_row(app, expense_id) is not None


# ===========================================================================
# OWNERSHIP
# ===========================================================================

class TestOwnership:
    """Spec: a missing id OR another user's id → 404, with no deletion."""

    def test_post_unknown_id_returns_404(self, client, seed_user_id):
        _authed(client, seed_user_id)
        resp = client.post("/expenses/999999/delete")
        assert resp.status_code == 404

    def test_post_another_users_id_returns_404(self, client, app, seed_user_id):
        other_id = _make_user(app)
        other_expense = _make_expense(
            app, other_id, amount=42.42, category="Health",
            date="2026-03-15", description="other-user-row",
        )
        _authed(client, seed_user_id)
        resp = client.post(f"/expenses/{other_expense}/delete")
        assert resp.status_code == 404

    def test_post_another_users_id_does_not_delete_row(self, client, app, seed_user_id):
        other_id = _make_user(app)
        other_expense = _make_expense(
            app, other_id, amount=42.42, category="Health",
            date="2026-03-15", description="other-user-row",
        )
        _authed(client, seed_user_id)
        client.post(f"/expenses/{other_expense}/delete")
        row = _get_expense_row(app, other_expense)
        assert row is not None
        assert row["user_id"] == other_id
        assert row["amount"] == pytest.approx(42.42)
        assert row["description"] == "other-user-row"


# ===========================================================================
# SUCCESSFUL DELETE
# ===========================================================================

class TestSuccessfulDelete:
    """Spec DoD: owner POST removes exactly that row and redirects to /profile."""

    def test_valid_delete_returns_302(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302

    def test_valid_delete_redirects_to_profile(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        resp = client.post(f"/expenses/{expense_id}/delete")
        assert "/profile" in resp.headers["Location"]

    def test_valid_delete_removes_the_row(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        client.post(f"/expenses/{expense_id}/delete")
        assert _get_expense_row(app, expense_id) is None

    def test_valid_delete_drops_count_by_one(self, client, app, seed_user_id):
        expense_id = _make_expense(app, seed_user_id)
        _authed(client, seed_user_id)
        before = _expense_count(app, seed_user_id)
        client.post(f"/expenses/{expense_id}/delete")
        assert _expense_count(app, seed_user_id) == before - 1


# ===========================================================================
# ONLY ONE ROW REMOVED
# ===========================================================================

class TestOnlyOneRowRemoved:
    """Spec DoD: deleting one expense leaves the user's other rows intact."""

    def test_other_rows_survive(self, client, app, seed_user_id):
        first = _make_expense(app, seed_user_id, description="keep-first")
        middle = _make_expense(app, seed_user_id, description="delete-middle")
        last = _make_expense(app, seed_user_id, description="keep-last")
        seed_rows = _expense_count(app, seed_user_id)

        _authed(client, seed_user_id)
        client.post(f"/expenses/{middle}/delete")

        assert _get_expense_row(app, middle) is None
        assert _get_expense_row(app, first) is not None
        assert _get_expense_row(app, last) is not None
        assert _expense_count(app, seed_user_id) == seed_rows - 1


# ===========================================================================
# PROFILE PAGE REFLECTS THE DELETE
# ===========================================================================

class TestProfileReflectsDelete:
    """Spec DoD: after a delete the row no longer surfaces on /profile."""

    def test_deleted_row_gone_from_profile(self, client, app, seed_user_id):
        unique_desc = "Spec-marker-delete-expense-09"
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-05-12", description=unique_desc,
        )
        _authed(client, seed_user_id)

        before = client.get("/profile?range=all").data.decode()
        assert unique_desc in before

        client.post(f"/expenses/{expense_id}/delete")

        after = client.get("/profile?range=all").data.decode()
        assert unique_desc not in after


# ===========================================================================
# PROFILE DELETE CONTROL
# ===========================================================================

class TestProfileDeleteControl:
    """Spec DoD: each row renders a POST delete form guarded by confirm()."""

    def test_profile_renders_delete_form_for_row(self, client, app, seed_user_id):
        expense_id = _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-05-12", description="row-with-delete-form",
        )
        _authed(client, seed_user_id)
        body = client.get("/profile?range=all").data.decode()
        assert f'action="/expenses/{expense_id}/delete"' in body
        assert 'method="POST"' in body or 'method="post"' in body

    def test_delete_form_has_confirm_guard(self, client, app, seed_user_id):
        _make_expense(
            app, seed_user_id, amount=10.0, category="Food",
            date="2026-05-12", description="row-with-confirm-guard",
        )
        _authed(client, seed_user_id)
        body = client.get("/profile?range=all").data.decode()
        assert "confirm(" in body
