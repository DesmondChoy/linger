#!/usr/bin/env python3
"""Serve the local synthetic-journal objective selector and return its result."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import secrets
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG = REPO_ROOT / "synthetic-journal-evaluation" / "evaluation-objectives.yaml"
DEFAULT_UI = Path(__file__).resolve().parent.parent / "ui" / "dist"
INJECTION_OBJECTIVE = "untrusted_content_injection_resistance"


class SelectorError(ValueError):
    """A catalog or selection is invalid."""


@dataclass(frozen=True)
class Catalog:
    catalog_id: str
    digest: str
    families: tuple[dict[str, str], ...]
    objectives: tuple[dict[str, Any], ...]
    constraint_reason: str

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(objective["id"] for objective in self.objectives)


def load_catalog(path: Path) -> Catalog:
    raw = path.read_bytes()
    document = yaml.safe_load(raw)
    if not isinstance(document, dict):
        raise SelectorError("The evaluation-objective catalog must be a mapping.")

    entries = document.get("evaluation_objectives")
    if not isinstance(entries, list) or not entries:
        raise SelectorError("The catalog must contain a non-empty list of evaluation objectives.")

    families = load_families(document)
    family_ids = {family["id"] for family in families}

    objectives: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("menu"), dict):
            raise SelectorError("Every objective must contain an id and menu.")
        objective_id = entry.get("id")
        menu = entry["menu"]
        title = menu.get("title")
        summary = menu.get("summary")
        selection_hint = menu.get("selection_hint")
        family = menu.get("family")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (objective_id, title, summary, selection_hint, family)
        ):
            raise SelectorError(
                "Every objective needs a non-empty id, title, summary, selection hint, and family."
            )
        if family not in family_ids:
            raise SelectorError(f"Objective {objective_id} names an unknown menu family: {family}")
        combines = entry.get("composition", {}).get("combines_well_with", [])
        if not isinstance(combines, list) or not all(isinstance(value, str) for value in combines):
            raise SelectorError(f"Objective {objective_id} has an invalid combines_well_with list.")
        objectives.append(
            {
                "id": objective_id,
                "title": title,
                "summary": " ".join(summary.split()),
                "selectionHint": " ".join(selection_hint.split()),
                "family": family,
                "combinesWellWith": list(combines),
            }
        )

    ids = [objective["id"] for objective in objectives]
    if len(ids) != len(set(ids)):
        raise SelectorError("Evaluation objective IDs must be unique.")
    for objective in objectives:
        if unknown := [value for value in objective["combinesWellWith"] if value not in set(ids)]:
            raise SelectorError(
                f"Objective {objective['id']} combines with an unknown objective: {unknown[0]}"
            )

    constraint = document.get("selection_constraints", {}).get(INJECTION_OBJECTIVE, {})
    if constraint.get("requires_any_other_objective") is not True:
        raise SelectorError("The injection-resistance selection constraint is missing.")
    reason = constraint.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise SelectorError("The injection-resistance selection constraint needs a reason.")

    catalog_id = document.get("catalog_id")
    if not isinstance(catalog_id, str) or not catalog_id.strip():
        raise SelectorError("The catalog_id must be non-empty text.")

    return Catalog(
        catalog_id=catalog_id,
        digest=hashlib.sha256(raw).hexdigest(),
        families=families,
        objectives=tuple(objectives),
        constraint_reason=reason,
    )


def load_families(document: dict[str, Any]) -> tuple[dict[str, str], ...]:
    entries = document.get("menu_families")
    if not isinstance(entries, list) or not entries:
        raise SelectorError("The catalog must define menu_families.")

    families: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SelectorError("Every menu family must be a mapping.")
        family_id = entry.get("id")
        label = entry.get("label")
        summary = entry.get("summary")
        if not all(isinstance(value, str) and value.strip() for value in (family_id, label, summary)):
            raise SelectorError("Every menu family needs a non-empty id, label, and summary.")
        families.append({"id": family_id, "label": label, "summary": " ".join(summary.split())})

    if len({family["id"] for family in families}) != len(families):
        raise SelectorError("Menu family IDs must be unique.")
    return tuple(families)


def validate_selection(catalog: Catalog, selected_ids: Any) -> tuple[str, ...]:
    if not isinstance(selected_ids, list) or not selected_ids:
        raise SelectorError("Select at least one evaluation objective.")
    if not all(isinstance(objective_id, str) for objective_id in selected_ids):
        raise SelectorError("The selection must contain objective IDs only.")
    if len(selected_ids) != len(set(selected_ids)):
        raise SelectorError("The selection contains a duplicate objective.")

    known_ids = set(catalog.ids)
    if unknown := set(selected_ids) - known_ids:
        raise SelectorError(f"Unknown evaluation objective: {sorted(unknown)[0]}")
    if selected_ids == [INJECTION_OBJECTIVE]:
        raise SelectorError(catalog.constraint_reason)

    selected = set(selected_ids)
    return tuple(objective_id for objective_id in catalog.ids if objective_id in selected)


def confirmed_result(catalog: Catalog, selected_ids: tuple[str, ...]) -> dict[str, Any]:
    selected = set(selected_ids)
    return {
        "catalog_id": catalog.catalog_id,
        "catalog_sha256": catalog.digest,
        "confirmed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "objective_ids": list(selected_ids),
        "objectives": [
            {"id": objective["id"], "title": objective["title"]}
            for objective in catalog.objectives
            if objective["id"] in selected
        ],
    }


@dataclass
class SelectorState:
    catalog: Catalog
    ui_dir: Path
    token: str
    result: dict[str, Any] | None = None
    expired: bool = False


class SelectorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, state: SelectorState):
        self.state = state
        super().__init__(("127.0.0.1", 0), SelectorHandler)


class SelectorHandler(BaseHTTPRequestHandler):
    server: SelectorServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return secrets.compare_digest(
            self.headers.get("X-Selector-Token", ""), self.server.state.token
        )

    def _serve_asset(self, request_path: str) -> None:
        relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
        candidate = (self.server.state.ui_dir / relative).resolve()
        ui_root = self.server.state.ui_dir.resolve()
        if ui_root not in candidate.parents and candidate != ui_root:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/catalog":
            if not self._authorized():
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "This selector link is invalid or expired."})
                return
            catalog = self.server.state.catalog
            self._send_json(
                HTTPStatus.OK,
                {
                    "catalogId": catalog.catalog_id,
                    "families": list(catalog.families),
                    "objectives": list(catalog.objectives),
                    "constraints": [
                        {
                            "objectiveId": INJECTION_OBJECTIVE,
                            "requiresAnyOtherObjective": True,
                            "reason": catalog.constraint_reason,
                        }
                    ],
                },
            )
            return
        self._serve_asset(path)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/confirm":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "This selector link is invalid or expired."})
            return
        if self.server.state.result is not None:
            self._send_json(HTTPStatus.CONFLICT, {"error": "This selection is already confirmed."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise SelectorError("The confirmation payload is invalid.")
            payload = json.loads(self.rfile.read(length))
            selected_ids = validate_selection(self.server.state.catalog, payload.get("objectiveIds"))
        except (SelectorError, json.JSONDecodeError, AttributeError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
            return

        self.server.state.result = confirmed_result(self.server.state.catalog, selected_ids)
        self._send_json(HTTPStatus.OK, {"status": "confirmed"})
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--ui", type=Path, default=DEFAULT_UI)
    parser.add_argument("--timeout", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        catalog = load_catalog(args.catalog.resolve())
        ui_dir = args.ui.resolve()
        if not (ui_dir / "index.html").is_file():
            raise SelectorError(f"The selector UI is not built: {ui_dir}")
        if args.timeout < 1:
            raise SelectorError("Timeout must be at least one second.")
    except (OSError, SelectorError, yaml.YAMLError) as error:
        print(f"objective selector error: {error}", file=sys.stderr)
        return 1

    state = SelectorState(catalog=catalog, ui_dir=ui_dir, token=secrets.token_urlsafe(24))
    try:
        server = SelectorServer(state)
    except PermissionError as error:
        print("OBJECTIVE_SELECTOR_BIND_PERMISSION_REQUIRED=127.0.0.1", flush=True)
        print(f"objective selector bind permission required: {error}", file=sys.stderr)
        return 3
    except OSError as error:
        print(f"objective selector bind error: {error}", file=sys.stderr)
        return 1

    def expire() -> None:
        state.expired = True
        server.shutdown()

    timer = threading.Timer(args.timeout, expire)
    timer.daemon = True
    timer.start()
    port = server.server_address[1]
    print(f"OBJECTIVE_SELECTOR_URL=http://127.0.0.1:{port}/#token={state.token}", flush=True)

    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        return 130
    finally:
        timer.cancel()
        server.server_close()

    if state.result is None:
        message = "The selector timed out without confirmation." if state.expired else "The selector closed without confirmation."
        print(message, file=sys.stderr)
        return 2

    print(f"CONFIRMED_SELECTION_JSON={json.dumps(state.result, separators=(',', ':'))}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
