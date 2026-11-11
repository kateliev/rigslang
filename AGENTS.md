# Instructions for AI agents

These rules apply to every AI agent that reads or changes this repository.

1. **No project names.** The owner's other repositories are a source: you may reuse their code and tools here. Do not write the names of those projects, or their domain data, into this repository. Keep examples neutral.
2. **The verifier decides.** Never write a `cast` block, a hash or a `proved` stamp that did not come from a real run (`python skills/rig/rig.py hash` and `prove`, or a real test run in the target language). Never imagine what code returns.
3. **Never falsify an intent.** When you describe existing code, the intent states what the code does, and real runs prove it. Anyone, human or model, may write or change an intent. A gate decides.
4. **One source.** The language is defined in `skills/rig/spec.md`. When the language changes, update the spec, `rig.py`, the viewer, the editor grammars (`editors/build.py`), the skill and the examples in the same commit.
5. **Plain language.** Write documentation in short, clear sentences (ASD-STE100 style): one word, one meaning.
