# Instructions for AI agents

These rules apply to every AI agent that reads or changes this repository.

1. **Generic only.** This repository holds the generic idea of Rig. Do not copy code, prompts, rule sets, data or texts from private or proprietary projects into it, even as examples. Write new, neutral examples.
2. **The verifier decides.** Never write a `cast` block, a hash or a `proved` stamp that did not come from a real run (`python skills/rig/rig.py hash` and `prove`, or a real test run in the target language). Never imagine what code returns.
3. **The human owns the intent.** If you write the intent of code that already exists, it is a draft. Show it to the human and ask them to confirm it.
4. **One source.** The language is defined in `skills/rig/spec.md`. When the language changes, update the spec, `rig.py`, the viewer, the editor grammars (`editors/build.py`), the skill and the examples in the same commit.
5. **Plain language.** Write documentation in short, clear sentences (ASD-STE100 style): one word, one meaning.
