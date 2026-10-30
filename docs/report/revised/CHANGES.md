# Revised group report: changes from draft 4

`group-project-report.md` is a Markdown version of `Linger_Group_Project_Report_4.docx` with the review changes applied. This file lists what changed, the old-to-new numbering, and what the authors still need to check.

## Files

| Path | What it is |
|---|---|
| `group-project-report.md` | The revised report |
| `figures/` | Every figure the report uses: ten new diagrams (SVG source and PNG) and 27 figures kept from the Word draft (PNG) |
| `tools/make_figures.py` | Writes the ten new diagrams as SVG |
| `tools/render_svgs.mjs` | Renders each SVG to a PNG at twice its size |
| `tools/patch_docx_images.py` | Copies the kept figures out of the Word draft and applies the small fixes listed below |

Regenerate the figures from the repository root:

```bash
python3 docs/report/revised/tools/make_figures.py
```

```bash
node docs/report/revised/tools/render_svgs.mjs
```

```bash
python3 -I docs/report/revised/tools/patch_docx_images.py path/to/Linger_Group_Project_Report_4.docx
```

Convert the report to Word. Pandoc's own Markdown reader (`-f markdown`) uses the column widths set in each table; the GitHub reader does not.

```bash
cd docs/report/revised && pandoc -f markdown-implicit_figures group-project-report.md --resource-path=. -o group-project-report.docx
```

## 1. Errors fixed

| Where | Change |
|---|---|
| 3.2.6 | Was an empty heading. Now describes Sculptor's offline loop, with a worked example from Experiment 4, round 1 (Table 3.2). Source: `docs/design/self-improving-memory-loop.md` and `evals/librarian/research_runs/round-1/`. |
| Figure 2.2 | Cited "Table 3.2, rows 1–6", which did not exist. Redrawn; now cites Figure 3.9, checks 1–6. |
| Learning 3 | Release recheck cross-reference corrected from 3.2.3 to 3.2.4. The reference to the missing "Table 10.1" now points to Table 9.1. |
| Section 10 numbering | Every figure and table is captioned and numbered in order. |
| Learning 2 | "The judge kept 0.70" corrected to 0.85 (61 of 72), matching the chart and the stage-survival table in `docs/report/group-project-report.md`. Scene 07 is now described. |
| Learning 2, Scene 08 | The text now places the 12-to-2 loss after the judge, where the chart puts it (Serendipity chose Alice and Hume). |
| Learning 3 and Figure 10.4 | "Provenance changed it to Lamp-Wick" reworded. Provenance flagged the speaker, Muse's revision introduced the error, and the second review passed it. Source: `docs/evaluation/five-agent-baseline-and-sculptor-options-2026-09-26.md` ("a wrong speaker attribution that Provenance had requested during revision"). Figure 10.3 now shows the added error as a path from over-refusal to missed error. |
| 3.2.3 | The "about 5%" claim now shows the per-Scene rates it rests on (4, 3, 0 and 1 of the last five runs) and the product 0.8 × 0.6 × 0.5 × 0.2. Source: the same evaluation document. |
| 4.3, step 2 | Restored the missing explanation of "that list": the model-written list of unused candidate passages, which the application now derives itself (`normalize_boundary_candidate`). |
| 3.1.3 | Serendipity is described with its three live skills only; the offline self-review skill was removed from the report, and Figure 3.3 was redrawn to match. The skill bullets now give each skill's routing, match and decline rules from its `SKILL.md`. |
| Figure 2.3 | Redrawn without "first deploy pending" and "pending release path". |
| OWASP | Table 6.1 names each category. The reference year now matches the 2026 numbering the register uses. |
| References | Added Panickssery et al. (2024), Kim et al. (2025), and IMDA (2026). Added placeholder entries for OpenAI (2024, 2025, 2026), xAI (2026) and OpenClaw (2026). Removed the uncited Xu et al. (2026) and the IMDA 2020 and 2024 frameworks. Shankar et al. (2024) is now cited in Table 9.1. |
| MAST names | Section 4.3 and Appendix B now use the same category names: specification and system design, inter-agent misalignment, task verification. |
| 4.2 | "The quotation she asked for" is now "the quotation the reader asked for". |
| Contents | Generated from the headings, so 10.2 and its heading now match. |

## 2. Repetition removed

| Content | Kept in | Removed from |
|---|---|---|
| Triage labels map to tools; tool inputs are ids only | 3.2.2 | 3.1.1 (now a pointer) |
| Muse's input fell from about 25k to 16k tokens | 3.2.2 | 3.1.1, 10.2 |
| Preflight can only select between two outcomes | 3.2.1 | 3.1.4, 5.1 (pointers) |
| Curation digest and stale-plan rejection | 3.2.5 | 3.1.4, 3.1.5 (pointers) |
| Memory capture rules | 3.2.5 (now also holds forgetting) | 2.3 |
| Provenance passing an uncited web claim | 3.2.4 | 6.3 (one pointer) |
| Release suite, 25 of 26 | 4.4 | 4.2 (the old 4.4) |
| Direct-Line and planted-memory attacks | 4.5 | 6.3 (Table 6.3 and three paragraphs cut to one bullet) |
| Introducing automated checks and LLM-review | 4.1.2 | Old 4.2.2 and 4.3 merged |
| The problem and competitor products | Figure 1.1, Table 1.1, Appendix B | 1.1 bullets (one sentence now), 1.2 bullets |
| Limitations and future work | Table 9.1 (with a next-step column) | Old Table 10.3 |
| Validator list in 3.2.4 | Figure 3.12 | Bullets cut to the two checks the figure does not show |

## 3. Structure

- Live release results moved from Section 7 into Section 4 (4.4 release suite, 4.5 security example). Section 7 now covers only application tests, the release pipeline run, and cost and load.
- 4.1 "Guardrails vs evaluations" is now a short box and Table 4.1 at the start of Section 4.
- A note at the start of 4.2 says which run each number comes from.
- 3.1.3 and 3.1.4 open with a sentence before the figure.
- Each subsection of 3.1 and 3.2 ends with the code that implements it and the section that tests it, as `AGENTS.md` asks.
- Development-history asides were rewritten as final-state rationale (3.1.1 revision mode). Comparison experiments moved to Appendix G (model change, request-plan fix, reviewer experiments).
- Section 9 is now "Limitations and Future Work", a single table. 10.4 was removed.
- 10.2 was renamed "Learnings from building multi-agent systems" so it no longer overlaps 10.3.

## 4. Moved to the appendix or cut

| Item | Now |
|---|---|
| R1 to R13 prose (about 2.5 pages) | Appendix C.1; Table 6.2 summarises it in the body |
| Four UI screenshots (old 2.4, 2.6, 2.7, 2.8) | Appendix F |
| Seven rows of the technology table | Appendix E (Table E.1) |
| Load table and its caveats (old Table 7.6) | Appendix D.3 |
| Model-change table, request-plan fix, reviewer experiments | Appendix G |
| "Hard by design" benchmark paragraph | One sentence in 4.1.1; citations in Appendix B |
| Competitor product descriptions | Appendix B |
| Old Figure 3.5 and 3.9 JSON panels | Cut; the formatted panels remain |
| Old Figure 5.1 (Inspect crop) | Cut; 5.2 points to Figure 2.5 |
| Old Figure 5.2 (IMDA dimensions) | Cut; Table 5.1 lists the dimensions |
| Old Figure 6.1 (OWASP chart) | Cut; Table 6.1 names the categories |
| Old Table 6.3 (application protection vs agent resistance) | Cut; one bullet in 6.3 |
| Old Table 8.2 (publication decisions) | Cut; four bullets beside Figure 8.1 |

Main body: about 17,500 words and 43 images before, about 15,700 words and 32 images now. That count includes the new 3.2.6, Table 6.2 and Table 9.1.

## 5. Diagrams

New diagrams share one style: Inter font, grey boxes for agents, white boxes for code, dark boxes for the reader, dashed boxes for fixed replies or optional services. The chat-turn strip (Figure 3.8) is the base for Figures 6.1, 7.1 and 10.1, so step numbers mean the same thing in every figure.

| New figure | Replaces | What changed |
|---|---|---|
| 2.1 Logical architecture | Old 2.1 | Fewer crossing lines: one bus from `run_chat_turn` to its components, one bus for typed tasks to agents, and dashed access lines that run straight down to stores. Logfire removed; Figure 2.3 shows it. |
| 2.2 Chat turn sequence | Old 2.2 | Fixed the dead table reference; long labels wrap. |
| 2.3 Physical architecture | Old 2.3 | Removed the stale "pending" text; the volume arrow now comes from the process, not from retrieval. |
| 3.4 Why source-gathering exists | — | New: the same five-source request under ranking, ranking with a prompt rule, and the bundle. Outcome counts from `docs/evaluation/five-agent-baseline-and-sculptor-options-2026-09-26.md`. |
| 3.8 Chat-turn strip | Uncaptioned strip in 3.2 | Captioned; shows 3.2.6 as offline. |
| 6.1 Security checkpoints | Old 6.2 (slide screenshot) | Built on the strip; badges 1 to 6 match Table 6.3; step 5's two checkpoints drawn as sub-steps. No slide navigation bar. |
| 7.1 Test coverage | Old 7.1 | Columns are the strip's steps; component evaluations shown per step. |
| 8.1 Release flow | Old 8.1 | No crossing lines; the feedback loop no longer wraps the figure; shows the auto-publish condition. |
| 10.1 Where answers were lost | Uncaptioned figure in Learning 2 | Built on the strip, with steps 5a to 5c inside step 5. |
| 10.3 Provenance verdicts | Old 10.6 | Shows the added error as its own path. |
| 10.4 Worked examples | Old 10.7 | Corrected Lamp-Wick wording. |
| Table 4.3 | Old Figure 4.7 (Sankey) | A table of counts, with a note on why Design failures sit outside MAST. Counts read from the Sankey band widths; see below. |

Fixes to figures kept from the Word draft (`tools/patch_docx_images.py`):

- Figure 1.1: cropped the slide deck's navigation bar.
- Figures 3.1, 3.5 and 3.7: removed the unused "Fixed reply, turn ends" legend entry.
- Figure 3.9: replaced `apps/backend/rate_limit.py` in step 1 with "ten messages a minute per account".
- Figure 4.1: "(Figure 2.9)" now reads "(Figure 2.6)", the review application's new number.
- Figure F.3: cropped the Supper club card, whose description showed a raw Markdown link.

## 6. Numbering map

| Draft 4 | Revised |
|---|---|
| Table 2.2 (state image) | Figure 2.4 |
| Figure 2.4 landing, 2.6 memories, 2.7 scenario list, 2.8 saved evaluation | Figures F.1, F.2, F.3, F.4 |
| Figure 2.5 chat and inspect | Figure 2.5 |
| Figure 2.9 review application | Figure 2.6 |
| Figures 3.4, 3.5, 3.6 | Figures 3.5, 3.6, 3.7 (new Figure 3.4 inserted) |
| Uncaptioned strip in 3.2 | Figure 3.8 |
| Figures 3.7, 3.8, 3.9, 3.10 | Figures 3.9, 3.10, 3.11, 3.12 |
| Sections 4.2, 4.2.1, 4.2.2 + 4.3, 4.4, 4.5 | Sections 4.1, 4.1.1, 4.1.2, 4.2, 4.3 |
| Section 7.1.2, Table 7.3 | Section 4.4, Table 4.4 |
| Section 7.1.3, Table 7.4 | Section 4.5, Table 4.5 |
| Section 7.1.4, Table 7.5 | Section 7.1.2, Table 7.3 |
| Table 7.6 | Table D.3 |
| Figure 6.2, Table 6.2 | Figure 6.1, Table 6.3 |
| Table 10.3 | Table 9.1 |
| Learning 2 figures (three, uncaptioned) | Figures 10.1, 10.2, G.1 |
| Figures 10.6, 10.7 | Figures 10.3, 10.4 |
| Learning 1 table (uncaptioned) | Table G.1 |

## 7. For the authors to check

1. **References to complete.** The OpenAI (2024, 2025, 2026), xAI (2026) and OpenClaw (2026) entries are placeholders: the draft cited them but listed no details. Also confirm the exact title of the 2026 OWASP edition, and the IMDA (2026), Kim et al. (2025) and Panickssery et al. (2024) entries.
2. **Table 9.1 next steps.** Old Table 10.3 had next steps for six areas. The other rows' next steps were drafted during the revision; confirm or edit them.
3. **Table 4.3 counts.** They were read from the Sankey's band widths: Model's own error 2/1/3/1, Design 0/0/0/4, Instructions 2/1/0/0, Other 0/0/0/3. Check them against the coding sheet. The sentence on why Design failures sit outside MAST is also an inference from the Sankey's labels.
4. **3.2.6 worked example.** Check that Table 3.2 matches what the team wants to claim from Experiment 4, round 1.
5. **Learning 1 numbers.** Name the suites behind "22 of 30" and "27 of 30" restraint runs and "74 of 160" (now Table G.1).
6. **Figure F.1** still shows a teammate's username ("Continue as kaymei"). Retake it signed out.
7. **Figure 2.3** shows "OpenAI gpt-6-luna" as the model provider, as the draft did. Keep it in step with Table 2.1 if the provider changes.
