"""Profile-page query helpers backed by raw sqlite3 via get_db().

All functions filter by user_id and use parameterised queries only.
Each opens one connection and closes it in a finally block.
"""

from database.db import get_db


def get_user_by_id(user_id):
    """Return {'id', 'name', 'email', 'member_since'} for user_id, or None.

    `member_since` is formatted as "Month YYYY" (e.g. "January 2026"),
    or "—" when created_at is NULL or unparseable.
    """
    raise NotImplementedError("Implemented in Phase B by summary-stats subagent")


def get_summary_stats(user_id):
    """Return {'total_spent': float, 'transaction_count': int, 'top_category': str}.

    Empty-state returns {'total_spent': 0.0, 'transaction_count': 0, 'top_category': '—'}.
    """
    raise NotImplementedError("Implemented in Phase B by summary-stats subagent")


def get_recent_transactions(user_id, limit=10):
    """Return list of {'date', 'description', 'category', 'amount'} dicts.

    Ordered newest date first, tiebreak by id DESC. Date formatted 'Mon DD, YYYY'.
    Empty list when user has no expenses.
    """
    raise NotImplementedError("Implemented in Phase B by transactions subagent")


def get_category_breakdown(user_id):
    """Return list of {'name', 'amount', 'pct'} dicts sorted by amount DESC.

    `pct` is an integer; percentages sum to exactly 100 with any rounding
    remainder absorbed by the largest-amount category. Empty list when
    the user has no expenses.
    """
    raise NotImplementedError("Implemented in Phase B by breakdown subagent")
