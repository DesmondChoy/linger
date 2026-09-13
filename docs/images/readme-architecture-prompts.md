# README architecture images

Generated with the built-in imagegen tool on 2026-09-13. These are conceptual
views of the current implementation, not deployment or complete branch diagrams.

## Assets and review

- `multi-agent-architecture-v1.png`: the five role Agents, selected runtime
  skills, and application-owned services. Not all roles run on each chat turn.
- `reviewed-agent-workflows-v1.png`: successful chat and curation paths. Curation
  is separate from interactive chat; the image does not establish that a
  proposal-only evaluation runs the full curation workflow. Retained as a
  supporting asset; the README now uses the runtime-skills detail below.
- `runtime-skills-detail-v1.png`: the implemented Provenance Agent and its three
  runtime skills, showing application selection, fresh review context, typed
  verdicts, and deterministic policy enforcement. Updated from the 2026-09-12
  proposal image using built-in imagegen.

Checked against `docs/agent-skills.md`, `apps/backend/chat_turn.py`,
`src/linger/orchestration/reflection.py`, and
`src/linger/orchestration/curation.py`. The workflow arrows omit the
emotional-preflight stop path. The runtime-skills detail also matches
`src/linger/agents/provenance/agent.py`, `skills.py`, and `curation_models.py`.
The README includes a text description of the illustrated skill execution.

The initial repository-image review excluded the older reflection and connection
flows. They include photograph input and an automatic failure-to-evaluation path,
neither of which is a current runtime capability. The book identity diagram is a detailed
chapter-focused snapshot; it does not cover current named-section permissions.
The evaluation-vocabulary image inspected at the start used the older package
terminology. This change does not replace existing image files.

## Overview generation prompt

Use case: infographic-diagram
Asset type: architectural overview for Linger's GitHub README, for professors assessing a multi-agent AI systems project.
Primary request: Create a polished, technically accurate landscape architecture illustration, approximately 3:2, high-resolution raster. White background, restrained pale-blue agent cards, dark navy lettering and thin dark connectors, crisp modern sans-serif typography, generous whitespace. Professional academic architecture figure, readable when scaled to a README width of 900 pixels. No mascots, robots, gradients, texture, decorative circuits, or invented components.
Title: "Linger: five agents, explicit responsibilities"
Subtitle: "One reusable agent per role. Application-selected runtime skills."
Composition: one large outlined container labeled "APPLICATION ORCHESTRATION". At the top inside it place a wide application control bar, labeled "Select task and skill · Build typed input · Validate output". Beneath that, arrange five evenly spaced role cards in a legible grid, three in first row and two in second row. Connect the control bar to each role card by fine clean lines; these represent task dispatch, NOT autonomous peer-to-peer communication. Avoid a dense crossing network. There must be exactly five role cards, no duplicates:
"Muse" with "Conversation and revision" and "Requests permitted specialists".
"Librarian" with "Reading-boundary inference" and "Evidence assessment".
"Serendipity" with "Connection discovery" and "Memories · books · optional web".
"Sculptor" with "Memory curation and surfacing" and "Separate controlled workflows".
"Provenance" with "Emotional preflight" and "Reply and curation review".
Small simple outline icons in each card, subordinate to legible text.
Under the five cards, still inside the container, a contrasting light-gray horizontal bar labeled "APPLICATION SERVICES" and a second line "Scoped retrieval · Memory policy · Deterministic release checks".
Footer outside container, exact wording: "Agents propose and assess. Application code controls access, writes, and release."
Do not imply all five roles run on each turn. Do not put storage inside agents or show direct writes from an agent. No photos, image input, automatic learning, automatic evaluation generation, self-modification, or claims of production readiness. Spell every agent name exactly. Do not add any other text.

## Workflow generation prompt

Use case: infographic-diagram
Asset type: second architecture illustration for Linger's GitHub README; academic audience.
Primary request: Create a clean technically accurate landscape architectural workflow diagram, approximately 3:2 high-resolution raster, white background, pale-blue AI-agent cards, light-gray application-code cards, dark navy crisp sans-serif lettering, small restrained outline icons, generous whitespace. Text must remain readable at 900-pixel width. No mascots, robots, gradients, texture, invented components or decorative circuits.
Title: "Reviewed reasoning, controlled actions"
Subtitle: "Every arrow is an application-managed handoff."
Use two clearly separated horizontal swimlanes, without arrows between the lanes.
TOP lane heading exact: "CHAT · live interactive flow".
Five main boxes connected by left-to-right arrows, in exact order:
1. "Reader" / "Message"
2. "Provenance" / "Emotional preflight"
3. "Muse" / "Draft candidate"
4. "Provenance" / "Review candidate"
5. "Application" / "Validate and release".
The two Provenance boxes mean two invocations of the same role, not two different agents.
Immediately below Muse place a smaller pale-blue support card: "Librarian + Serendipity" / "Optional specialist calls". A bidirectional connector links only this support card and Muse, representing application-managed tool calls.
Below the top lane add this legible note: "One reviewed revision may be requested. Rejected or invalid candidates produce an application-owned response."
BOTTOM lane heading exact: "CURATION · separate controlled workflow".
Five main boxes connected left-to-right, in exact order:
1. "Application" / "Select bounded originals"
2. "Sculptor" / "Propose curation"
3. "Provenance" / "Review exact proposal"
4. "Memory policy" / "Validate and apply"
5. "Curated view" / "Originals preserved".
Below bottom lane add this note: "Only an approved, validated proposal is applied. No proposal or failed review leaves memories unchanged."
Bottom footer exact: "Curation is separate from chat. Interactive memory capture is disabled."
Main boxes should be comfortably large and body text short with deliberate line breaks. No direct agent-to-user release, direct model-to-storage write, chat-to-curation trigger, or claim of fully automatic long-term memory. Do not add any other text.

## Workflow correction prompt

Use case: infographic-diagram
Edit target: the supplied Linger "Reviewed reasoning, controlled actions" diagram.
Preserve the layout, dimensions, typography, connectors, all correct text, and the two separate swimlanes.
Make only these three changes:
1. Change the first box label in the CHAT lane from "Reader" to "User", keeping "Message" below it. This avoids confusion with Linger's separate developer tool named Reader.
2. Change only the fill of the bottom-lane "Memory policy" box from pale blue to the same light gray used by the bottom-lane "Application" box. Memory policy is deterministic application code, not an AI agent. Keep its shield icon and all text.
3. Replace the bottom-lane explanatory note with this exact sentence: "Only approved, validated proposals are applied. If no proposal is made or review fails, memories remain unchanged."
Do not change any other element or add any content.

## Runtime-skills detail edit prompt

Source: the Provenance proposal diagram generated on 2026-09-12 in the task
"Locate provenance curation ownership". The original is preserved in Codex's
generated-image storage. Only the updated asset is referenced by the README.

Use case: infographic-diagram.
Input image: edit target, the existing Linger diagram titled "Inside an agent: skills define the task".
Primary request: Update this diagram to describe the implemented architecture, preserving its two-column layout, all boxes, connectors, icons, three assigned skills, five review steps, white background, pale-blue and teal palette, navy typography, and readable text. This is a targeted documentation update, not a redesign.
Make these exact text changes:
1. Change the subtitle "Provenance example — proposed design" to "Provenance example: implemented runtime skills".
2. Change the top-right badge "PROPOSED" to "IMPLEMENTED".
3. Change the bottom strip from "Same responsibilities • No skill-discovery model call • Existing authority preserved" to "Explicit responsibilities • No skill-discovery model call • Application-owned authority".
4. Change the final footer to exactly: "All five agents use this pattern. Each retains its own tools, context, and authority limits."
Preserve all other words and meaning, including:
- "1 reusable Agent"
- "Emotional preflight", "Candidate review", "Curation review"
- "Selection stays in application code"
- "Same object, separate review runs"
- "Markdown holds instructions; Python enforces contracts."
- the right-hand sequence: application selects Curation review, load selected task contract, run shared Provenance Agent with fresh review context, return a typed verdict (allow/revise/reject), application validates and applies policy
- "An allow verdict alone does not write data".
The diagram shows Provenance, which has no tools and uses fresh review context. Do not add a tool or cross-run memory. The same reuse pattern applies to all five roles, but their tools and histories differ. Do not suggest production readiness, model-selected skills, automatic learning, direct writes, or new capabilities. Output a crisp high-resolution raster image with all labels fully legible and no clipping.
