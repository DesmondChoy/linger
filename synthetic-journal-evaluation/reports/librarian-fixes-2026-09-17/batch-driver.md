# Repeatable eleven-suite batch

Run from the repository root with the existing virtual environment:

```sh
.venv/bin/python synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/run_batch.py --plan
.venv/bin/python synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/run_batch.py
```

The first command only inspects commands and hashes. The second launches live calls and must be run with the already approved external-network permission. It atomically reserves one of at most twenty iterations in `live-budget.json` before launching any suite. `--suites 11 smoke` runs a targeted subset and also consumes one iteration. An interrupted, blocked, or failed launch still consumes its reservation. No automatic suite retry occurs; bounded model repairs inside the native runtime remain enabled.

The full set is saved-menu numbers 4, 6, 7, 8, 9, 10, 11, 12, standalone `release`, notebook `direct`, and `smoke`. The frozen original menu is copied to `saved-menu.json`; selected scenario input hashes must still match it. Each numbered suite uses the native scenario helper, which preserves its own unique scenario output, analysis, and telemetry files. The batch additionally copies the evaluation JSON and records the helper summary in its unique iteration directory. The two standalone suites use copied `run_live.py`; `direct` executes the notebook's twelve case helpers, not all notebook cells. The smoke copy accepts an output argument and retains native diagnostics and emitted evaluation links.

All subprocesses use `openai:gpt-5.6-luna`. The standalone suites disable web search; smoke enables it. Numbered scenarios start with web disabled and the native helper enables it where the saved selection requires it. Cached retrieval models run with `HF_HUB_OFFLINE=1`. At most three suite processes run concurrently. Model, prompt, evaluator, notebook, and scenario input hashes are recorded before and after the batch; source drift prevents a passing batch.

A suite passes only if its process and native helper succeed and its saved output passes strict checks. Every scenario Scene must be present exactly once with all hard grades passing. Smoke requires all six stages. Every standalone case must be present exactly once with correct strength, complete recall, exact precision, valid citations and safe scope. Release additionally requires an application-owned call contract, successful Provenance and release, and the native aggregate targets. Aggregate success cannot hide a failed case. The driver performs no additional semantic review.

Each iteration contains source hashes, reservation, per-suite logs, results, status files, progress, and `summary.json`. `selected_pass` covers the requested subset. `all_pass` additionally requires the complete eleven-suite set. Seven offline driver tests cover original book/connection schemas, original hidden standalone failures, strict completeness, native commands, and concurrent twenty-iteration enforcement using a temporary budget. The real budget remains untouched by preparation and `--plan`.
