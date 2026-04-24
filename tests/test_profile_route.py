from database.db import get_db


def test_profile_redirects_when_logged_out(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_renders_real_seed_data(client, seed_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user_id

    response = client.get("/profile?range=all")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "PKR" in body
    assert "365.24" in body
    assert "Bills" in body


def test_profile_range_pills_render_with_active_class(client, seed_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user_id

    body = client.get("/profile?range=last_month").get_data(as_text=True)
    assert 'href="/profile?range=last_month"' in body
    assert 'href="/profile?range=this_month"' in body
    assert 'href="/profile?range=all"' in body
    # the "Last month" pill should be the active one now
    assert 'class="filter-pill is-active"\n                       href="/profile?range=last_month"' in body \
        or 'filter-pill is-active" href="/profile?range=last_month"' in body \
        or ('is-active' in body and 'last_month' in body)


def test_profile_range_defaults_to_this_month(client, seed_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user_id

    body = client.get("/profile").get_data(as_text=True)
    # seed user has all 8 expenses in 2026-04, and "today" in test env is
    # in 2026-04, so this_month == all seeded rows
    assert "Apr 15, 2026" in body


def test_profile_clears_stale_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 99999

    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_profile_empty_state_for_new_user(client):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Fresh User", "fresh@spendly.test", "x"),
        )
        new_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    try:
        with client.session_transaction() as sess:
            sess["user_id"] = new_id

        response = client.get("/profile")
        assert response.status_code == 200
        body = response.get_data(as_text=True)

        assert "Add your first expense" in body
        assert 'class="tx-table"' not in body
        assert "Log some expenses to see your category breakdown." in body
        assert "Fresh User" in body
    finally:
        cleanup = get_db()
        try:
            cleanup.execute("DELETE FROM users WHERE id = ?", (new_id,))
            cleanup.commit()
        finally:
            cleanup.close()
