from datetime import datetime

import pytest

from database.db import get_db


@pytest.fixture(autouse=True)
def _isolate_inserts(app):
    """Roll back any expense rows this test inserts.

    The shared seed DB persists across tests, so without this the legacy
    Step 5 / 6 suites see extra rows and break their fixed counts/totals.
    """
    conn = get_db()
    try:
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM expenses").fetchone()[0]
    finally:
        conn.close()
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM expenses WHERE id > ?", (max_id,))
        conn.commit()
    finally:
        conn.close()


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _count_expenses(user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _latest_expense(user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Auth gate                                                           #
# ------------------------------------------------------------------ #

def test_get_requires_login(client):
    response = client.get("/expenses/add")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_requires_login_and_writes_no_row(client, seed_user_id):
    before = _count_expenses(seed_user_id)
    response = client.post(
        "/expenses/add",
        data={"amount": "50", "category": "Food", "date": "2026-05-03"},
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert _count_expenses(seed_user_id) == before


# ------------------------------------------------------------------ #
# GET behaviour                                                       #
# ------------------------------------------------------------------ #

def test_get_renders_form_with_today_default(client, seed_user_id):
    _login(client, seed_user_id)
    response = client.get("/expenses/add")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    today = datetime.now().strftime("%Y-%m-%d")
    assert f'value="{today}"' in body
    assert 'name="amount"' in body
    assert 'name="category"' in body
    assert 'name="description"' in body


# ------------------------------------------------------------------ #
# Successful POST                                                     #
# ------------------------------------------------------------------ #

def test_post_valid_inserts_and_redirects(client, seed_user_id):
    _login(client, seed_user_id)
    before = _count_expenses(seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": "49.99",
            "category": "Food",
            "date": "2026-05-03",
            "description": "Tea",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    assert _count_expenses(seed_user_id) == before + 1

    row = _latest_expense(seed_user_id)
    assert row["user_id"] == seed_user_id
    assert float(row["amount"]) == pytest.approx(49.99)
    assert row["category"] == "Food"
    assert row["date"] == "2026-05-03"
    assert row["description"] == "Tea"


def test_new_expense_visible_on_profile(client, seed_user_id):
    _login(client, seed_user_id)
    client.post(
        "/expenses/add",
        data={
            "amount": "123.45",
            "category": "Shopping",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Visible-marker-expense",
        },
    )
    body = client.get("/profile?range=all").get_data(as_text=True)
    assert "Visible-marker-expense" in body
    assert "123.45" in body


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("bad_amount", ["0", "-5", "abc", ""])
def test_invalid_amount_rejected(client, seed_user_id, bad_amount):
    _login(client, seed_user_id)
    before = _count_expenses(seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-05-03",
            "description": "x",
        },
    )
    assert response.status_code == 200
    assert "auth-error" in response.get_data(as_text=True)
    assert _count_expenses(seed_user_id) == before


def test_invalid_category_rejected(client, seed_user_id):
    _login(client, seed_user_id)
    before = _count_expenses(seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": "10",
            "category": "Crypto",
            "date": "2026-05-03",
            "description": "x",
        },
    )
    assert response.status_code == 200
    assert "auth-error" in response.get_data(as_text=True)
    assert _count_expenses(seed_user_id) == before


@pytest.mark.parametrize("bad_date", ["not-a-date", ""])
def test_invalid_date_rejected(client, seed_user_id, bad_date):
    _login(client, seed_user_id)
    before = _count_expenses(seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": "10",
            "category": "Food",
            "date": bad_date,
            "description": "x",
        },
    )
    assert response.status_code == 200
    assert "auth-error" in response.get_data(as_text=True)
    assert _count_expenses(seed_user_id) == before


def test_empty_description_stores_null(client, seed_user_id):
    _login(client, seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": "8.50",
            "category": "Other",
            "date": "2026-05-03",
            "description": "   ",
        },
    )
    assert response.status_code == 302
    row = _latest_expense(seed_user_id)
    assert row["description"] is None


# ------------------------------------------------------------------ #
# Error round-trip preserves form values                              #
# ------------------------------------------------------------------ #

def test_form_values_preserved_on_error(client, seed_user_id):
    _login(client, seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": "-5",
            "category": "Transport",
            "date": "2026-05-03",
            "description": "Tea",
        },
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'value="-5"' in body
    assert 'value="Tea"' in body
    assert 'value="2026-05-03"' in body
    assert 'value="Transport" selected' in body


# ------------------------------------------------------------------ #
# Profile page CTA                                                    #
# ------------------------------------------------------------------ #

def test_profile_cta_links_to_add(client, seed_user_id):
    _login(client, seed_user_id)
    body = client.get("/profile").get_data(as_text=True)
    assert 'href="/expenses/add"' in body


# ------------------------------------------------------------------ #
# user_id is taken from session, never from form                      #
# ------------------------------------------------------------------ #

def test_user_id_from_session_not_form(client, seed_user_id):
    _login(client, seed_user_id)
    response = client.post(
        "/expenses/add",
        data={
            "amount": "1.00",
            "category": "Other",
            "date": "2026-05-03",
            "description": "session-attribution-test",
            "user_id": "999999",
        },
    )
    assert response.status_code == 302
    row = _latest_expense(seed_user_id)
    assert row["description"] == "session-attribution-test"
    assert row["user_id"] == seed_user_id
