# Claim-mapping diagnostic, iteration 7

The four-case component run completed with 2/4 passing. All four actual verdicts were `pass`, with every declared claim marked supported and no findings. Both negative controls therefore failed by actual decision mismatch; neither is merely a risk-code mismatch. Both positive controls passed. No review repair retries are recorded.

The saved diagnostic inputs match the current case fixtures exactly after typed serialization, and all four reviews satisfy current structural validation. The model, prompt digest, case digest, complete inputs and outputs are preserved in `suite-mapping.json`. Original grades and inputs were not changed.

| Case | Source actually declared | Evidence assessment |
| --- | --- | --- |
| Wrong record | Chapter 5, lines 960–1016 | False approval. The claim says Alice cannot remember as before and that a familiar verse came out differently. This record contains the identity/size conversation, not either detail. |
| Correct record | Chapter 5, lines 1004–1056 | Correct approval. This record contains both the memory difficulty and the changed recitation. |
| Joint, missing contribution | Only lines 960–1016 | False approval. The source contributes identity/size difficulty but cannot supply the later verse clause. |
| Joint, complete | Both records | Correct approval. Each record contributes its respective part of the same complete claim. |

The later record is present in the canonical bundle even in both negative controls. The observed decisions are consistent with borrowing support from available but undeclared evidence; the output does not reveal the model's private reasoning, so that mechanism remains an inference. The defect established by the record is approval of an unsupported named-source mapping despite explicit derived group membership.

The next bounded contract correction should ask once whether each exact claim is supported collectively by its declared group, then separately whether every member contributes a relevant part. A valid earlier contribution with a missing later source is `contributes=true` but collectively `supported=false`. A wrong sole source is both noncontributing and collectively unsupported. A valid two-source claim must not require each source to establish the whole claim.

A short per-member source excerpt would additionally make positive contribution judgments concretely source-local. Validate it only against the named canonical source kind and ID, preserve decoded exact substring rules and the current retry limit, and keep it private to review. This cannot prove semantic entailment: an irrelevant authentic excerpt can still accompany a bad model judgment, and a valid partial excerpt does not establish collective completeness. It also adds copying/length risk, so it should remain a bounded excerpt rather than duplicate complete sources or introduce another model call.
