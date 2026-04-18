import re
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db

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

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
    finally:
        conn.close()

    if user is None:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    member_since = "—"
    if user["created_at"]:
        try:
            dt = datetime.strptime(user["created_at"], "%Y-%m-%d %H:%M:%S")
            member_since = f"{dt:%B %Y}"
        except ValueError:
            member_since = "—"

    initials = "".join(part[0] for part in user["name"].split()[:2]).upper() or "?"

    # Demo data for design preview only — replaced by real DB query in Step 07.
    demo_stats = {
        "total_spent": 48250,
        "transactions": 12,
        "top_category": "Food",
    }
    demo_expenses = [
        {"date": "Apr 16, 2026", "description": "Grocery run — Imtiaz",     "category": "Food",          "amount": 6420},
        {"date": "Apr 15, 2026", "description": "Careem to airport",        "category": "Transport",     "amount": 1850},
        {"date": "Apr 14, 2026", "description": "Electricity bill",         "category": "Bills",         "amount": 9300},
        {"date": "Apr 13, 2026", "description": "Pharmacy — allergy meds",  "category": "Health",        "amount": 1120},
        {"date": "Apr 12, 2026", "description": "Cinepax — evening show",   "category": "Entertainment", "amount": 2400},
        {"date": "Apr 11, 2026", "description": "Daraz — desk lamp",        "category": "Shopping",      "amount": 3750},
        {"date": "Apr 10, 2026", "description": "Misc — gift wrap",         "category": "Other",         "amount":  600},
    ]
    demo_breakdown = [
        {"category": "Food",          "amount": 14200},
        {"category": "Bills",         "amount": 12050},
        {"category": "Transport",     "amount":  7400},
        {"category": "Shopping",      "amount":  5100},
        {"category": "Entertainment", "amount":  3200},
        {"category": "Health",        "amount":  1700},
        {"category": "Other",         "amount":   600},
    ]
    breakdown_max = max((b["amount"] for b in demo_breakdown), default=1)

    return render_template(
        "profile.html",
        user=user,
        initials=initials,
        member_since=member_since,
        demo_stats=demo_stats,
        demo_expenses=demo_expenses,
        demo_breakdown=demo_breakdown,
        breakdown_max=breakdown_max,
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
