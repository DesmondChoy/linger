# Serendipity self-improvement loop

Model `openai:gpt-6-luna`, 5 repeats per case. Practice 33 cases; held back 13 cases (keller, pinocchio).

Pass mark: Scored in the same session as the production skill, a candidate passes when its practice passes exceed production's by at least 10, no practice case loses more than 2 passes, and no practice case that passed every production run falls below 4. A pass counts only if a fresh paired comparison passes again.

Round 0 (production skill, traces for the review): 151 of 165 practice runs.

| Round | Mode, parent | Target failure | Production | Candidate | Gain | Gain by pattern | Frontier | Decision | Confirmation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | improve, production | Topical recommendation rejected for incomplete explanation | 143 | 150 | +7 | recall -2, restraint +3, routing +4, selection +2 | round-1 | fail: practice gain 7 is below 10; stable cases fell below 4: ['serendipity-recall-two-matching-records-v3'] | — |
| 2 | improve, round-1 | External recommendations require the source to answer the whole question | 148 | 149 | +1 | recall +1, restraint +0, routing +0, selection +0 | round-1, round-2 | fail: practice gain 1 is below 10 | — |
| 3 | merge, round-1 | Outside recommendation is over-expanded or over-rejected | 148 | 147 | -1 | recall +1, restraint -2, routing +2, selection -2 | round-1, round-2 | fail: practice gain -1 is below 10; stable cases fell below 4: ['serendipity-decline-insufficient-bridge-v3'] | — |
