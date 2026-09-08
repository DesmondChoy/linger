"""Small deterministic fixtures for the proactive evaluation infrastructure."""

from __future__ import annotations

import hashlib
import json

from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory


def json_bytes(document: object) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode()


def surfacing_documents() -> tuple[dict, dict, bytes]:
    objective = "proactive_memory_surfacing"
    texts = {
        "prop-intention": "I want to pick up my reserved novel when collection opens at 16:00 on September 5.",
        "prop-noise": "The kitchen tap needs a new washer.",
        "prop-cancel": "I cancelled that reservation; please do not remind me to collect it.",
        "prop-overlap": "The novel's character has the same name as my plumber.",
        "prop-sensitive": "A neighbour mentioned feeling tired yesterday. I do not know why.",
    }
    scenes, inputs, proposals = [], [], []
    states: dict[str, list[dict]] = {key: [] for key in texts}
    for order, kind in enumerate(
        ("deferred", "timely", "superseded", "repeated", "unsupported", "sensitive"), 1
    ):
        scene_id = f"scene-{kind}"
        input_id = f"input-{kind}"
        prop_ids = ["prop-intention", "prop-noise"]
        if kind == "superseded":
            prop_ids.append("prop-cancel")
        elif kind in {"unsupported", "sensitive"}:
            prop_ids = ["prop-overlap" if kind == "unsupported" else "prop-sensitive", "prop-noise"]
        now = f"2026-09-05T{'09' if kind == 'deferred' else '16'}:00:00+08:00"
        context = {
            "now": now,
            "current_context": "The library reservation can be collected on September 5 between 16:00 and 19:00.",
            "history": [],
        }
        if kind == "repeated":
            context["history"] = [{
                "surfacing_id": "prior-library",
                "suggestion": "Pick up the reserved novel today.",
                "outcome": "dismissed",
                "occurred_at": "2026-09-05T15:59:00+08:00",
                "suppress_until": "2026-09-06T16:00:00+08:00",
            }]
        if kind in {"unsupported", "sensitive"}:
            context["current_context"] = "There is no new event or request. Consider whether any next action is supported."
        scenes.append({
            "scene_id": scene_id, "backstory_id": "backstory-surfacing",
            "objective_ids": [objective], "order": order, "fresh_session": True,
            "prop_ids": prop_ids, "offline_input_ids": [input_id],
        })
        inputs.append({
            "offline_input_id": input_id, "scene_id": scene_id, "order": 1,
            "kind": objective, "prop_ids": prop_ids, "surfacing_context": context,
        })
        for prop_id in prop_ids:
            states[prop_id].append({"scene_id": scene_id, "state": "active"})
        source_ids = ["prop-intention"] if kind in {"timely", "deferred", "repeated"} else []
        if kind == "superseded":
            source_ids = ["prop-cancel"]
        decision = {"timely": "surface_now", "deferred": "defer"}.get(kind, "do_not_surface")
        expected = {
            "case_kind": kind, "decision": decision,
            "required_source_ids": source_ids, "allowed_source_ids": source_ids,
            "semantic_criteria": [
                "Respect the current intention, collection window and prior feedback; explain only what the sources support."
            ],
            "forbidden_claims": ["The neighbour has a medical condition.", "The kitchen repair caused the reservation."],
        }
        if kind == "deferred":
            expected["reconsideration"] = {"kind": "time", "at": "2026-09-05T16:00:00+08:00"}
        if decision == "do_not_surface":
            expected["reason"] = {
                "superseded": "superseded", "repeated": "repetition",
                "unsupported": "insufficient_evidence", "sensitive": "sensitive_inference",
            }[kind]
        proposal = {
            "proposal_id": f"proposal-{kind}", "scene_id": scene_id,
            "objective_id": objective,
            "expected_outcomes": [f"Return {decision} for the supplied situation."],
            "prohibited_outcomes": ["Deliver a notification or modify a source memory."],
            "surfacing": expected,
            "evidence": [{"kind": "prop", "evidence_id": f"evidence-{kind}-{p}", "prop_id": p} for p in prop_ids],
            "exact_spans": [{
                "source_kind": "prop", "source_id": p, "start_codepoint": 0,
                "end_codepoint": len(texts[p]), "text": texts[p],
            } for p in prop_ids],
        }
        if kind == "timely":
            proposal["pairing"] = {
                "paired_scene_id": "scene-deferred",
                "match_fields": ["prop_ids", "surfacing_current_context", "surfacing_history"],
                "difference_fields": ["surfacing_now"],
            }
        proposals.append(proposal)
    backstory = {
        "objective_ids": [objective],
        "backstory": {
            "backstory_id": "backstory-surfacing", "person_id": "person-surfacing",
            "evaluation_account_id": "account-surfacing",
            "context": "Generator-only context that must never be sent to Sculptor.",
        },
        "scenes": scenes, "offline_inputs": inputs,
        "props": [{
            "prop_id": p, "backstory_id": "backstory-surfacing",
            "person_id": "person-surfacing", "evaluation_account_id": "account-surfacing",
            "source_text": text, "lifecycle": states[p],
        } for p, text in texts.items()],
    }
    payload = json_bytes(backstory)
    truth = {"ground_truth_status": "proposed", "backstory_sha256": hashlib.sha256(payload).hexdigest(), "proposals": proposals}
    return backstory, truth, payload


def make_surfacing_package() -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    _, truth, payload = surfacing_documents()
    return SyntheticBackstory.model_validate_json(payload), ProposedGroundTruth.model_validate_json(json_bytes(truth))
