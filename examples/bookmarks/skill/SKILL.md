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

Code walks this flow. You do not walk it yourself: you start a run and answer what waits.
Run every command in the folder of the tool (the folder that holds `rig.json`).

1. Start a run: `python3 tool.py run '<inputs as JSON>'` (inputs: file=<path>).
2. Read the result. It is one JSON object.
   - `outcome`: the run ended at that end. Report it, with `problems` first. `result` is what the run made (only when a step leads to the end).
   - `waiting`: the run stopped at a node that code cannot do. Read `kind`, `do` and `check`. `sees` holds the facts of the run that you need for this node: use them, and nothing else.
     - `model` (a gate): decide what `check` says. Answer: `python3 tool.py answer <run> '{"pass": true}'` (or false, with `"why"`).
     - `step`: do what `do` says. Answer: `python3 tool.py answer <run> '{"result": ...}'`. When `waiting` has `schema`, the result must have that form.
     - `human`: show the person the question (`name` and `check`), `sees`, and the text of `say` as it is (it names the answers; the first option is the default). Then wait. Give the answer of the person, never your own: `python3 tool.py approve <run> yes` (or `no`), or `python3 tool.py approve <run> <the words of the person>`.
   - `problems` in `waiting`: your last answer at this node failed. Fix these problems in the new answer.
   - `refused`: the call was out of order. It is final: do not repeat it. Read `at` and continue from there.
3. Repeat step 2 until the result has `outcome`. The outcome `error` means that code failed: report the error text. Do not answer for code.

Never decide a hard or soft gate: code decides them. Use only values from a result or from the rules.
`python3 tool.py status <run>` shows a run again; `python3 tool.py rules` shows the rules.

More than one item: `python3 tool.py batch '<a JSON list of inputs>' --report reports/<name>.md`. Code starts a run for each item and gives a summary. Then answer the runs in `left_for_model`, one at a time (`status <run>` shows what each waits for). Give the person the list `waits_for_person` and the path of the report. `python3 tool.py queues` shows what waits, at any time.

## Flow (the map of the run)

The lines run in order. A gate that passes goes on to the next line.

### `read` Read the export (step)

- Do: read the bookmarks file: every folder with its path, every bookmark with its title, URL, folder and date
- Rules: `files.work`
- Done by code: `steps.read`. The runner does this.

### `file-ok` A bookmarks export (hard gate)

- Check: the file is a bookmarks file in the Netscape HTML form, with at least one bookmark; the live JSON file of the browser is refused
- Decided by code: `gates.file_ok`. The runner does this.
- Fail: go to `bad-file` (not a bookmarks export).

### Duplicates and similar URLs

#### `similar` Remove exact duplicates, group similar URLs (step)

- Do: find copies of one URL, ignoring http or https, www, a last slash, a #part and the tracking parameters of dupes.tracking; keep the copy in the deeper folder, else the oldest. Then group the URLs of one site where one path starts with another; fold the plain variants of similar.index_names; skip the sites of similar.skip_hosts and similar.skip_pattern; cut the groups into pages
- Rules: `dupes.tracking`, `keep.bar`, `similar.index_names`, `similar.skip_hosts`, `similar.skip_pattern`, `similar.max_group`, `similar.page_size`
- Done by code: `steps.dupes`, `steps.group`. The runner does this.

**For each `page` in `similar.pages`** (block `for:page`):
- Do the lines of this block once for each item. The item is `page`.

##### `show` Show the page (step)

- Do: write the page of groups into a file; when the person said rest on an earlier page, decide this page as they said, and ask nothing
- Rules: `sort.title_chars`
- Done by code: `steps.page`. The runner does this.

##### `choose` Which URLs to keep? (human gate)

- Only when `show.ask` is not empty and not false. Else go on to the next line.
- Check: show the person each group of this page: its site and its URLs with their numbers, and the path of the page file. Give the person the answers of show.how: each one is the end of the command
- Sees: `show`
- A person decides. Stop and ask the person. Do not decide this gate yourself.
- The answers: `yes`, `yes rest`, `no`. The first is the default: the answer when the person only agrees. Code (`steps.apply`) reads the answer; when it does not understand it, ask again.
- Note: the answer is the words after approve: yes, then G=all, G=short, G=K or rest. no keeps every URL from here on. Code asks again when it does not understand a word

**End of the block `for:page`.**

### Sorting

#### `loose` Find loose and misfiled bookmarks (step)

- Do: leave alone the bookmarks that fit their folder; take the loose ones (sort.loose_depth) and the likely misfiled ones (sort.host_elsewhere; not for a site of similar.skip_hosts); cut them into batches of sort.batch. Then, once for all batches, find for each one the folders most like it: its present folder and the best others, sort.choices in all
- Rules: `sort.loose_depth`, `sort.host_elsewhere`, `sort.batch`, `sort.choices`, `keep.bar`, `similar.skip_hosts`, `similar.skip_pattern`
- Done by code: `steps.loose`. The runner does this.

**For each `batch` in `loose.batches`** (block `for:batch`):
- Do the lines of this block once for each item. The item is `batch`.
- When more than 20% of the items are left (fail -> continue), the block fails after the last item.
- Fail: go to `held`.

##### `prepare` The batch for the model (step)

- Do: give the bookmarks of the batch, each with its numbered choices, a map of the top folders with the names of their sub-folders, and the new folders of the earlier batches; keep the whole folder list for the gate
- Rules: `sort.url_chars`, `sort.title_chars`, `keep.bar`
- Done by code: `steps.prepare`. The runner does this.

##### `sort` Sort the batch (step)

- Do: for each bookmark of the batch, first write topic: what the page is about, in a few words. Name the subject, not the site: for a shop, what it sells; for a profile, what the person makes. Then pick the choice whose folder is about that topic. now is the number of its present folder: pick now when that folder fits the topic, and move the bookmark only when another choice fits clearly better. Look only at the choices of that bookmark, and decide each bookmark once. When no choice fits, keep pick and also give "folder": the whole path of a folder of map, with > between the names; folder then counts in place of pick. When no folder fits at all, give as folder the whole path of a new folder under a folder of a choice or of map, and "new": true; at most `{sort.new_per_batch}` new folders in this batch. A folder of new_so_far needs no "new". Give the result as a list with one object for each bookmark: {"id": <id>, "topic": "<a few words>", "pick": <number>}. Do not change a URL or a title. When waiting has problems, your last answer failed: fix them
- Rules: `sort.new_per_batch`
- Sees: `prepare.batch`, `prepare.of`, `prepare.bookmarks`, `prepare.map`, `prepare.new_so_far`
- The answer has the type `(list (record id int topic str pick int folder (maybe str) new (maybe bool)))`.
- You do this step when the run waits here.

##### `sort-ok` Every bookmark once, in a known folder (hard gate)

- Check: the answer has every id of the batch once and no other id, no changed URL or title, a pick that is one of the choices of that bookmark, or a folder (it counts in place of the pick) of the file or a new folder under one, at most `{sort.new_per_batch}` new folders in the batch and `{sort.new_max}` in all; then the batch is saved
- Rules: `sort.new_per_batch`, `sort.new_max`, `sort.rounds`
- Decided by code: `gates.sort_ok`, `steps.keep`. The runner does this.
- On fail: do `sort` again, at most sort.rounds times. Then take the fail line.
- Note: steps.keep saves a batch that passed: it runs only after gates.sort_ok passes
- Fail: leave this item, note it for the report, and go on to the next item of `for:batch`.

**End of the block `for:batch`.**

#### `folders` Collect the new folders (step)

- Do: list the new folders that the model proposed, with the number of bookmarks and some titles for each
- Done by code: `steps.folders`. The runner does this.

#### `new-ok` Make these new folders? (human gate)

- Only when `folders.new` is not empty and not false. Else go on to the next line.
- Check: show the person each new folder: its path, how many bookmarks go to it, and the examples. Give the person the answers of folders.how: each one is the end of the command
- Sees: `folders`
- A person decides. Stop and ask the person. Do not decide this gate yourself.
- The answers: `yes`, `no`. The first is the default: the answer when the person only agrees. Code (`steps.accept`) reads the answer; when it does not understand it, ask again.
- Note: yes N=no leaves out new folder N: its bookmarks stay where they are. no makes no new folder

### Output

#### `report` Write the dry-run report (step)

- Do: count and list what the new file would remove, fold, move and make, and write the report into the work folder; write nothing else. When links.check is on, a later version checks the links first and moves dead ones to links.folder; now it only reads dead.json of the work folder, when it exists
- Rules: `links.check`, `links.folder`
- Done by code: `steps.report`. The runner does this.

#### `share` Not too much removed (hard gate)

- Check: the plan removes at most `{safety.max_removed}` percent of the bookmarks
- Rules: `safety.max_removed`
- Decided by code: `gates.share_ok`. The runner does this.
- Fail: go to `held` (the plan removes too much).

#### `approve` May the tool write the new bookmarks file? (human gate)

- Check: show the person the counts of the dry run and the path of the report
- Sees: `report`
- A person decides. Stop and ask the person. Do not decide this gate yourself.
- Fail: go to `declined` (the person said no).

#### `build` Build the new file (step)

- Do: write the new file into the work folder and read it again
- Rules: `files.out`
- Done by code: `steps.build`. The runner does this.

#### `verify` The new file keeps what it must (hard gate)

- Check: the new file has every bookmark that stays, with its title and URL, every folder of the export with its name, every new folder, and every moved bookmark in its new folder
- Decided by code: `gates.verify`. The runner does this.
- Fail: go to `held` (the new file failed its check).

#### `target` The output file is free (hard gate)

- Check: no file has the name of the output, or the rule permissions.overwrite is on
- Rules: `permissions.overwrite`
- Decided by code: `gates.may_place`. The runner does this.
- Fail: go to `held` (the output file exists).

#### `place` Place the new file (step)

- Do: copy the checked file to the folder of files.out; the export and the files of the browser stay as they are
- Rules: `permissions.overwrite`
- Done by code: `steps.place`. The runner does this.

### `done` Written: import the new file into Edge (end)

- Stop here.

### `bad-file` Not a bookmarks export (end)

- Stop here.

### `held` Held back by a safety check: nothing written (end)

- Stop here.

### `declined` The person said no: nothing written (end)

- Stop here.
