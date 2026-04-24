import math

import pytest

from database.queries import get_category_breakdown


SEED_TOTAL = 365.24
SEED_AMOUNTS = [120.00, 89.99, 45.00, 35.25, 35.00, 25.00, 15.00]


def test_seven_categories_for_seed_user(app, seed_user_id):
    result = get_category_breakdown(seed_user_id)
    assert len(result) == 7


def test_sorted_by_amount_desc(app, seed_user_id):
    result = get_category_breakdown(seed_user_id)
    assert result[0]["name"] == "Bills"
    assert result[0]["amount"] == pytest.approx(120.00)
    amounts = [row["amount"] for row in result]
    for prev, curr in zip(amounts, amounts[1:]):
        assert prev >= curr


def test_row_shape(app, seed_user_id):
    result = get_category_breakdown(seed_user_id)
    for row in result:
        assert set(row.keys()) == {"name", "amount", "pct"}
        assert isinstance(row["name"], str)
        assert isinstance(row["amount"], (float, int))
        assert isinstance(row["pct"], int)
        assert not isinstance(row["pct"], bool)


def test_pct_sums_to_100(app, seed_user_id):
    result = get_category_breakdown(seed_user_id)
    assert sum(r["pct"] for r in result) == 100


def test_pct_remainder_on_largest(app, seed_user_id):
    result = get_category_breakdown(seed_user_id)
    floored = [math.floor(a / SEED_TOTAL * 100) for a in SEED_AMOUNTS]
    remainder = 100 - sum(floored)
    expected_bills_pct = math.floor(120.00 / SEED_TOTAL * 100) + remainder
    assert result[0]["name"] == "Bills"
    assert result[0]["pct"] == expected_bills_pct


def test_empty_for_unknown_user(app):
    assert get_category_breakdown(99999) == []
