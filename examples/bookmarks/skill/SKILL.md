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
| `files.work` | Folder for the work of each run |
| `files.out` | Folder for the new bookmarks file |
| `keep.bar` | Leave the favorites bar alone |
| `dupes.tracking` | Tracking parameters to ignore |
| `similar.skip_hosts` | Sites with many separate pages: never group |
| `similar.skip_pattern` | Host names of documentation sites: never group |
| `similar.index_names` | Last parts of a path that name the same page as the folder |
| `similar.max_group` | Largest group to show to the person; range 2 to 50 |
| `similar.page_size` | Groups on one page of choices; range 1 to 100 |
| `sort.loose_depth` | Folders this deep or less hold loose bookmarks; range 0 to 3 |
| `sort.host_elsewhere` | Bookmarks of the same site in another folder that make one likely misfiled; range 1 to 20 |
| `sort.batch` | Bookmarks in one batch for the model; range 10 to 100 |
| `sort.choices` | Folders to choose from for one bookmark; range 2 to 12 |
| `sort.rounds` | Retries of one batch; range 0 to 5 |
| `sort.new_per_batch` | New folders in one batch; range 0 to 10 |
| `sort.new_max` | New folders in all; range 0 to 50 |
| `sort.url_chars` | Longest URL that the model sees, in characters; range 40 to 400 |
| `sort.title_chars` | Longest title that the model and the person see, in characters; range 20 to 300 |
| `safety.max_removed` | Largest share of bookmarks that one run may remove, in percent; range 1 to 100 |
| `links.check` | Check the links (not in this version) |
| `links.folder` | Folder for dead links |
| `permissions.overwrite` | The tool may write over an earlier new file |

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
