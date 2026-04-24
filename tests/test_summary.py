import re

import pytest

from database.db import get_db
from database.queries import get_user_by_id, get_summary_stats


def test_get_user_by_id_returns_dict_for_seed_user(seed_user_id):
    result = get_user_by_id(seed_user_id)
    assert isinstance(result, dict)
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert isinstance(result["member_since"], str)
    assert (
        re.match(r"^[A-Z][a-z]+ \d{4}$", result["member_since"])
        or result["member_since"] == "—"
    )


def test_get_user_by_id_returns_none_for_unknown(app):
    assert get_user_by_id(99999) is None


def test_get_user_by_id_omits_password_hash(seed_user_id):
    result = get_user_by_id(seed_user_id)
    assert result is not None
    assert "password_hash" not in result


def test_summary_stats_for_seed_user(seed_user_id):
    stats = get_summary_stats(seed_user_id)
    assert stats["total_spent"] == pytest.approx(365.24)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_summary_stats_empty_user(app):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Empty User", "empty@spendly.com", "x"),
        )
        new_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    try:
        stats = get_summary_stats(new_id)
        assert stats["total_spent"] == 0 or stats["total_spent"] == 0.0
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—"
    finally:
        cleanup = get_db()
        try:
            cleanup.execute("DELETE FROM users WHERE id = ?", (new_id,))
            cleanup.commit()
        finally:
            cleanup.close()
