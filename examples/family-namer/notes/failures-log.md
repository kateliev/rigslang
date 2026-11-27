# Failures log: family-namer

What failed and why: a method that did not work, an experiment, a kind of item that the tool cannot do. Code bugs go to `bugs-and-fixes.md`.

Read it before a batch. Do not repeat a failure that is here. Newest entry at the bottom.

| Date | What was tried | What happened | Why | What to do |
|---|---|---|---|---|
| 2026-11-27 | The chain to font-names with the preset `mac` (HFS, 31 characters) | font-names ended at `same`: nothing to rename | Every placeholder name already fits: the longest family of the lists is `AjaxTheLesser`, and its longest file name has 28 characters | To see font-names shorten names, use the preset `dos` (8.3), or a list with longer names |
