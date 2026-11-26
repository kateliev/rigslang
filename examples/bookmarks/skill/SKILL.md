---
name: bookmarks
description: clean up a bookmarks HTML file that Edge exported: remove exact duplicates, fold similar URLs as the person chooses, sort loose bookmarks into folders, and write a new file to import
---

# bookmarks

clean up a bookmarks HTML file that Edge exported: remove exact duplicates, fold similar URLs as the person chooses, sort loose bookmarks into folders, and write a new file to import

Never: overwrite an existing output file unless permissions.overwrite is on (gate `target`)
Never: write the new file without human approval (gate `approve`)

## Rules

Read the value of each rule from `../gen/bookmarks.json`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.

| Rule | Meaning |
|---|---|
| `files.work` | Folder for the work of each run. Note: relative to the tool folder; one sub-folder for each run, with the choices and the sorted batches. Not in version control |
| `files.out` | Folder for the new bookmarks file. Note: relative to the tool folder; the export stays where it is |
| `keep.bar` | Leave the favorites bar alone. Note: a bookmark directly on the favorites bar is a shortcut that the person put there: it is never removed, grouped or moved |
| `dupes.tracking` | Tracking parameters to ignore. Note: a name that ends with _ is a prefix. These parameters do not change the page |
| `similar.skip_hosts` | Sites with many separate pages: never group. Note: on these sites a longer path is another page with its own content, not a variant. Add a site here to stop its groups. A sub-domain counts too (bg.wikipedia.org). Such a site has pages of many topics, so in sorting it never makes a bookmark misfiled and never points to a folder |
| `similar.skip_pattern` | Host names of documentation sites: never group |
| `similar.index_names` | Last parts of a path that name the same page as the folder. Note: home.org/index.html is home.org; code folds such a variant when the short URL is a bookmark too |
| `similar.max_group` | Largest group to show to the person; range 2 to 50. Note: a larger group is a site with many pages, not variants of one page; first value, check it on the real file |
| `similar.page_size` | Groups on one page of choices; range 1 to 100. Note: a page must be easy to read in a chat. 2026-11-25, first run on a real export with a local Qwen 35B: of a page of 20 groups the model showed 9, so 20 became 8 |
| `sort.loose_depth` | Folders this deep or less hold loose bookmarks; range 0 to 3. Note: 1: the top level and the top folders, such as Other favorites. The favorites bar is left alone (keep.bar) |
| `sort.host_elsewhere` | Bookmarks of the same site in another folder that make one likely misfiled; range 1 to 20. Note: first value, set on the test file; a single bookmark of a site in another folder says little |
| `sort.batch` | Bookmarks in one batch for the model; range 10 to 100. Note: the owner asked for batches of about fifty to a hundred; a small local model loses items in a longer list. 2026-11-25, first real run with a local Qwen 35B: a batch of 60 with the whole list of 227 folders made the model think in a loop and give no answer, so 60 became 30 and the model got choices (sort.choices) |
| `sort.choices` | Folders to choose from for one bookmark; range 2 to 12. Note: its present folder and the folders that code finds most like it, by shared words and by site. The model picks one of these and does not read the whole folder list. First value |
| `sort.rounds` | Retries of one batch; range 0 to 5. Note: after the retries the batch stays unsorted and the report lists it |
| `sort.new_per_batch` | New folders in one batch; range 0 to 10. Note: the owner wants the folders of the file plus a few new ones |
| `sort.new_max` | New folders in all; range 0 to 50. Note: the owner wants the folders of the file plus a few new ones |
| `sort.url_chars` | Longest URL that the model sees, in characters; range 40 to 400. Note: a longer URL is cut; the model does not need the query to sort |
| `sort.title_chars` | Longest title that the model and the person see, in characters; range 20 to 300. Note: a longer title is cut in what is shown; the file keeps the whole title |
| `safety.max_removed` | Largest share of bookmarks that one run may remove, in percent; range 1 to 100. Note: a plan that removes more points at a bug or a wrong rule; the run is held back. First value |
| `links.check` | Check the links (not in this version). Note: the hook for a link checker: it will move dead links to the folder links.folder, never delete them |
| `links.folder` | Folder for dead links |
| `permissions.overwrite` | The tool may write over an earlier new file. Note: off: when the output file exists, the run ends at held and writes nothing |

## How to run

Code walks this flow. Start a run and answer only what waits. Run every command in the folder that holds `rig.json`.

1. Start: `python3 tool.py run '<inputs as JSON>'` (inputs: file=<path>).
2. Read the JSON result:
   - `outcome`: the run ended. Report it, with `problems` first (and `result` if present). `error` means code failed.
   - `waiting` (`kind: model`): decide `check` from `sees` (respecting `intent`). Run `python3 tool.py answer <run> '{"pass": true, "why": "..."}'` (or `false`).
   - `waiting` (`kind: step`): do `do` from `sees`. Run `python3 tool.py answer <run> '{"result": ...}'` matching `schema` if present.
   - `waiting` (`kind: reason`): deliberate (`mode`: `careful` or `creative`) respecting `intent`, `never` boundaries, and any `candidates` count; use `python3 tool.py arena <run> <tool>` for read-only tools up to `budget`. Run `python3 tool.py answer <run> '{"result": ...}'`.
   - `waiting` (`kind: human`): show the person `name`, `check`, `sees`, and `say` word for word; wait, then run `python3 tool.py approve <run> yes` (or `no` / their words). Never answer for a person.
   - `waiting.problems`: fix those problems in the new answer. `refused`: final — run `python3 tool.py status <run>`.
3. Repeat step 2 until `outcome`. Never decide a hard or soft gate yourself.

More commands: `python3 tool.py batch '<JSON list>' --report reports/<name>.md`, `python3 tool.py next-batch`, `python3 tool.py queues`, `python3 tool.py status <run>`, `python3 tool.py rules`, `python3 tool.py flow`.

## Flow (summary)

The runner walks 10 code steps and 5 code gates automatically (`python3 tool.py flow` shows the full map).

| Node | Kind | Action / check | Sees | Out / options |
|---|---|---|---|---|
| `choose` | human gate | Which URLs to keep? — show the person each group of this page: its site and its URLs with their numbers, and the path of the page file. Give the person the answers of show.how: each one is the end of the command | `show` | `yes` / `yes rest` / `no` |
| `sort` | model step | for each bookmark of the batch, first write topic: what the page is about, in a few words. Name the subject, not the site: for a shop, what it sells; for a profile, what the person makes. Then pick the choice whose folder is about that topic. now is the number of its present folder: pick now when that folder fits the topic, and move the bookmark only when another choice fits clearly better. Look only at the choices of that bookmark, and decide each bookmark once. When no choice fits, keep pick and also give "folder": the whole path of a folder of map, with > between the names; folder then counts in place of pick. When no folder fits at all, give as folder the whole path of a new folder under a folder of a choice or of map, and "new": true; at most `{sort.new_per_batch}` new folders in this batch. A folder of new_so_far needs no "new". Give the result as a list with one object for each bookmark: {"id": <id>, "topic": "<a few words>", "pick": <number>}. Do not change a URL or a title. When waiting has problems, your last answer failed: fix them | `prepare.batch`, `prepare.of`, `prepare.bookmarks`, `prepare.map`, `prepare.new_so_far` | `list[{id: int, topic: str, pick: int, folder?: str, new?: bool}]` |
| `new-ok` | human gate | Make these new folders? — show the person each new folder: its path, how many bookmarks go to it, and the examples. Give the person the answers of folders.how: each one is the end of the command | `folders` | `yes` / `no` |
| `approve` | human gate | May the tool write the new bookmarks file? — show the person the counts of the dry run and the path of the report | `report` |  |

Ends: `done` — Written: import the new file into Edge, `bad-file` — Not a bookmarks export, `held` — Held back by a safety check: nothing written, `declined` — The person said no: nothing written.
