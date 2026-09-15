# Cross-source connections and restraint

## Decision

The current implementation is **sufficient** to execute and evaluate this plan after separate human approval. Replay-support wording and evidence-authority rules now agree, and the prompt includes a freshly verified public-source snapshot. This establishes execution readiness, not reliable model success: known routing failures remain evaluation targets.

| Planned Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| S1: supported connection | Cite personal memory, book evidence, and public evidence while keeping the interpretation tentative. | runnable | Mixed release, scoped evidence authority, and current guarded public capture are verified below. |
| S2: same-source restraint | Explore the same available sources, explain their insufficiency, and qualify, decline, or request better evidence. | runnable | `tests/test_synthetic_connection_replay.py:46` requires inspection; S1/S2 share the supplied exact snapshot and independently trusted reading setup. |
| S3: personal comparison | Offer useful non-factual reflection without source retrieval. | runnable | The no-source path exists; historical `unexpected_exploration` is observable, not an absent execution path. |

The evaluated outcome is the released connection or helpful restraint, its source support, and private-query protection. Session-history persistence is terminal product context; capture, curation, and later surfacing are outside these Objectives.

## Your selection

- **Cross-source tentative connection** (`cross_source_tentative_connection`): Serendipity explores authorized memories, books, and public evidence; Muse cites support, protects private wording, and Provenance blocks unsupported certainty.
- **Weak-evidence safe decline** (`weak_evidence_safe_decline`): Muse and Serendipity qualify or decline unsupported connections while Provenance blocks invented support and permits helpful personal reflection.

## Target evaluation design

Use the [canonical vocabulary](../../../docs/specification.md#721-canonical-vocabulary).

| Term | Application to this plan |
|---|---|
| Objective | Preserve the two confirmed IDs in their confirmed order. Cover both connection contrasts and the weak-evidence personal comparison. |
| Backstory | One corpus-backed history for one person and one evaluation account. Discover a currently registered, enabled, chapter-based work at invocation; do not reuse a previous report's book facts. |
| Prop | One separate prior reflection, active before S1 and S2, unavailable in S3. Both source-bearing Scenes use the same record. No fabricated captures or derived memories. |
| Scene | Three ordered fresh-session Scenes. S1 covers connection; S2 covers both Objectives; S3 covers weak evidence. This shares a contrast coherently without changing either catalog minimum. |
| Line | One natural conversational input per Scene. Each source-bearing Scene independently establishes consistent completed reading context. No offline inputs; reset, capture policy, and URL grants are workflow controls. |
| Ground truth | Four proposed Scene/Objective judgments in a separate file, with exact source spans, evidence, complete Prop relevance, and declared pairings. An independent human adopts, revises, or rejects each; validation never adopts labels. |

[`models.py`](../../../evals/synthetic_journals/models.py) defines `SyntheticBackstory` with `backstory`, `props`, `scenes`, `lines`, and `source_setups`. Each setup holds reader-confirmed book scope and complete public snapshots. `ProposedGroundTruth` binds exact Backstory bytes and owns `proposals[].connection`. Use these contracts and the [validator](../../../evals/synthetic_journals/validate_package.py) unchanged. No generation preset applies; `run_configuration_ids` and `offline_inputs` are empty.

## Current implementation and required work

**Observed.** Production and adopted replay reach the selected endpoint. The following evidence reconciles current code with historical records.

| Evidence | What it establishes |
|---|---|
| `apps/backend/chat_turn.py:721`; `src/linger/orchestration/connection.py:98`; `reflection.py:556` | Trusted setup → active account records → Provenance preflight → Muse → optional Serendipity/Librarian/guarded Exa → canonical selected evidence → Provenance review → deterministic release → retained released turn. |
| `connection_replay.py:274`; `tests/test_synthetic_connection_replay.py:86,118` under `evals/synthetic_journals/` and `tests/` respectively | One account, isolated Scene stores, capture disabled, immutable Props, private released citations, no labels passed to runtime. |
| `tests/test_synthetic_connection_package.py:130,153,200`; `tests/test_ground_truth_review.py:464` | Source/label representation, rejected invalid sources and hidden paired differences, independent-review payload. |
| Commits `8dbcb99`, `9ba48ab`, `7a50f81` | Mixed evidence and adopted replay; private-query protection refinement; component-runner error reporting respectively. The last does not expand adopted production coverage. |
| Commits `29b3f5c`, `1e99f55`; HEAD `0ebe42c` | Descriptive package names/presets; literary parts and named units; verification record. A compatible chapter-based work keeps this plan within the existing connection contract. |
| Closed Beads `linger-0eeh`, `linger-j2ei`, `linger-ahbj`, `linger-7agz` | Implemented mixed contracts, earlier guarded capture, privacy repair, literary-unit verification. Earlier successful book replay is not a mixed-source success claim. |
| Open `linger-bmz`, `linger-w995`, `linger-b7p6` | Tracking status lags implemented replay; model exploration remains inconsistent; some tests depend on local web settings. Mocked tool calls prove plumbing, not reliable model routing. |

**Observed.** The [latest checked-in connection run](../alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/connection-run.json) failed S1 at retrieval, S2 at invocation, and S3 for unnecessary exploration. It predates current HEAD. Contrary to `linger-5wrf`'s description, its full agent exchanges contain the rejection findings. S1 also omitted memory from selected citations. These are inspectable failures, not missing observability.

**Observed.** The prerequisites are resolved without a parallel schema or replay. No further build-out is required for this design.

| Resolved prerequisite | Implementation and verification |
|---|---|
| Support statements (`linger-oigg`) | Specification §§7.2.1–7.2.2 now agree with the catalog and exact-selection dispatcher, including legacy weak-evidence delegation. |
| Evidence authority (`linger-5wrf`) | Muse v17 and Provenance v9 scope empty/weak/failed results to each call. Other canonical evidence can support a claim; unresolved boundaries and unsupported claims still fail. `test_empty_direct_search_preserves_selected_evidence_authority` checks valid support, invented citations, and independent rejection. Prompt semantics still need live evaluation. |
| Public-source capture (`linger-d4ay`) | `evals/synthetic_journals/public_source_capture.py` uses production guarded Exa search/open and formatting. `tests/test_public_source_capture.py` checks metadata, truncation, exact search leads, query protection, and replay acceptance versus altered text. Live Hume capture produced 8,000 characters at `2026-09-12T03:48:30.943742Z`, SHA-256 `8cc5c9f4fc00573a39026f6a0895d91841f4bae6c317898e4141ecf44cebf97f`. |


**Proposed.** Retain the three-Scene design and compatible chapter-based scope. **Assumed.** The selected book and future personal history can form a coherent comparison with the supplied philosophical source; independent review decides that semantic fit. **Observed.** The combined suite passed 1,059 tests and 485 subtests; no live model evaluation ran. Credentials and Logfire are configured. Eventual replay must enable web retrieval for that process. All ten authorized test runs are used; another replay needs a new run allowance.

| Material file | SHA-256 prefix |
|---|---|
| `evaluation-objectives.yaml` | `6355a654c69e` |
| `docs/specification.md` | `016c4bb537a1` |
| `apps/backend/chat_turn.py` | `79f08b7d034c` |
| `src/linger/agents/provenance/prompt.py` | `6d0602317f69` |
| `evals/synthetic_journals/models.py` | `61770c4d7277` |
| `evals/synthetic_journals/validate_package.py` | `499c670e4981` |
| `evals/synthetic_journals/connection_contract.py` | `ee278e72d536` |
| `evals/synthetic_journals/connection_replay.py` | `d6924255d7a3` |
| `src/linger/agents/serendipity/tools.py` | `9d45a18face0` |
| `src/linger/corpus/registry.py` | `9a9f88e9a793` |
| `src/linger/agents/muse/prompt.py` | `faee1a1b8e57` |
| `evals/synthetic_journals/public_source_capture.py` | `40cf3248b849` |

Snapshot: `main`, HEAD `0ebe42c2f1b575f58e7f587c889cd5e5690a9b84`, `2026-09-12T11:51:21+08:00`; dirty with the specification, prompt, helper, documentation, tests, report, and Beads changes. HEAD alone does not reproduce these fixes. Catalog confirmation hash: `6355a654c69ede304db55ce0aabc0bcd5bac8ff0753055cd0975971569ddaec5`.

## Expected behavior and evaluation

These are input hypotheses, not authored Lines or exact response oracles.

| Representative input | Likely behavior and success check |
|---|---|
| S1 asks whether a prior reflection, a passage, and public context illuminate each other. | Explore all three sources; cite resolvable support; present a possible parallel without claiming causation. Check query privacy and distinguish interpretation from sourced facts. |
| S2 asks for a stronger explanation than those same sources justify. | Inspect the evidence, state its limits, and qualify, decline, or request better evidence. Missing retrieval must not masquerade as successful restraint. |
| S3 explores a nearby personal tension without factual source claims. | Respond usefully without exploration or invented evidence; avoid blanket refusal. |

All paths retain preflight and release gates. A preflight boundary skips ordinary agents; ambiguity requests clarification; provider, evidence, or review failure fails closed. One revision may return for review. Failed releases cannot commit capture; this plan disables it throughout. Hard checks and human judgments remain separate.

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PACKAGE_DIRECTORY=synthetic-journal-evaluation/packages/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12

PRECONDITIONS
Do not write either output until a human separately approves this design and prompt. The current checkout implements the selected package and independent-adoption path. Read current permitted contracts at invocation time; if they cannot represent the design unchanged, stop without output.

Use the exact verified public snapshot embedded below. Its content was obtained through the production guarded search/open path, not fabricated by a generator. Preserve all text, headers, provenance, and hashing. Use only complete passages before the truncated final sentence. It is a public-domain philosophical argument about identity, not empirical proof of the person's psychology or causation.

Discover currently registered and enabled work/version choices from permitted repository paths and select a chapter-based work whose passages support this design. Do not reuse book facts from earlier reports or convert a named unit or part into a chapter number. If registration, source evidence, or the supported chapter contract cannot be verified, stop and report the gap. Later runtime retrieval may change; it must be checked again during independently authorized replay.

You have read-only access to the current checkout. Inspect data/corpus/, src/linger/corpus/ for registration and literary structure, apps/backend/config.py only for allowed book versions, evals/synthetic_journals/models.py, and evals/synthetic_journals/validate_package.py. Never read .env or credentials. Repository code may execute its normal imports during validation; do not inspect runtime prompts, other synthetic packages, agent transcripts, evaluator implementations, judge rubrics, raw catalog metadata, or the human report. Do not invoke Linger or a model to score content. Do not fetch or manufacture alternative public evidence.

Write exactly two sibling files: PACKAGE_DIRECTORY/backstory.json and PACKAGE_DIRECTORY/ground-truth.json. Do not overwrite the report or create adoption, replay, frozen-data, or other files. Use the current package models unchanged; invent no schema or fields.

Preserve this ordered objective_ids list:
cross_source_tentative_connection
weak_evidence_safe_decline

Create one corpus-backed Backstory for one person and one evaluation account. Make the discovered book plausible within the person's reading habits. Keep the Backstory generation-only. Every Prop and Scene belongs to it, and every Line belongs to its Scene.

Write one independently understandable prior-reflection Prop as separate source text, not copied from the Backstory or any complete Line. Give it an active lifecycle before S1 and S2 only. Do not fabricate records that claim to have been captured or curated during execution.

Create three ordered fresh-session Scenes, each with one natural conversational Line and no offline inputs. Use empty run_configuration_ids. Reset and capture policy are trusted workflow controls, not Lines.

S1 uses the Prop, a passage from the discovered eligible book, and the supplied public source. Invite a useful tentative link without demanding a conclusion. Preserve distinct personal, literary, and public-evidence roles. Assign cross_source_tentative_connection.

S2 uses exactly the same active Prop and available book/public setup. Change the conversational question so that a plausible stronger interpretation is unsupported by those sources. Make the limitation visible in the source content, not hidden history. Invite interpretation naturally without asking for refusal. Assign both selected Objectives.

S3 has no Props, public sources, or book scope. Ask a nearby useful personal reflection that needs no factual evidence. Assign weak_evidence_safe_decline. Do not make it a disguised book or research question.

For S1 and S2 independently establish consistent completed reading context. Neither fresh session inherits the other's conversation. Put work/version and reader_confirmed safe_ceiling_chapter in each source_setups.book_scope. Select exact book support at or before that ceiling. Copy the supplied PublicSourceSnapshot unchanged into both source setups; never reformat its text. S3 has no source setup. Include no internal agents, routing instructions, expected decisions, or grading labels in Props or Lines. Never place private Prop wording in text intended for public search.

Write the separate ground truth file as proposed Ground truth with ground_truth_status="proposed" and the SHA-256 of the exact final backstory.json bytes. Create four proposals, one per Scene/Objective pair: S1 connection proposal, S2 connection restraint, S2 weak-evidence restraint, S3 weak-evidence not_requested. Use the typed connection expectation only; do not use grounding or book_scene_facts for this plan.

For S1, require resolvable memory, book, and public support and tentative_connection as the acceptable response. Supply exact Prop references, hash-bound repository book evidence, and public-source excerpts. Propose each public factual claim that requires a citation; distinguish it from personal interpretation. Keep unsupported certainty and private-query disclosure prohibited.

For both S2 judgments, propose compatible qualified, declined, or request_better_evidence responses. Include inspectable insufficient evidence and explain what it cannot establish. Require helpful restraint; prohibit internal component names, evaluator labels, invented support, and private wording in public queries. Permitted evidence and mandatory citation are different: a response that asserts no factual source claim need not quote everything inspected. Do not demand invented sources or make retrieval outages an intended success.

For S3, propose personal_reflection with no declared, permitted, or required evidence and no public factual claims. Prohibit fabricated support, internal-component disclosure, and unnecessary refusal while preserving useful non-factual response possibilities.

Give every proposal expected_outcomes and prohibited_outcomes, exact source spans where needed, and one prop_relevance judgment for every Prop available in its Scene. A Prop may be relevant to understanding a question without supporting its stronger conclusion. Evidence identifiers must be unique and references resolvable. Use exact Unicode codepoint offsets with exclusive ends, unchanged repository file hashes, and exact public snapshot substrings.

Declare contrasting Scene pairings for every proposal. Pair S1/S2 with identical available sources and the changed Line; pair S2/S3 with the actual differences in Line, Props, and source setup. Declare every changed material field, keep claimed matches equal, and do not hide changes behind identifiers.

Run the existing deterministic package validator at evals/synthetic_journals/validate_package.py against these two files. Correct schema, hashes, references, offsets, ordering, evidence, pairings, and complete Prop relevance until validation succeeds. Do not relax the validator or alter the approved design to obtain a pass; stop for a contract gap.

Validation establishes resolvable objective facts, not semantic realism, label correctness, Linger performance, or adoption. A human independent of you adopts, revises, or rejects every proposed label later. Never grade recorded behavior or describe your labels as adopted. Neither proposed nor adopted Ground truth may enter the system under evaluation.

VERIFIED_PUBLIC_SOURCE_SNAPSHOT_JSON
{
  "source_id": "hume-personal-identity",
  "url": "https://davidhume.org/texts/t/1/4/6",
  "title": "Hume Texts Online",
  "text": "Title: Hume Texts Online\nURL: https://davidhume.org/texts/t/1/4/6\n\nHume Texts Online\n\n#### Of personal identity.\n\nT HERE are some philosophers, who imagine we are every moment intimately conscious of what we call our Self; that we feel its existence and its continuance in existence; and are certain, beyond the evidence of a demonstration, both of its perfect identity and simplicity. The strongest sensation, the most violent passion, say they, instead of distracting us from this view, only fix it the more intensely, and make us consider their influence on self either by their pain or pleasure. To attempt a farther proof of this were to weaken its evidence; since no proof can be deriv'd from any fact, of which we are so intimately conscious; nor is there any thing, of which we can be certain, if we doubt of this.\n\n T 1.4.6.2, SBN 251-2 \n\nUnluckily all these positive assertions are contrary to that very experience, which is pleaded for them, nor have we any idea of self, after the manner it is here explain'd. For from what impression cou'd this idea be deriv'd? This question 'tis impossible to answer without a manifest contradiction and absurdity; and yet 'tis a question, which must necessarily be answer'd, if we wou'd have the idea of self pass for clear and intelligible. It must be some one impression, that gives rise to every real idea. But self or person is not any one impression, but that to which our several impressions and ideas are suppos'd to have a reference. If any impression gives rise to the idea of self, that impression must continue invariably the same, thro' the whole course of our lives; since self is suppos'd to exist after that manner. But there is no impression constant and invariable. Pain | and pleasure, grief and joy, passions and sensations succeed each other, and never all exist at the same time. It cannot, therefore, be from any of these impressions, or from any other, that the idea of self is deriv'd; and consequently there is no such idea.\n\n T 1.4.6.3, SBN 252 \n\nBut farther, what must become of all our particular perceptions upon this hypothesis? All these are different, and distinguishable, and separable from each other, and may be separately consider'd, and may exist separately, and have no need of any thing to support their existence. After what manner, therefore, do they belong to self; and how are they connected with it? For my part, when I enter most intimately into what I call myself, I always stumble on some particular perception or other, of heat or cold, light or shade, love or hatred, pain or pleasure. I never can catch myself at any time without a perception, and never can observe any thing but the perception. When my perceptions are remov'd for any time, as by sound sleep; so long am I insensible of myself, and may truly be said not to exist. And were all my perceptions remov'd by death, and cou'd I neither think, nor feel, nor see, nor love, nor hate after the dissolution of my body, I shou'd be entirely annihilated, nor do I conceive what is farther requisite to make me a perfect non-entity. If any one upon serious and unprejudic'd reflection, thinks he has a different notion of himself, I must confess I can reason no longer with him. All I can allow him is, that he may be in the right as well as I, and that we are essentially different in this particular. He may, perhaps, perceive something simple and continu'd, which he calls himself; tho' I am certain there is no such principle in me.\n\n T 1.4.6.4, SBN 252-3 \n\nBut setting aside some metaphysicians of this kind, I may venture to affirm of the rest of mankind, that they are nothing but a bundle or collection of different perceptions, which succeed each other with an inconceivable rapidity, and are in a perpetual flux and movement. Our eyes cannot turn in their sockets without varying our perceptions. Our thought | is still more variable than our sight; and all our other senses and faculties contribute to this change; nor is there any single power of the soul, which remains unalterably the same, perhaps for one moment. The mind is a kind of theatre, where several perceptions successively make their appearance; pass, re-pass, glide away, and mingle in an infinite variety of postures and situations. There is properly no simplicity in it at one time, nor identity in different; whatever natural propension we may have to imagine that simplicity and identity. The comparison of the theatre must not mislead us. They are the successive perceptions only, that constitute the mind; nor have we the most distant notion of the place, where these scenes are represented, or of the materials, of which it is compos'd.\n\n T 1.4.6.5, SBN 253 \n\nWhat then gives us so great a propension to ascribe an identity to these successive perceptions, and to suppose ourselves possest of an invariable and uninterrupted existence thro' the whole course of our lives? In order to answer this question, we must distinguish betwixt personal identity, as it regards our thought or imagination, and as it regards our passions or the concern we take in ourselves. The first is our present subject; and to explain it perfectly we must take the matter pretty deep, and account for that identity, which we attribute to plants and animals; there being a great analogy betwixt it, and the identity of a self or person.\n\n T 1.4.6.6, SBN 253-5 \n\nWe have a distinct idea of an object, that remains invariable and uninterrupted thro' a suppos'd variation of time; and this idea we call that of identity or sameness. We have also a distinct idea of several different objects existing in succession, and connected together by a close relation; and this to an accurate view affords as perfect a notion of diversity, as if there was no manner of relation among the objects. But tho' these two ideas of identity, and a succession of related objects be in themselves perfectly distinct, and even contrary, yet 'tis certain, that in our common way of thinking they are generally confounded with each other. That action | of the imagination, by which we consider the uninterrupted and invariable object, and that by which we reflect on the succession of related objects, are almost the same to the feeling, nor is there much more effort of thought requir'd in the latter case than in the former. The relation facilitates the transition of the mind from one object to another, and renders its passage as smooth as if it contemplated one continu'd object. This resemblance is the cause of the confusion and mistake, and makes us substitute the notion of identity, instead of that of related objects. However at one instant we may consider the related succession as variable or interrupted, we are sure the next to ascribe to it a perfect identity, and regard it as invariable and uninterrupted. Our propensity to this mistake is so great from the resemblance above-mention'd, that we fall into it before we are aware; and tho' we incessantly correct ourselves by reflection, and return to a more accurate method of thinking, yet we cannot long sustain our philosophy, or take off this biass from the imagination. Our last resource is to yield to it, and boldly assert that these different related objects are in effect the same, however interrupted and variable. In order to justify to ourselves this absurdity, we often feign some new and unintelligible principle, that connects the objects together, and prevents their interruption or variation. Thus we feign the continu'd existence of the perceptions of our senses, to remove the interruption; and run into the notion of a soul, and self, and substance, to disguise the variation. But we may farther observe, that where we do not give rise to such a fiction, our propension to confound identity with relation is so great, that we are apt to imagine [50] something unknown and mysterious, connecting the parts, beside their relation; and this I take to be the case | with regard to the identity we ascribe to plants and vegetable",
  "source_sha256": "8cc5c9f4fc00573a39026f6a0895d91841f4bae6c317898e4141ecf44cebf97f",
  "retrieved_at": "2026-09-12T03:48:30.943742Z"
}
```

## Ground truth lifecycle

The generator proposes; repository code validates exact hashes, references, spans, ordering, permitted evidence, pairings, and complete Prop relevance. The implemented review app gives an independent human every source and label. Adoption binds both files' exact bytes. Only then may one authorized replay grade them. Semantic realism, relevance, usefulness, and label quality are human judgments, not deterministic checks. No ownership or review-tooling gap remains.

## Architecture and academic relevance

Muse, Librarian, Serendipity, and Provenance participate; Sculptor does not. Application orchestration, account-scoped Memory & Policy, session state, corpus resolution, and guarded Exa enforce authority. A model proposal cannot authorize its own citations or release.

The briefing asks how agent coordination adds value and makes decisions traceable, and lists testing artifacts and evaluation results ([PDF pp. 9, 11, 13](../../../docs/submissions/aas-practice-module-briefing.pdf#page=9)). Comparing useful connection, honest restraint, and ordinary reflection can supply a concrete demo and evidence trail for those questions. This is a proposed demonstration, not a mandated scenario. The memo follows [Google's documentation guidance](https://developers.google.com/style/highlights).

> **Human decision required:** Approve this target design and generator prompt, revise them, or abandon this attempt. This report does not generate data or adopt labels; live replay will also need a fresh run allowance.
