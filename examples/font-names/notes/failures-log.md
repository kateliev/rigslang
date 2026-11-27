# Failures log: font-names

What failed and why: a method that did not work, an experiment, a kind of item that the tool cannot do. Code bugs go to `bugs-and-fixes.md`.

Read it before a batch. Do not repeat a failure that is here. Newest entry at the bottom.

| Date | What was tried | What happened | Why | What to do |
|---|---|---|---|---|
| 2026-11-27 | A case folder `reserved/` with the file `Aux.otf` | On Windows the file is not a normal file: `read` did not see it, and the folder cannot be checked out | `AUX` is a reserved device name on Windows, also with a suffix | Test reserved names in `tests/test_gates.py` and `tests/test_engine.py`, never with a real file |
| 2026-11-27 | Standard `dos83` with abbreviations of the model | 8 letters do not hold a family and a style; every table still needs a cut | The limit is too small for readable names | `abbr-ok` holds the run back (checked: with `shorten.method cut` too, the model is asked and the run is held). For 8.3, set `shorten.ask_model off`: the run takes the cut names of code, and the person agrees to them. A `.woff2` or `.woff` file never fits 8.3 (suffix of 3 letters at most): `fits` holds the run back |
