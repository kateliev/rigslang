# Instructions for AI agents

These rules apply to every AI agent that reads or changes this repository.

1. **No project names.** The owner's other repositories are a source: you may reuse their code and tools here. Do not write the names of those projects, or their domain data, into this repository. Keep examples neutral.
2. **The verifier decides.** Never write a test result, a level, an expected value of a regression case or a recorded answer that did not come from a real run (`python3 -m unittest`, `rig.py test`, `rig.py doctor`, the runner, or a real test run in the target language). Never imagine what code returns.
3. **Never falsify an intent.** When you describe existing code, the intent states what the code does, and real runs prove it. Anyone, human or model, may write or change an intent. A gate decides.
4. **One source.** The language is defined in `skills/rig/spec.md`. When the language changes, update the spec, `rig.py`, the viewer, the editor grammars (`editors/build.py`), the skill and the examples in the same commit.
5. **The kit stays in step.** The method is in `skills/rig/guide/`. When the runtime (`skills/rig/kit/rigkit.py`), the project commands (`skills/rig/rig_project.py`) or a template changes: run `python3 skills/rig/rig.py build examples/font-names` (each tool keeps a copy of the runtime), update the guide page that describes the change, and keep `docs/status.md` true (what exists, what is not verified, what is open). The example `examples/font-names` is the pattern: when a text and the example disagree, fix the text. Read `examples/README.md` before you change an example.
6. **All tests pass before a commit:** `python3 -m unittest discover -s tests`. A new project of every level must pass its own doctor.
7. **Plain language.** Write documentation in short, clear sentences (ASD-STE100 style): one word, one meaning.
