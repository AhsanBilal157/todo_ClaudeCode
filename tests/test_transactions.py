from database.db import get_db
from database.queries import get_recent_transactions


def test_returns_eight_rows_for_seed_user(seed_user_id, app):
    rows = get_recent_transactions(seed_user_id)
    assert len(rows) == 8


def test_ordered_newest_first(seed_user_id, app):
    rows = get_recent_transactions(seed_user_id)
    assert rows[0]["date"] == "Apr 15, 2026"
    assert rows[-1]["date"] == "Apr 01, 2026"


def test_row_shape(seed_user_id, app):
    rows = get_recent_transactions(seed_user_id)
    assert rows, "expected seeded rows"
    expected_keys = {"date", "description", "category", "amount"}
    for row in rows:
        assert set(row.keys()) == expected_keys
        assert isinstance(row["date"], str)
        assert isinstance(row["description"], str)
        assert isinstance(row["category"], str)
        assert isinstance(row["amount"], float)


def test_limit_respected(seed_user_id, app):
    rows = get_recent_transactions(seed_user_id, limit=3)
    assert len(rows) == 3


def test_empty_for_unknown_user(seed_user_id, app):
    assert get_recent_transactions(99999) == []


def test_empty_for_user_with_no_expenses(seed_user_id, app):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("No Expenses", "noexpenses@spendly.test", "x"),
        )
        new_user_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    try:
        assert get_recent_transactions(new_user_id) == []
    finally:
        cleanup = get_db()
        try:
            cleanup.execute("DELETE FROM users WHERE id = ?", (new_user_id,))
            cleanup.commit()
        finally:
            cleanup.close()
