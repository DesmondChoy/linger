"""Contract regressions for synthetic book Ground truth and replay planning."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.book_contract import (
    BookContractError,
    compile_book_replay_plan,
)
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_scenario import validate_scenario

ROOT = Path(__file__).resolve().parents[1]
VERSION = "pg11-v01b38ea4"
CHAPTERS = ROOT / "data/corpus/alice-in-wonderland" / VERSION / "chapters"
QUOTE = "“Who are _you?_” said the Caterpillar."
FORBIDDEN = "Off with her head!"


def _excerpt(
    chapter_id: str, filename: str, evidence_id: str, text: str
) -> dict[str, object]:
    source = (CHAPTERS / filename).read_text(encoding="utf-8")
    start = source.index(text)
    return {
        "kind": "corpus_text",
        "evidence_id": evidence_id,
        "chapter_id": chapter_id,
        "start_codepoint": start,
        "end_codepoint": start + len(text),
        "text": text,
    }


def _documents(
    *,
    objective_ids: tuple[str, ...] = (
        "grounded_book_reflection",
        "spoiler_boundary_clarification",
    ),
) -> tuple[dict[str, object], dict[str, object]]:
    prop_text = "Alice and the Caterpillar's questions about identity stayed with me."
    infer_line = "Why does Alice struggle to explain who she is?"
    clarify_line = "What happens after Alice's conversation about identity?"
    personal_line = "I also struggle to explain who I am when plans change."
    all_scenes = {
        "infer": {
            "scene_id": "scene-infer",
            "backstory_id": "backstory-book",
            "objective_ids": list(objective_ids),
            "order": 1,
            "fresh_session": True,
            "prop_ids": ["prop-event"],
            "line_ids": ["line-infer"],
            "offline_input_ids": [],
        },
        "clarify": {
            "scene_id": "scene-clarify",
            "backstory_id": "backstory-book",
            "objective_ids": ["spoiler_boundary_clarification"],
            "order": 2,
            "fresh_session": True,
            "prop_ids": ["prop-event"],
            "line_ids": ["line-clarify"],
            "offline_input_ids": [],
        },
        "personal": {
            "scene_id": "scene-personal",
            "backstory_id": "backstory-book",
            "objective_ids": ["grounded_book_reflection"],
            "order": 3,
            "fresh_session": True,
            "prop_ids": [],
            "line_ids": ["line-personal"],
            "offline_input_ids": [],
        },
    }
    selected_scenes = [all_scenes["infer"]]
    selected_lines = [
        {
            "line_id": "line-infer",
            "scene_id": "scene-infer",
            "order": 1,
            "text": infer_line,
        }
    ]
    if "spoiler_boundary_clarification" in objective_ids:
        selected_scenes.append(all_scenes["clarify"])
        selected_lines.append(
            {
                "line_id": "line-clarify",
                "scene_id": "scene-clarify",
                "order": 1,
                "text": clarify_line,
            }
        )
    if "grounded_book_reflection" in objective_ids:
        selected_scenes.append(all_scenes["personal"])
        selected_lines.append(
            {
                "line_id": "line-personal",
                "scene_id": "scene-personal",
                "order": 1,
                "text": personal_line,
            }
        )
    for order, scene in enumerate(selected_scenes, start=1):
        scene["order"] = order

    backstory = {
        "objective_ids": list(objective_ids),
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": "backstory-book",
            "person_id": "person-book",
            "evaluation_account_id": "account-book",
            "context": "A reader connects personal change to Alice in Wonderland.",
        },
        "props": [
            {
                "prop_id": "prop-event",
                "backstory_id": "backstory-book",
                "person_id": "person-book",
                "evaluation_account_id": "account-book",
                "source_text": prop_text,
                "lifecycle": [
                    {"scene_id": scene["scene_id"], "state": "active"}
                    for scene in selected_scenes
                    if scene["prop_ids"]
                ],
            }
        ],
        "scenes": selected_scenes,
        "lines": selected_lines,
        "offline_inputs": [],
    }
    backstory_bytes = json.dumps(backstory, sort_keys=True).encode()
    support = _excerpt(
        f"{VERSION}-ch05", "05-advice-from-a-caterpillar.md", "support", QUOTE
    )
    later = _excerpt(
        f"{VERSION}-ch08", "08-the-queens-croquet-ground.md", "later", FORBIDDEN
    )
    prop_span = {
        "source_kind": "prop",
        "source_id": "prop-event",
        "start_codepoint": 0,
        "end_codepoint": len(prop_text),
        "text": prop_text,
    }
    infer_span = {
        "source_kind": "line",
        "source_id": "line-infer",
        "start_codepoint": 0,
        "end_codepoint": len(infer_line),
        "text": infer_line,
    }
    clarify_span = {
        "source_kind": "line",
        "source_id": "line-clarify",
        "start_codepoint": 0,
        "end_codepoint": len(clarify_line),
        "text": clarify_line,
    }
    facts = [
        {
            "scene_id": "scene-infer",
            "scope": {
                "kind": "librarian_inferred",
                "work_id": "pg11",
                "book_version_id": VERSION,
                "authorised_prop_ids": ["prop-event"],
                "supporting_evidence_ids": ["support"],
            },
            "basis_spans": [prop_span, infer_span],
            "evidence": [support, later],
        }
    ]
    proposals: list[dict[str, object]] = []
    if "grounded_book_reflection" in objective_ids:
        proposals.extend(
            [
                {
                    "proposal_id": "grounded-infer",
                    "scene_id": "scene-infer",
                    "objective_id": "grounded_book_reflection",
                    "expected_outcomes": ["Use the permitted passage."],
                    "prohibited_outcomes": ["Use another passage."],
                    "pairing": {
                        "paired_scene_id": "scene-personal",
                        "match_fields": ["backstory_id", "fresh_session"],
                        "difference_fields": ["prop_ids", "line_text"],
                    },
                    "book_expectation": {
                        "kind": "grounded_book_reflection",
                        "retrieval": "required",
                        "permitted_evidence_ids": ["support"],
                        "exact_quotation_evidence_ids": ["support"],
                    },
                },
                {
                    "proposal_id": "grounded-personal",
                    "scene_id": "scene-personal",
                    "objective_id": "grounded_book_reflection",
                    "expected_outcomes": ["Reflect without retrieval."],
                    "prohibited_outcomes": ["Retrieve book text."],
                    "pairing": {
                        "paired_scene_id": "scene-infer",
                        "match_fields": ["backstory_id", "fresh_session"],
                        "difference_fields": ["prop_ids", "line_text"],
                    },
                    "book_expectation": {
                        "kind": "grounded_book_reflection",
                        "retrieval": "not_required",
                    },
                },
            ]
        )
    if "spoiler_boundary_clarification" in objective_ids:
        facts.append(
            {
                "scene_id": "scene-clarify",
                "scope": {
                    "kind": "clarification",
                    "work_id": "pg11",
                    "book_version_id": VERSION,
                    "authorised_prop_ids": ["prop-event"],
                },
                "basis_spans": [prop_span, clarify_span],
                "evidence": [later | {"evidence_id": "later-clarify"}],
            }
        )
        proposals.extend(
            [
                {
                    "proposal_id": "spoiler-infer",
                    "scene_id": "scene-infer",
                    "objective_id": "spoiler_boundary_clarification",
                    "expected_outcomes": ["Infer the supported boundary."],
                    "prohibited_outcomes": ["Reveal a later fact."],
                    "pairing": {
                        "paired_scene_id": "scene-clarify",
                        "match_fields": ["backstory_id", "fresh_session", "prop_ids"],
                        "difference_fields": ["line_text"],
                    },
                    "book_expectation": {
                        "kind": "spoiler_boundary_clarification",
                        "forbidden_later_evidence_ids": ["later"],
                    },
                },
                {
                    "proposal_id": "spoiler-clarify",
                    "scene_id": "scene-clarify",
                    "objective_id": "spoiler_boundary_clarification",
                    "expected_outcomes": ["Ask for clarification."],
                    "prohibited_outcomes": ["Reveal a later fact."],
                    "pairing": {
                        "paired_scene_id": "scene-infer",
                        "match_fields": ["backstory_id", "fresh_session", "prop_ids"],
                        "difference_fields": ["line_text"],
                    },
                    "book_expectation": {
                        "kind": "spoiler_boundary_clarification",
                        "forbidden_later_evidence_ids": ["later-clarify"],
                    },
                },
            ]
        )
    ground_truth = {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "book_scene_facts": facts,
        "proposals": proposals,
    }
    return backstory, ground_truth


def _validated(objective_ids: tuple[str, ...]):
    backstory_doc, ground_truth_doc = _documents(objective_ids=objective_ids)
    backstory_bytes = json.dumps(backstory_doc, sort_keys=True).encode()
    backstory = SyntheticBackstory.model_validate_json(json.dumps(backstory_doc))
    ground_truth = ProposedGroundTruth.model_validate_json(json.dumps(ground_truth_doc))
    validate_scenario(
        backstory, ground_truth, backstory_bytes=backstory_bytes, run_configurations={}
    )
    return compile_book_replay_plan(backstory, ground_truth)


@pytest.mark.parametrize(
    "objective_ids",
    [
        ("grounded_book_reflection",),
        ("spoiler_boundary_clarification",),
        ("grounded_book_reflection", "spoiler_boundary_clarification"),
        ("spoiler_boundary_clarification", "grounded_book_reflection"),
    ],
)
def test_compiler_supports_each_book_selection_and_both_orders(
    objective_ids: tuple[str, ...],
) -> None:
    plan = _validated(objective_ids)
    assert plan.objective_ids == frozenset(objective_ids)
    assert sum(len(scene.proposals) for scene in plan.scenes) == sum(
        len(scene.scene.objective_ids) for scene in plan.scenes
    )


def test_book_objective_rejects_generic_or_legacy_ground_truth() -> None:
    _, ground_truth = _documents(objective_ids=("grounded_book_reflection",))
    proposal = ground_truth["proposals"][0]  # type: ignore[index]
    proposal["grounding"] = {
        "primary_behavior": "non_grounded_reflection",
        "expected": {"kind": "ungrounded_release"},
    }
    with pytest.raises(ValidationError):
        ProposedGroundTruth.model_validate_json(json.dumps(ground_truth))


@pytest.mark.parametrize(
    "mutation",
    ["extra_proposal", "missing_proposal", "inactive_prop", "confirmed_spoiler"],
)
def test_compiler_rejects_unsupported_scene_contract(mutation: str) -> None:
    content, truth = _documents()
    if mutation == "extra_proposal":
        truth["proposals"][0]["scene_id"] = "scene-clarify"
    elif mutation == "missing_proposal":
        truth["proposals"].pop(0)
    elif mutation == "inactive_prop":
        extra = json.loads(json.dumps(content["props"][0]))
        extra["prop_id"] = "prop-inactive"
        extra["lifecycle"] = [{"scene_id": "scene-infer", "state": "inactive"}]
        content["props"].append(extra)
        content["scenes"][0]["prop_ids"].append("prop-inactive")
        truth["proposals"][2]["pairing"]["match_fields"].remove("prop_ids")
        truth["proposals"][3]["pairing"]["match_fields"].remove("prop_ids")
    else:
        truth["book_scene_facts"][0]["scope"] = {
            "kind": "reader_confirmed",
            "work_id": "pg11",
            "book_version_id": VERSION,
            "safe_ceiling_chapter": 5,
        }
        truth["book_scene_facts"][0]["basis_spans"] = []
    backstory = SyntheticBackstory.model_validate_json(json.dumps(content))
    ground_truth = ProposedGroundTruth.model_validate_json(json.dumps(truth))
    with pytest.raises(BookContractError):
        compile_book_replay_plan(backstory, ground_truth)


def test_compiler_rejects_wrong_chapter_identity_for_equal_text() -> None:
    backstory_doc, ground_truth_doc = _documents(
        objective_ids=("grounded_book_reflection",)
    )
    ground_truth_doc["book_scene_facts"][0]["evidence"][0]["chapter_id"] = f"{VERSION}-ch08"  # type: ignore[index]
    backstory_bytes = json.dumps(backstory_doc, sort_keys=True).encode()
    backstory = SyntheticBackstory.model_validate_json(json.dumps(backstory_doc))
    ground_truth = ProposedGroundTruth.model_validate_json(json.dumps(ground_truth_doc))
    with pytest.raises((BookContractError, ValueError), match="chapter|span|text"):
        validate_scenario(
            backstory,
            ground_truth,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )


def test_compiles_hybrid_windows_and_exact_source_occurrence() -> None:
    plan = _validated(("grounded_book_reflection",))
    records = plan.scenes[0].evidence_by_id["support"].accepted_runtime_records
    assert any(len(record.text) > 500 for record in records)
    assert all(
        record.source_lines[0] <= 964 <= record.source_lines[1] for record in records
    )


def test_repeated_text_does_not_match_another_paragraph() -> None:
    from evals.synthetic_journals.book_evidence import BookEvidenceResolver
    from evals.synthetic_journals.models import CorpusTextEvidence

    first = _excerpt(
        f"{VERSION}-ch08", "08-the-queens-croquet-ground.md", "first", FORBIDDEN
    )
    markdown = (CHAPTERS / "08-the-queens-croquet-ground.md").read_text(encoding="utf-8")
    start = markdown.index(FORBIDDEN, first["end_codepoint"])
    second = first | {
        "evidence_id": "second",
        "start_codepoint": start,
        "end_codepoint": start + len(FORBIDDEN),
    }
    resolver = BookEvidenceResolver(ROOT)
    records = [
        resolver.resolve(
            "pg11", VERSION, CorpusTextEvidence.model_validate_json(json.dumps(item))
        ).accepted_runtime_records
        for item in (first, second)
    ]
    first_paragraph = min(records[0], key=lambda item: len(item.text))
    assert FORBIDDEN in first_paragraph.text
    assert first_paragraph not in records[1]


def test_compiler_rejects_changed_immutable_source(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "data", tmp_path / "data")
    source = tmp_path / "data/gutenberg/alice-in-wonderland.txt"
    source.write_text(source.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    content, truth = _documents()
    with pytest.raises(BookContractError, match="source|SHA|integrity"):
        compile_book_replay_plan(
            SyntheticBackstory.model_validate_json(json.dumps(content)),
            ProposedGroundTruth.model_validate_json(json.dumps(truth)),
            repository_root=tmp_path,
        )


def test_compiler_rejects_false_input_basis_even_without_file_validator() -> None:
    content, truth = _documents()
    truth["book_scene_facts"][0]["basis_spans"][0]["text"] = "invented"  # type: ignore[index]
    with pytest.raises(BookContractError, match="span"):
        compile_book_replay_plan(
            SyntheticBackstory.model_validate_json(json.dumps(content)),
            ProposedGroundTruth.model_validate_json(json.dumps(truth)),
        )


def _registered_unit_excerpt(
    work_id: str, unit_order: int, evidence_id: str
) -> dict[str, object]:
    from apps.backend.librarian import _paragraphs
    from src.linger.corpus.registry import CORPORA
    from src.linger.corpus.units import load_units, read_unit

    registration = CORPORA[work_id]
    unit = next(unit for unit in load_units(registration) if unit.order == unit_order)
    metadata, body = read_unit(registration, unit)
    text = _paragraphs(metadata, body)[0].text[:80]
    markdown = (registration.root / unit.path).read_text(encoding="utf-8")
    source_body = body.split("\n\n", 1)[1]
    start = markdown.index(text, len(markdown) - len(source_body))
    return {
        "kind": "corpus_text", "evidence_id": evidence_id,
        "chapter_id": unit.chapter_id, "start_codepoint": start,
        "end_codepoint": start + len(text), "text": text,
    }


def _section_book_documents(work_id: str, *, grounded_only: bool = False):
    from src.linger.corpus.registry import CORPORA
    from src.linger.corpus.units import load_units

    registration = CORPORA[work_id]
    chapters = [
        unit for unit in load_units(registration)
        if unit.part_id == "main" and unit.chapter_number is not None
    ]
    objectives = ("grounded_book_reflection",) if grounded_only else (
        "grounded_book_reflection", "spoiler_boundary_clarification"
    )
    content, truth = _documents(objective_ids=objectives)
    for facts in truth["book_scene_facts"]:
        facts["scope"]["work_id"] = work_id
        facts["scope"]["book_version_id"] = registration.book.book_version_id
        facts["evidence"] = [
            _registered_unit_excerpt(
                work_id, chapters[0 if item["evidence_id"] == "support" else 1].order,
                item["evidence_id"],
            )
            for item in facts["evidence"]
        ]
    return content, truth


def _compile_book_documents(content, truth):
    return compile_book_replay_plan(
        SyntheticBackstory.model_validate_json(json.dumps(content)),
        ProposedGroundTruth.model_validate_json(json.dumps(truth)),
    )


def _separate_objective_documents():
    content, truth = _documents()
    scenes = {scene["scene_id"]: scene for scene in content["scenes"]}
    scenes["scene-infer"]["objective_ids"] = ["spoiler_boundary_clarification"]
    grounded = {
        **scenes["scene-personal"], "scene_id": "scene-grounded",
        "line_ids": ["line-grounded"],
    }
    content["scenes"] = [grounded, scenes["scene-personal"], scenes["scene-infer"], scenes["scene-clarify"]]
    for order, scene in enumerate(content["scenes"], 1):
        scene["order"] = order
    content["lines"].append({
        "line_id": "line-grounded", "scene_id": "scene-grounded", "order": 1,
        "text": "I finished chapter 5 of Alice in Wonderland. What exactly does the Caterpillar ask Alice?",
    })
    truth["book_scene_facts"].append({
        "scene_id": "scene-grounded",
        "scope": {
            "kind": "reader_confirmed", "work_id": "pg11",
            "book_version_id": VERSION, "safe_ceiling_chapter": 5,
        },
        "basis_spans": [],
        "evidence": [truth["book_scene_facts"][0]["evidence"][0]],
    })
    for proposal in truth["proposals"]:
        if proposal["objective_id"] != "grounded_book_reflection":
            continue
        if proposal["scene_id"] == "scene-infer":
            proposal["scene_id"] = "scene-grounded"
        else:
            proposal["pairing"]["paired_scene_id"] = "scene-grounded"
        proposal["pairing"]["match_fields"].append("prop_ids")
        proposal["pairing"]["difference_fields"].remove("prop_ids")
    truth["backstory_sha256"] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    return content, truth


def test_combined_objectives_allow_separate_grounding_without_memory():
    content, truth = _separate_objective_documents()
    backstory = SyntheticBackstory.model_validate_json(json.dumps(content))
    ground_truth = ProposedGroundTruth.model_validate_json(json.dumps(truth))
    validate_scenario(
        backstory, ground_truth,
        backstory_bytes=json.dumps(content, sort_keys=True).encode(),
        run_configurations={},
    )
    plan = compile_book_replay_plan(backstory, ground_truth)
    assert len(plan.scenes) == 4
    assert all(len(scene.scene.objective_ids) == 1 for scene in plan.scenes)
    assert plan.scenes[0].facts.scope.kind == "reader_confirmed"
    assert plan.scenes[0].safe_ceiling_chapter == 5
    assert plan.scenes[0].props == plan.scenes[1].props == ()
    assert plan.scenes[2].facts.scope.kind == "librarian_inferred"
    assert plan.scenes[2].props and plan.scenes[3].props


@pytest.mark.parametrize("missing_scene, required_coverage", [
    ("scene-grounded", "retrieval-required and no-retrieval Scenes"),
    ("scene-personal", "retrieval-required and no-retrieval Scenes"),
    ("scene-infer", "inferred and clarification Scenes"),
    ("scene-clarify", "inferred and clarification Scenes"),
])
def test_separate_objectives_still_require_each_comparison_case(missing_scene, required_coverage):
    content, truth = _separate_objective_documents()
    for field in ("scenes", "lines"):
        content[field] = [item for item in content[field] if item["scene_id"] != missing_scene]
    for order, scene in enumerate(content["scenes"], 1):
        scene["order"] = order
    for prop in content["props"]:
        prop["lifecycle"] = [item for item in prop["lifecycle"] if item["scene_id"] != missing_scene]
    for field in ("book_scene_facts", "proposals"):
        truth[field] = [item for item in truth[field] if item["scene_id"] != missing_scene]
    with pytest.raises(BookContractError, match=required_coverage):
        _compile_book_documents(content, truth)


def test_separate_objectives_still_require_same_objective_pairings():
    content, truth = _separate_objective_documents()
    truth["proposals"][0]["pairing"]["paired_scene_id"] = "scene-infer"
    with pytest.raises(BookContractError, match="must pair the same Objective"):
        _compile_book_documents(content, truth)


@pytest.mark.parametrize("work_id, first_order, label", [
    ("pg23", 4, "Chapter 1"),
    ("pg2397", 3, "Part I, Chapter 1"),
])
def test_section_evidence_matches_canonical_runtime_records(work_id, first_order, label):
    from apps.backend.librarian import Librarian
    from evals.synthetic_journals.book_evidence import BookEvidenceResolver
    from evals.synthetic_journals.models import CorpusTextEvidence
    from src.linger.corpus.registry import CORPORA

    excerpt = _registered_unit_excerpt(work_id, first_order, "support")
    resolved = BookEvidenceResolver(ROOT).resolve(
        work_id, CORPORA[work_id].book.book_version_id,
        CorpusTextEvidence.model_validate_json(json.dumps(excerpt)),
    )
    assert resolved.chapter_number == 1
    assert resolved.chapter_number != first_order
    assert resolved.accepted_runtime_records
    for record in resolved.accepted_runtime_records:
        assert record.chapter_id == excerpt["chapter_id"]
        assert record.chapter_number == 1
        assert record.part_id == "main"
        assert record.location.startswith(label + " — ")
        assert Librarian().fetch_by_id(record.evidence_id) == record


@pytest.mark.parametrize("work_id", ["pg23", "pg2397"])
def test_section_book_compiler_derives_literary_ceiling(work_id):
    content, truth = _section_book_documents(work_id)
    validate_scenario(
        SyntheticBackstory.model_validate_json(json.dumps(content)),
        ProposedGroundTruth.model_validate_json(json.dumps(truth)),
        backstory_bytes=json.dumps(content, sort_keys=True).encode(),
        run_configurations={},
    )
    plan = _compile_book_documents(content, truth)
    assert plan.scenes[0].safe_ceiling_chapter == 1
    assert plan.scenes[0].evidence_by_id["later"].chapter_number == 2


@pytest.mark.parametrize("work_id, maximum", [("pg23", 11), ("pg2397", 23)])
def test_section_reader_confirmed_ceiling_uses_main_narrative_extent(work_id, maximum):
    from src.linger.corpus.registry import CORPORA

    content, truth = _section_book_documents(work_id, grounded_only=True)
    facts = truth["book_scene_facts"][0]
    facts["scope"] = {
        "kind": "reader_confirmed", "work_id": work_id,
        "book_version_id": CORPORA[work_id].book.book_version_id,
        "safe_ceiling_chapter": maximum,
    }
    facts["basis_spans"] = []
    plan = _compile_book_documents(content, truth)
    assert plan.scenes[0].safe_ceiling_chapter == maximum
    facts["scope"]["safe_ceiling_chapter"] = maximum + 1
    with pytest.raises(BookContractError, match="ceiling exceeds corpus"):
        _compile_book_documents(content, truth)


@pytest.mark.parametrize("work_id, unit_order", [
    ("pg23", 1),   # Preface
    ("pg23", 15),  # Appendix
    ("pg2397", 1),  # Dedication
    ("pg2397", 27),  # Letter
    ("pg2397", 136),  # Part III, Chapter 1
])
def test_section_book_compiler_rejects_named_units_and_other_parts(work_id, unit_order):
    content, truth = _section_book_documents(work_id)
    truth["book_scene_facts"][0]["evidence"][0] = _registered_unit_excerpt(
        work_id, unit_order, "support"
    )
    with pytest.raises(BookContractError, match="numbered main-text chapter"):
        _compile_book_documents(content, truth)
