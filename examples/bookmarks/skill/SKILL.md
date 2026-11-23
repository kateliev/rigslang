---
name: bookmarks
description: clean up a bookmarks HTML file that Edge exported: remove exact duplicates, fold similar URLs as the person chooses, sort loose bookmarks into folders, and write a new file to import
---

# bookmarks

clean up a bookmarks HTML file that Edge exported: remove exact duplicates, fold similar URLs as the person chooses, sort loose bookmarks into folders, and write a new file to import

## Rules

Read the value of each rule from `../gen/bookmarks.json`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.

| Rule | Meaning |
|---|---|
| `files.work` | Folder for the work of each run. Note: relative to the tool folder; one sub-folder for each run, with the choices and the sorted batches. Not in version control |
| `files.out` | Folder for the new bookmarks file. Note: relative to the tool folder; the export stays where it is |
| `keep.bar` | Leave the favorites bar alone. Note: a bookmark directly on the favorites bar is a shortcut that the person put there: it is never removed, grouped or moved |
| `dupes.tracking` | Tracking parameters to ignore. Note: a name that ends with _ is a prefix. These parameters do not change the page |
| `similar.skip_hosts` | Sites with many separate pages: never group. Note: on these sites a longer path is another page with its own content, not a variant. Add a site here to stop its groups |
| `similar.skip_pattern` | Host names of documentation sites: never group |
| `similar.index_names` | Last parts of a path that name the same page as the folder. Note: home.org/index.html is home.org; code folds such a variant when the short URL is a bookmark too |
| `similar.max_group` | Largest group to show to the person; min 2, max 50. Note: a larger group is a site with many pages, not variants of one page; first value, check it on the real file |
| `similar.page_size` | Groups on one page of choices (groups); min 1, max 100. Note: first value; a page must be easy to read in a chat |
| `sort.loose_depth` | Folders this deep or less hold loose bookmarks; min 0, max 3. Note: 1: the top level and the top folders, such as Other favorites. The favorites bar is left alone (keep.bar) |
| `sort.host_elsewhere` | Bookmarks of the same site in another folder that make one likely misfiled; min 1, max 20. Note: first value, set on the test file; a single bookmark of a site in another folder says little |
| `sort.batch` | Bookmarks in one batch for the model (bookmarks); min 10, max 100. Note: the owner asked for batches of about fifty to a hundred; a small local model loses items in a longer list |
| `sort.rounds` | Retries of one batch; min 0, max 5. Note: after the retries the batch stays unsorted and the report lists it |
| `sort.new_per_batch` | New folders in one batch; min 0, max 10. Note: the owner wants the folders of the file plus a few new ones |
| `sort.new_max` | New folders in all; min 0, max 50. Note: the owner wants the folders of the file plus a few new ones |
| `sort.url_chars` | Longest URL that the model sees (characters); min 40, max 400. Note: a longer URL is cut; the model does not need the query to sort |
| `sort.title_chars` | Longest title that the model and the person see (characters); min 20, max 300. Note: a longer title is cut in what is shown; the file keeps the whole title |
| `safety.max_removed` | Largest share of bookmarks that one run may remove (percent); min 1, max 100. Note: a plan that removes more points at a bug or a wrong rule; the run is held back. First value |
| `links.check` | Check the links (not in this version). Note: the hook for a link checker: it will move dead links to the folder links.folder, never delete them |
| `links.folder` | Folder for dead links |
| `permissions.overwrite` | The tool may write over an earlier new file. Note: off: when the output file exists, the run ends at exists and writes nothing |
| `run.max_visits` | Most visits of one node in a run; min 10, max 100000. Note: the pages of choices and the sort batches are loops; a file of many thousand bookmarks needs some hundred rounds |

## How to run

Code walks this flow. You do not walk it yourself: you start a run and answer what waits.
Run every command in the folder of the tool (the folder that holds `rig.json`).

1. Start a run: `python3 tool.py run '<inputs as JSON>'` (inputs: file=<path>).
2. Read the result. It is one JSON object.
   - `outcome`: the run ended at that end node. Report it, with `problems` first. `result` is what the run made (only when a step leads to the end).
   - `waiting`: the run stopped at a node that code cannot do. Read `kind`, `do` and `brief`. `sees` holds the facts of the run that you need for this node: use them, and nothing else.
     - `judge`: decide as `brief` says. Answer: `python3 tool.py answer <run> '{"pass": true}'` (or false, with `"why"`).
     - `step`: do what `do` says. Answer: `python3 tool.py answer <run> '{"result": ...}'`.
     - `human`: show the person what `brief` says, ask, and wait. Then give the decision of the person, never your own: `python3 tool.py approve <run> yes` (or `no`, with a note).
   - `error`: a step failed. Report the error text. Do not answer the node; after the cause is fixed: `python3 tool.py resume <run>`.
   - `refused`: the call was out of order. It is final: do not repeat it. Read `at` and continue from there.
3. Repeat step 2 until the result has `outcome`.

Never decide a hard or soft gate: code decides them. Use only values from a result or from the rules.
`python3 tool.py status <run>` shows a run again; `python3 tool.py rules` shows the rules.

More than one item: `python3 tool.py batch '<a JSON list of inputs>' --report reports/<name>.md`. Code starts a run for each item and gives a summary. Then answer the runs in `left_for_model`, one at a time (`status <run>` shows what each waits for). Give the person the list `waits_for_person` and the path of the report. `python3 tool.py queues` shows what waits, at any time.

## Flow (the map of the run)

### `read` Read the export (step)

- Do: read the bookmarks file: every folder with its path, every bookmark with its title, URL, folder and date
- Rules: `files.work`
- Done by code: `steps.read`. The runner does this.
- Next: go to `file-ok`.

### `file-ok` A bookmarks export (hard gate)

- Check: the file is a bookmarks file in the Netscape HTML form, with at least one bookmark; the live JSON file of the browser is refused
- Decided by code: `gates.file_ok`. The runner does this.
- Pass: go to `dupes`.
- Fail: go to `bad-file` (not a bookmarks export).

### `dupes` Remove exact duplicates (step)

- Do: find copies of one URL, ignoring http or https, www, a last slash, a #part and the tracking parameters of dupes.tracking; keep the copy in the deeper folder, else the oldest
- Rules: `dupes.tracking`, `keep.bar`
- Done by code: `steps.dupes`. The runner does this.
- Next: go to `group`.

### `group` Group similar URLs (step)

- Do: group the URLs of one site where one path starts with another; fold the plain variants of similar.index_names; skip the sites of similar.skip_hosts and similar.skip_pattern; cut the groups into pages
- Rules: `similar.index_names`, `similar.skip_hosts`, `similar.skip_pattern`, `similar.max_group`, `similar.page_size`
- Done by code: `steps.group`. The runner does this.
- Next: go to `page`.

### `page` Next page of groups (step)

- Do: take the next page of groups that the person has not decided
- Rules: `sort.title_chars`, `run.max_visits`
- Done by code: `steps.page`. The runner does this.
- Next: go to `page-left`.

### `page-left` A page waits (hard gate)

- Check: a page of groups is not decided yet
- Decided by code: `gates.page_left`. The runner does this.
- Pass: go to `choose`.
- Fail: go to `loose` (every page is decided).

### `choose` The person chooses the URLs to keep (human gate)

- Sees: `page`
- A person decides: show the person each group of this page: its site and its URLs with their numbers, and the path of the page file. Ask which URLs to keep. Give the person the answers of how: each one is the end of the command. Stop and ask the person. Do not decide this gate yourself.
- Pass: go to `apply`.
- Fail: go to `apply` (keep every URL from here on).

### `apply` Apply the choices of the page (step)

- Do: read the answer of the person; save the choices of the page only when every word is understood
- Done by code: `steps.apply`. The runner does this.
- Next: go to `choice-ok`.

### `choice-ok` The answer is understood (hard gate)

- Check: every word of the answer names a group of the page and a choice
- Decided by code: `gates.choice_ok`. The runner does this.
- Pass: go to `page`.
- Fail: go to `choose` (the answer is not understood).

### `loose` Find loose and misfiled bookmarks (step)

- Do: leave alone the bookmarks that fit their folder; take the loose ones (sort.loose_depth) and the likely misfiled ones (sort.host_elsewhere); cut them into batches of sort.batch
- Rules: `sort.loose_depth`, `sort.host_elsewhere`, `sort.batch`, `keep.bar`
- Done by code: `steps.loose`. The runner does this.
- Next: go to `batch`.

### `batch` Next batch to sort (step)

- Do: take the next batch that is not sorted, with the folder list
- Rules: `sort.url_chars`, `sort.title_chars`, `run.max_visits`, `keep.bar`
- Done by code: `steps.batch`. The runner does this.
- Next: go to `batch-left`.

### `batch-left` A batch waits (hard gate)

- Check: a batch is not sorted yet
- Decided by code: `gates.batch_left`. The runner does this.
- Pass: go to `sort`.
- Fail: go to `folders` (every batch is sorted).

### `sort` Sort the batch (step)

- Do: put each bookmark of the batch into the folder where it fits best. Choose a folder of the list folders. A bookmark that fits its present folder keeps that folder. Only when no folder fits, propose a new folder: give its whole path under a folder of the list, and "new": true; at most `{sort.new_per_batch}` new folders in this batch. Give the result as a list with one object for each bookmark: {"id": <id>, "folder": "<path>"}. Write each path as in the list, with > between the names. Do not change a URL or a title. When waiting has problems, your last answer failed: fix them
- Rules: `sort.new_per_batch`
- Sees: `batch`
- You do this step when the run waits here.
- Next: go to `sort-ok`.

### `sort-ok` Every bookmark once, in a known folder (hard gate)

- Check: the answer has every id of the batch once and no other id, no changed URL or title, only folders of the list or new folders under them, at most `{sort.new_per_batch}` new folders in the batch and `{sort.new_max}` in all
- Rules: `sort.new_per_batch`, `sort.new_max`
- Decided by code: `gates.sort_ok`. The runner does this.
- Pass: go to `keep`.
- Fail: go to `rounds` (the answer is not good).

### `rounds` A retry is left (hard gate)

- Check: the batch was sent back at most `{sort.rounds}` times
- Rules: `sort.rounds`
- Decided by code: `gates.rounds_left`. The runner does this.
- Pass: go to `sort`.
- Fail: go to `skip` (no retry left).

### `keep` Keep the sorted batch (step)

- Do: save the folders of the batch; a bookmark whose folder did not change does not move
- Done by code: `steps.keep`. The runner does this.
- Next: go to `batch`.

### `skip` Leave the batch unsorted (step)

- Do: save the batch as unsorted: its bookmarks stay where they are, and the report lists it
- Done by code: `steps.skip`. The runner does this.
- Next: go to `batch`.

### `folders` Collect the new folders (step)

- Do: list the new folders that the model proposed, with the number of bookmarks and some titles for each
- Done by code: `steps.folders`. The runner does this.
- Next: go to `any-new`.

### `any-new` A new folder is proposed (hard gate)

- Check: the model proposed at least one new folder
- Decided by code: `gates.any_new`. The runner does this.
- Pass: go to `new-ok`.
- Fail: go to `links` (no new folder).

### `new-ok` The person agrees to the new folders (human gate)

- Sees: `folders`
- A person decides: show the person each new folder: its path, how many bookmarks go to it, and the examples. Ask: may the tool make these folders? Give the person the answers of how: each one is the end of the command. Stop and ask the person. Do not decide this gate yourself.
- Pass: go to `accept`.
- Fail: go to `accept` (no new folder).

### `accept` Apply the answer about the new folders (step)

- Do: read the answer of the person; a left-out folder keeps its bookmarks where they were
- Done by code: `steps.accept`. The runner does this.
- Next: go to `accept-ok`.

### `accept-ok` The answer is understood (hard gate)

- Check: every word of the answer names a new folder of the list
- Decided by code: `gates.accept_ok`. The runner does this.
- Pass: go to `links`.
- Fail: go to `new-ok` (the answer is not understood).

### `links` Dead links (a hook, not in this version) (step)

- Do: when links.check is on, a later version checks the links and moves dead ones to links.folder; now it only reads dead.json of the work folder, when it exists
- Rules: `links.check`, `links.folder`
- Done by code: `steps.links`. The runner does this.
- Next: go to `report`.

### `report` Write the dry-run report (step)

- Do: count and list what the new file would remove, fold, move and make, and write the report into the work folder; write nothing else
- Done by code: `steps.report`. The runner does this.
- Next: go to `share`.

### `share` Not too much removed (hard gate)

- Check: the plan removes at most `{safety.max_removed}` percent of the bookmarks
- Rules: `safety.max_removed`
- Decided by code: `gates.share_ok`. The runner does this.
- Pass: go to `approve`.
- Fail: go to `held` (the plan removes too much).

### `approve` The person agrees with the report (human gate)

- Sees: `report`
- A person decides: show the person the counts of the dry run and the path of the report. Ask: may the tool write the new bookmarks file?. Stop and ask the person. Do not decide this gate yourself.
- Pass: go to `build`.
- Fail: go to `declined` (the person said no).

### `build` Build the new file (step)

- Do: write the new file into the work folder and read it again
- Rules: `files.out`
- Done by code: `steps.build`. The runner does this.
- Next: go to `verify`.

### `verify` The new file keeps what it must (hard gate)

- Check: the new file has every bookmark that stays, with its title and URL, every folder of the export with its name, every new folder, and every moved bookmark in its new folder
- Decided by code: `gates.verify`. The runner does this.
- Pass: go to `target`.
- Fail: go to `held` (the new file failed its check).

### `target` The output file is free (hard gate)

- Check: no file has the name of the output, or the rule permissions.overwrite is on
- Rules: `permissions.overwrite`
- Decided by code: `gates.may_place`. The runner does this.
- Pass: go to `place`.
- Fail: go to `exists` (the output file exists).

### `place` Place the new file (step)

- Do: copy the checked file to the folder of files.out; the export and the files of the browser stay as they are
- Rules: `permissions.overwrite`
- Done by code: `steps.place`. The runner does this.
- Next: go to `done`.

### `done` Written: import the new file into Edge (end)

- Stop here.

### `declined` The person said no: nothing written (end)

- Stop here.

### `held` Held back by a safety check: nothing written (end)

- Stop here.

### `exists` The output file exists: nothing written (end)

- Stop here.

### `bad-file` Not a bookmarks export (end)

- Stop here.
