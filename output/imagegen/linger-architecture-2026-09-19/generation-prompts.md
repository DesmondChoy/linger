# Linger architecture image pair

Created on 19 September 2026 using the built-in image_gen tool. The second image uses the finalized first image as its supplied reference.

Source snapshot: d62a9ad. The diagram describes implemented code and callable workflows, not proof of an externally deployed service.

Final files:

- current-implementation.png — six implemented strengths annotated; solid shapes.
- proposed-improvements-integrated.png — selected final revision, with the nine proposed additions placed beside the existing components they affect. See integrated-revision-prompts.md for the revision prompts.
- proposed-improvements.png — superseded draft with a separate recommendations panel; not selected for the GitHub reply.

Accuracy notes:

- The application controls handoffs, evidence, memory writes and answer release. Repeated Provenance boxes depict different tasks of the same reusable role.
- Chat does not trigger Sculptor. Reviewed curation is a separate callable workflow. Interactive capture is off by default, and the complete conversational capture-to-curation-to-later-surfacing journey remains unfinished.
- The proposed real-reviewer change concerns capture_curation_replay specifically. The separate connection_curation_replay runner already uses production review.
- Session state is process-local. Durable memories are local account-scoped files mediated by Memory & Policy Service.
- Logfire export requires configuration. Runtime export excludes human conversation content; explicit synthetic evaluation can export synthetic content.
- The current CI includes pytest, frontend Vitest, and Ground truth review-UI tests. Frontend build/lint and behavioural release gates remain proposed.

Source files checked:

- README.md and docs/agent-skills.md
- .github/workflows/ci.yml
- apps/backend/main.py, chat_turn.py, sessions.py, telemetry.py
- src/linger/agents/skills.py
- src/linger/orchestration/reflection.py and curation.py
- src/linger/services/memory.py
- evals/synthetic_journals/adoption.py, capture_curation_replay.py, curation_replay.py, connection_curation_replay.py

The nine proposed additions match the course-gap comment drafted in this task. The diagrams deliberately retain existing authority and privacy boundaries and do not introduce training infrastructure or distributed services.

## Current implementation — initial generation

```text
Use case: infographic-diagram.
Create the FIRST of two matching architecture images for Linger, a course-assessed personal reflection and memory application. This image must show CURRENT IMPLEMENTATION only. Produce a polished, high-resolution landscape technical infographic, approximately 3:2 aspect ratio, large readable text, precise orthogonal connectors, generous spacing, flat vector-like shapes on a warm white background. Restrained navy/teal/blue palette, solid outlines for all implemented components. No dotted or dashed shapes anywhere in this first image. Do not make an illustrative robot poster. This is an understandable software architecture with annotated existing capabilities, not a screenshot. Use exact component names and short labels below; readable typography matters more than decoration.

Title: "Linger — implemented architecture"
Subtitle: "Current code: d62a9ad • 19 September 2026"
Legend: "Solid shapes = implemented"
Small scope note: "Local, single-user prototype"

COMPOSITION: Three full-width horizontal bands with a narrow right-hand observability column. Top band is development and evaluation, middle is the largest application/runtime band, bottom is a clearly SEPARATE callable memory workflow. The diagram must remain roomy enough to be the unchanged base of a second image with future additions around it.

TOP BAND: label "Development and evaluation"
Two parallel sequences, visually separate from live chat:
1) "Versioned repository" with smaller text "Code • agent skills • five book corpora" → "Automated tests" with smaller text "GitHub Actions: pytest + Vitest + review UI" and note "Provider calls blocked in unit tests".
2) "Human review" → "Reviewed evaluation data" with smaller text "Approval tied to exact scenario files" → "Scenario replay" with smaller text "Controlled calls to application workflows".
Include an attached small annotation "Versioned books and agent instructions" / "Source hashes and skill fingerprints".
Do NOT draw CI deploying or publishing the app. There is no release/deployment pipeline yet.

MIDDLE BAND: label "Live conversation"
Left entry: simple Reader icon → "React UI" / "Chat • live agent map • inspection" ↔ "FastAPI" / "HTTP and progress stream".
These enter a large solid-outline container called "Application-owned workflow".
Its bold annotation is "Controlled agent actions and answer release".
Within this container show the ordered main path:
"Provenance" / "Emotional preflight" → "Muse" / "Draft or revise" → "Provenance" / "Candidate review" → "Application checks" / "Release, clarify or decline".
Return arrow from Application checks to React UI labelled "Final response".
Include a small loop from candidate review back to Muse labelled "At most one revision". These repeated Provenance boxes are invocations of ONE reusable role, not separate agents.
Under Muse put two specialist nodes connected THROUGH a small bar labelled "Application tool adapters":
"Librarian" / "Reading boundary • book evidence"
"Serendipity" / "Memory recall • connections"
All their invocation arrows stay inside the application-control container. Do not imply free autonomous peer-to-peer transport.
Below those, data/service boxes:
"Scoped book retrieval" / "BM25 + embeddings + reranker" connected to Librarian and Serendipity, and to "Five versioned books".
"Memory & Policy Service" / "Permitted memory snapshots" connected to Serendipity and to cylinder "Local account memories".
"Public web" / "Optional, granted access only" connected to Serendipity through its tool adapter.
Small side box linked to application container: "Session history" / "Process memory; cleared on restart".
Below the role group a compact shared infrastructure strip: "Model provider" / "All five role agents use the configured hosted model".
Note near the control boundary: "One reusable Agent per role • typed tasks • application-selected skills".
No direct agent writes to memory, no vector database, no authentication server, no cloud hosting, no autonomous agent swarm.

BOTTOM BAND: title "Reviewed memory changes"
Subtitle: "Separate callable workflow — chat does not trigger Sculptor"
Show an orderly left-to-right sequence:
"Memory service" / "Select originals" → "Sculptor" / "Propose curation" → "Provenance" / "Review proposal" → "Application + Memory Policy" / "Validate and apply" → "Curated memory view".
Add a bold annotation beneath: "Original records preserved • approved changes audited".
All nodes solid: this callable workflow IS implemented. The Provenance and Memory Policy nodes reuse the same roles/services shown above.
Small note: "Interactive capture is off by default. Reviewed capture can run when explicitly enabled."
Small separate note: "Automatic capture → curation → later surfacing remains incomplete." This is a limitation note, not a future component box.

RIGHT OBSERVABILITY COLUMN:
Header "Useful logs with privacy checks"
"Logfire — runtime" / "Metadata only; no private chat text", connected from the live application by a thin SOLID teal line labelled "operational metadata".
"Logfire — synthetic evaluations" / "Synthetic inputs, outputs and results", connected from Scenario replay by a SOLID blue line labelled "synthetic content".
Note "Exported-data tests check privacy".
Keep these two paths distinct. Never draw raw human messages into Logfire.

VISUAL RULES: All 6 exact strength annotations must be easy to locate: "Automated tests"; "Controlled agent actions and answer release"; "Versioned books and agent instructions"; "Reviewed memory changes"; "Reviewed evaluation data"; "Useful logs with privacy checks". Every arrow has a specific source and destination, no ambiguous crossing spaghetti. Use small restrained role icons if helpful. Do not include future recommendations in this first image. Keep text concise, spelled correctly, no fabricated metrics or test counts. No watermark, no NUS logo, no extra branding. Make a complete finished diagram with excellent legibility.
```

## Current implementation — connection and header corrections

```text
Edit the provided Linger architecture diagram. It is the edit target, not just a style reference. Keep its exact overall composition, panel arrangement, six strength annotations, all existing components, navy/teal style, and current-state scope. Make only these clarity/correctness fixes:
1. Replace the dark blue-gray gradient behind the title with a clean pale near-white header so "Linger — implemented architecture" is high contrast and readable.
2. In the live conversation panel, make one unambiguous SOLID connector go directly from the Muse box down to "Application tool adapters", then branch that bar to Librarian and Serendipity. The adapter invocation must visibly originate at Muse, NOT at the review/revision line.
3. Delete the U-shaped double-ended connector directly between Librarian and Serendipity. Both use the application-controlled "Scoped book retrieval" service. Preserve Librarian → Scoped book retrieval; add a distinct solid elbow connector from Serendipity to Scoped book retrieval, clearly ending at the retrieval box. Avoid crossing text or another node.
4. Connect the "Session history" box to the application workflow boundary with a complete clear line, removing the existing floating two-headed arrow stub.
5. Fix the runtime-log arrow label to exactly "operational metadata", on two lines if needed, with no missing letters or truncated text.
6. In the unused space beneath React UI/FastAPI, add a small unobtrusive plain-text annotation (not a new future box): "The application controls every handoff.\nPreflight can stop the turn before Muse.\nProvenance is one role reused across reviews."
7. Every implemented shape and connector remains SOLID. Do not add recommendations or dotted outlines yet. Keep the bottom callable memory curation lane and its incomplete conversational-memory note exactly in meaning. Do not remove or rewrite the source/version subtitle. High-quality readable diagram text; preserve all other facts.
```

## Current implementation — final corrections

```text
Use the supplied diagram as the EDIT TARGET. Preserve every existing shape, all six capability annotations, all panels, text, typography and connectors. Make ONLY these final tiny corrections:
A. Replace the truncated green label beside the arrow to "Logfire — runtime" with the exact two-line text "Runtime\nmetadata". It must fit cleanly.
B. From the bottom edge of the Serendipity box, ADD a short solid dark-blue connector to the top of "Memory & Policy Service". Also ADD a solid dark-blue elbow connector from the right edge of Serendipity to the top edge of "Public web". Keep its current connector to Scoped book retrieval.
C. In the free space immediately under the three-line note beginning "The application controls every handoff", ADD one line "At most one response revision." Keep the final response line below it.
These are the only changes. Do not delete any other connection, do not move boxes, do not alter the bottom reviewed-memory lane, do not add future features. All shapes and connectors remain solid. The final output must be the complete diagram, not a crop.
```

## Proposed improvements — reference-based second image

```text
Use case: infographic-diagram, editing an existing architecture image.
This is the SECOND image in a matched pair. Use the supplied FIRST IMAGE as the exact architecture reference and base. It depicts implemented Linger at commit d62a9ad. Preserve the implemented architecture, all existing solid blue/teal nodes, arrows, six strength annotations, separate memory-curation lane, private-log separation, and scope notes. The user wants to see potential additions without mistaking them for shipped functionality.

OUTPUT COMPOSITION:
Expand the canvas DOWNWARD into a tall, nearly square high-resolution poster, approximately 2048 x 2048 or larger if possible. Keep the original diagram at full readable width in the upper portion, without squashing or cropping it. Append a spacious recommendation panel below with NINE distinct amber DOTTED-OUTLINE rounded cards in a three-column, three-row grid. Match the original navy typography, pale background and flat graphic style. Existing components retain solid blue/teal outlines. All proposed cards, badges and proposed connector lines must be AMBER with visibly dotted strokes, made of separated round dots. No solid orange outlines and no solid proposed component. Actual text is solid dark ink for readability.

TITLE/LEGEND:
Change the title to "Linger — current architecture + proposed improvements".
Keep the date and base commit in the subtitle.
Replace the original legend with:
"Solid = implemented"
"Amber dotted = proposed, not implemented"
The addition panel has a clear title "Potential improvements" and one small instruction "Match each number to its location in the architecture."
Preserve that chat does not currently trigger Sculptor and interactive capture is off by default. No new sign-in, release gate or cloud deployment is shown as already existing.

NUMBERED ATTACHMENT POINTS:
Put small amber dotted circles containing numbers beside existing areas, avoiding all labels and arrows. These mark where the proposed cards apply, without adding false implemented edges:
1 next to Automated tests.
2 next to Scenario replay.
3 also next to Scenario replay, but distinct from 2; specifically the capture + curation evaluation.
4 beside the React UI / FastAPI group.
5 beside Session history / application account-and-memory boundary.
6 beside Versioned repository and its fingerprint note.
7 beside Logfire — runtime.
8 beside the Human review / Reviewed evaluation data sequence.
9 beside Application tool adapters.
Do not cover existing text. Use whitespace. Numbered markers and matching cards are enough; do not run nine long crossing lines through the architecture.

NINE DOTTED PROPOSED CARDS — exact headings, in this order:
1. "CI completeness"
   "Add frontend build + lint to GitHub Actions."
2. "Behavioural release evidence"
   "Real-model checks + semantic review before release."
   "Repeat key cases; keep a separate holdout."
3. "Capture/curation integration coverage"
   "Use real Provenance in capture + curation evaluation."
   "Prove that rejected changes are not applied."
4. "Deployment and recovery"
   "Versioned package → Test environment → Approved release"
   "Smoke checks + restore the previous version."
5. "Account isolation and stated scale"
   "Sign-in + separate account access."
   "Measure five concurrent sessions."
   Small qualifier: "If the multiple-account target is retained."
6. "Release and experiment traceability"
   "One run manifest links code, settings, prompts, data and results."
7. "Operational budgets"
   "Set limits for latency, cost and failures."
   "Flag releases that exceed them."
8. "Failure-to-regression feedback"
   "Failure metadata → Synthetic case → Human review → Regression test"
   "Keep private conversations out."
9. "Security checks across the delivery path"
   "Dependency + code scans."
   "Test attacks hidden in retrieved content."

Below the cards add a small plain footer:
"These additions are recommendations. Keep the existing application-owned authority and privacy boundaries."
Optional second footer if space permits:
"No Kubernetes, training pipeline or distributed workflow engine is required for these improvements."

QUALITY CONSTRAINTS:
All nine recommendations must be present once and readable. Wrap long headings instead of shrinking them excessively. Do not silently replace or omit an implemented node to make room. Do not connect Sculptor to live chat. Do not change the implemented callable curation path into a proposed/dotted path. Card 3 is a change to a specific evaluation runner, not a claim that real runtime curation review is missing. Preserve all first-image architecture facts. Keep all original components visually recognisable in the same positions relative to each other. No decorative robots, no invented platforms, no fabricated performance figures. Excellent text fidelity and balanced whitespace.
```
