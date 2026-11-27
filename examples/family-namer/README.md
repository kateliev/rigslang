# family-namer

A rig built with RIGS, level 2 (flow). It names a new font family after a figure or a thing that a story asks for, then makes a folder of empty placeholder font files. The output folder is the input of [font-names](../font-names/): run font-names on it to shorten the file names.

The tool never invents a name. Code holds the lists of names (`lists/`) and draws names at random. The model only chooses: first the list that the story asks for, then three of the drawn names, with a reason for each. Code checks every answer, and a person chooses the name.

| Who decides | What |
|---|---|
| Code | the lists, the random draw (`names.seed`), a known list (`topic-ok`, `has-list`), names from the draw (`picks-ok`), valid family names (`names-ok`), a new folder (`free`), every placeholder written (`written`) |
| The model | the list for the story (`step topic by model`: one fast call), three names with reasons (`reason pick`, `mode creative`, `candidates 3`), and whether the names fit the story (`gate fits model`: a guess, marked **guessed**) |
| A person | the name of the family (`gate choose human`, `options 1 \| 2 \| 3`, read by `steps.choice`) |

What this example shows that font-names does not: a single-shot `step ... by model`, a `reason` block in `mode creative` with `candidates 3`, randomness done by code with a seed rule, and a human gate with `options` and a `by` function.

| File | What it is |
|---|---|
| `family-namer.rig` | The source: the rules, the steps, the reason block, the gates and the ends. Change the flow and the values here. |
| `lists/` | The name lists, one JSON file for each list: `plants.json` (29 trees), `trojan-heroes.json` (65 names) and `winds.json` (13 names). Each list names its source. |
| `gates.py` | Every decision that code can make. Pure Python, with tests. |
| `steps.py` | The work: read the lists, draw, make family names, read the choice of the person, write the placeholders. The only code that touches the files. |
| `tool.py` | The runner: one command line that every front calls. |
| `tests/` | The tests of the gates and the steps, the regression set, and the case folder `cases/taken` (a family folder that exists). |
| `reports/` | Records of real runs, for example the chain on the list `plants`. |
| `gen/` | Compiled from the source: the catalogue. Do not edit. |
| `skill/SKILL.md` | Compiled from the source: the Agent Skill. Do not edit. |
| `rigkit.py` | The tool's own copy of the RIGS runtime. `rig.py build` keeps it current. |
| `rig.json` | The project file: the level, the source, the compiled files, the tests command. |
| `out/`, `runs/` | The new families, and the runs. Not in version control. |

`RIG` is the path of `skills/rig/rig.py` in the RIGS repository.

## Run

A run with a fixed seed, so that the draw is the same each time (`names.seed 0` makes a new draw for each run; the result records the seed that it used):

```bash
python3 tool.py run '{"story": "A sturdy serif for a museum show about the siege of Troy"}' --set names.seed=7
```

The run waits at `topic` for the model. The model sees the story and the lists, and names one list:

```bash
python3 tool.py answer r1 '{"result": {"list": "trojan-heroes", "why": "the story is about the siege of Troy"}}'
```

Code draws 8 names. With seed 7 they are Lycaon, Sthenelus, Phoenix, Derinoe, Odysseus, Diomedes, Glaucus and Paris. The run waits at `pick`: the model chooses three of them, best first:

```bash
python3 tool.py answer r1 '{"result": [{"name": "Odysseus", "why": "the hero of the long way home; the long name reads well in a serif"}, {"name": "Diomedes", "why": "a bold fighter at the walls of Troy; round letters for a sturdy face"}, {"name": "Glaucus", "why": "an ally who fought for Troy; a short name with an open G"}]}'
```

Then the model judges the gate `fits`, and a person chooses a name with its number (or types the name):

```bash
python3 tool.py answer r1 '{"pass": true, "why": "all three are heroes of the siege of Troy"}'
python3 tool.py approve r1 2
```

The run ends at `done`. The result names the family `Diomedes`, its reason, the seed, and the folder `out/Diomedes` with four empty files: `Diomedes-Bold.otf`, `Diomedes-BoldItalic.otf`, `Diomedes-Italic.otf` and `Diomedes-Regular.otf`. An answer that the gate does not understand (`approve r1 4`) makes the gate ask again. `approve r1 no` ends at `declined`, and nothing is written.

Or let a model do its part: `python3 tool.py work r1 --api-url URL --model NAME`. The worker routes `topic` to the fast model and `pick` to the reasoning tier (`--reason-model`). No live model run of this example is recorded yet.

## The chain: family-namer, then font-names

The folder of the new family is the input of font-names. The run ids below are the ids of a new `runs/` folder in font-names, in this order.

### Heroes: font-names needs no model

These runs used the folder `out/Diomedes` from the run above:

```bash
cd ../font-names
python3 tool.py run '{"folder": "../family-namer/out/Diomedes"}' --preset mac
```

Run `r1` ends at `same`: every name already fits HFS (31 characters). The longest family of the hero and wind lists is `AjaxTheLesser` (13 letters), so with these styles no name is longer than 28 characters.

```bash
python3 tool.py run '{"folder": "../family-namer/out/Diomedes"}' --preset dos
python3 tool.py approve r2 yes
```

The preset `dos` (8.3, no model) gives `DMDSBD.otf`, `DMDSBDIT.otf`, `DMDSIT.otf` and `DMDSRG.otf`. Run `r2` ends at `ready`: a dry run, nothing renamed. To rename, start a new run with the permission:

```bash
python3 tool.py run '{"folder": "../family-namer/out/Diomedes"}' --preset dos --set permissions.rename=on
python3 tool.py approve r3 yes
python3 tool.py restore r3
```

Run `r3` renamed the four files and ended at `done`. `restore r3` put the old names back.

### Plants: font-names asks the model

The list `plants` holds trees with long binomial names. With the preset `mac`, their file names do not fit HFS with the built-in table, so font-names stops at its reason block `abbreviate`. A story such as "A calm book face named after a tree" asks for this list. With `names.seed=7`, played answers and the choice 1, family-namer wrote `out/MetasequoiaGlyptostroboides`. Then:

```bash
cd ../font-names
python3 tool.py run '{"folder": "../family-namer/out/MetasequoiaGlyptostroboides"}' --preset mac
```

The run waits at `abbreviate` for the weak words `Metasequoia` and `Glyptostroboides`. Without fair abbreviations, the names would be `MtsqGlptstrbds-Rg` and so on (dropped vowels). The commands, the played answers and the exact `waiting` JSON are in [reports/chain-plants-2026-11-27.md](reports/chain-plants-2026-11-27.md). A real model gives the next answers: `python3 tool.py work r1 --api-url URL --model NAME`.

## Change

Change a value or the flow in `family-namer.rig`, and the code in `gates.py` and `steps.py`. To add a list, put a JSON file in `lists/`: `{"name": ..., "about": ..., "source": ..., "names": [{"name": ..., "note": ...}]}`. The test `test_the_lists_of_the_tool_are_valid` checks that every name becomes a valid family name. For `plants`, `test_every_plant_makes_font_names_ask_the_model` also checks with the engine of font-names that each name makes it stop at `abbreviate`. Then:

```bash
python3 RIG build .
```

```bash
python3 RIG doctor .
```

To record the regression set again after a change of the flow (never write `expect` by hand):

```bash
python3 tool.py regress tests/regression-set.json --baseline
```
