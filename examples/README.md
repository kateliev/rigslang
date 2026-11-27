# The examples

Two small tools, built with RIGS. Read this page before you read or change an example. When the guide and an example disagree, the example is right, because its tests run.

| Example | Level | What it does |
|---|---|---|
| [font-names](font-names/) | 3 (production) | Gives the font files of a family short names that fit a delivery standard (SharePoint, MAX_PATH, HFS, ISO 9660, 8.3, 5:3:3). **The pattern to copy.** |
| [family-namer](family-namer/) | 2 (flow) | Names a new font family from a story, with names from lists of the tool, and writes empty placeholder files. |

Both work with no font: the test cases are empty files that have font names.

## What each example shows

| Part of the language | font-names | family-namer |
|---|---|---|
| Code steps and hard gates, tested | yes | yes |
| `step ... by model` (one fast model call) | no | `topic` |
| `reason` block | `abbreviate`: `mode careful`, read-only `tools`, `budget`, `candidates 2` | `pick`: `mode creative`, `candidates 3` |
| `model` gate (a guess, marked **guessed**) | `readable` | `fits` |
| `human` gate | `approve` (yes or no) | `choose` (`options 1 \| 2 \| 3`, read by `steps.choice`) |
| Permission rule (`permissions.*`, off by default) | `permissions.rename` | no (it writes only into a new folder) |
| `rollback` and an undo log | yes | no |
| Rules: `rules` blocks, a tuple, presets | `abbr_letters (2, 4)`, presets `mac` and `dos` | lists and a seed |
| Randomness | no | code draws the names, with the rule `names.seed` |

The idea in both: code does all that code can do and checks every answer. The model gets only the small judgment that code cannot make. A person decides before anything changes.

## Read an example in this order

1. `README.md`: what the tool does, who decides what, the commands.
2. `<name>.rig`: the flow, from top to bottom. Open it in the viewer to see it as a graph (the README says how).
3. `gates.py`: what code decides. Pure functions; the numbers come from rules.
4. `steps.py` (and `engine.py` in font-names): the work. Only steps touch files.
5. `tests/`: the unit tests and `regression-set.json`, one case for each end.
6. `notes/` and `bugs-and-fixes.md`: what was true, what failed, and why.
7. `reports/`: records of runs. `font-names/reports/blind-run-plants-2026-11-27.md` is a run by a model that saw only what the tool showed it.

## The two together

The output folder of family-namer is the input of font-names. With a long tree name from the list `plants` (for example `MetasequoiaGlyptostroboides`), the table of font-names is not enough, so font-names asks its `reason` block for abbreviations. [tests/test_examples.py](../tests/test_examples.py) runs this chain with played answers. The record of a real run of the chain is `family-namer/reports/chain-plants-2026-11-27.md`.

## Run and check

Run the commands in the folder of the example. On Windows, `python3` can be a stub of the Microsoft Store: then write `py -3` (or `python`).

After a change, all of these must pass:

```bash
python3 ../../skills/rig/rig.py build .
```

```bash
python3 ../../skills/rig/rig.py doctor .
```

```bash
python3 -m unittest discover -s tests
```

```bash
python3 tool.py regress tests/regression-set.json
```

From the root of the repository, also run `python3 -m unittest discover -s tests`.

## Rules for a change

- An expected value comes from a real run. Write the `expect` of a regression case with `python3 tool.py regress tests/regression-set.json --baseline`, then read what it wrote. Never write it by hand.
- A test leaves the repository as it found it. A case that renames or writes files puts them back (`tool.py`, `clean_cases`) or works in a temporary folder.
- A test fixture is an empty file with a made-up name. Never use the name of a real font, a real foundry, or another project of the owner (`AGENTS.md`, rule 1). A Windows device name (`CON`, `AUX`, `NUL`, ...) cannot be a file name there.
- A model answer in a test or a regression case is played, and the record says so. Only a report of a real model run says what a model did.
- The docstring of an arena tool is what the model reads about it (`waiting.tool_help`). Say what the tool does and which JSON it takes.

## What is verified, and what is not

- Verified: the tests, the regression sets and the doctor of both examples; the chain, with played answers.
- One real model run: on 2026-11-27, a Claude subagent that saw only the skill and the run answered `abbreviate` and `readable` of font-names, twice (before and after a fix). It is one case, with a strong model.
- Not verified: a run by a smaller local model, which is what these tools are designed for; a model run of family-namer; the plugin and HTTP fronts with these examples.

## The earlier examples

`release-tool`, `band-facts` and `bookmarks` were retired on 2026-11-27. They are in git at commit `fd5da04`. [docs/history/README.md](../docs/history/README.md) says why.
