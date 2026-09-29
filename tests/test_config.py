from pathlib import Path

from apps.backend.config import Settings


def test_runtime_storage_directories_can_be_set_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("LINGER_STATE_DIR", "/var/lib/linger")
    monkeypatch.setenv("LINGER_MEMORY_DIR", "/var/lib/linger-memories")

    settings = Settings(_env_file=None, linger_model="openai:test")

    assert settings.linger_state_dir == Path("/var/lib/linger")
    assert settings.linger_memory_dir == Path("/var/lib/linger-memories")

