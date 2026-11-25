# bookmarks: clean up a bookmarks file of Edge

The tool reads a bookmarks HTML file that Microsoft Edge exported. It removes exact duplicates, folds similar URLs as the person chooses, and sorts loose bookmarks into folders. Then it writes a **new** HTML file to import into Edge.

It is a Rig tool, level 4 (production), made with `rig.py new`. Code does the work and every check. A local model in LM Studio does only the sorting. A person decides the similar URLs, the new folders, and whether to write the file.

The tool never changes the export, and never reads or writes the live `Bookmarks` file of the browser.

## The safe way with Edge sync

Sync is on, so a change in Edge goes to every device. Do it in this order:

1. In Edge: Settings, Favorites, **Export favorites**. Save the HTML file.
2. Run the tool on that file (below). Read the dry-run report. Answer the questions.
3. In Edge: Settings, Favorites, **Import favorites**, "Favorites or bookmarks HTML file". Choose the new file. It goes into a new folder.
4. Look at the imported folder in Edge.
5. When it is right, delete the old folders in Edge. Sync then sends normal changes to the other devices.

## Who decides what

| Node | Kind | Who |
|---|---|---|
| `file-ok`, `sort-ok`, `share`, `verify`, `target` | hard gate | code |
| `choose` (similar URLs, a page at a time), `new-ok` (new folders), `approve` (the report) | human gate | the person. `choose` and `new-ok` have `options`: code (`steps.apply`, `steps.accept`) reads the answer, and the gate asks again when it does not understand it |
| `sort` (one batch of bookmarks into folders) | step | the model; its answer has the type of `out`. In the plugin, the worker gives each batch to the model in a new context (`work_run`), with the answer bound to that schema |
| `read`, `similar`, `show`, `loose`, `prepare`, `folders`, `report`, `build`, `place` | step | code |

The flow is written in language version 1: 18 steps and gates and 4 ends (version 0 had 30 and 5). The lines run in order. Two `for` blocks hold the loops: `for page in similar.pages` (the pages of choices) and `for batch in loose.batches` (the batches to sort). The runner saves the run after each page and each batch.

What code does, in order:

1. **Read.** Every folder with its path, every bookmark with its title, URL, folder and date. The folders of the file are never renamed or deleted.
2. **Exact duplicates.** Two URLs are the same when they differ only in http or https, `www.`, a last `/`, a `#part`, or tracking parameters (`dupes.tracking`). A `#/route` or `#!route` stays: it is a page of a one-page site. The copy in the deeper folder stays, else the oldest.
3. **Similar URLs.** On one site, URLs where one path starts with another form a group (`home.org`, `home.org/events`, `home.org/users/account`). Plain variants such as `/index.html` or `/default.aspx` fold into the short URL with no question (`similar.index_names`). Sites with many separate pages are never grouped (`similar.skip_hosts`, `similar.skip_pattern`). Every other group goes to the person, a page at a time.
4. **Sort.** Code leaves alone each bookmark that shares its site with another bookmark of its folder, and every bookmark on the favorites bar. The model gets the loose bookmarks (the top level, and the top folders such as Other favorites) and the likely misfiled ones (alone in their folder, while another folder has `sort.host_elsewhere` of their site), in batches of `sort.batch`. A site of `similar.skip_hosts` (one site, many topics) never makes a bookmark misfiled. Before the first batch, code finds for each bookmark the folders most like it: the folders that share the most words with it (folder names and the titles filed there, weighted so that a common word counts less) or hold pages of its site, and its present folder at the place of its own score; `sort.choices` in all (`bm.candidates`). The model does not get the folder list: it gets the numbered choices of each bookmark, and a small map of the top folders with the names of their sub-folders. For each bookmark it writes a short topic and picks a number (`{"id": 12, "topic": "bread recipes", "pick": 2}`). When no choice fits, it also gives a folder of the map, or a new folder under one (`"new": true`). The gate `sort-ok` checks every answer: each bookmark once, no other id, no changed URL or title, a pick that is one of the choices, or a folder of the file or a new folder under one, at most `sort.new_per_batch` and `sort.new_max` new folders. A bad answer goes back to the model at most `sort.rounds` times (`retry`). Then the batch is left unsorted (`fail -> continue`). When more than 20% of the batches are left (`tolerate 20%`), the run ends at `held`.
5. **Dry run.** The report counts and lists what would be removed, folded, moved and made. Nothing else is written. The gate `share` holds back a plan that removes more than `safety.max_removed` percent.
6. **Write.** After the person agrees, code writes the file into the work folder, reads it again, and the gate `verify` checks it. Then it copies it to `out/`.

## Run it with a local model (LM Studio)

This is the main front. You need Node.js 23.6 or newer, Python 3, and LM Studio with a model that can call tools.

```bash
cd plugin && npm install && lms dev
```

Open a new chat in LM Studio, turn on the plugin, and write for example:

> Please clean up my Edge bookmarks. The exported file is /Users/me/Downloads/favorites.html

The model starts a run. When the run needs you, the model shows the question and the answers. Answer with a chat message that starts with `approve`:

| You write | It means |
|---|---|
| `approve yes` | Similar URLs: keep the shortest of each group on this page. New folders: make them all. Report: write the file. |
| `approve yes 1=all` | Group 1: keep every URL. The other groups: the shortest. |
| `approve yes 1=3` | Group 1: keep only URL 3. |
| `approve yes rest` | The shortest on this page and on every later page. |
| `approve no` | Similar URLs: keep every URL, here and later. New folders: make none. Report: write nothing. |
| `approve yes 2=no` | New folders: make all but number 2. |

The short forms above work only when exactly one run waits for you. When more than one run waits, the plugin refuses them and names the runs: then write the run id, for example `approve 20261123-232451-01 yes`. The `say` text of the question gives each answer in this long form. The plugin passes your `approve` message to the tool as your answer before the model reads it. The model cannot answer for you. The same answer works in a terminal: the result has the command in `waiting.command`.

A long file does not fit in one chat. When the chat is full, open a new chat and write "Go on with my bookmarks run". The model calls `queues`, finds the run, and goes on from the last saved batch.

## Run it with Claude

The compiled skill is `skill/SKILL.md`. Put the folder `skill/` at `.claude/skills/bookmarks/`, and tell Claude where the tool folder is.

## Run it by hand

```bash
python3 tool.py run '{"file": "~/Downloads/favorites.html"}'
```

The result is one JSON line. `waiting` says what the run needs:

```bash
python3 tool.py approve RUN yes 1=all
```

```bash
python3 tool.py answer RUN '{"result": [{"id": 4, "topic": "cooking", "pick": 2}]}'
```

```bash
python3 tool.py status RUN
```

```bash
python3 tool.py queues
```

## Where things are

| Path | What it holds |
|---|---|
| `work/<file>-<time>/` | One folder for each run: the parsed file, the duplicates, the groups, one file for each page of choices (`choices/`) and each sorted batch (`sorted/`), the report, the new file before it is checked. |
| `out/<file>-cleaned.html` | The new file to import. A second run does not write over it (`permissions.overwrite`). |
| `runs/<run id>/` | One folder for each run of the runner: the run, a copy of the flow and the rules, every answer of the model and of the person. A run goes on after a restart: `python3 tool.py resume RUN`. `python3 tool.py replay RUN` plays the recorded answers again with the current code. |

None of these goes into version control. Neither does any HTML file outside `tests/fixtures/`.

## Change a value

The values are rules in `bookmarks.rig`. To change one for one run, add `--set`:

```bash
python3 tool.py run '{"file": "favorites.html"}' --set sort.batch=40
```

To change it for good, change the rule in `bookmarks.rig`, then:

```bash
python3 ../../skills/rig/rig.py build .
```

The list of sites that are never grouped is the rule `similar.skip_hosts`. To see all rules as a table and the flow as a graph:

```bash
python3 ../../skills/rig/rig.py serve bookmarks.rig --json gen/bookmarks.json
```

## Check it

```bash
python3 ../../skills/rig/rig.py doctor .
```

```bash
python3 tool.py regress tests/regression-set.json
```

The tests and the regression set use only the synthetic file `tests/fixtures/export.html`. `tests/make_big.py` makes a larger synthetic file for a long run with a model.

## Dead links: not in this version

The step `report` holds the hook (`steps.dead_links`). A later link checker writes the ids of dead bookmarks to `dead.json` in the work folder. The report then moves them to the folder of `links.folder` ("Dead links"). Nothing is deleted. With `links.check` on, this version stops with an error that says so.

## Limits

- A folder is never renamed, merged or deleted. An empty folder stays.
- The model sees a URL cut at `sort.url_chars` and a title cut at `sort.title_chars`. The file keeps the whole text.
- A batch that fails `sort-ok` after `sort.rounds` retries stays unsorted. The report lists it. When more than 20% of the batches stay unsorted, nothing is written (`held`).
- The output file exists: the run ends at `held` with the reason "the output file exists" (version 0 had its own end, `exists`).
- After an `approve no` on a page, every later page keeps all its URLs too.
- What was verified and what was not: see `notes/project-facts.md`.

## After a change, also update

- The table "You write / It means" above, when the answers of a human gate change (`steps.how_page`, `steps.how_new`).
