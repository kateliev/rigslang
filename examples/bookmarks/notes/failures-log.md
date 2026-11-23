# Failures log: bookmarks

What failed and why: a method that did not work, an experiment, a kind of item that the tool cannot do. Code bugs go to `bugs-and-fixes.md`.

Read it before a batch. Do not repeat a failure that is here. Newest entry at the bottom.

| Date | What was tried | What happened | Why | What to do |
|---|---|---|---|---|
| 2026-11-23 | The answers of a human gate as a rule with letters: "G=K keeps only URL K of group G" | Qwen 35B passed it on as `G=1` and `G=1.2`, and left out `yes` | A small model copies the shape of an example, not the meaning of a letter | Code writes the answers with the real numbers of the page (`steps.how_page`): `yes 1=all`, `yes 1=3` |
| 2026-11-23 | The model told the operator to run `approve` in a terminal | In the second run the model asked the operator to answer in the chat, and left out the command | In a chat window, an answer in the chat is the natural thing | The plugin now reads an `approve` message of the operator as the answer of the person (kit change, `operatorAnswer`) |
