import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "container_entrypoint", Path(__file__).resolve().parents[1] / "docker/entrypoint.py",
)
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class Executed(Exception):
    pass


def mock_execution(monkeypatch, events):
    def execute(command, arguments):
        events.append(("exec", command, arguments))
        raise Executed

    monkeypatch.setattr(entrypoint.os, "execvp", execute)


def test_nonroot_executes_command_without_touching_state_or_credentials(monkeypatch):
    events = []
    monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 10001)
    monkeypatch.setattr(entrypoint, "open_state_directory", lambda _: pytest.fail("nonroot migration"))
    monkeypatch.setattr(entrypoint.os, "setgroups", lambda _: pytest.fail("nonroot privilege change"))
    mock_execution(monkeypatch, events)

    with pytest.raises(Executed):
        entrypoint.main(["uvicorn", "apps.backend.main:app", "--port", "8000"])

    assert events == [("exec", "uvicorn", ["uvicorn", "apps.backend.main:app", "--port", "8000"])]


def test_root_migrates_existing_state_before_dropping_all_privileges(tmp_path, monkeypatch):
    state = tmp_path.resolve() / "state"
    nested = state / "memories" / "reader"
    nested.mkdir(parents=True)
    account = state / "accounts.sqlite3"
    account.write_bytes(b"existing account data")
    memory = nested / "memory.json"
    memory.write_text('{"text": "existing memory"}')
    outside = tmp_path / "unrelated"
    outside.write_text("untouched")
    expected = {(path.stat().st_dev, path.stat().st_ino) for path in (state, state / "memories", nested, account, memory)}
    events = []

    def record_ownership(descriptor, uid, gid):
        info = os.fstat(descriptor)
        events.append(("owner", (info.st_dev, info.st_ino), uid, gid))

    monkeypatch.setenv("LINGER_STATE_DIR", str(state))
    monkeypatch.setenv("HOME", "/root")
    monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 0)
    monkeypatch.setattr(entrypoint.os, "fchown", record_ownership)
    monkeypatch.setattr(entrypoint.os, "setgroups", lambda groups: events.append(("groups", groups)))
    monkeypatch.setattr(entrypoint.os, "setgid", lambda gid: events.append(("gid", gid)))
    monkeypatch.setattr(entrypoint.os, "setuid", lambda uid: events.append(("uid", uid)))
    mock_execution(monkeypatch, events)

    with pytest.raises(Executed):
        entrypoint.main(["uvicorn", "apps.backend.main:app"])

    ownership = events[:-4]
    assert {event[1] for event in ownership} == expected
    assert all(event[0] == "owner" and event[2:] == (10001, 10001) for event in ownership)
    assert events[-4:] == [
        ("groups", []), ("gid", 10001), ("uid", 10001),
        ("exec", "uvicorn", ["uvicorn", "apps.backend.main:app"]),
    ]
    assert account.read_bytes() == b"existing account data"
    assert memory.read_text() == '{"text": "existing memory"}'
    assert outside.read_text() == "untouched"
    assert os.environ["HOME"] == "/home/linger"


def test_missing_state_directory_is_created_and_owned(tmp_path, monkeypatch):
    state = tmp_path.resolve() / "new-state"
    migrated = []
    monkeypatch.setattr(entrypoint.os, "fchown", lambda fd, uid, gid: migrated.append((os.fstat(fd).st_ino, uid, gid)))

    descriptor = entrypoint.open_state_directory(str(state))
    try:
        entrypoint.migrate_ownership(descriptor)
    finally:
        os.close(descriptor)

    assert state.is_dir()
    assert migrated == [(state.stat().st_ino, 10001, 10001)]


@pytest.mark.parametrize("link_is_parent", [False, True])
def test_symlink_escape_refuses_startup_and_never_changes_target(tmp_path, monkeypatch, link_is_parent):
    outside = tmp_path.resolve() / "outside"
    outside.mkdir()
    target = outside / "secret"
    target.write_text("external data")
    state = tmp_path.resolve() / "state"
    if link_is_parent:
        state.symlink_to(outside, target_is_directory=True)
    else:
        state.mkdir()
        (state / "escape").symlink_to(outside, target_is_directory=True)
    changed = []
    monkeypatch.setenv("LINGER_STATE_DIR", str(state))
    monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 0)
    monkeypatch.setattr(entrypoint.os, "fchown", lambda fd, *_: changed.append(os.fstat(fd).st_ino))
    monkeypatch.setattr(entrypoint.os, "setgroups", lambda _: pytest.fail("privileges dropped despite unsafe state"))
    monkeypatch.setattr(entrypoint.os, "execvp", lambda *_: pytest.fail("unsafe state started"))

    with pytest.raises((OSError, ValueError)):
        entrypoint.main(["uvicorn"])

    assert changed == []
    assert target.read_text() == "external data"


@pytest.mark.parametrize("path", ["relative/state", "/", "/var/lib/../state"])
def test_unsafe_state_directory_is_refused(path):
    with pytest.raises(ValueError, match="absolute directory below"):
        entrypoint.open_state_directory(path)


def test_hardlink_never_changes_a_file_outside_the_state_directory(tmp_path, monkeypatch):
    outside = tmp_path.resolve() / "outside"
    outside.write_text("external data")
    state = tmp_path.resolve() / "state"
    state.mkdir()
    (state / "linked-file").hardlink_to(outside)
    monkeypatch.setattr(entrypoint.os, "fchown", lambda *_: pytest.fail("external inode changed"))
    descriptor = entrypoint.open_state_directory(str(state))
    try:
        with pytest.raises(ValueError, match="Hard links"):
            entrypoint.migrate_ownership(descriptor)
    finally:
        os.close(descriptor)
    assert outside.read_text() == "external data"


def test_failure_to_drop_privileges_never_executes_application(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGER_STATE_DIR", str(tmp_path.resolve()))
    monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 0)
    monkeypatch.setattr(entrypoint.os, "fchown", lambda *_: None)

    def fail_drop(_):
        raise PermissionError("cannot clear supplementary groups")

    monkeypatch.setattr(entrypoint.os, "setgroups", fail_drop)
    monkeypatch.setattr(entrypoint.os, "execvp", lambda *_: pytest.fail("application kept root privileges"))
    with pytest.raises(PermissionError, match="supplementary groups"):
        entrypoint.main(["uvicorn"])
