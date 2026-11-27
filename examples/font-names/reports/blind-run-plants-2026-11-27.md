# A blind model run of `abbreviate`, 2026-11-27

The first run in which a model answered the reason block `abbreviate` with no knowledge of the source. The model was a fresh Claude subagent. It got only what a driving agent gets: the compiled `skill/SKILL.md` and the `waiting` JSON of the run. It was told not to read any source file, and to stop at the human gate.

Limit of this run: the model is Claude (a strong model), through the command line. The weaker local model that the tool is designed for has not run it yet.

## The input

Four empty placeholder files that `examples/family-namer` made from the list `plants` (see its report `chain-plants-2026-11-27.md`):

`MetasequoiaGlyptostroboides-Regular.otf`, `-Italic.otf`, `-Bold.otf`, `-BoldItalic.otf`

```bash
python3 tool.py run '{"folder": "<the folder>"}' --preset mac
```

The run waited at `abbreviate`. The weak words were `Metasequoia` and `Glyptostroboides`. Without the model, the names would be `MtsqGlptstrbds-Bd` and the like (vowels dropped by code).

## What the model did

From the model's own account. The runner keeps no record of arena calls (see Findings), so the calls below are not in the run files:

1. `tool.py status r1`, `tool.py rules`, `tool.py flow`, and it read `gen/font-names.json`, as the skill says.
2. `tool.py arena r1 steps.table`: the built-in table and the letter limits `[2, 4]`.
3. `tool.py arena r1 steps.try_names '{"Metasequoia": "Meta", "Glyptostroboides": "Glyp"}'`: `"the answer is not a table of abbreviations"`. The argument must be `{"table": {...}}`; nothing told the model this. One try was lost.
4. `try_names` with `{"table": {"Metasequoia": "Meta", "Glyptostroboides": "Glyp"}}`: fair, names `MetaGlyp-Bd`, `-BdIt`, `-It`, `-Rg`.
5. `try_names` with `{"table": {"Metasequoia": "Mtsq", "Glyptostroboides": "Glpt"}}`: fair, names `MtsqGlpt-…`.

It used 4 of 6 tries.

## What the run recorded

From `runs/r1` (checked after the run):

| Node | Answer |
|---|---|
| `abbreviate` | `[{"Metasequoia": "Meta", "Glyptostroboides": "Glyp"}, {"Metasequoia": "Mtsq", "Glyptostroboides": "Glpt"}]` |
| `abbr-ok` | passed (code) |
| `fits`, `unique` | passed (code) |
| `readable` | pass, "MetaGlyp keeps the start of both family words with their vowels, and Bd, BdIt, It, Rg are the standard table style abbreviations, so a type designer can recognise the family and the style in each name." (guessed) |

Path: `read files-ok plan abbreviate abbr-ok final fits unique readable something`, then it waits at `approve`. `problems`: none. `guessed`: `readable`. Both candidates were fair and gave names of the same length, so code took the first one.

| Old name | New name |
|---|---|
| MetasequoiaGlyptostroboides-Bold.otf | MetaGlyp-Bd.otf |
| MetasequoiaGlyptostroboides-BoldItalic.otf | MetaGlyp-BdIt.otf |
| MetasequoiaGlyptostroboides-Italic.otf | MetaGlyp-It.otf |
| MetasequoiaGlyptostroboides-Regular.otf | MetaGlyp-Rg.otf |

The files were not renamed: `permissions.rename` is off, and the person has not answered `approve`.

## Findings

1. **Fixed (see the second run).** **The arguments of the arena tools are not told to the model.** The payload has `"tools": ["steps.try_names", "steps.table"]` and the skill has `tool.py arena <run> <tool>`, but neither says what JSON a tool takes. The model found `{"table": ...}` by a failed try.
2. **Fixed.** **A wrong argument gives an unclear message.** `try_names` answered "the answer is not a table of abbreviations", not "expected {"table": {...}}".
3. **Fixed.** **The runner keeps no record of arena calls.** `arena_used` goes back to 0 after the answer, and `answers.json` has only the answers. A run cannot show which tools the model called, or what they returned.
4. **`tool.py rules` shows the rule defaults, not the values of a run.** The run used the preset `mac` (HFS), but `rules` said `target.standard: sp_server`, and the model took that as the standard of the run.
5. **The style text is not clear.** It says "no dropped vowels", but the example "Grotesque: Grt" drops vowels. The model read it as "no vowels dropped by code", which is the meaning.
6. **The order of candidates can matter.** When two fair tables tie, code takes the first. Nothing tells the model this.
7. `tool.py --help` and `tool.py arena --help` do not print help.

The reasoning itself worked: the model tested before it answered, both tables were fair at the first real try, and `MetaGlyp` reads far better than the `MtsqGlptstrbds` of code.

## The second run, after the fixes

The fixes, the same day:

- The runner shows the docstring of each arena tool to the model as `waiting.tool_help`, and the worker puts it in the job text. The skill says to read it. The two tools of font-names now say what they take: `try_names` takes `{"table": {"Word": "Abbr", ...}}`, `table` takes `{}`.
- `try_names` answers a call without `"table"` with: give the table inside "table": {"table": {"Metasequoia": "Meta", ...}}; got <what it got>.
- The run keeps every arena call in `arena_log` (node, tool, arguments, result), and `status` shows it as `arena`.

A new blind subagent drove a new run on the same four files. It read `skill/SKILL.md` and `tool.py status r1` itself, and no other file. From the run files (`status r1`, `answers.json`):

| # | Arena call | Result |
|---|---|---|
| 1 | `steps.table` `{}` | the built-in table, letters `[2, 4]` |
| 2 | `steps.try_names` `{"table": {"Metasequoia": "Meta", "Glyptostroboides": "Glyp"}}` | fair, `MetaGlyp-Bd` … |
| 3 | `steps.try_names` `{"table": {"Metasequoia": "Mtsq", "Glyptostroboides": "Gly"}}` | fair, `MtsqGly-Bd` … |

No call was lost: 3 of 6 tries, no wrong argument. The answer was the two tables; code took `Meta`/`Glyp`. `readable`: pass (guessed). The run waits at `approve`; the names are the same as in the first run.

New points from the second model, still open:

- It could not see the length limit of the standard, or how near each name is to it. It relied on `fair`.
- Nothing says how code picks the best of two fair tables (fewest shortening steps, then the most letters, then the first).
- `fair` speaks for `abbr-ok` only, not for `fits` and `unique`.
