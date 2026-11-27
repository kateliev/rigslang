# History

Where Rig came from. These notes are kept as they were written; the method of today is in [the guide](../../skills/rig/guide/README.md).

| File | What it is |
|---|---|
| [sidenote-agent-configuration.md](sidenote-agent-configuration.md) | The first note: agent configuration as a graph of gates and rules. |
| [self-writing-language.md](self-writing-language.md) | The memo on intent as data and code that writes itself (the snippet scale). |
| [findings-2026-11-11.md](findings-2026-11-11.md) | Research on related work, and what to learn from it. |
| [handout-language-v1.md](handout-language-v1.md) | The work order of language version 1 (2026-11-25). |
| [handout-docs-review.md](handout-docs-review.md), [review-docs-2026-11.md](review-docs-2026-11.md) | The work order and the report of the review of the texts (2026-11-25). |
| [notes-2026-11.md](notes-2026-11.md) | The dated notes that `docs/status.md` held until 2026-11-25: how version 1 was made, and the first runs with a local model. |

The examples of language version 0 and the task file of the snippet scale are only in git: `git show 5337e26:docs/history/older-examples/`. `rig.py` refuses their words.

The examples of language version 2 before the pattern example `font-names` (retired 2026-11-27) are only in git, at commit `fd5da04`:

| Example | Level | What it was | Why it was retired |
|---|---|---|---|
| `release-tool` | 3 | Check a release folder (notes, version, tests) and publish it. The pattern example until 2026-11-27. | Too small to show why the language helps: it had no `reason` block, and its model jobs were a rewrite and a tone check. |
| `band-facts` | 2 | Facts about a band from Wikipedia. | Too small, and it depended on a web service. |
| `bookmarks` | 3 | Clean up a browser bookmarks export: duplicates, similar URLs, sort loose bookmarks into folders. | The job of the model was a search over hundreds of items, the shape that a small model does worst. Its lessons are in [weak-model.md](../../skills/rig/guide/weak-model.md). |

Read one with `git show fd5da04:examples/<name>/<file>`, for example `git show fd5da04:examples/bookmarks/notes/failures-log.md`.
