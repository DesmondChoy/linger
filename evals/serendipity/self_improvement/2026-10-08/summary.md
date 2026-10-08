# Serendipity self-improvement loop

Model `openai:gpt-6-luna`, 5 repeats per case. Practice 33 cases; held back 13 cases (keller, pinocchio).

Pass mark: Scored in the same session as the production skill, a candidate passes when its practice passes exceed production's by at least 10, no practice case loses more than 2 passes, and no practice case that passed every production run falls below 4. A pass counts only if a fresh paired comparison passes again.

Round 0 (production skill, traces for the review): 123 of 165 practice runs.

| Round | Target failure | Production | Candidate | Gain | Decision | Confirmation |
|---|---|---|---|---|---|---|
| 1 | Public-source evidence held to an overly demanding standard | 124 | 122 | -2 | fail: practice gain -2 is below 10; cases lost more than 2 passes: ['serendipity-unsafe-evidence-leaves-too-little-v3']; stable cases fell below 4: ['serendipity-unsafe-evidence-leaves-too-little-v3'] | — |
| 2 | Supported evidence not developed into a two-candidate shortlist | 121 | 117 | -4 | fail: practice gain -4 is below 10; cases lost more than 2 passes: ['serendipity-alice-connect-to-reader-memory-v3']; stable cases fell below 4: ['serendipity-alice-connect-to-reader-memory-v3', 'serendipity-alice-memory-connection-real-over-echo-v3', 'serendipity-recall-two-matching-records-v3', 'serendipity-stop-after-primary-source-v3'] | — |
| 3 | Outside recommendation misrouted through book search | 116 | 112 | -4 | fail: practice gain -4 is below 10; cases lost more than 2 passes: ['serendipity-expand-to-cross-source-v3', 'serendipity-route-external-recommendation-v3'] | — |
