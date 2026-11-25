# Older examples

These files are from before the kit (2026-11-11 and 2026-11-12), in language version 0. They show the snippet scale of Rig, where the code of a unit is inside the `.rig` file as a cast. Language version 1 (2026-11-25) removed the snippet scale, so `rig.py` refuses these files now, and no test uses them. They are kept as a record. Do not copy them for a new tool: copy [release-tool](../../../examples/release-tool/).

| File | What it shows |
|---|---|
| [slugify.rig](slugify.rig) | A snippet: a matrix and a proved cast. |
| [contacts.rig](contacts.rig) | A tool unit with steps and gates, and units that it `uses`. |
| [release-check.rig](release-check.rig) | An agent as one file, with no code. [release-tool](../../../examples/release-tool/) is the same idea as a real tool. |
| [translate-ui.rig](translate-ui.rig) | A larger agent unit with presets. |
| [bandsearch/](bandsearch/) | An LM Studio plugin with TypeScript casts. [band-facts](../../../examples/band-facts/) is the same tool built with the kit. |
