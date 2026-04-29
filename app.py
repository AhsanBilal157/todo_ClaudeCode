import re
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db
from database import queries

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name:
        return render_template("register.html", error="Please enter your name.")
    if not email:
        return render_template("register.html", error="Please enter your email.")
    if not EMAIL_RE.match(email):
        return render_template("register.html", error="Please enter a valid email address.")
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.")

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            return render_template(
                "register.html",
                error="An account with that email already exists.",
            )

        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template(
                "register.html",
                error="An account with that email already exists.",
            )
    finally:
        conn.close()

    return redirect(url_for("profile"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    error = "Invalid email or password."

    if not email or not password:
        return render_template("login.html", error=error)

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error=error)

    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = queries.get_user_by_id(session["user_id"])
    if user is None:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    raw_from = request.args.get("from", "")
    raw_to = request.args.get("to", "")
    has_from_key = "from" in request.args
    has_to_key = "to" in request.args

    if has_from_key and has_to_key and not raw_from and not raw_to:
        preserved_range = request.args.get("range")
        if preserved_range in queries.TX_RANGES:
            return redirect(url_for("profile", range=preserved_range))
        return redirect(url_for("profile"))

    filter_error = None
    date_from = None
    date_to = None

    parsed_from = None
    parsed_to = None
    if raw_from:
        try:
            parsed_from = datetime.strptime(raw_from, "%Y-%m-%d")
        except ValueError:
            filter_error = "Please enter dates as YYYY-MM-DD."
    if raw_to and filter_error is None:
        try:
            parsed_to = datetime.strptime(raw_to, "%Y-%m-%d")
        except ValueError:
            filter_error = "Please enter dates as YYYY-MM-DD."

    if filter_error is None and parsed_from and parsed_to and parsed_from > parsed_to:
        filter_error = "Start date must be on or before end date."

    if filter_error is None:
        date_from = raw_from if parsed_from else None
        date_to = raw_to if parsed_to else None

    tx_range = request.args.get("range", "this_month")
    if tx_range not in queries.TX_RANGES:
        tx_range = "this_month"

    if bool(date_from) or bool(date_to):
        # "custom" is a sentinel — must never collide with a real preset.
        assert "custom" not in queries.TX_RANGES, \
            "TX_RANGES must not contain 'custom' — it's reserved for the date filter sentinel"
        tx_range = "custom"

    user_id = session["user_id"]
    stats = queries.get_summary_stats(user_id)
    expenses = queries.get_recent_transactions(
        user_id,
        limit=10,
        period=tx_range,
        date_from=date_from,
        date_to=date_to,
    )
    breakdown = queries.get_category_breakdown(user_id)
    breakdown_max_pct = max((b["pct"] for b in breakdown), default=1)

    initials = "".join(part[0] for part in user["name"].split()[:2]).upper() or "?"

    return render_template(
        "profile.html",
        user=user,
        initials=initials,
        member_since=user["member_since"],
        stats=stats,
        expenses=expenses,
        breakdown=breakdown,
        breakdown_max_pct=breakdown_max_pct,
        tx_range=tx_range,
        date_from=date_from or "",
        date_to=date_to or "",
        filter_error=filter_error,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=True, port=5005)
