"""Profile-page query helpers backed by raw sqlite3 via get_db().

All functions filter by user_id and use parameterised queries only.
Each opens one connection and closes it in a finally block.
"""

import math
from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    """Return {'id', 'name', 'email', 'member_since'} for user_id, or None.

    `member_since` is formatted as "Month YYYY" (e.g. "January 2026"),
    or "—" when created_at is NULL or unparseable.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    member_since = "—"
    created_at = row["created_at"]
    if created_at:
        try:
            dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            member_since = f"{dt:%B %Y}"
        except ValueError:
            member_since = "—"

    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "member_since": member_since,
    }


def get_summary_stats(user_id):
    """Return {'total_spent': float, 'transaction_count': int, 'top_category': str}.

    Empty-state returns {'total_spent': 0.0, 'transaction_count': 0, 'top_category': '—'}.
    """
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        top_row = conn.execute(
            "SELECT category, SUM(amount) AS cat_total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY cat_total DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    total_spent = float(totals["total"]) if totals is not None else 0.0
    transaction_count = int(totals["count"]) if totals is not None else 0
    top_category = top_row["category"] if top_row is not None else "—"

    return {
        "total_spent": total_spent,
        "transaction_count": transaction_count,
        "top_category": top_category,
    }


TX_RANGES = ("this_month", "last_month", "all")


def get_recent_transactions(user_id, limit=10, period="all", date_from=None, date_to=None):
    """Return list of {'date', 'description', 'category', 'amount'} dicts.

    Ordered newest date first, tiebreak by id DESC. Date formatted 'Mon DD, YYYY'.
    `period` filters by date: 'this_month', 'last_month', or 'all' (default).
    Unknown periods fall back to 'all'. Empty list when user has no expenses.

    `date_from` / `date_to` (YYYY-MM-DD strings) take precedence over `period`
    when either is set, applying inclusive `date >= ?` / `date <= ?` filters.
    """
    use_custom = bool(date_from) or bool(date_to)

    if not use_custom and period not in TX_RANGES:
        period = "all"

    date_clause = ""
    extra_params = []
    if use_custom:
        if date_from:
            date_clause += " AND date >= ?"
            extra_params.append(date_from)
        if date_to:
            date_clause += " AND date <= ?"
            extra_params.append(date_to)
    elif period == "this_month":
        date_clause = " AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
    elif period == "last_month":
        date_clause = " AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')"

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + date_clause +
            " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *extra_params, limit),
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        raw_date = row["date"]
        try:
            formatted_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%b %d, %Y")
        except ValueError:
            formatted_date = raw_date

        results.append(
            {
                "date": formatted_date,
                "description": row["description"] if row["description"] is not None else "",
                "category": row["category"],
                "amount": float(row["amount"]),
            }
        )

    return results


def get_category_breakdown(user_id):
    """Return list of {'name', 'amount', 'pct'} dicts sorted by amount DESC.

    `pct` is an integer; percentages sum to exactly 100 with any rounding
    remainder absorbed by the largest-amount category. Empty list when
    the user has no expenses.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    categories = [(row["category"], float(row["total"])) for row in rows]
    grand_total = sum(amount for _, amount in categories)

    if grand_total <= 0:
        return [{"name": name, "amount": amount, "pct": 0} for name, amount in categories]

    floored = [math.floor(amount / grand_total * 100) for _, amount in categories]
    remainder = 100 - sum(floored)

    result = []
    for idx, (name, amount) in enumerate(categories):
        pct = floored[idx]
        if idx == 0:
            pct += remainder
        result.append({"name": name, "amount": amount, "pct": pct})

    return result


def add_expense(user_id, amount, category, date, description):
    """Insert one expense row for user_id; return the new row id.

    Caller is responsible for validation. `description` may be None.
    """
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
