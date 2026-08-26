#!/usr/bin/env python3
"""Serve a local Ground truth review app and return the human decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import sys
import tempfile
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.sculptor.harness import ExpectedCurationProposal  # noqa: E402
from evals.synthetic_journals.adoption import (  # noqa: E402
    build_ground_truth_adoption,
    proposed_ground_truth_sha256,
)
from evals.synthetic_journals.models import (  # noqa: E402
    GroundTruthProposal,
    ProposedGroundTruth,
    SyntheticBackstory,
)
from evals.synthetic_journals.validate_package import (  # noqa: E402
    PackageValidationError,
    validate_package_files,
)


DEFAULT_UI = Path(__file__).resolve().parent.parent / "ui" / "dist"
ADOPTION_FILENAME = "ground-truth-adoption.json"
SUPPORTED_REPLAYS = {
    "reviewed_automatic_memory_capture": "capture",
    "bounded_memory_curation": "bounded curation",
}


class ReviewError(ValueError):
    """The review request or decision is invalid."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _proposal_summary(proposal: GroundTruthProposal) -> str:
    if proposal.capture is not None:
        return (
            "Capture candidate"
            if proposal.capture.kind == "capture_candidate"
            else "No capture candidate"
        )
    if proposal.curation is not None:
        expected = proposal.curation.expected
        if isinstance(expected, ExpectedCurationProposal):
            labels = {
                "link_duplicates": "Link duplicates",
                "update_derived_summary": "Update derived summary",
                "assign_topic_group": "Assign topic group",
            }
            return labels[expected.action.action]
        return "No curation proposal"
    if proposal.prop_relevance:
        relevant = sum(
            item.relevance == "relevant" for item in proposal.prop_relevance
        )
        distractors = len(proposal.prop_relevance) - relevant
        return f"{relevant} relevant · {distractors} distractor"
    return "Review expected behavior"


def _source_roles(proposal: GroundTruthProposal) -> dict[str, str]:
    roles = {
        item.prop_id: item.relevance.replace("_", " ")
        for item in proposal.prop_relevance
    }
    if proposal.curation is None:
        return roles
    expected = proposal.curation.expected
    if isinstance(expected, ExpectedCurationProposal):
        for source_id in expected.action.source_memory_ids:
            roles[source_id] = "expected source"
    return roles


def _span_payload(proposal: GroundTruthProposal) -> list[dict[str, Any]]:
    spans = [item.model_dump(mode="json") for item in proposal.exact_spans]
    if proposal.capture is not None and proposal.capture.kind == "capture_candidate":
        spans.append(proposal.capture.span.model_dump(mode="json"))
    return spans


def build_review_payload(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    backstory_path: Path,
    ground_truth_path: Path,
    backstory_bytes: bytes,
    ground_truth_bytes: bytes,
    report_path: Path | None,
) -> dict[str, Any]:
    """Join package entities into a legible, deterministic review projection."""

    lines = {item.line_id: item for item in backstory.lines}
    props = {item.prop_id: item for item in backstory.props}
    offline_inputs = {
        item.offline_input_id: item for item in backstory.offline_inputs
    }
    proposals = {
        (item.scene_id, item.objective_id): item
        for item in ground_truth.proposals
    }
    rows: list[dict[str, Any]] = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        for objective_id in scene.objective_ids:
            proposal = proposals[(scene.scene_id, objective_id)]
            roles = _source_roles(proposal)
            inputs: list[dict[str, Any]] = []
            for line_id in scene.line_ids:
                line = lines[line_id]
                inputs.append(
                    {
                        "kind": "Line",
                        "id": line.line_id,
                        "order": line.order,
                        "text": line.text,
                        "role": None,
                    }
                )
            for prop_id in scene.prop_ids:
                prop = props[prop_id]
                lifecycle = next(
                    item.state
                    for item in prop.lifecycle
                    if item.scene_id == scene.scene_id
                )
                inputs.append(
                    {
                        "kind": "Prop",
                        "id": prop.prop_id,
                        "order": None,
                        "text": prop.source_text,
                        "role": roles.get(prop.prop_id, "context"),
                        "lifecycle": lifecycle,
                    }
                )
            for input_id in scene.offline_input_ids:
                item = offline_inputs[input_id]
                inputs.append(
                    {
                        "kind": "Offline input",
                        "id": item.offline_input_id,
                        "order": item.order,
                        "text": item.text,
                        "role": item.kind,
                        "propIds": list(item.prop_ids),
                    }
                )
            rows.append(
                {
                    "proposalId": proposal.proposal_id,
                    "sceneId": scene.scene_id,
                    "sceneOrder": scene.order,
                    "objectiveId": objective_id,
                    "freshSession": scene.fresh_session,
                    "summary": _proposal_summary(proposal),
                    "inputs": inputs,
                    "expectedOutcomes": list(proposal.expected_outcomes),
                    "prohibitedOutcomes": list(proposal.prohibited_outcomes),
                    "spans": _span_payload(proposal),
                    "evidence": [
                        item.model_dump(mode="json") for item in proposal.evidence
                    ],
                    "propRelevance": [
                        item.model_dump(mode="json")
                        for item in proposal.prop_relevance
                    ],
                    "pairing": (
                        proposal.pairing.model_dump(mode="json")
                        if proposal.pairing is not None
                        else None
                    ),
                    "capture": (
                        proposal.capture.model_dump(mode="json")
                        if proposal.capture is not None
                        else None
                    ),
                    "curation": (
                        proposal.curation.model_dump(mode="json")
                        if proposal.curation is not None
                        else None
                    ),
                }
            )

    objective_ids = list(backstory.objective_ids)
    replay_name = (
        SUPPORTED_REPLAYS.get(objective_ids[0])
        if len(objective_ids) == 1
        else None
    )
    report_text = ""
    if report_path is not None:
        report_text = report_path.read_text(encoding="utf-8")
    return {
        "package": {
            "backstoryPath": str(backstory_path),
            "groundTruthPath": str(ground_truth_path),
            "backstorySha256": _sha256(backstory_bytes),
            "proposedGroundTruthSha256": proposed_ground_truth_sha256(
                ground_truth_bytes
            ),
            "groundTruthStatus": ground_truth.ground_truth_status,
            "objectiveIds": objective_ids,
            "backstoryId": backstory.backstory.backstory_id,
            "backstoryContext": backstory.backstory.context,
            "personId": backstory.backstory.person_id,
        },
        "report": {
            "path": str(report_path) if report_path is not None else None,
            "text": report_text,
        },
        "replay": {
            "supported": replay_name is not None,
            "name": replay_name,
            "confirmLabel": (
                "Confirm and run evaluation"
                if replay_name is not None
                else "Confirm Ground truth"
            ),
            "note": (
                "Confirmation returns to the agent, which will start one "
                f"provider-backed {replay_name} replay. It may make billable "
                "model calls and write evaluation telemetry."
                if replay_name is not None
                else "This Objective has no implemented replay. Confirmation "
                "records adoption only."
            ),
        },
        "rows": rows,
    }


@dataclass
class ReviewState:
    backstory_path: Path
    ground_truth_path: Path
    adoption_path: Path
    ui_dir: Path
    reviewer_id: str
    token: str
    backstory_bytes: bytes
    ground_truth_bytes: bytes
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    expired: bool = False

    @property
    def proposal_ids(self) -> tuple[str, ...]:
        return tuple(row["proposalId"] for row in self.payload["rows"])


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, state: ReviewState):
        self.state = state
        super().__init__(("127.0.0.1", 0), ReviewHandler)


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

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
            self.headers.get("X-Review-Token", ""), self.server.state.token
        )

    def _serve_asset(self, request_path: str) -> None:
        relative = (
            "index.html"
            if request_path in ("", "/")
            else request_path.lstrip("/")
        )
        candidate = (self.server.state.ui_dir / relative).resolve()
        ui_root = self.server.state.ui_dir.resolve()
        if ui_root not in candidate.parents and candidate != ui_root:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = candidate.read_bytes()
        content_type = (
            mimetypes.guess_type(candidate.name)[0]
            or "application/octet-stream"
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/review":
            if not self._authorized():
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "This review link is invalid or expired."},
                )
                return
            self._send_json(HTTPStatus.OK, self.server.state.payload)
            return
        self._serve_asset(path)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/decision":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "This review link is invalid or expired."},
            )
            return
        state = self.server.state
        if state.result is not None:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"error": "This review already has a decision."},
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ReviewError("The review decision payload is invalid.")
            payload = json.loads(self.rfile.read(length))
            result = _handle_decision(state, payload)
        except (
            ReviewError,
            PackageValidationError,
            json.JSONDecodeError,
            OSError,
        ) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
            return

        state.result = result
        self._send_json(HTTPStatus.OK, {"status": result["decision"]})
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def _validate_id_list(
    value: Any,
    *,
    label: str,
    known_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReviewError(f"{label} must contain proposal IDs only.")
    if len(value) != len(set(value)):
        raise ReviewError(f"{label} contains a duplicate proposal ID.")
    unknown = set(value) - set(known_ids)
    if unknown:
        unknown_id = sorted(unknown)[0]
        raise ReviewError(f"{label} contains an unknown proposal ID: {unknown_id}")
    return tuple(value)


def _assert_package_unchanged(state: ReviewState) -> ProposedGroundTruth:
    if state.backstory_path.read_bytes() != state.backstory_bytes:
        raise ReviewError("backstory.json changed while review was open.")
    if state.ground_truth_path.read_bytes() != state.ground_truth_bytes:
        raise ReviewError("ground-truth.json changed while review was open.")
    _, ground_truth = validate_package_files(
        state.backstory_path,
        state.ground_truth_path,
    )
    return ground_truth


def _write_new_file(path: Path, text: str) -> None:
    if path.exists():
        raise ReviewError(f"Adoption output already exists: {path}")
    path.parent.mkdir(parents=False, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, path)
    except FileExistsError as error:
        raise ReviewError(f"Adoption output already exists: {path}") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def _handle_decision(state: ReviewState, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ReviewError("The review decision must be an object.")
    action = payload.get("action")
    if action not in {"confirm", "make_changes"}:
        raise ReviewError("Choose Confirm or Make Changes.")
    reviewed = _validate_id_list(
        payload.get("reviewedProposalIds", []),
        label="reviewedProposalIds",
        known_ids=state.proposal_ids,
    )
    flagged = _validate_id_list(
        payload.get("flaggedProposalIds", []),
        label="flaggedProposalIds",
        known_ids=state.proposal_ids,
    )
    overlap = set(reviewed) & set(flagged)
    if overlap:
        proposal_id = sorted(overlap)[0]
        raise ReviewError(
            f"Proposal {proposal_id} cannot be both approved and flagged."
        )
    common = {
        "decision": action,
        "backstory_sha256": _sha256(state.backstory_bytes),
        "proposed_ground_truth_sha256": proposed_ground_truth_sha256(
            state.ground_truth_bytes
        ),
        "reviewed_proposal_ids": list(reviewed),
        "flagged_proposal_ids": list(flagged),
        "unchecked_proposal_ids": [
            proposal_id
            for proposal_id in state.proposal_ids
            if proposal_id not in set(reviewed)
        ],
        "objective_ids": state.payload["package"]["objectiveIds"],
    }
    if action == "make_changes":
        return common
    if flagged:
        raise ReviewError("Confirm cannot include proposals flagged for changes.")
    if set(reviewed) != set(state.proposal_ids) or len(reviewed) != len(
        state.proposal_ids
    ):
        raise ReviewError("Review every Ground truth row before confirming.")

    ground_truth = _assert_package_unchanged(state)
    adoption = build_ground_truth_adoption(
        ground_truth,
        state.ground_truth_bytes,
        reviewer_id=state.reviewer_id,
    )
    rendered = adoption.model_dump_json(indent=2) + "\n"
    _write_new_file(state.adoption_path, rendered)
    return {
        **common,
        "adoption_path": str(state.adoption_path),
        "adoption_sha256": _sha256(rendered.encode("utf-8")),
        "adopted_ground_truth_identity": adoption.adopted_ground_truth_identity,
        "replay_supported": state.payload["replay"]["supported"],
    }


def create_review_state(args: argparse.Namespace) -> ReviewState:
    backstory_path = args.backstory.resolve()
    ground_truth_path = args.ground_truth.resolve()
    adoption_path = (
        args.adoption.resolve()
        if args.adoption is not None
        else backstory_path.with_name(ADOPTION_FILENAME)
    )
    if backstory_path.parent != ground_truth_path.parent:
        raise ReviewError("Backstory and Ground truth must be sibling files.")
    if adoption_path.parent != backstory_path.parent:
        raise ReviewError("Ground truth adoption must be written beside the package.")
    if adoption_path.exists():
        raise ReviewError(f"Adoption output already exists: {adoption_path}")
    reviewer_id = args.reviewer_id.strip()
    if not reviewer_id:
        raise ReviewError("A human reviewer ID is required.")
    ui_dir = args.ui.resolve()
    if not (ui_dir / "index.html").is_file():
        raise ReviewError(f"The review UI is not built: {ui_dir}")
    if args.timeout < 1:
        raise ReviewError("Timeout must be at least one second.")

    backstory, ground_truth = validate_package_files(
        backstory_path,
        ground_truth_path,
    )
    backstory_bytes = backstory_path.read_bytes()
    ground_truth_bytes = ground_truth_path.read_bytes()
    report_path = backstory_path.with_name("pre-generation-report.md")
    if not report_path.is_file():
        report_path = None
    payload = build_review_payload(
        backstory,
        ground_truth,
        backstory_path=backstory_path,
        ground_truth_path=ground_truth_path,
        backstory_bytes=backstory_bytes,
        ground_truth_bytes=ground_truth_bytes,
        report_path=report_path,
    )
    return ReviewState(
        backstory_path=backstory_path,
        ground_truth_path=ground_truth_path,
        adoption_path=adoption_path,
        ui_dir=ui_dir,
        reviewer_id=reviewer_id,
        token=secrets.token_urlsafe(24),
        backstory_bytes=backstory_bytes,
        ground_truth_bytes=ground_truth_bytes,
        payload=payload,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--ui", type=Path, default=DEFAULT_UI)
    parser.add_argument("--timeout", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        state = create_review_state(args)
    except (OSError, PackageValidationError, ReviewError) as error:
        print(f"Ground truth review error: {error}", file=sys.stderr)
        return 1
    try:
        server = ReviewServer(state)
    except PermissionError as error:
        print(
            "GROUND_TRUTH_REVIEW_BIND_PERMISSION_REQUIRED=127.0.0.1",
            flush=True,
        )
        print(f"Ground truth review bind permission required: {error}", file=sys.stderr)
        return 3
    except OSError as error:
        print(f"Ground truth review bind error: {error}", file=sys.stderr)
        return 1

    def expire() -> None:
        state.expired = True
        server.shutdown()

    timer = threading.Timer(args.timeout, expire)
    timer.daemon = True
    timer.start()
    port = server.server_address[1]
    print(
        f"GROUND_TRUTH_REVIEW_URL=http://127.0.0.1:{port}/#token={state.token}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        return 130
    finally:
        timer.cancel()
        server.server_close()

    if state.result is None:
        message = (
            "The Ground truth review timed out without a decision."
            if state.expired
            else "The Ground truth review closed without a decision."
        )
        print(message, file=sys.stderr)
        return 2
    print(
        "GROUND_TRUTH_REVIEW_JSON="
        + json.dumps(state.result, separators=(",", ":")),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
