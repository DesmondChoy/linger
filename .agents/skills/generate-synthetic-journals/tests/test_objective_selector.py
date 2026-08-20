from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "objective_selector.py"
SPEC = importlib.util.spec_from_file_location("objective_selector", SCRIPT)
assert SPEC and SPEC.loader
selector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selector
SPEC.loader.exec_module(selector)


def test_current_catalog_has_ten_unique_objectives() -> None:
    catalog = selector.load_catalog(selector.DEFAULT_CATALOG)

    assert len(catalog.objectives) == 10
    assert len(set(catalog.ids)) == 10


def test_injection_resistance_requires_a_primary_objective() -> None:
    catalog = selector.load_catalog(selector.DEFAULT_CATALOG)

    with pytest.raises(selector.SelectorError, match="security overlay"):
        selector.validate_selection(catalog, [selector.INJECTION_OBJECTIVE])

    assert selector.validate_selection(
        catalog,
        [selector.INJECTION_OBJECTIVE, "grounded_book_reflection"],
    ) == ("grounded_book_reflection", selector.INJECTION_OBJECTIVE)


def test_duplicate_and_unknown_objectives_fail_closed() -> None:
    catalog = selector.load_catalog(selector.DEFAULT_CATALOG)

    with pytest.raises(selector.SelectorError, match="duplicate"):
        selector.validate_selection(catalog, ["grounded_book_reflection"] * 2)
    with pytest.raises(selector.SelectorError, match="Unknown"):
        selector.validate_selection(catalog, ["invented_objective"])


def test_main_classifies_loopback_permission_denial(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        selector,
        "parse_args",
        lambda: argparse.Namespace(
            catalog=selector.DEFAULT_CATALOG,
            ui=selector.DEFAULT_UI,
            timeout=900,
        ),
    )

    def deny_bind(state: selector.SelectorState) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(selector, "SelectorServer", deny_bind)

    assert selector.main() == 3
    captured = capsys.readouterr()
    assert captured.out == "OBJECTIVE_SELECTOR_BIND_PERMISSION_REQUIRED=127.0.0.1\n"
    assert "objective selector bind permission required" in captured.err


def test_server_returns_catalog_and_confirmed_selection(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("selector", encoding="utf-8")
    catalog = selector.load_catalog(selector.DEFAULT_CATALOG)
    state = selector.SelectorState(catalog=catalog, ui_dir=tmp_path, token="test-token")
    server = selector.SelectorServer(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(f"{base_url}/api/catalog", headers={"X-Selector-Token": "test-token"})
        with urlopen(request) as response:
            payload = json.load(response)
        assert len(payload["objectives"]) == 10

        body = json.dumps({"objectiveIds": ["grounded_book_reflection"]}).encode()
        request = Request(
            f"{base_url}/api/confirm",
            data=body,
            headers={"Content-Type": "application/json", "X-Selector-Token": "test-token"},
            method="POST",
        )
        with urlopen(request) as response:
            assert json.load(response) == {"status": "confirmed"}
        assert state.result["objective_ids"] == ["grounded_book_reflection"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_rejects_an_unauthorized_request(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("selector", encoding="utf-8")
    state = selector.SelectorState(
        catalog=selector.load_catalog(selector.DEFAULT_CATALOG),
        ui_dir=tmp_path,
        token="test-token",
    )
    server = selector.SelectorServer(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        request = Request(f"http://127.0.0.1:{server.server_address[1]}/api/catalog")
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
