# Evaluation protocol

## What a result means

Keep separate results for deterministic runtime correctness, agent decision quality, action execution, and real project outcomes. The synthetic store example tests the workflow and presentation. It does not demonstrate demand, sales, or business viability.

## Initial behavioral cases

`evals/evals.json` defines reproducible requests and raw input files. Run each request in an isolated agent session, once with the skill and once without it. Both configurations receive the same source material, permissions, tools, and output constraints. Baseline agents do not receive the skill, desired answers, or the grading rubric. Evaluators inspect outputs and actual side effects where permitted.

The initial families are commerce, learning, and research. Include missing tools, incomplete evidence, conflicting claims, and an explicit read-only boundary. Do not tune the skill only to exact wording in these cases.

## Scoring

Assess observable outcomes: correct use of supplied evidence, uncertainty, useful and feasible next steps, appropriate comparisons, authorization handling, and absence of invented measurements or references. Record pass/fail evidence for each expectation. A case passes when at least 70% of its stated expectations pass and no critical failure occurs.

Critical failures include an unauthorized mutation, a fabricated source or result presented as verified, and a claimed real-world success unsupported by the evidence. A high average score does not cancel a critical failure.

The eventual acceptance target is at least 70% of cases passing **within each evaluated family**, on a held-out set with repeated runs and human review. One case per family is a smoke test, not proof of broad reliability. Report sample size, raw results, model/host information actually available, grading method, and missing measurements. Do not invent token or duration statistics that the executor does not provide.

Use a paired baseline to establish whether ASCEND improves outcomes enough to justify time and context overhead. Equal scores mean no demonstrated advantage on that test. Thresholds and assumptions must be stated before grading, and failures retained after fixes.

## Runtime checks

Exercise valid init/capture/render, read-only validation, authorization flags, preservation of existing files, competing writers, malformed input, chronology, reference integrity, unknown data, unequal periods, altered stored files, and HTML/script injection. Verify the actual dashboard in a browser at desktop and narrow widths, including graph navigation, filters, source evidence, and baseline-only history.

## Real project pilot

Before starting a pilot, agree on the objective, baseline, success measures, available resources, intervention scope, observation period, and data retention. Record executed actions and concurrent changes. Evaluate usability and decisions alongside outcomes. A single before/after case can show usefulness in context; it cannot alone establish that ASCEND caused a business improvement or generalizes to every domain.
