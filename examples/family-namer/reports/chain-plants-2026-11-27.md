# The chain on the list plants, 2026-11-27

family-namer ran to `done` on a plants story, and font-names ran on the new folder with `--preset mac`. font-names stopped at its reason block `abbreviate`, as the list `plants` is made to do.

**The answers of the model and of the person in family-namer were played by hand, not given by a model or a person.** They are below. The answers of font-names (`abbreviate`, then `readable`) were not given: a real model answers them in the next step, and a played answer would prove nothing.

Run ids are the ids of a new `runs/` folder in each tool.

## 1. family-namer (played answers)

```bash
cd examples/family-namer
python3 tool.py run '{"story": "A calm book face named after a tree"}' --set names.seed=7
```

The run waited at `topic`. The model saw three lists: `plants` (29 names), `trojan-heroes` (65), `winds` (13).

```bash
python3 tool.py answer r1 '{"result": {"list": "plants", "why": "the story asks for a tree, and plants is the list of trees"}}'
```

`topic-ok` and `has-list` passed. With seed 7, `sample` drew: Handroanthus impetiginosus, Sequoiadendron giganteum, Casuarina cunninghamiana, Eucalyptus camaldulensis, Chamaecyparis lawsoniana, Chamaecyparis nootkatensis, Lithocarpus cleistocarpus, Metasequoia glyptostroboides. The run waited at `pick`.

```bash
python3 tool.py answer r1 '{"result": [{"name": "Metasequoia glyptostroboides", "why": "the dawn redwood, a calm and very old tree; the long name gives a quiet, even texture of letters"}, {"name": "Sequoiadendron giganteum", "why": "the giant sequoia stands still for thousands of years; a long name with round letters"}, {"name": "Chamaecyparis nootkatensis", "why": "a quiet cypress of the northern coast; the name has an even rhythm"}]}'
python3 tool.py answer r1 '{"pass": true, "why": "all three are trees, as the story asks"}'
python3 tool.py approve r1 1
```

`picks-ok` and `names-ok` passed (families `MetasequoiaGlyptostroboides`, `SequoiadendronGiganteum`, `ChamaecyparisNootkatensis`). `fits` passed (a guess). The person chose 1. The run ended at `done`:

- path: `lists topic topic-ok has-list sample pick picks-ok names names-ok fits choose free write written report done`
- result: family `MetasequoiaGlyptostroboides`, list `plants`, seed 7, folder `out/MetasequoiaGlyptostroboides`, files `MetasequoiaGlyptostroboides-Bold.otf`, `MetasequoiaGlyptostroboides-BoldItalic.otf`, `MetasequoiaGlyptostroboides-Italic.otf`, `MetasequoiaGlyptostroboides-Regular.otf`

## 2. font-names (`--preset mac`, no answers)

```bash
cd ../font-names
python3 tool.py run '{"folder": "../family-namer/out/MetasequoiaGlyptostroboides"}' --preset mac
```

The run went `read files-ok plan if:plan.weak_words` and waits at `abbreviate`. The weak words are `Metasequoia`, `Glyptostroboides`. With the built-in table and dropped vowels, the names would be `MtsqGlptstrbds-Bd`, `MtsqGlptstrbds-BdIt`, `MtsqGlptstrbds-It`, `MtsqGlptstrbds-Rg`. The exact output of the run:

```json
{"run": "r1", "at": "abbreviate", "waiting": {"node": "abbreviate", "kind": "reason", "name": "Propose abbreviations", "intent": {"text": "give every font file of a family a short file name that fits a delivery standard, stays readable and stays unique", "local": "propose short abbreviations for the family and style words that the table does not know", "audience": "type designers and font distributors", "style": "names a type designer can read: table abbreviations, no dropped vowels, no cut words", "never": [{"text": "rename a file without the approval of a person", "gate": "approve"}, {"text": "rename a file when permissions.rename is off", "gate": "allowed"}, {"text": "give two files the same name", "gate": "unique"}]}, "mode": "careful", "tools": ["steps.try_names", "steps.table"], "budget": 6, "budget_remaining": 6, "candidates": 2, "do": "propose a table of abbreviations, one for each weak word, as type designers write them (Grotesque: Grt): the first letter of the word, then letters of the word in their order, [2, 4] letters (shortest, longest). Test each table with try_names before you answer; table shows the built-in words", "sees": {"plan.weak_words": ["Metasequoia", "Glyptostroboides"], "plan.rows": [{"files": ["MetasequoiaGlyptostroboides-Bold.otf"], "short": "MtsqGlptstrbds-Bd", "steps": ["abbr_style", "abbr_family", "vow_style", "vow_family"]}, {"files": ["MetasequoiaGlyptostroboides-BoldItalic.otf"], "short": "MtsqGlptstrbds-BdIt", "steps": ["abbr_style", "abbr_family", "vow_style", "vow_family"]}, {"files": ["MetasequoiaGlyptostroboides-Italic.otf"], "short": "MtsqGlptstrbds-It", "steps": ["abbr_style", "abbr_family", "vow_style", "vow_family"]}, {"files": ["MetasequoiaGlyptostroboides-Regular.otf"], "short": "MtsqGlptstrbds-Rg", "steps": ["abbr_style", "abbr_family", "vow_style", "vow_family"]}]}, "out": "dict[str, str]", "schema": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "object", "additionalProperties": {"type": "string"}}}, "answer": "{\"result\": [<distinct candidates matching out>]}"}, "problems": [], "guessed": [], "path": ["read", "files-ok", "plan", "if:plan.weak_words"]}
```

The `waiting` part, formatted:

```json
{
 "node": "abbreviate",
 "kind": "reason",
 "name": "Propose abbreviations",
 "intent": {
  "text": "give every font file of a family a short file name that fits a delivery standard, stays readable and stays unique",
  "local": "propose short abbreviations for the family and style words that the table does not know",
  "audience": "type designers and font distributors",
  "style": "names a type designer can read: table abbreviations, no dropped vowels, no cut words",
  "never": [
   {
    "text": "rename a file without the approval of a person",
    "gate": "approve"
   },
   {
    "text": "rename a file when permissions.rename is off",
    "gate": "allowed"
   },
   {
    "text": "give two files the same name",
    "gate": "unique"
   }
  ]
 },
 "mode": "careful",
 "tools": [
  "steps.try_names",
  "steps.table"
 ],
 "budget": 6,
 "budget_remaining": 6,
 "candidates": 2,
 "do": "propose a table of abbreviations, one for each weak word, as type designers write them (Grotesque: Grt): the first letter of the word, then letters of the word in their order, [2, 4] letters (shortest, longest). Test each table with try_names before you answer; table shows the built-in words",
 "sees": {
  "plan.weak_words": [
   "Metasequoia",
   "Glyptostroboides"
  ],
  "plan.rows": [
   {
    "files": [
     "MetasequoiaGlyptostroboides-Bold.otf"
    ],
    "short": "MtsqGlptstrbds-Bd",
    "steps": [
     "abbr_style",
     "abbr_family",
     "vow_style",
     "vow_family"
    ]
   },
   {
    "files": [
     "MetasequoiaGlyptostroboides-BoldItalic.otf"
    ],
    "short": "MtsqGlptstrbds-BdIt",
    "steps": [
     "abbr_style",
     "abbr_family",
     "vow_style",
     "vow_family"
    ]
   },
   {
    "files": [
     "MetasequoiaGlyptostroboides-Italic.otf"
    ],
    "short": "MtsqGlptstrbds-It",
    "steps": [
     "abbr_style",
     "abbr_family",
     "vow_style",
     "vow_family"
    ]
   },
   {
    "files": [
     "MetasequoiaGlyptostroboides-Regular.otf"
    ],
    "short": "MtsqGlptstrbds-Rg",
    "steps": [
     "abbr_style",
     "abbr_family",
     "vow_style",
     "vow_family"
    ]
   }
  ]
 },
 "out": "dict[str, str]",
 "schema": {
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "items": {
   "type": "object",
   "additionalProperties": {
    "type": "string"
   }
  }
 },
 "answer": "{\"result\": [<distinct candidates matching out>]}"
}
```

## 3. After the runs

The run of font-names and the folders `out/` and `runs/` of family-namer were removed, so that the repository is as it was.

## Not done

- The answers of `abbreviate` and `readable`: they are for a real model (`python3 tool.py work r1 --api-url URL --model NAME` in font-names, after the same run).
