"""Offline checks for reservation limits and strict saved-result grading."""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import tempfile
from threading import Event, Lock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("batch_driver", BASE / "run_batch.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
SAVED = BASE / "iteration-18-c15a6da6"


class BatchDriverTests(unittest.TestCase):
    def test_concurrency_limit_queues_each_suite_once_without_new_reservations(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "run"
            folder.mkdir()
            menu = Path(temp) / "menu.json"
            driver.write(menu, {"entries": []})
            entered = []
            lock, two_started, release = Lock(), Event(), Event()

            def execute(suite, menu, folder, expected_ids):
                with lock:
                    entered.append(suite)
                    if len(entered) == 2:
                        two_started.set()
                self.assertTrue(release.wait(5))
                result = {"suite": suite, "passed": True, "failures": []}
                driver.write(folder / f"suite-{suite}.status.json", result)
                return result

            args = SimpleNamespace(suites=["direct", "smoke", "mapping"], menu=menu,
                                   budget=Path(temp) / "budget.json", plan=False, concurrency=2)
            with patch.object(driver, "source_hashes", return_value={}), \
                    patch.object(driver, "reserve", return_value=(folder, {"iteration": 18})) as reserve, \
                    patch.object(driver, "finish_reservation") as finish, \
                    patch.object(driver, "execute", side_effect=execute), \
                    ThreadPoolExecutor(max_workers=1) as outer:
                future = outer.submit(driver.main, args)
                try:
                    self.assertTrue(two_started.wait(5))
                    self.assertEqual(2, len(entered))
                finally:
                    release.set()
                self.assertEqual(0, future.result(timeout=5))
                reserve.assert_called_once()
                finish.assert_called_once()
            self.assertCountEqual(args.suites, entered)
            self.assertEqual(2, driver.read(folder / "summary.json")["maximum_concurrent_suites"])

    def test_saved_book_and_connection_schemas(self):
        for number in (4, 6, 7, 8, 9, 10, 11, 12):
            with self.subTest(number=number):
                artifact = driver.read(SAVED / f"suite-{number}.json")
                for scene in artifact["scenes"]:
                    observed = driver.grade(str(number), {"scenes": [scene]}, [scene["scene_id"]])
                    if "hard_gate_pass" in scene:
                        expected = scene["hard_gate_pass"]
                    else:
                        expected = all(grade["hard_pass"] for grade in scene["grades"])
                    self.assertEqual(expected, not observed)

    def test_smoke_requires_all_six_stages(self):
        report = driver.read(SAVED / "suite-smoke.json")
        self.assertEqual([], driver.grade("smoke", report, []))
        report["stages"].pop()
        self.assertTrue(driver.grade("smoke", report, []))

    def test_mapping_requires_every_case_and_its_actual_grade(self):
        rows = [{"case_id": str(i), "grade": {"passed": True}, "error_type": None}
                for i in range(4)]
        report = {"cases": rows, "summary": {"targets_pass": True}}
        ids = [row["case_id"] for row in rows]
        self.assertEqual([], driver.grade("mapping", report, ids))
        rows[0]["grade"]["passed"] = False
        self.assertIn("0:mapping_grade", driver.grade("mapping", report, ids))
        rows.pop()
        self.assertIn("incomplete_or_duplicate_cases", driver.grade("mapping", report, ids))

    def test_standalone_aggregate_pass_does_not_hide_case_failures(self):
        report = driver.read(SAVED / "suite-release.json")
        ids = [row["case_id"] for row in report["cases"]]
        self.assertEqual([], driver.grade("release", report, ids))
        cases = {row["case_id"]: row for row in report["cases"]}
        cases["identity-theme"]["strength_correct"] = False
        cases["pigeon-serpent"]["final_evidence_recall"] = 0.0
        self.assertTrue(report["summary"]["targets_pass"])
        failures = driver.grade("release", report, ids)
        self.assertIn("identity-theme:strength_correct", failures)
        self.assertIn("pigeon-serpent:recall", failures)

    def test_direct_detects_saved_citation_and_strength_failures(self):
        report = driver.read(SAVED / "suite-direct.json")
        ids = [row["case_id"] for row in report["cases"]]
        self.assertEqual([], driver.grade("direct", report, ids))
        cases = {row["case_id"]: row for row in report["cases"]}
        cases["drink-me"]["citations_resolve"] = False
        cases["identity-theme"]["strength_correct"] = False
        failures = driver.grade("direct", report, ids)
        self.assertIn("drink-me:citations", failures)
        self.assertIn("identity-theme:strength_correct", failures)
        report["cases"].append(copy.deepcopy(report["cases"][0]))
        self.assertIn("incomplete_or_duplicate_cases", driver.grade("direct", report, [row["case_id"] for row in report["cases"]]))

    def test_complete_release_contract_and_each_failure(self):
        row = {"case_id": "x", "strength_correct": True, "final_evidence_recall": 1.0,
               "final_citation_precision": 1.0, "exact_citations_resolve": True,
               "spoiler_exposure": False, "release_source": "muse_candidate", "failure_stage": None,
               "provenance_verdicts": ["pass"], "librarian_calls": [{"query_argument_absent": True,
               "work_id_matches": True, "book_version_id_matches": True, "application_owned_scope": True}]}
        rows = [dict(copy.deepcopy(row), case_id=str(i)) for i in range(12)]
        report = {"summary": {"targets_pass": True}, "cases": rows}
        ids = [row["case_id"] for row in rows]
        self.assertEqual([], driver.grade("release", report, ids))
        rows[0]["librarian_calls"][0]["application_owned_scope"] = False
        self.assertIn("0:call_contract", driver.grade("release", report, ids))
        rows[0]["final_evidence_recall"] = True
        self.assertIn("0:recall", driver.grade("release", report, ids))

    def test_concurrent_reservations_stop_at_twenty_without_touching_real_budget(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(driver, "BASE", Path(temp)):
            budget = Path(temp) / "budget.json"
            driver.write(budget, {"maximum_iterations": 20, "iterations": [], "counting_rule": "preserved"})
            def reserve(_):
                try:
                    return driver.reserve(budget, ["smoke"], {})[1]["iteration"]
                except RuntimeError:
                    return None
            with ThreadPoolExecutor(max_workers=3) as executor:
                results = list(executor.map(reserve, range(23)))
            self.assertEqual(list(range(1, 21)), sorted(value for value in results if value is not None))
            self.assertEqual(3, results.count(None))
            self.assertEqual(20, len(driver.read(budget)["iterations"]))
            self.assertEqual("preserved", driver.read(budget)["counting_rule"])

    def test_native_helper_and_web_policy_commands(self):
        for suite in driver.SUITES:
            argv = driver.command(suite, BASE / "saved-menu.json", BASE / "unused.json")
            self.assertEqual(str(driver.PYTHON), argv[0])
            if suite.isdigit():
                self.assertIn("evals.synthetic_journals.run_scenario", argv)
                self.assertEqual(driver.MODEL, argv[-1])


if __name__ == "__main__":
    unittest.main()
