# Failures log: bookmarks

What failed and why: a method that did not work, an experiment, a kind of item that the tool cannot do. Code bugs go to `bugs-and-fixes.md`.

Read it before a batch. Do not repeat a failure that is here. Newest entry at the bottom.

| Date | What was tried | What happened | Why | What to do |
|---|---|---|---|---|
| 2026-11-23 | The answers of a human gate as a rule with letters: "G=K keeps only URL K of group G" | Qwen 35B passed it on as `G=1` and `G=1.2`, and left out `yes` | A small model copies the shape of an example, not the meaning of a letter | Code writes the answers with the real numbers of the page (`steps.how_page`): `yes 1=all`, `yes 1=3` |
| 2026-11-23 | The model told the operator to run `approve` in a terminal | In the second run the model asked the operator to answer in the chat, and left out the command | In a chat window, an answer in the chat is the natural thing | The plugin now reads an `approve` message of the operator as the answer of the person (kit change, `operatorAnswer`) |
| 2026-11-25 | Sort batch 1 of 5 on a real export: 60 bookmarks and the whole list of 227 folders | Qwen 35B wrote about 57,000 characters of thinking and no answer. For each bookmark it read the folder list line by line ("Let's look at X. No.") and then repeated the same lines | A choice among 227 paths is a search; a small model does it in its thinking and loses its place. Many of the 188 misfiled bookmarks were pages of wikipedia, google, github or reddit, sites that say nothing about a topic | Code finds the folders most like each bookmark once, in `steps.loose` (`bm.candidates`). The model gets at most `sort.choices` numbered choices and answers `{"id", "pick"}`; it does not see the folder list. A site of `similar.skip_hosts` no longer makes a bookmark misfiled. `sort.batch` 60 became 30 |
