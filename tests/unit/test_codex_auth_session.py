from autoteam import codex_auth


def test_login_codex_via_session_uses_unified_flow_and_returns_bundle(monkeypatch):
    events = []

    class FakeSessionCodexAuthFlow:
        def __init__(self, **kwargs):
            events.append(("init", kwargs))

        def start(self):
            events.append(("start", None))
            return {"step": "completed", "detail": None}

        def complete(self):
            events.append(("complete", None))
            return {"bundle": {"email": "owner@example.com", "plan_type": "team"}}

        def stop(self):
            events.append(("stop", None))

    monkeypatch.setattr(codex_auth, "SessionCodexAuthFlow", FakeSessionCodexAuthFlow)
    monkeypatch.setattr(codex_auth, "get_admin_email", lambda: "owner@example.com")
    monkeypatch.setattr(codex_auth, "get_admin_session_token", lambda: "session-token")
    monkeypatch.setattr(codex_auth, "get_chatgpt_account_id", lambda: "acc-1")
    monkeypatch.setattr(codex_auth, "get_chatgpt_workspace_name", lambda: "Idapro")

    bundle = codex_auth.login_codex_via_session()

    assert bundle == {"email": "owner@example.com", "plan_type": "team"}
    assert events[0][0] == "init"
    assert events[0][1]["email"] == "owner@example.com"
    assert events[0][1]["session_token"] == "session-token"
    assert events[0][1]["account_id"] == "acc-1"
    assert events[0][1]["workspace_name"] == "Idapro"
    assert callable(events[0][1]["auth_file_callback"])
    assert [name for name, _ in events[1:]] == ["start", "complete", "stop"]


def test_login_codex_via_session_returns_none_when_flow_requires_more_steps(monkeypatch):
    events = []

    class FakeSessionCodexAuthFlow:
        def __init__(self, **kwargs):
            events.append(("init", kwargs))

        def start(self):
            events.append(("start", None))
            return {"step": "email_required", "detail": "https://auth.openai.com/login"}

        def complete(self):
            raise AssertionError("complete should not be called")

        def stop(self):
            events.append(("stop", None))

    monkeypatch.setattr(codex_auth, "SessionCodexAuthFlow", FakeSessionCodexAuthFlow)
    monkeypatch.setattr(codex_auth, "get_admin_email", lambda: "owner@example.com")
    monkeypatch.setattr(codex_auth, "get_admin_session_token", lambda: "session-token")
    monkeypatch.setattr(codex_auth, "get_chatgpt_account_id", lambda: "acc-1")
    monkeypatch.setattr(codex_auth, "get_chatgpt_workspace_name", lambda: "Idapro")

    bundle = codex_auth.login_codex_via_session()

    assert bundle is None
    assert [name for name, _ in events[1:]] == ["start", "stop"]


def test_refresh_main_auth_file_saves_bundle_from_session_login(monkeypatch):
    monkeypatch.setattr(
        codex_auth,
        "login_codex_via_session",
        lambda: {"email": "owner@example.com", "account_id": "acc-1", "plan_type": "team"},
    )
    monkeypatch.setattr(codex_auth, "save_main_auth_file", lambda bundle: f"/tmp/{bundle['account_id']}.json")

    result = codex_auth.refresh_main_auth_file()

    assert result == {
        "email": "owner@example.com",
        "auth_file": "/tmp/acc-1.json",
        "plan_type": "team",
    }


class _FakeElement:
    def __init__(self, text, *, visible=True):
        self._text = text
        self._visible = visible
        self.clicked = False
        self.click_calls = []

    def is_visible(self, timeout=0):
        return self._visible

    def inner_text(self, timeout=0):
        return self._text

    def click(self, timeout=0, force=False):
        self.clicked = True
        self.click_calls.append({"timeout": timeout, "force": force})


class _AlwaysFailClickElement(_FakeElement):
    def click(self, timeout=0, force=False):
        self.click_calls.append({"timeout": timeout, "force": force})
        raise RuntimeError("click failed")


class _FakeCollection:
    def __init__(self, items=None, text=None):
        self._items = items or []
        self._text = text

    @property
    def first(self):
        if self._items:
            return self._items[0]
        return _FakeElement("", visible=False)

    def all(self):
        return list(self._items)

    def inner_text(self, timeout=0):
        if self._text is None:
            raise AssertionError("unexpected inner_text call")
        return self._text


class _FakePage:
    def __init__(self, *, url, body, elements=None):
        self.url = url
        self._body = body
        self._elements = elements or []

    def locator(self, selector):
        if selector == "body":
            return _FakeCollection(text=self._body)
        if isinstance(self._elements, dict):
            return _FakeCollection(items=self._elements.get(selector, []))
        if str(selector).startswith("text="):
            return _FakeCollection(items=[])
        return _FakeCollection(items=self._elements)


def test_existing_session_account_selection_clicks_matching_session_button():
    target = _FakeElement("User tmp-69a5d0b0@gpttome.indevs.in")
    remove = _FakeElement("")
    page = _FakePage(
        url="https://auth.openai.com/choose-an-account",
        body="选择帐户 User tmp-69a5d0b0@gpttome.indevs.in 登录至另一个帐户 创建帐户",
        elements={
            'button[name="session_id"]': [target],
            'button[data-dd-action-name="Select existing session"]': [],
            "button": [remove],
        },
    )

    assert codex_auth._is_existing_session_selection_page(page) is True
    assert codex_auth._select_existing_account_session(page, "tmp-69a5d0b0@gpttome.indevs.in") is True
    assert target.click_calls == [{"timeout": 3000, "force": False}]
    assert remove.clicked is False


def test_session_flow_clicks_existing_session_selection_page(monkeypatch):
    monkeypatch.setattr(codex_auth.time, "sleep", lambda _seconds: None)

    target = _FakeElement("User owner@example.com")
    page = _FakePage(
        url="https://auth.openai.com/choose-an-account",
        body="Choose account User owner@example.com Log in with another account",
        elements={
            'button[name="session_id"]': [target],
            'button[data-dd-action-name="Select existing session"]': [],
        },
    )
    flow = codex_auth.SessionCodexAuthFlow(
        email="owner@example.com",
        session_token="session-token",
        account_id="acc-1",
        workspace_name="Idapro",
    )
    flow.page = page

    assert flow._click_workspace_or_consent() is True
    assert target.clicked is True


def test_workspace_selection_detection_ignores_otp_pages():
    page = _FakePage(
        url="https://auth.openai.com/email-verification",
        body="Check your inbox Enter the verification code we just sent to user@example.com",
    )

    assert codex_auth._is_workspace_selection_page(page) is False
    assert codex_auth._select_team_workspace(page, "Idapro") is False


def test_account_deactivated_email_verification_error_is_non_retryable():
    error_type, error_detail, retryable = codex_auth._classify_oauth_failure(
        "https://auth.openai.com/email-verification",
        "验证过程中出错 (account_deactivated)。请重试。",
    )

    assert error_type == "account_deactivated"
    assert "封禁" in error_detail or "停用" in error_detail
    assert retryable is False


def test_account_deactivated_password_page_returns_terminal_failure():
    page = _FakePage(
        url="https://auth.openai.com/log-in/password",
        body="验证过程中出错 (account_deactivated)。请重试。",
    )

    result = codex_auth._account_deactivated_failure_result(page)

    assert result["ok"] is False
    assert result["error_type"] == "account_deactivated"
    assert result["retryable"] is False
    assert result["current_url"] == "https://auth.openai.com/log-in/password"


def test_workspace_label_candidates_ignore_action_buttons():
    items = [
        _FakeElement("Cancel"),
        _FakeElement("Log in with a one-time code"),
        _FakeElement("Idapro"),
        _FakeElement("Personal account"),
    ]
    page = _FakePage(
        url="https://auth.openai.com/workspace",
        body="Choose a workspace Workspace Idapro Personal account",
        elements=items,
    )

    candidates = [text for text, _loc in codex_auth._workspace_label_candidates(page)]

    assert candidates == ["Idapro", "Personal account"]


def test_workspace_selection_detection_ignores_generic_organization_setup_page():
    page = _FakePage(
        url="https://auth.openai.com/organization",
        body="New organization Finish setting up on the next page",
        elements=[_FakeElement("New organization Finish setting up on the next page")],
    )

    assert codex_auth._is_workspace_selection_page(page) is False
    assert codex_auth._select_team_workspace(page, "Idapro") is False


def test_team_workspace_selection_requires_exact_workspace_name():
    items = [
        _FakeElement("New organization Finish setting up on the next page"),
        _FakeElement("Personal account"),
    ]
    page = _FakePage(
        url="https://auth.openai.com/workspace",
        body="Choose a workspace Workspace Personal account",
        elements=items,
    )

    assert codex_auth._workspace_label_candidates(page) == [("Personal account", items[1])]
    assert codex_auth._select_team_workspace(page, "Idapro") is False


def test_workspace_selection_retries_matched_target_click_three_rounds():
    target = _FakeElement("Idapro")
    page = _FakePage(
        url="https://auth.openai.com/workspace",
        body="Choose a workspace Workspace Idapro Personal account",
        elements=[target, _FakeElement("Personal account")],
    )

    assert codex_auth._select_team_workspace(page, "Idapro") is True
    assert target.click_calls == [
        {"timeout": 3000, "force": False},
        {"timeout": 1000, "force": False},
        {"timeout": 1000, "force": False},
    ]


def test_workspace_selection_uses_force_fallback_each_failed_round():
    target = _AlwaysFailClickElement("Idapro")
    page = _FakePage(
        url="https://auth.openai.com/workspace",
        body="Choose a workspace Workspace Idapro Personal account",
        elements=[target, _FakeElement("Personal account")],
    )

    assert codex_auth._select_team_workspace(page, "Idapro") is False
    assert target.click_calls == [
        {"timeout": 3000, "force": False},
        {"timeout": 1000, "force": True},
        {"timeout": 1000, "force": False},
        {"timeout": 1000, "force": True},
        {"timeout": 1000, "force": False},
        {"timeout": 1000, "force": True},
    ]
