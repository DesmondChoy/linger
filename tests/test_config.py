from pathlib import Path

from apps.backend.config import REPO_ROOT, Settings


def test_runtime_storage_directories_can_be_set_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("LINGER_STATE_DIR", "/var/lib/linger")
    monkeypatch.setenv("LINGER_MEMORY_DIR", "/var/lib/linger-memories")

    settings = Settings(_env_file=None, linger_model="openai:test")

    assert settings.linger_state_dir == Path("/var/lib/linger")
    assert settings.linger_memory_dir == Path("/var/lib/linger-memories")


def test_state_directory_override_preserves_default_memory_directory(monkeypatch) -> None:
    monkeypatch.setenv("LINGER_STATE_DIR", "/var/lib/linger")
    monkeypatch.delenv("LINGER_MEMORY_DIR", raising=False)

    settings = Settings(_env_file=None, linger_model="openai:test")

    assert settings.linger_state_dir == Path("/var/lib/linger")
    assert settings.linger_memory_dir == REPO_ROOT / "memories"
