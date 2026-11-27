# Bugs and fixes: family-namer

One entry for each code bug: the steps, the gates, the runner, a front. Method problems go to `notes/failures-log.md`.

- Newest entry at the bottom. Number the entries: B1, B2, ...
- Write the symptom as the user or the agent saw it (the error text, the reason of the stop).
- Give the cause, the fix (files and functions), how the fix was checked, and what is left.
- A fixed bug gets a regression case, so that it cannot come back unseen.

| # | Date | Symptom | Where | Status |
|---|---|---|---|---|
| B1 | 2026-11-27 | A run that ended at `done` gave no `result`: the chosen name and the folder were not in the answer | The runner shows the value of the step before the end. In the first flow the gate `written` came before `done` | Fixed: the step `report` (`steps.report`) after `written` gives the name, the reason, the seed and the folder. Checked by `test_a_full_run_writes_the_placeholders` and the two regression cases that end at `done` |
| B2 | 2026-11-27 | With `--set names.sample=2`, every run was held back at `picks-ok`: "'Apeliotes' comes twice" | The range of `names.sample` was `2..30`, but `pick` must give three distinct drawn names (`candidates 3`) | Fixed: the range is `3..30`; a run with 2 is refused at the start. Checked by `test_a_sample_smaller_than_the_candidates_is_refused`. Left: the language cannot link the range to `candidates`; both must change together by hand |
