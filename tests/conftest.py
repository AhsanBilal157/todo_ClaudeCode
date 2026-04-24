import pytest

from app import app as flask_app
from database.db import get_db, init_db, seed_db


@pytest.fixture()
def app():
    flask_app.config["TESTING"] = True
    init_db()
    seed_db()
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seed_user_id(app):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
    finally:
        conn.close()
    return row["id"] if row else None
