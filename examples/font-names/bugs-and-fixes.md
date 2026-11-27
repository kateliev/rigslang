# Bugs and fixes: font-names

One entry for each code bug: the steps, the gates, the runner, a front. Method problems go to `notes/failures-log.md`.

- Newest entry at the bottom. Number the entries: B1, B2, ...
- Write the symptom as the user or the agent saw it (the error text, the reason of the stop).
- Give the cause, the fix (files and functions), how the fix was checked, and what is left.
- A fixed bug gets a regression case, so that it cannot come back unseen.

| # | Date | Symptom | Where | Status |
|---|---|---|---|---|
| B1 | 2026-11-27 | The answer `{"Specimen": "S"}` passed `abbr-ok`: one letter is an initial, not an abbreviation | `engine.score` had a longest length only | Fixed: the rule `shorten.abbr_letters (2, 4)` gives the shortest and the longest. Checked by `test_unfair_tables` and the regression case "the model is fair on the retry" |
| B2 | 2026-11-27 | Standard `mac533` gave the names of the style table (`...-XBdCnIt`), not 5:3:3 | `engine.build_rows`: the port lost the method that each standard suggests | Fixed: `Standard.method`; `shorten.method auto` takes it. Checked by `test_mac533_is_the_method_of_its_standard` |
