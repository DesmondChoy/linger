"""Ground truth cannot authorize its own attack or alter a matched control."""

import hashlib
import json
from pathlib import Path

import pytest

from evals.synthetic_journals.models import RunConfiguration
from evals.synthetic_journals.replay_support import replay_support_for
from evals.synthetic_journals.validate_scenario import ScenarioValidationError, validate_scenario_files


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "synthetic-journal-evaluation/scenarios/line-attack-response-and-capture--muse-provenance--2026-10-01"


def _validate(tmp_path, mutate):
    backstory = json.loads((SCENARIO / "backstory.json").read_text())
    truth = json.loads((SCENARIO / "ground-truth.json").read_text())
    mutate(backstory, truth)
    raw = (json.dumps(backstory) + "\n").encode()
    truth["backstory_sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / "backstory.json").write_bytes(raw)
    (tmp_path / "ground-truth.json").write_text(json.dumps(truth))
    return validate_scenario_files(tmp_path / "backstory.json", tmp_path / "ground-truth.json")


def test_direct_line_fixture_is_valid_and_keeps_ground_truth_proposed():
    backstory, truth = validate_scenario_files(SCENARIO / "backstory.json", SCENARIO / "ground-truth.json")
    assert len(backstory.scenes) == 4 and len(truth.proposals) == 8
    assert not backstory.props
    assert truth.ground_truth_status == "proposed"
    support = replay_support_for(backstory.objective_ids)
    assert support.module == "evals.synthetic_journals.line_attack_replay"


def test_line_attack_configuration_cannot_also_request_curation_loop():
    configuration = json.loads((
        ROOT / "synthetic-journal-evaluation/generation-presets/line-attack-response-and-capture-controls.json"
    ).read_text())
    configuration["curation_recall_loop"] = {"curation_rounds": 1, "repetitions": 1}

    with pytest.raises(ValueError, match="exactly one mix or curation recall loop"):
        RunConfiguration.model_validate(configuration)


@pytest.mark.parametrize(("change", "reason"), [
    (lambda b, g: b["scenes"][0].update(fresh_session=False), "fresh-session"),
    (lambda b, g: g["proposals"][1]["line_attack"].update(source_line_id="line-reply-clean"), "current Line"),
    (lambda b, g: g["proposals"][1]["line_attack"].update(paired_scene_id="scene-line-memory-clean"), "matched pair"),
    (lambda b, g: g["proposals"][1]["line_attack"].update(forbidden_reply="unrelated"), "forbidden reply"),
    (lambda b, g: g["proposals"][3]["line_attack"].update(forbidden_reply="control-marker"), "clean Line"),
    (lambda b, g: g["proposals"][2]["line_capture"].update(required_spans=[]), "must require"),
    (lambda b, g: g["proposals"][0]["line_capture"].update(required_spans=g["proposals"][0]["line_capture"]["allowed_spans"]), "safe refusal"),
    (lambda b, g: g["proposals"][0]["line_capture"].update(allowed_spans=[g["proposals"][1]["line_attack"]["attack_span"]]), "cannot authorize"),
    (lambda b, g: b["lines"][0].update(text=b["lines"][0]["text"]+" extra"), "only by the attack"),
    (lambda b, g: g["proposals"][1]["line_attack"]["attack_span"].update(end_codepoint=10000), "exact source bytes"),
    (lambda b, g: g["proposals"][0].update(objective_id="weak_evidence_safe_decline"), "capture Objective"),
])
def test_invalid_line_security_contract_is_rejected(tmp_path, change, reason):
    with pytest.raises(ScenarioValidationError, match=reason):
        _validate(tmp_path, change)


def test_attack_span_bytes_are_verified_even_when_the_backstory_hash_is_current(tmp_path):
    def change(backstory, truth):
        attack = truth["proposals"][1]["line_attack"]["attack_span"]
        attack["start_codepoint"] -= 1
    with pytest.raises(ScenarioValidationError, match="exact source bytes"):
        _validate(tmp_path, change)
