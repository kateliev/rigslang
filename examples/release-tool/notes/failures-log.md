# Failures log: release

What failed and why. Code bugs go to `bugs-and-fixes.md`. Newest entry at the bottom.

| Date | What was tried | What happened | Why | What to do |
|---|---|---|---|---|
| 2026-11-15 | The word limit of the notes only as text in the instructions of the model (an earlier example in this repository did this with a limit of its own). | The model went over the limit and nothing saw it. | A limit in a prompt is a suggestion. | Every limit is a rule, and a gate in code reads it (`gates.notes_ok`). |
