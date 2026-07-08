"""Invite-code registration and role enforcement."""

from __future__ import annotations


def _create_invite(client, note="for a friend"):
    res = client.post("/auth/invites", json={"note": note})
    assert res.status_code == 201, res.text
    return res.json()


def _register(client, code, email="friend@example.com", password="a-strong-member-pass-123"):
    return client.post(
        "/auth/register",
        json={"invite_code": code, "email": email, "password": password},
    )


def test_owner_can_mint_and_list_invites(client):
    created = _create_invite(client)
    assert created["code"]
    assert created["note"] == "for a friend"

    listed = client.get("/auth/invites").json()["invites"]
    assert len(listed) == 1
    assert listed[0]["status"] == "pending"
    # plaintext code is never in the listing
    assert "code" not in listed[0]


def test_register_with_invite_creates_member_session(client):
    code = _create_invite(client)["code"]

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as friend:
        res = _register(friend, code)
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["user"]["email"] == "friend@example.com"
        assert body["user"]["role"] == "member"

        # The session is live immediately.
        friend.headers.update({"X-CSRF-Token": body["csrf_token"]})
        me = friend.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["role"] == "member"

    # Invite now shows used.
    listed = client.get("/auth/invites").json()["invites"]
    assert listed[0]["status"] == "used"
    assert listed[0]["used_by_email"] == "friend@example.com"


def test_invite_single_use(client):
    code = _create_invite(client)["code"]

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c1:
        assert _register(c1, code, email="one@example.com").status_code == 201
    with TestClient(create_app()) as c2:
        res = _register(c2, code, email="two@example.com")
        assert res.status_code == 401
        assert "Invalid or expired" in res.json()["detail"]


def test_register_rejects_bogus_code(client):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        res = _register(c, "definitely-not-a-real-code")
        assert res.status_code == 401


def test_member_cannot_mint_invites(client):
    code = _create_invite(client)["code"]

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as friend:
        body = _register(friend, code).json()
        friend.headers.update({"X-CSRF-Token": body["csrf_token"]})
        res = friend.post("/auth/invites", json={"note": "sneaky"})
        assert res.status_code == 403


def test_revoke_unused_invite(client):
    created = _create_invite(client)
    assert client.delete(f"/auth/invites/{created['id']}").status_code == 204

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        assert _register(c, created["code"]).status_code == 401
