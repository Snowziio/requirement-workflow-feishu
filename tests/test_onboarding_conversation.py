"""Integration tests for the creation-group onboarding conversation."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

# ── Stub lark_oapi so service_app can be imported without runtime deps ──────
for mod_name in ["lark_oapi", "lark_oapi.ws", "lark_oapi.event",
                  "lark_oapi.event.callback", "lark_oapi.event.callback.model",
                  "lark_oapi.event.callback.model.p2_card_action_trigger",
                  "lark_oapi.api.im.v1.model.p2_im_message_receive_v1"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

lark_stub = sys.modules["lark_oapi"]
lark_stub.EventDispatcherHandler = type("EventDispatcherHandler", (), {"builder": staticmethod(lambda *a, **kw: MagicMock())})
lark_stub.LogLevel = type("LogLevel", (), {"INFO": "INFO"})()
lark_stub.ws = sys.modules["lark_oapi.ws"]

p2_card_mod = sys.modules["lark_oapi.event.callback.model.p2_card_action_trigger"]
p2_card_mod.P2CardActionTrigger = object
p2_card_mod.P2CardActionTriggerResponse = object

p2_im_mod = sys.modules["lark_oapi.api.im.v1.model.p2_im_message_receive_v1"]
p2_im_mod.P2ImMessageReceiveV1 = object

# ── Now import the real modules ──────────────────────────────────────────────
from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import OnboardingState
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp, MessageContext


def _make_app() -> CoordinatorRuntimeApp:
    settings = Settings(
        feishu_app_id="app",
        feishu_app_secret="secret",
        creation_group_chat_id="creation_chat",
        github_token="ghp_test",
    )
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.settings = settings
    app.service = CoordinatorService()
    app.gateway = MagicMock()
    app.store = MagicMock()
    app._observed_creation_group_chat_id = "creation_chat"
    app._pending_onboarding_project = {}
    app._pending_requirement_info = {}
    return app


def _ctx(text: str, user_id: str = "user1", chat_id: str = "creation_chat") -> MessageContext:
    return MessageContext(
        chat_id=chat_id,
        chat_type="group",
        user_id=user_id,
        text=text,
        sender_name="Test User",
    )


def _texts(responses) -> list[str]:
    return [r.text for r in responses if hasattr(r, "text")]


# ── Tests ────────────────────────────────────────────────────────────────────

def test_new_project_triggers_onboarding():
    app = _make_app()
    responses = app.handle_text_message(_ctx("新建需求 PROJ 登录功能 用户可以用邮箱登录"))
    texts = _texts(responses)
    assert any("新项目" in t or "GitHub" in t for t in texts)
    assert app._pending_onboarding_project.get("user1") == "PROJ"


def test_invalid_url_reprompts():
    app = _make_app()
    app.handle_text_message(_ctx("新建需求 PROJ 登录功能 简述"))
    responses = app.handle_text_message(_ctx("not-a-url"))
    texts = _texts(responses)
    assert any("格式" in t or "github.com" in t for t in texts)
    assert "PROJ" not in app.service.project_configs


def test_valid_url_advances_to_project_type():
    app = _make_app()
    app.handle_text_message(_ctx("新建需求 PROJ 登录功能 简述"))
    responses = app.handle_text_message(_ctx("https://github.com/org/repo"))
    texts = _texts(responses)
    assert any("全新" in t or "代码库" in t for t in texts)
    cfg = app.service.project_configs.get("PROJ")
    assert cfg is not None
    assert cfg.github_repo_url == "https://github.com/org/repo"
    assert cfg.onboarding_state == OnboardingState.COLLECTING_PROJECT_TYPE


def test_select_new_project_advances_to_tech_stack():
    app = _make_app()
    app.handle_text_message(_ctx("新建需求 PROJ 登录功能 简述"))
    app.handle_text_message(_ctx("https://github.com/org/repo"))
    responses = app.handle_text_message(_ctx("A"))
    texts = _texts(responses)
    assert any("技术栈" in t or "tech" in t.lower() for t in texts)
    assert app.service.project_configs["PROJ"].onboarding_state == OnboardingState.COLLECTING_TECH_STACK
    assert app.service.project_configs["PROJ"].is_new_project is True


def test_select_existing_project_advances_to_tech_stack():
    app = _make_app()
    app.handle_text_message(_ctx("新建需求 PROJ 登录功能 简述"))
    app.handle_text_message(_ctx("https://github.com/org/repo"))
    responses = app.handle_text_message(_ctx("B"))
    texts = _texts(responses)
    assert any("技术栈" in t for t in texts)
    assert app.service.project_configs["PROJ"].is_new_project is False


def test_parse_tech_stack():
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    result = CoordinatorRuntimeApp._parse_tech_stack("Python/FastAPI/PostgreSQL/pytest")
    assert result["language"] == "Python"
    assert result["framework"] == "FastAPI"
    assert result["database"] == "PostgreSQL"
    assert result["test_framework"] == "pytest"


def test_parse_creation_command_with_ui_flag():
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    result = CoordinatorRuntimeApp._parse_creation_command("新建需求 PROJ 登录功能 用户用邮箱登录 --ui")
    assert result is not None
    project, name, summary, needs_ui = result
    assert project == "PROJ"
    assert name == "登录功能"
    assert needs_ui is True


def test_parse_creation_command_without_ui_flag():
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    result = CoordinatorRuntimeApp._parse_creation_command("新建需求 PROJ 登录功能 用户用邮箱登录")
    assert result is not None
    _, _, _, needs_ui = result
    assert needs_ui is False


def test_existing_project_uses_normal_flow():
    app = _make_app()
    from requirement_workflow_v12.project_config import ProjectConfig
    app.service.project_configs["EXISTING"] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    responses = app.handle_text_message(_ctx("新建需求 EXISTING 新功能 简述"))
    # Should not enter onboarding — returns a card (normal flow)
    assert not any(hasattr(r, "text") and "新项目" in r.text for r in responses)
    assert app._pending_onboarding_project.get("user1") is None
