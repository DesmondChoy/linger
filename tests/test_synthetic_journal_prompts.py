"""Contract checks for reusable synthetic-journal prompt inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from evals.synthetic_journals.contracts import PersonaInput
from src.linger.agents.muse.models import (
    MemoryCandidateReasonCode,
    NoMemoryCandidateReasonCode,
)
from src.linger.agents.provenance.models import RiskCode


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "synthetic-journals"
PROMPTS = ROOT / "prompts" / "synthetic-journals"
PERSONAS = {
    "amina-yusuf",
    "idris-okafor",
    "maya-chen",
    "priya-nair",
    "tomas-alvarez",
}


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_five_persona_inputs_share_the_contract() -> None:
    paths = sorted((DATA / "personas").glob("*/input.json"))
    assert {path.parent.name for path in paths} == PERSONAS

    for path in paths:
        value = _json(path)
        assert set(value) == {
            "schema_version",
            "persona_id",
            "person_name",
            "background",
            "reading_list",
            "history_profile",
        }
        assert value["schema_version"] == 1
        assert value["persona_id"] == path.parent.name
        PersonaInput.model_validate(value)

        history = value["history_profile"]
        assert isinstance(history, dict)
        lengths = history["entry_length_mix"]
        assert isinstance(lengths, dict)
        assert sum(lengths.values()) == history["entry_count"]
        assert 2 <= history["generation_chunk_size"] <= 6

        attachments = history["attachments"]
        assert isinstance(attachments, dict)
        if attachments["target_count"]:
            assert attachments["allowed_kinds"]
            assert attachments["description_rules"]


def test_every_reading_list_entry_resolves_to_the_shipped_corpus() -> None:
    shipped: set[tuple[str, str]] = set()
    for catalog_path in (ROOT / "data" / "corpus").glob("*/*/catalog.json"):
        catalog = _json(catalog_path)
        shipped.add((str(catalog["work_id"]), str(catalog["book_version_id"])))

    assert shipped
    for path in (DATA / "personas").glob("*/input.json"):
        value = _json(path)
        reading_list = value["reading_list"]
        assert isinstance(reading_list, list) and reading_list
        for book in reading_list:
            assert isinstance(book, dict)
            assert (book["book_id"], book["book_version_id"]) in shipped


def test_prompt_templates_declare_their_runtime_variables() -> None:
    expected = {
        "01-create-journal-profile.md": {"PERSONA_INPUT_JSON"},
        "02-generate-journal-entries.md": {
            "PERSONA_INPUT_JSON",
            "JOURNAL_PROFILE_JSON",
            "PRIOR_ENTRIES_JSON",
            "CHUNK_REQUEST_JSON",
            "LIBRARIAN_EVIDENCE_RECORDS_JSON",
        },
        "03-annotate-journal-entries.md": {
            "JOURNAL_ENTRIES_JSON",
            "ANNOTATION_CONTEXT_JSON",
            "CAPTURE_POLICY_CONTRACT",
            "LIBRARIAN_EVIDENCE_RECORDS_JSON",
        },
        "04-review-journal-dataset.md": {
            "PERSONA_INPUT_JSON",
            "JOURNAL_PROFILE_JSON",
            "JOURNAL_ENTRIES_JSON",
        },
    }

    prompt_names = {
        path.name for path in PROMPTS.glob("*.md") if path.name != "README.md"
    }
    assert prompt_names == set(expected)
    for filename, variables in expected.items():
        text = (PROMPTS / filename).read_text(encoding="utf-8")
        for variable in variables:
            assert f"{{{{{variable}}}}}" in text


def test_input_schema_is_valid_json_and_names_the_shared_variables() -> None:
    schema = _json(DATA / "input.schema.json")
    assert schema["type"] == "object"
    assert set(schema["required"]) == {
        "schema_version",
        "persona_id",
        "person_name",
        "background",
        "reading_list",
        "history_profile",
    }


def test_capture_policy_is_versioned_and_stage_separated() -> None:
    policy = (DATA / "policies" / "capture-policy-v1.md").read_text(
        encoding="utf-8"
    )
    assert "Muse nomination" in policy
    assert "Provenance capture review" in policy
    assert "Memory & Policy outcome" in policy
    assert "withheld from Muse" in policy
    assert "src/linger/agents/provenance/models.py" not in policy
    assert "automatic_capture_disabled" in policy.split(
        "## Provenance capture review", maxsplit=1
    )[0]
    for code in (
        *get_args(MemoryCandidateReasonCode),
        *get_args(NoMemoryCandidateReasonCode),
        *get_args(RiskCode),
    ):
        assert f"`{code}`" in policy


def test_prompt_examples_match_strict_contract_field_names() -> None:
    profile = (PROMPTS / "01-create-journal-profile.md").read_text(encoding="utf-8")
    assert '"ordinary_or_low_stakes_entries"' in profile
    assert '"ordinary_or_low-stakes_entries"' not in profile
