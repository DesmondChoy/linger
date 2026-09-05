# Book evaluation findings

## Result

One human-approved provider-backed replay completed on 2026-09-05 using
`openai:gpt-5.6-luna`. Two of four adopted judgments passed their deterministic
checks. The combined grounded-reflection Scene failed both of its judgments.

| Scene | Adopted expectation | Recorded behavior | Result |
|---|---|---|---|
| `pigeon-reflection` | Infer the supported reading boundary and quote the Pigeon passage. | Asked for the latest completed chapter or scene, without retrieval or quotation. | `pigeon-grounding` and `pigeon-boundary` failed. |
| `uncertain-growth` | Clarify the ambiguous reading position without retrieving a continuation. | Asked for the latest completed chapter or scene. | `growth-boundary` passed. |
| `personal-reflection` | Help with the personal concern without book retrieval. | Offered reflection and possible introductions without book tools. | `personal-grounding` passed. |

The optional semantic model review was not run. A deterministic pass does not
establish prose quality or prove the absence of paraphrased spoilers.

## Discovery: remembered context did not reach boundary inference

The failing Scene had one seeded Prop about Alice's conversation with the
Caterpillar. Its private boundary-inference input nevertheless contained zero
`relevant_memories`. Librarian proposed chapter 5 with confidence 0.99, citing
`pg11-v01b38ea4-ch05-ln1179-1219`, but labeled the basis `line_only` and cited no
memory IDs.

The application deliberately refuses to authorize reading progress from a
Line alone. In [boundary.py](../../../src/linger/orchestration/boundary.py),
`infer_spoiler_boundary` converts that basis into `progress_unverified` and a
clarification question. The recorded response was:

> What is the latest chapter or scene in Alice's Adventures in Wonderland that you have completed?

This narrows the failure: Librarian found the expected chapter, but the
memory-supported authorization required by the adopted Ground truth was absent.
Without an authorized boundary, the requested retrieval and quotation did not
happen. The quotation and support failures are consequences of that same Scene
outcome, not evidence of several independent bugs.

The trace does not yet establish why the seeded Prop was absent from the
selected memories. Follow-up `linger-h4gl` must trace memory selection and assess
the adopted assumptions. Do not weaken the authorization rule or rewrite the
approved labels merely to make this run pass. Any changed labels require fresh
human review, and another paid replay requires fresh approval.

## Evidence and scope

- [Backstory and inputs](backstory.json), [proposed Ground truth](ground-truth.json),
  and [human adoption](ground-truth-adoption.json) retain their reviewed bytes.
- [Replay summary](replay-summary.json) preserves each result, response, failure
  code, and the private boundary decision with its selected-memory count. It is
  a projection, not the complete transcript.
- Run ID: `fcb72e67a47c47b397145b09659a6b3b`.
- Trace ID: `01a06f5a6753ec83246c151a60b08b41` in the configured
  [Linger Logfire project](https://logfire-us.pydantic.dev/kevinmanuellee/linger).
- Complete local artifact: `/tmp/linger-book-replay.PSECz6/run.json`.
  SHA-256: `3a9166cc487decdd35b81df08a1ad363b10b6b68b740f0db3f6b6af3ee90b28d`.
  Temporary storage is not a repository archive; the committed summary is the
  portable findings record and omits full prompts and private candidate text.

The replay ran before upstream commits `59bc372` and `a6f1c06` were integrated.
Its base was `ac0f281` plus the then-uncommitted canonical book-contract changes.
The [pre-generation report](pre-generation-report.md) records that historical
readiness assessment. No provider replay was performed after the merge.

After integration, the full Python suite passed 641 tests and 305 subtests.
The review UI production build and both Node tests passed. Those checks verify
the implementation; they do not turn this failed evaluation into a pass.
