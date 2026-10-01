# Round 1 error analysis

## Categories

- **Answer window falls beyond the returned-passage cutoff** (2: n07, n11): The exact answering window appears in the query’s turn-order candidates but is not in the returned pool; higher-listed windows are returned instead. In n07 the answer ranks 109th by keyword and 8th by meaning and occurs deep in turn order; in n11 the answer occurs just after the first three turn-order entries. 2 traces.
- **Exact answer window absent from the candidate turn order** (1: n09): The exact answering window does not appear in the displayed turn-order list or returned pool, although other windows from the answering chapter or about the same episode appear. The answer ranks are 10th by keyword and 4th by meaning in n09. 1 trace.

## Notes on each trace

- n01 (pass): —
- n02 (pass): —
- n03 (pass): —
- n04 (pass): —
- n05 (pass): —
- n06 (pass): —
- n07 (FAIL): The answering passage in chapter 11 explains that Fire Eater felt sorry for Pinocchio and spared him; it was not among the passages returned. The pool instead included a chapter 10 passage about the earlier threat and unrelated passages.
- n08 (pass): —
- n09 (FAIL): The answering passage in chapter 18 describes Pinocchio burying and watering the coins, but that exact window is absent from the turn-order list and returned pool. The pool instead contains passages about his lie to the Fairy and the Fox’s earlier explanation of the Field of Wonders.
- n10 (pass): —
- n11 (FAIL): The answering passage in chapter 22 shows Pinocchio barking, the Farmer finding the Weasels, and catching them. The returned passages cover the guard-dog setup and the Weasels’ offer, not that outcome.
- n12 (pass): —
- n13 (pass): —
- n14 (pass): —
- n15 (pass): —
- n16 (pass): —
- n17 (pass): —
- n18 (pass): —
- n19 (pass): —
- n20 (pass): —
