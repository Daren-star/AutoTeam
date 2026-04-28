import types

from autoteam import accounts, manager


def test_reinvite_account_uses_unified_oauth_login_and_marks_active(monkeypatch):
    events = []

    monkeypatch.setattr(
        manager,
        "login_codex_via_browser",
        lambda email, password, mail_client=None: {
            "email": email,
            "access_token": "token-1",
            "refresh_token": "refresh-1",
            "plan_type": "team",
        },
    )
    monkeypatch.setattr(manager, "save_auth_file", lambda bundle: f"/tmp/{bundle['email']}.json")
    monkeypatch.setattr(
        manager,
        "update_account",
        lambda email, **kwargs: events.append(("update", email, kwargs)),
    )
    monkeypatch.setattr(
        manager, "_auth_repair_reset", lambda email: events.append(("auth_repair_reset", email))
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))
    monkeypatch.setattr(manager.time, "time", lambda: 1234567890)
    monkeypatch.setattr(
        manager,
        "_is_email_in_team",
        lambda email: (_ for _ in ()).throw(AssertionError("should not check team membership separately")),
    )

    result = manager.reinvite_account(
        types.SimpleNamespace(browser=False),
        None,
        {"email": "tmp-user@example.com", "password": "secret"},
    )

    assert result is True
    assert events == [
        (
            "update",
            "tmp-user@example.com",
            {
                "status": accounts.STATUS_ACTIVE,
                "last_active_at": 1234567890,
                "auth_file": "/tmp/tmp-user@example.com.json",
            },
        ),
        ("auth_repair_reset", "tmp-user@example.com"),
        ("sync_to_cpa", None),
    ]


def test_create_account_direct_syncs_to_cpa_after_successful_registration(monkeypatch):
    events = []

    class FakeMailClient:
        provider_name = "cloudmail"

        def create_temp_email(self):
            return 42, "new-user@example.com"

        def delete_account(self, _account_id):
            raise AssertionError("successful direct registration must not delete temp email")

    monkeypatch.setattr(manager, "_register_direct_once", lambda *args, **kwargs: True)
    monkeypatch.setattr(manager, "_is_email_in_team", lambda email: False)
    monkeypatch.setattr(
        manager,
        "add_account",
        lambda email, password, **kwargs: events.append(("add_account", email, kwargs)),
    )
    monkeypatch.setattr(
        manager,
        "login_codex_via_browser",
        lambda email, password, mail_client=None, return_result=False: {
            "email": email,
            "access_token": "token-1",
            "refresh_token": "refresh-1",
            "plan_type": "team",
        },
    )
    monkeypatch.setattr(manager, "save_auth_file", lambda bundle: f"/tmp/{bundle['email']}.json")
    monkeypatch.setattr(
        manager,
        "update_account",
        lambda email, **kwargs: events.append(("update", email, kwargs)),
    )
    monkeypatch.setattr(
        manager, "_auth_repair_reset", lambda email: events.append(("auth_repair_reset", email))
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))
    monkeypatch.setattr(manager.time, "time", lambda: 1234567890)

    result = manager.create_account_direct(FakeMailClient())

    assert result == "new-user@example.com"
    assert events == [
        (
            "add_account",
            "new-user@example.com",
            {
                "cloudmail_account_id": 42,
                "mail_provider": "cloudmail",
                "mail_account_id": 42,
            },
        ),
        (
            "update",
            "new-user@example.com",
            {
                "status": accounts.STATUS_ACTIVE,
                "auth_file": "/tmp/new-user@example.com.json",
                "last_active_at": 1234567890,
            },
        ),
        ("auth_repair_reset", "new-user@example.com"),
        ("sync_to_cpa", None),
    ]


def test_reinvite_account_marks_standby_when_oauth_login_returns_non_team(monkeypatch):
    updates = []

    monkeypatch.setattr(
        manager,
        "login_codex_via_browser",
        lambda email, password, mail_client=None: {
            "email": email,
            "access_token": "token-1",
            "refresh_token": "refresh-1",
            "plan_type": "free",
        },
    )
    monkeypatch.setattr(
        manager,
        "update_account",
        lambda email, **kwargs: updates.append((email, kwargs)),
    )
    monkeypatch.setattr(manager, "_record_auth_repair_failure", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        manager,
        "_is_email_in_team",
        lambda email: False,
    )

    result = manager.reinvite_account(
        types.SimpleNamespace(browser=False),
        None,
        {"email": "tmp-user@example.com", "password": ""},
    )

    assert result is False
    assert updates == [
        (
            "tmp-user@example.com",
            {
                "status": accounts.STATUS_STANDBY,
                "auth_retry_count": 0,
                "auth_last_error": None,
                "auth_last_error_detail": None,
                "auth_last_failed_at": None,
                "auth_retry_after": None,
                "auth_retry_paused": False,
            },
        )
    ]


def test_reinvite_account_marks_auth_pending_when_oauth_login_fails_but_team_seat_is_still_occupied(monkeypatch):
    updates = []

    monkeypatch.setattr(manager, "login_codex_via_browser", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        manager,
        "update_account",
        lambda email, **kwargs: updates.append((email, kwargs)),
    )
    monkeypatch.setattr(manager, "_record_auth_repair_failure", lambda *args, **kwargs: {})
    monkeypatch.setattr(manager, "_is_email_in_team", lambda email: True)

    result = manager.reinvite_account(
        types.SimpleNamespace(browser=False),
        None,
        {"email": "tmp-user@example.com", "password": ""},
    )

    assert result is False
    assert updates == [("tmp-user@example.com", {"status": accounts.STATUS_AUTH_PENDING})]
