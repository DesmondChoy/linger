"""The scenario snapshot carries replayable turns and nothing private or local."""

import importlib.util
import json
import shutil
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "apps/frontend/scripts/export_scenarios.py"
SCENARIO_SNAPSHOT = SCRIPT.parent.parent / "src/replay/scenarios"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_scenarios", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScenarioExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        exporter = load_exporter()
        index = json.loads((SCENARIO_SNAPSHOT / "index.json").read_text())
        cls.snapshot = {
            **index,
            "scenarios": [
                json.loads((SCENARIO_SNAPSHOT / f"{scenario['id']}.json").read_text())
                for scenario in index["scenarios"]
            ],
        }
        cls.files = exporter.files(cls.snapshot)
        cls.text = "".join(cls.files.values())

    def test_leaves_out_prompts_transcripts_and_local_paths(self) -> None:
        for forbidden in ('"model_messages"', '"input_prompt"', "/Users/"):
            self.assertNotIn(forbidden, self.text)

    def test_every_scenario_has_a_completed_run_covering_its_scenes(self) -> None:
        self.assertTrue(self.snapshot["scenarios"])
        for scenario in self.snapshot["scenarios"]:
            planned = {scene["id"] for scene in scenario["scenes"]}
            for run in scenario["runs"]:
                self.assertTrue(run["startedAt"], scenario["id"])
                self.assertEqual(planned, {scene["sceneId"] for scene in run["scenes"]}, scenario["id"])
                self.assertEqual(run["total"], len(run["scenes"]))

    def test_chat_scenes_carry_turns_and_curation_scenes_carry_a_response(self) -> None:
        for scenario in self.snapshot["scenarios"]:
            for scene in scenario["runs"][0]["scenes"]:
                self.assertTrue(scene["turns"] or scene["curation"], f"{scenario['id']} {scene['sceneId']}")
                for turn in scene["turns"]:
                    self.assertTrue(turn["userMessage"])

    def test_carries_the_recorded_contract_inputs_and_sources(self) -> None:
        chat_turns = [
            turn for scenario in self.snapshot["scenarios"] for scene in scenario["runs"][0]["scenes"]
            for turn in scene["turns"]
        ]
        drafted = [turn for turn in chat_turns if turn["museTurn"]]
        self.assertTrue(drafted)
        self.assertTrue(all("policy" in turn["museTurn"] for turn in drafted))
        self.assertTrue(any(turn["sources"] for turn in chat_turns))
        self.assertTrue(any(turn["connectionEvents"] for turn in chat_turns))
        self.assertTrue(all(exchange["input"] for turn in drafted for exchange in turn["exchanges"]
                            if exchange["role"] == "Muse" and exchange["stage"] == "draft"))

    def test_writes_a_small_index_and_one_file_per_scenario(self) -> None:
        index = json.loads(self.files["index.json"])
        self.assertEqual(
            {f"{scenario['id']}.json" for scenario in index["scenarios"]} | {"index.json"},
            set(self.files),
        )
        self.assertNotIn("scenes", index["scenarios"][0])

    def test_scenarios_are_grouped_by_catalog_family(self) -> None:
        families = {family["id"] for family in self.snapshot["families"]}
        self.assertTrue({scenario["family"] for scenario in self.snapshot["scenarios"]} <= families)


def test_export_reads_the_retained_result_and_skips_scenarios_without_one(tmp_path, monkeypatch):
    exporter = load_exporter()
    scenario_id = "alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03"
    unrun_id = "pottery-memory-curation--sculptor--2026-08-29"
    scenarios = tmp_path / "synthetic-journal-evaluation/scenarios"
    for folder_id in (scenario_id, unrun_id):
        folder = scenarios / folder_id
        folder.mkdir(parents=True)
        for name in ("backstory.json", "ground-truth.json"):
            shutil.copyfile(exporter.SCENARIOS / folder_id / name, folder / name)
    catalog = scenarios.parent / "evaluation-objectives.yaml"
    shutil.copyfile(exporter.CATALOG, catalog)

    backstory = json.loads((scenarios / scenario_id / "backstory.json").read_text())
    scenes = [
        {
            "scene_id": scene["scene_id"],
            "reply": "Recorded fixture reply.",
            "release_source": "muse",
            "grades": [{"hard_pass": True, "failures": []}],
            "agent_exchanges": [{
                "sequence": 1,
                "role": "Muse",
                "stage": "draft",
                "input_prompt": json.dumps({"muse_turn": {"policy": {"fixture": True}}}),
                "model_messages": [{"timestamp": "2026-10-06T10:00:00+00:00"}],
            }],
        }
        for scene in backstory["scenes"]
    ]
    results = tmp_path / "results"
    (results / scenario_id).mkdir(parents=True)
    (results / scenario_id / "result.json").write_text(json.dumps({
        "run": {"id": "fixture-run"},
        "evidence": {
            "evaluation": {"format": "json", "data": {"scenes": scenes}},
            "analysis": {"format": "json", "data": {"review": {"verdict": "passed", "scenes": [
                {"scene_id": backstory["scenes"][0]["scene_id"], "assessment": "passed"},
            ]}}},
        },
        "diagnostics": {"summary.json": {"format": "json", "data": {
            "started_at": "2026-10-06T10:00:00+00:00", "model": "fixture-model",
            "command": ["/Users/someone/.venv/bin/python"],
        }}},
    }))

    monkeypatch.setattr(exporter, "REPO", tmp_path)
    monkeypatch.setattr(exporter, "SCENARIOS", scenarios)
    monkeypatch.setattr(exporter, "RESULTS", results)
    monkeypatch.setattr(exporter, "CATALOG", catalog)
    snapshot = exporter.export()

    assert [scenario["id"] for scenario in snapshot["scenarios"]] == [scenario_id]
    scenario = snapshot["scenarios"][0]
    assert scenario["family"] == "retrieval_and_grounding"
    assert len(scenario["runs"]) == 1
    run = scenario["runs"][0]
    assert run["id"] == "fixture-run"
    assert run["startedAt"] == "2026-10-06T10:00:00+00:00"
    assert run["model"] == "fixture-model"
    assert run["verdict"] == "passed"
    assert run["scenes"][0]["assessment"] == "passed"
    assert run["passed"] == run["total"] == len(backstory["scenes"])
    for planned, recorded in zip(scenario["scenes"], run["scenes"], strict=True):
        assert recorded["sceneId"] == planned["id"]
        turn = recorded["turns"][0]
        assert turn["userMessage"] == " ".join(planned["lines"])
        assert turn["reply"] == "Recorded fixture reply."
        assert turn["museTurn"] == {"policy": {"fixture": True}}
        assert turn["exchanges"][0]["startMs"] == 0
    output = exporter.files(snapshot)
    assert set(output) == {"index.json", f"{scenario_id}.json"}
    assert json.loads(output[f"{scenario_id}.json"]) == scenario
    assert "/Users/" not in "".join(output.values())


def test_export_preserves_long_recorded_provenance_decisions():
    exporter = load_exporter()
    scenario_id = "alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12"
    retained = json.loads((exporter.RESULTS / scenario_id / "result.json").read_text())
    scene = next(scene for scene in retained["evidence"]["evaluation"]["data"]["scenes"] if scene["scene_id"] == "S1")
    reviews = [
        exchange for exchange in scene["agent_exchanges"]
        if exchange["role"] == "Provenance" and exchange["stage"] == "review"
    ]
    assert len(reviews) == 2
    assert all(len(json.dumps(exchange["output"], ensure_ascii=False)) > exporter.OUTPUT_LIMIT for exchange in reviews)

    outputs = [json.loads(exchange["output"]) for exchange in exporter.exchanges({"agent_exchanges": reviews})]

    assert [output["response_decision"] for output in outputs] == ["revise", "pass"]
    assert [output["findings"] for output in outputs] == [review["output"]["findings"] for review in reviews]


def test_export_bounds_output_text_without_breaking_json():
    exporter = load_exporter()
    original = {
        "response_decision": "pass",
        "findings": [{"code": "unsupported_claim", "explanation": "x" * (exporter.OUTPUT_LIMIT + 1)}],
        "coverage_audit": [{"span_index": 0, "accurate": True}],
        "optional": None,
    }
    for recorded in (original, json.dumps(original)):
        exported = exporter.exchanges({"agent_exchanges": [{"output": recorded}]})[0]["output"]
        output = json.loads(exported)
        assert output["response_decision"] == "pass"
        assert output["coverage_audit"] == original["coverage_audit"]
        assert output["optional"] is None
        assert output["findings"] == [{
            "code": "unsupported_claim", "explanation": "x" * (exporter.OUTPUT_LIMIT - 1) + "…",
        }]

    plain = exporter.exchanges({"agent_exchanges": [{"output": "x" * (exporter.OUTPUT_LIMIT + 1)}]})[0]["output"]
    assert plain == "x" * (exporter.OUTPUT_LIMIT - 1) + "…"


if __name__ == "__main__":
    unittest.main()
