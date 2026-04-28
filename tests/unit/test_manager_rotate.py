from autoteam import config, manager


class _FakeChatGPT:
    def __init__(self):
        self.browser = True
        self.started = 0
        self.stopped = 0

    def start(self):
        self.browser = True
        self.started += 1

    def stop(self):
        self.browser = False
        self.stopped += 1


class _FakeMailClient:
    def login(self):
        return None


def test_cmd_rotate_skips_google_accounts_during_auto_reuse(monkeypatch):
    chatgpt = _FakeChatGPT()
    count_values = iter([4, 5, 5])
    events = []

    monkeypatch.setattr(manager, "sync_account_states", lambda: events.append(("sync_account_states", None)))
    monkeypatch.setattr(manager, "cmd_check", lambda: events.append(("cmd_check", None)))
    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", lambda: [])
    monkeypatch.setattr(manager, "get_team_member_count", lambda _chatgpt: next(count_values))
    monkeypatch.setattr(
        manager,
        "get_standby_accounts",
        lambda: [
            {"email": "bubblehuntr@gmail.com"},
            {"email": "old-2@example.com"},
        ],
    )
    monkeypatch.setattr(
        manager,
        "reinvite_account",
        lambda _chatgpt, _mail, acc: events.append(("reinvite", acc["email"])) or True,
    )
    monkeypatch.setattr(
        manager,
        "create_new_account",
        lambda _chatgpt, _mail: events.append(("create", None)) or True,
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))

    manager.cmd_rotate(target_seats=5)

    assert events == [
        ("sync_account_states", None),
        ("cmd_check", None),
        ("reinvite", "old-2@example.com"),
        ("sync_to_cpa", None),
    ]
    assert chatgpt.stopped == 1


def test_cmd_rotate_prefers_saved_quota_reset_when_deciding_standby_reuse(monkeypatch):
    chatgpt = _FakeChatGPT()
    count_values = iter([4, 5, 5])
    events = []
    now = 1_700_000_000

    monkeypatch.setattr(manager.time, "time", lambda: now)
    monkeypatch.setattr(manager, "sync_account_states", lambda: events.append(("sync_account_states", None)))
    monkeypatch.setattr(manager, "cmd_check", lambda: events.append(("cmd_check", None)))
    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", lambda: [])
    monkeypatch.setattr(manager, "get_team_member_count", lambda _chatgpt: next(count_values))
    monkeypatch.setattr(
        manager,
        "get_standby_accounts",
        lambda: [
            {
                "email": "stale@example.com",
                "auth_file": "/tmp/missing-auth.json",
                "quota_resets_at": now + 1200,
                "last_quota": {
                    "primary_pct": 100,
                    "primary_resets_at": now - 60,
                    "weekly_pct": 100,
                    "weekly_resets_at": now + 1200,
                },
            }
        ],
    )
    monkeypatch.setattr(
        manager,
        "reinvite_account",
        lambda _chatgpt, _mail, acc: events.append(("reinvite", acc["email"])) or True,
    )
    monkeypatch.setattr(
        manager,
        "create_new_account",
        lambda _chatgpt, _mail: events.append(("create", None)) or True,
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))

    manager.cmd_rotate(target_seats=5)

    assert events == [
        ("sync_account_states", None),
        ("cmd_check", None),
        ("create", None),
        ("sync_to_cpa", None),
    ]


def test_cmd_rotate_stops_creating_when_refreshed_team_count_hits_target(monkeypatch):
    chatgpt = _FakeChatGPT()
    count_values = iter([3, 5, 5])
    events = []

    monkeypatch.setattr(manager, "sync_account_states", lambda: events.append(("sync_account_states", None)))
    monkeypatch.setattr(manager, "cmd_check", lambda: events.append(("cmd_check", None)))
    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", lambda: [])
    monkeypatch.setattr(manager, "get_team_member_count", lambda _chatgpt: next(count_values))
    monkeypatch.setattr(manager, "get_standby_accounts", lambda: [])
    monkeypatch.setattr(
        manager,
        "create_new_account",
        lambda _chatgpt, _mail: events.append(("create", None)) or False,
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))

    manager.cmd_rotate(target_seats=5)

    assert events == [
        ("sync_account_states", None),
        ("cmd_check", None),
        ("create", None),
        ("sync_to_cpa", None),
    ]


def test_cmd_rotate_does_not_create_new_account_when_team_seats_are_full_but_pool_active_is_still_short(monkeypatch):
    chatgpt = _FakeChatGPT()
    count_values = iter([4, 5, 5])
    events = []

    monkeypatch.setattr(manager, "sync_account_states", lambda: events.append(("sync_account_states", None)))
    monkeypatch.setattr(manager, "cmd_check", lambda: events.append(("cmd_check", None)))
    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", lambda: [])
    monkeypatch.setattr(manager, "_count_pool_active_accounts", lambda *args, **kwargs: 3)
    monkeypatch.setattr(manager, "get_team_member_count", lambda _chatgpt: next(count_values))
    monkeypatch.setattr(manager, "get_standby_accounts", lambda: [{"email": "reuse@example.com"}])
    monkeypatch.setattr(
        manager,
        "reinvite_account",
        lambda _chatgpt, _mail, acc: events.append(("reinvite", acc["email"])) or False,
    )
    monkeypatch.setattr(
        manager,
        "create_new_account",
        lambda _chatgpt, _mail: events.append(("create", None)) or True,
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))

    manager.cmd_rotate(target_seats=5)

    assert events == [
        ("sync_account_states", None),
        ("cmd_check", None),
        ("reinvite", "reuse@example.com"),
        ("sync_to_cpa", None),
    ]


def test_cmd_rotate_one_use_mode_deletes_exhausted_and_standby_then_creates(monkeypatch):
    chatgpt = _FakeChatGPT()
    count_values = iter([5, 4, 5, 5])
    events = []
    accounts = [
        {"email": "used@example.com", "status": "exhausted", "mail_provider": "cloudmail"},
        {"email": "old-standby@example.com", "status": "standby", "mail_provider": "cloudmail"},
    ]

    monkeypatch.setattr(config, "ACCOUNT_REUSE_MODE", "one_use", raising=False)
    monkeypatch.setattr(manager, "sync_account_states", lambda: events.append(("sync_account_states", None)))
    monkeypatch.setattr(manager, "cmd_check", lambda: events.append(("cmd_check", None)))
    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "_get_account_mail_client", lambda _acc: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", lambda: accounts)
    monkeypatch.setattr(manager, "get_team_member_count", lambda _chatgpt: next(count_values))
    monkeypatch.setattr(manager, "_is_main_account_email", lambda _email: False)
    monkeypatch.setattr(
        manager,
        "delete_managed_account",
        lambda email, **kwargs: events.append(("delete", email, kwargs.get("sync_cpa_after"))) or {
            "team_member_removed": email == "used@example.com",
            "invite_removed": False,
            "cloudmail_deleted": True,
        },
    )
    monkeypatch.setattr(
        manager,
        "get_standby_accounts",
        lambda: (_ for _ in ()).throw(AssertionError("one-use mode must not reuse standby accounts")),
    )
    monkeypatch.setattr(
        manager,
        "reinvite_account",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("one-use mode must not reinvite")),
    )
    monkeypatch.setattr(
        manager,
        "create_new_account",
        lambda _chatgpt, _mail: events.append(("create", None)) or True,
    )
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))

    manager.cmd_rotate(target_seats=5)

    assert events == [
        ("sync_account_states", None),
        ("cmd_check", None),
        ("delete", "used@example.com", False),
        ("delete", "old-standby@example.com", False),
        ("create", None),
        ("sync_to_cpa", None),
    ]
