# Annotated Logfire tutorial screenshots

Created on 14 September 2026 using the built-in imagegen tool. Each image was edited from the original capture and visually checked against its input. The tutorial and its worked-example results were not rerun.

Green numbered circles match the instructions on the same PDF page. Green indicates attention or an action, not a pass. Amber outlines mark interpretation cautions. The local review screenshot still shows an unchecked approval box.

The exact final prompts, input screenshot paths, generated source paths, and saved asset paths are in [annotation-prompts.json](annotation-prompts.json). The source paths record the authoring workspace; use the relative links below to open the committed images.

| PDF page | Saved screenshot | Callouts |
| --- | --- | --- |
| 3 | [reviewer.png](reviewer.png) | 1 compares Scene inputs with Proposed Ground truth; 2 points to the unchecked approval box. |
| 4 | [dataset.png](dataset.png) | 3 opens Review latest run. Amber marks the Not reported caveat. |
| 5 | [overview.png](overview.png) | 1 completed cases; 2 task errors; 3 grade label; 4 run metadata. Amber marks Assertions. |
| 6 | [case15.png](case15.png) | 1 expands Input; 2 compares actual and expected output; 3 opens the trace. |
| 7 | [case14-review-flag.png](case14-review-flag.png) | 1 automated grade; 2 separate semantic review requirement. |
| 9 | [trace.png](trace.png) | 1 actual exchange and supplied memories; 2 structured assistant result. |
| 10 | [agents.png](agents.png) | 1 opens Sculptor Traces. |
| 10 | [models.png](models.png) | 2 selects the model row. |

The case 15 screenshot was regenerated once to keep its comparison arrow clear of the Expected output heading. The prompt manifest contains the accepted final prompt. All other selected images use their first annotation prompt.
