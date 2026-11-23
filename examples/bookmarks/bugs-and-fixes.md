# Bugs and fixes: bookmarks

One entry for each code bug: the steps, the gates, the runner, a front. Method problems go to `notes/failures-log.md`.

- Newest entry at the bottom. Number the entries: B1, B2, ...
- Write the symptom as the user or the agent saw it (the error text, the reason of the stop).
- Give the cause, the fix (files and functions), how the fix was checked, and what is left.
- A fixed bug gets a regression case, so that it cannot come back unseen.

| # | Date | Symptom | Where | Status |
|---|---|---|---|---|
| B1 | 2026-11-23 | The favorites bar was in the folder list of the sort, so the model could move a bookmark onto the bar | `steps.batch` | Fixed: with `keep.bar` on, the bar is not in the list, and `sort-ok` refuses it. Test: `test_steps.Steps.test_the_steps_in_order` |
| B2 | 2026-11-23 | A long run with a model: 13 bookmarks in the right folder went to the model as "misfiled" | `bm.fits` | Fixed: loose bookmarks of a site (in the top folders) no longer count as "another folder that has the site". Test: `test_bm.Fits.test_loose_misfiled_and_fit` |
