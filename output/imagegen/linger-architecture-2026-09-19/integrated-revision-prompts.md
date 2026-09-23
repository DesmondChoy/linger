# Integrated architecture revision

Created using the built-in image_gen tool on 19 September 2026. Final file: proposed-improvements-integrated.png. This supersedes proposed-improvements.png for the GitHub reply. It uses current-implementation.png as the architecture reference and places proposed dotted amber additions within the existing architectural regions. Source snapshot remains d62a9ad.

## Integrated layout prompt

```text
Use case: infographic-diagram. Edit/recompose the supplied current Linger architecture image into ONE integrated architecture diagram showing existing components and proposed improvements together.

REFERENCE: Image 1 is the current implemented architecture, the source of truth for all existing components, relationships and visual style. Preserve its architecture and six strength annotations. You MAY expand whitespace, move nodes and rebalance section sizes to fit additions legibly.

CRITICAL USER CORRECTION: Put EVERY proposed improvement directly beside or within the existing component/workflow that it changes. Show proposed architectural steps and their local dotted connectors IN THE ARCHITECTURE. There must be NO separate recommendations panel, NO grid of recommendation cards below the diagram, NO detached appendix, NO numbered legend requiring the reader to match items elsewhere. The current architecture and future improvements must read as one coherent connected diagram.

DESIGN:
A large, exceptionally readable landscape infographic, roughly 3:2, ideally 3072 x 2048. Clean near-white background, navy text, solid blue/teal implemented boxes, amber DOTTED proposed boxes and connectors. Use round separated dots for future outlines. Proposed text is dark for readability. All implemented parts retain solid outlines. Let the canvas expand as needed; avoid small text, overlapping connectors or crowded boxes.
Title: "Linger — proposed improvements in context"
Subtitle: "Base implementation: d62a9ad • 19 September 2026"
Legend at top right: "Solid = implemented" and "Amber dotted = proposed".
Retain functional regions from the original: development/evaluation at top, live conversation in the middle, separate reviewed-memory workflow at bottom, logs near the right. These are architectural regions, NOT a separate future-features region. Interleave current and proposed nodes in EACH appropriate region.

IMPLEMENTED ARCHITECTURE TO RETAIN:
Development: "Versioned repository" (code • agent skills • five book corpora) → "Automated tests" (GitHub Actions: pytest + Vitest + review UI). Note unit tests block provider calls. Attached solid note "Versioned books and agent instructions" / "Source hashes and skill fingerprints".
Evaluation: "Human review" → "Reviewed evaluation data" (approval tied to exact files) → "Scenario replay" → "Logfire — synthetic evaluations" (synthetic content and results).

Runtime: Reader ↔ "React UI" ↔ "FastAPI" ↔ large solid "Application-owned workflow" boundary.
Strength annotation: "Controlled agent actions and answer release".
Inside main sequence: "Provenance / Emotional preflight" → "Muse / Draft or revise" → "Provenance / Candidate review" → "Application checks / Release, clarify or decline".
Final response returns to UI. Note "Preflight can stop the turn. At most one revision." Repeated Provenance means one reusable role.
Muse → "Application tool adapters" → "Librarian / Reading boundary • book evidence" and "Serendipity / Memory recall • connections".
Both Librarian and Serendipity connect to "Scoped book retrieval / BM25 + embeddings + reranker", connected to "Five versioned books".
Serendipity connects to "Memory & Policy Service / Permitted memory snapshots" → "Local account memories". Serendipity also connects to "Public web / Granted access only".
"Session history / Process memory; cleared on restart" connected to the APPLICATION boundary, not an autonomous agent.
"Model provider / Configured hosted model for all five roles" as shared strip.
Note "One reusable Agent per role • typed tasks • application-selected skills".
Application runtime → "Logfire — runtime / Metadata only; no private chat text". Logs region strength title "Useful logs with privacy checks", note "Exported-data tests check privacy". Keep runtime and synthetic paths distinct.

Bottom solid workflow: "Reviewed memory changes" / "Separate callable workflow — chat does not trigger Sculptor".
"Memory service / Select originals" → "Sculptor / Propose curation" → "Provenance / Review proposal" → "Application + Memory Policy / Validate and apply" → "Curated memory view".
"Original records preserved • approved changes audited".
Small note "Interactive capture is off by default. Automatic capture → curation → later surfacing remains incomplete."

INTEGRATE THESE NINE PROPOSED ADDITIONS EXACTLY AT THEIR RELEVANT LOCATIONS:
1. Directly ATTACHED beside "Automated tests", INSIDE development area, amber dotted extension:
Heading "CI completeness"
Detail "Frontend build + lint"
A short dotted connector attaches it to the current automated tests. It should visually extend the test chain.

2. Directly AFTER/BELOW "Scenario replay", alongside that existing evaluation flow, a dotted proposed gate:
Heading "Behavioural release evidence"
Detail "Real-model checks + semantic review"
Detail "Repeat key cases • separate holdout"
Dotted edge from scenario replay into this gate and toward the proposed release path. This is visually part of evaluation, not an unrelated comment.

3. INSIDE the existing "Reviewed memory changes" region, next to its Provenance-review and apply stages, attach a dotted EVALUATION annotation:
Heading "Capture/curation integration coverage"
Detail "Evaluation runner: real Provenance review"
Detail "Prove rejected changes cannot be applied"
Short dotted leader attaches to the review/apply pair. A small label "capture + curation evaluation" makes scope clear. Do NOT replace the existing solid runtime Provenance review or imply it is missing. This recommendation concerns one evaluation runner.

4. Near the React UI/FastAPI entry, directly ABOVE or to the LEFT of that application group, integrate a dotted deployment pipeline:
Heading "Deployment and recovery"
Inside the dotted boundary show three short steps with dotted arrows:
"Versioned package" → "Test environment" → "Approved release"
Below: "Smoke checks • rollback"
Dotted connector to UI/FastAPI indicating proposed hosting/release. Existing UI/API remain solid. This deployment group sits in the application region, not in a recommendations appendix.

5. At the application entry adjacent to FastAPI, with short dotted link to the memory boundary where practicable, integrate:
Heading "Account isolation and stated scale"
Detail "Sign-in + account access checks"
Detail "Measure five concurrent sessions"
Qualifier "If the multiple-account target is retained"
Represent as dotted proposed access boundary associated with API/session/account files. Keep current session storage solid and explicitly in-process.

6. Directly beside/under Versioned repository and its existing fingerprints annotation:
Heading "Release and experiment traceability"
Detail "One manifest: code • settings • prompts • data • results"
Short dotted lines associate this manifest with repository and scenario replay/release as space permits. Existing source hashes stay solid. This addition belongs within development/evaluation.

7. Beside "Logfire — runtime", INSIDE the logs region:
Heading "Operational budgets"
Detail "Latency • cost • failure limits"
Detail "Flag releases that exceed limits"
Short dotted edge from runtime logs to this added control. Keep the metadata-only label visible.

8. BETWEEN the runtime logs and the existing human-reviewed evaluation data, as an integrated dotted return path:
Heading "Failure-to-regression feedback"
Detail "Failure metadata → synthetic case → human review → regression test"
Detail "Keep private conversations out"
Place near the Human review node/logging column junction; use clean dotted orthogonal connector from runtime metadata to this proposal, then into existing Human review. NO raw-chat arrow. This is a visible feedback loop in the architecture.

9. Directly near Automated tests / CI extension, as a sibling dotted test node WITHIN development:
Heading "Security checks across the delivery path"
Detail "Dependency + code scans"
Detail "Retrieved-content attack tests"
Attach to the test path with a short dotted line. If space permits a discreet dotted leader toward scoped retrieval/tool adapters; do not create tangled long crossings.

FINAL CHECKS:
All nine exact headings readable; each future item spatially integrated at its affected architectural component. No bottom recommendation grid. No isolated future-features panel. All future shapes AND future edges dotted amber. Existing solid curation pipeline stays implemented and separate from chat. No new autonomous peer transport, cloud vendor, vector database, training pipeline or infrastructure platform. Preserve provider, data, session and privacy authority boundaries. Existing six strength annotations remain visible. Clean complete finished diagram, no clipped labels, no watermark.
```

## Connector corrections

```text
Edit the supplied integrated architecture image. Keep the successful integrated layout, all nine amber dotted improvements at their current local positions, ALL component boxes and all text, colors, typography and section sizes exactly as shown. Make ONLY these connector corrections, with no other changes:

1. Remove the short SOLID blue arrow directly between "Automated tests" and "Human review". These are two separate existing development/evaluation flows, not a sequential pipeline. Preserve Versioned repository → Automated tests, Human review → Reviewed evaluation data → Scenario replay, and all dotted annotations.

2. Remove the short SOLID horizontal connector directly between "Scoped book retrieval" and "Memory & Policy Service". These are separate services. Preserve BOTH existing specialist connections to scoped book retrieval, Serendipity → Memory & Policy Service, the connection to Local account memories, the books connection, and the granted Public web connection.

3. Remove the short amber dotted branch leading UP from the Failure-to-regression feedback path into "Behavioural release evidence". Feedback goes to Human review; it is not the source for that release gate. Preserve Scenario replay → Behavioural release evidence and Logfire runtime → Failure-to-regression feedback → Human review. Add ONE amber DOTTED orthogonal connector from the bottom of the Behavioural release evidence box to the top of the "Approved release" step inside Deployment and recovery, routed through clear whitespace at the bottom edge of the development region and top edge of live conversation. Avoid crossing labels; this is the proposed release-evidence dependency. Use a downward arrowhead into Approved release.

4. The small solid teal connector into Session history currently begins from Application tool adapters. Remove that connector. Connect Session history to the outer Application-owned workflow boundary with one short solid line at the right side of the Session history box. Session history is application-owned state.

Everything else remains invariant. Do not group proposals into a separate appendix. Keep solid = implemented and amber dotted = proposed. Complete full image, no crops. No added text or decorative elements.
5. Remove the amber dotted connector from Release and experiment traceability into Security checks. Keep the manifest attached locally to Versioned repository only. Do not add a replacement long connector.
```

## Final connector correction

```text
Make a minimal connector-only edit to this supplied integrated Linger diagram. Preserve EVERY box, ALL text, all positions, existing solid architecture, all nine dotted future improvements, dimensions and colors exactly.
1. Delete the long amber dotted connector running from the top of Approved release up into the left edge of Failure-to-regression feedback. These two boxes must NOT be connected. Do not add any connection between deployment and the top region.
2. Restore ONE simple amber DOTTED connector from the TOP edge of the "Logfire — runtime" box, going vertically upward through the empty right-hand logging column, then turning LEFT at the height of the "Failure-to-regression feedback" box and ending with an arrowhead at the RIGHT edge of that feedback box. This line represents runtime failure METADATA going into synthetic regression-case creation. It must not touch or branch to "Behavioural release evidence". Preserve the existing feedback-to-Human-review connector.
3. Add a tiny short vertical amber dotted connector from the bottom of Automated tests down to the top of CI completeness.
Only those three connector edits. No other changes, do not add text, do not regenerate layout, do not add an appendix. Keep all existing words and all nine integrated dotted proposed additions. Output the full finished diagram.
```

