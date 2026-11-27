# font-names

A rig built with RIGS, level 3 (production). It gives the font files of a family short file names that fit a delivery standard: SharePoint, Windows MAX_PATH, HFS (31), ISO 9660, DOS 8.3 or Mac 5:3:3. The names stay readable and unique, and nothing is renamed without a person.

Code does almost all of the work (`engine.py`): the name pattern, the Adobe 5088 table of style abbreviations, the limits and character rules of each standard, and the uniqueness. The model has one small job. When the table does not know a word of the family, the only ways left for code are to drop vowels, use initials or cut the name. Then a `reason` block asks the model for abbreviations of those words, and the model can test each table with the real engine (`try_names`) before it answers. A hard gate decides whether the answer is fair.

| Who decides | What |
|---|---|
| Code | the names, every limit, fair abbreviations (`abbr-ok`), uniqueness, permission, the check after the rename |
| The model | abbreviations for words that the table does not know (`reason abbreviate`, 2 candidates, read-only tools, budget), and whether the names still read well (`gate readable model`: a guess, marked **guessed**) |
| A person | the rename (`approve`) |

The test cases need no font: the tool reads and renames files only, so the fixtures in `tests/cases/` are empty files with font names.

| File | What it is |
|---|---|
| `font-names.rig` | The source: the rules, the steps, the reason block, the gates and the ends. Change the flow and the values here. |
| `engine.py` | The naming engine. Pure Python, standard library only. |
| `gates.py` | Every decision that code can make. Pure Python, with tests. |
| `steps.py` | The work: read the folder, plan, the arena tools, rename and undo. The only code that touches the files. |
| `tool.py` | The runner: one command line that every front calls. |
| `tests/` | The tests of the engine, the gates and the steps, the regression set, and the case folders. |
| `gen/` | Compiled from the source: the catalogue. Do not edit. |
| `skill/SKILL.md` | Compiled from the source: the Agent Skill. Do not edit. |
| `rigkit.py` | The tool's own copy of the RIGS runtime. `rig.py build` keeps it current. |
| `rig.json` | The project file: the level, the source, the compiled files, the tests command. |
| `runs/`, `undo/` | The runs, and the undo log of each rename. Not in version control. |

Run the commands in this folder. They use `python3`. On Windows, `python3` can be a stub of the Microsoft Store that only prints "Python was not found": then write `py -3` (or `python`) in its place.

## Run

A dry run on a family whose words the table does not know (HFS, 31 characters):

```bash
python3 tool.py run '{"folder": "tests/cases/display"}' --preset mac
```

The preset `mac` sets the standard HFS; the preset `dos` sets 8.3 without the model. The run waits at `abbreviate` for the model. The model can test a table, answer with two candidates, then judge the gate `readable`:

```bash
python3 tool.py arena r1 steps.try_names '{"table": {"Specimen": "Spc", "Grotesque": "Grt"}}'
python3 tool.py answer r1 '{"result": [{"Specimen": "Spc", "Grotesque": "Grt"}, {"Specimen": "Sp", "Grotesque": "Gr"}]}'
python3 tool.py answer r1 '{"pass": true, "why": "Spc and Grt read as Specimen Grotesque"}'
python3 tool.py approve r1 yes
```

The run ends at `ready`: `SpecimenGrotesqueDisplay-ExtraBoldCondensedItalic.woff2` would become `SpcGrtDs-XBdCnIt.woff2`, and nothing is renamed. With `--set permissions.rename=on` it renames the files and ends at `done`. `python3 tool.py restore r1` puts the old names back.

Or let a model do its part: `python3 tool.py work r1 --api-url URL --model NAME`.

## See the flow as a graph

Start the viewer on the source file:

```bash
python3 ../../skills/rig/rig.py serve font-names.rig --json gen/font-names.json
```

Open http://127.0.0.1:8765 in a browser (`--port N` sets another port). Stop the viewer with Ctrl+C.

The page has four tabs:

| Tab | What it shows |
|---|---|
| Units | The intent, the inputs and the output, and a table of every node: what it does, where it goes, and the rules it reads. |
| Graph | The flow. The top band is code, the middle band is the model, the bottom band is the person. The columns are the order of the lines; the ends stand at the right. |
| Skill | The Agent Skill that `build` compiles from the source. |
| JSON | The compiled catalogue. |

In the graph:

- Turn the mouse wheel to zoom, drag the background to move, and drag a node by its header. `F` (or **Fit**) shows the whole flow again. The first view shows the whole flow, so zoom in to read the nodes.
- Click a node to read it in the panel at the right. The panel also explains the lines, the lanes and the kinds of node.
- **run…** shows the path of a run of `runs/`. Make a run first (see Run): then choose `r1`. The nodes get the numbers of the path, and the panel shows the end, the problems, and the gates that the model guessed.
- **preset…** shows the values of a preset (`mac`, `dos`).
- The check boxes show or hide the rule wires, the fail paths and the flow lines.
- Change a value in a rule box, then click **Save**: the viewer writes the value into `font-names.rig` and compiles `gen/font-names.json` again. Then run `build` (see Change), so that the skill and the other compiled files follow.

`python3 tool.py serve-http` also serves the graph, read only, at http://127.0.0.1:8780/viewer?serve=1.

## Change

Change a value or the flow in `font-names.rig`, and the code in `engine.py`, `gates.py` and `steps.py`. Then:

```bash
python3 ../../skills/rig/rig.py build .
```

```bash
python3 ../../skills/rig/rig.py doctor .
```
