"""Optional per-role model and reasoning overrides."""

import pytest

from apps.backend.config import get_settings
from src.linger.agents import build


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("LINGER_MODEL", "openai:gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def configure(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()

    yield configure
    get_settings.cache_clear()


def test_roles_without_an_override_use_the_shared_model(settings):
    settings()
    model = build.build_model("muse")
    assert model.model_name == "gpt-6-luna"
    assert model.settings == build.LUNA_SETTINGS


def test_serendipity_defaults_to_medium_reasoning_on_openai(settings):
    settings()
    model = build.build_model("serendipity")
    assert model.model_name == "gpt-6-luna"
    assert model.settings == {"openai_reasoning_effort": "medium"}


def test_an_explicit_setting_overrides_the_serendipity_default(settings):
    settings(LINGER_ROLE_REASONING='{"serendipity": "low"}')
    assert build.build_model("serendipity").settings == {"openai_reasoning_effort": "low"}


def test_the_reasoning_default_is_skipped_for_other_providers(settings):
    settings(LINGER_MODEL="google:gemini-2.5-flash", GOOGLE_API_KEY="test-key")
    model = build.build_model("serendipity")
    assert model.model_name == "gemini-2.5-flash"


def test_a_role_override_changes_only_that_role(settings):
    settings(
        LINGER_ROLE_MODELS='{"serendipity": "openai:gpt-5.6-luna"}',
        LINGER_ROLE_REASONING='{"serendipity": "medium"}',
    )
    serendipity = build.build_model("serendipity")
    muse = build.build_model("muse")
    assert serendipity.model_name == "gpt-5.6-luna"
    assert serendipity.settings == {"openai_reasoning_effort": "medium"}
    assert muse.model_name == "gpt-6-luna" and muse.settings == build.LUNA_SETTINGS


def test_reasoning_alone_keeps_the_shared_model(settings):
    settings(LINGER_ROLE_REASONING='{"serendipity": "high"}')
    model = build.build_model("serendipity")
    assert model.model_name == "gpt-6-luna"
    assert model.settings == {"openai_reasoning_effort": "high"}


@pytest.mark.parametrize(("env", "message"), [
    ({"LINGER_ROLE_MODELS": '{"serendipty": "openai:gpt-6-luna"}'}, "Unknown roles"),
    ({"LINGER_ROLE_REASONING": '{"serendipity": "extreme"}'}, "Reasoning effort"),
    ({"LINGER_ROLE_MODELS": '{"serendipity": "gpt-6-luna"}'}, "Unsupported model"),
])
def test_invalid_overrides_fail_with_a_clear_message(settings, env, message):
    settings(**env)
    with pytest.raises(RuntimeError, match=message):
        build.build_model("serendipity")
