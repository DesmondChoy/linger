"""The persona snapshot carries replayable turns and nothing private or local."""

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "apps/frontend/scripts/export_personas.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_personas", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PersonaExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        exporter = load_exporter()
        cls.snapshot = exporter.export()
        cls.files = exporter.files(cls.snapshot)
        cls.text = "".join(cls.files.values())

    def test_leaves_out_prompts_transcripts_and_local_paths(self) -> None:
        for forbidden in ('"model_messages"', '"input_prompt"', "/Users/"):
            self.assertNotIn(forbidden, self.text)

    def test_every_persona_has_a_completed_run_covering_its_scenes(self) -> None:
        self.assertTrue(self.snapshot["personas"])
        for persona in self.snapshot["personas"]:
            planned = {scene["id"] for scene in persona["scenes"]}
            for run in persona["runs"]:
                self.assertTrue(run["startedAt"], persona["id"])
                self.assertEqual(planned, {scene["sceneId"] for scene in run["scenes"]}, persona["id"])
                self.assertEqual(run["total"], len(run["scenes"]))

    def test_chat_scenes_carry_turns_and_curation_scenes_carry_a_response(self) -> None:
        for persona in self.snapshot["personas"]:
            for scene in persona["runs"][0]["scenes"]:
                self.assertTrue(scene["turns"] or scene["curation"], f"{persona['id']} {scene['sceneId']}")
                for turn in scene["turns"]:
                    self.assertTrue(turn["userMessage"])

    def test_carries_the_recorded_contract_inputs_and_sources(self) -> None:
        chat_turns = [
            turn for persona in self.snapshot["personas"] for scene in persona["runs"][0]["scenes"]
            for turn in scene["turns"]
        ]
        drafted = [turn for turn in chat_turns if turn["museTurn"]]
        self.assertTrue(drafted)
        self.assertTrue(all("policy" in turn["museTurn"] for turn in drafted))
        self.assertTrue(any(turn["sources"] for turn in chat_turns))
        self.assertTrue(any(turn["connectionEvents"] for turn in chat_turns))
        self.assertTrue(all(exchange["input"] for turn in drafted for exchange in turn["exchanges"]
                            if exchange["role"] == "Muse" and exchange["stage"] == "draft"))

    def test_writes_a_small_index_and_one_file_per_persona(self) -> None:
        index = json.loads(self.files["index.json"])
        self.assertEqual(
            {f"{persona['id']}.json" for persona in index["personas"]} | {"index.json"},
            set(self.files),
        )
        self.assertNotIn("scenes", index["personas"][0])

    def test_personas_are_grouped_by_catalog_family(self) -> None:
        families = {family["id"] for family in self.snapshot["families"]}
        self.assertTrue({persona["family"] for persona in self.snapshot["personas"]} <= families)


if __name__ == "__main__":
    unittest.main()
