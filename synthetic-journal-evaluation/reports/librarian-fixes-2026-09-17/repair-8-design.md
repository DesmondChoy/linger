# Repair after iteration 8

Drafted while batch8 remains source-frozen; implementation starts only after its completion. Original ground truth and adoption records remain unchanged.

## Complete the first boundary repair message

Pinocchio8 contains a transposed memory ID in both assessment and support fields plus duplicate/missing candidate inventory. The raw before-validation hook reports only the inventory defects, spends the one repair, then the typed after-validation hook discovers the ID typo. Include independently checkable raw memory-ID inventory faults in the first error list, even if event inventory is malformed. Assessment IDs must cover supplied memories exactly; supporting IDs must be authorized and correspond to grounded-prior-knowledge assessments, not all memories. Preserve typed grounding checks and the application recheck. No output mutation or extra retries.

Regression target: one combined defective FunctionModel response followed by a corrected response; the single feedback message includes all concurrent inventory and memory-ID defects, and exactly two calls suffice. Repairing only inventory while retaining the wrong memory ID must still fail closed within the same two-call budget.

## Preserve source identity during quotation repair

Roses8 has an actual incomplete/altered quotation. The review identifies an existing declaration object as defective but labels its quotation audit declaration index null. Clarify existing field/error guidance: use the existing declaration index even when its quote is invalid; null means there is no associated declaration and requires a current response-span finding. Keep source binding, location validation and the existing output-repair budget unchanged. This does not justify accepting the defective quote.

## Test higher reasoning effort before adding more rules

Hume8 incorrectly rejects an ordinary statement that the sources do not establish a conclusion, despite the existing policy permitting bounded uncertainty. Smoke8 falsely reports a missing declaration after the complete canonical quotation is correctly added at index1. Pigeon8 repeatedly miscopies canonical text in public output. Those are adherence/judgment failures, not missing source data. Mapping8 now proves the source-local excerpt guard corrects prior false approval (all four fixed controls pass).

Keep the approved model `openai:gpt-5.6-luna`. Test explicit high reasoning in its central OpenAI model construction; other model configurations retain their existing defaults. No new model, role, retry, or relaxed grade. The installed PydanticAI Responses adapter accepts `settings={"openai_reasoning_effort": "high"}`. Official model documentation lists medium as default and high as supported: https://developers.openai.com/api/docs/models/gpt-5.6-luna . Higher effort may increase latency/cost and is a candidate improvement, not a verified fix. Report the setting in the batch metadata. Reconsider this small candidate change if a bounded targeted run does not improve substantive reliability.

Defer canonical quote rendering and additional source-binding projection until this simpler experiment resolves whether more application machinery is warranted. Authentic source excerpts still do not prove semantic entailment, and extra verified evidence remains a separate human expectation decision.

## Boundary repair implementation evidence

The raw candidate validator now reports assessment identity coverage and supporting-memory identity faults before any early return for malformed event inventory. Feedback includes exact supplied and actual IDs, missing/unknown/duplicate assessment IDs, and supporting IDs inconsistent with the grounded assessments. Supporting memories remain the grounded subset, not every supplied memory. The typed after-validator and application authorization recheck remain unchanged; no output is rewritten and no retry is added.

Five new focused regressions failed before the implementation because the first repair omitted memory identity faults. The combined FunctionModel case now fixes memory and inventory faults in its one existing repair, while a response fixing only inventory still exhausts the same two total calls. Tests also preserve mixed supported/unsupported memories and report identity faults even when event inventory is malformed. The nearby boundary suite passed 67 tests. An offline probe against Pinocchio8's saved first candidate now reports all five concurrent error paths, including both incorrectly copied memory-ID fields. No provider request was made.
