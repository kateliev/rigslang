# Project facts: bookmarks

What is true about this project. An agent reads this file before it works, on any computer. The memory of an agent is not the same on every computer; this file is.

## What the tool does

It cleans up a bookmarks HTML file that Edge exported, and writes a new HTML file to import. See `README.md`.

## The pipeline

1. The owner exports the bookmarks from Edge as HTML.
2. The tool reads the export, and writes its work into `work/` and the new file into `out/`.
3. The owner imports the new file into Edge. Edge puts it in a new folder.
4. The owner checks it, then deletes the old folders inside Edge. Edge sync carries these normal changes to the other devices.

The tool never touches the files of the browser. Sync is the reason: a changed live file could be overwritten by sync, or could spread a damage to every device.

## Decisions of the owner

- 2026-11-23: The existing folder tree is the base. It is never renamed or deleted. A few new folders are allowed where a category is missing (`sort.new_max`).
- 2026-11-23: Exact duplicates: keep the copy in the deeper folder, else the oldest.
- 2026-11-23: Similar URLs on one site: the person chooses, a page at a time. The default is the shortest URL. Big sites with many separate pages are never grouped, and the list is a rule that the owner can change.
- 2026-11-23: Code makes the decisions and does the checks. The model only sorts.
- 2026-11-23: Dead links: later. They will go to a "Dead links" folder, never be deleted.
- 2026-11-23: The tool lives in `examples/bookmarks` of the Rig repository. The real bookmarks file never goes into version control.

## Decisions of the builder, for the owner to confirm

- The favorites bar is left alone (`keep.bar`): its bookmarks are never removed, grouped or moved, and it is not a folder for the sort. A duplicate on the bar stays, together with the best other copy. Reason: a bookmark on the bar is a shortcut that the owner put there on purpose.
- `approve no` on a page of similar URLs means "keep every URL here and on every later page", not only this page.
- The first values of `similar.max_group`, `similar.page_size`, `sort.host_elsewhere` and `safety.max_removed` come from the synthetic test file only. Check them on the first real run, with the dry-run report.

## Words

| Word | Meaning |
|---|---|
| export | The HTML file that Edge wrote. The tool only reads it. |
| new file | The HTML file that the tool writes into `out/`, to import. |
| group | Bookmarks on one site where one path starts with another. |
| variant | A URL that names the same page as a shorter one: `/index.html`, `/default.aspx`. Code folds it with no question. |
| page | Up to `similar.page_size` groups that the person answers together. |
| loose | A bookmark in the top level or directly in a top folder, such as Other favorites (not the favorites bar). |
| misfiled | A bookmark alone with its site in its folder, while another folder has at least `sort.host_elsewhere` bookmarks of that site. |
| batch | Up to `sort.batch` loose or misfiled bookmarks that the model sorts in one answer. |
| work folder | `work/<file>-<time>/`: everything that one run found and decided, one file for each page and each batch. |

## Facts about the host application

- Edge exports the Netscape bookmark format: `<DT><H3>` for a folder, `<DT><A HREF=...>` for a bookmark, `<DL><p>` lists. The favorites bar has `PERSONAL_TOOLBAR_FOLDER="true"`.
- The live file of Edge is JSON (`Bookmarks` in the profile folder). The gate `file-ok` refuses a JSON file.
- An attribute such as `ICON` can hold a large data URL. The tool keeps every attribute as it was.
- Not checked yet: an export of the real Edge on the owner's computer. The test file follows the Netscape format of Chromium browsers.

## What is verified

See `docs/status.md` of the repository for the whole picture. For this tool, on 2026-11-23:

- The tests (`tests/`) and the 7 regression cases pass. Every end and every gate is on the path of a case.
- A local Qwen 35B model (`qwen3.6-35b-a3b`, LM Studio) used the plugin code through `plugin/agent.ts`: the same tools, rules text, bridge and `approve` step as in the chat window. The operator messages were played by the builder, on synthetic files only.

| Run | Tool calls | Time | What happened |
|---|---|---|---|
| test file, 12 to sort, 2 similar groups | start, 1 sort batch | 60 s | Showed the page of groups and the answers; `approve yes 1=all` passed on; 12 sorted, none refused; report, `approve yes`, file written. |
| 381 bookmarks, 313 to sort (`tests/make_big.py`) | start, 7 sort answers for 6 batches | 5 min | Batch 1 failed `sort-ok` once (new folders without `"new": true`); the model fixed it from `waiting.problems`. 300 of 300 moves went to the right topic. It proposed 2 new folders; both approved; file written. |
| 231 bookmarks, a new chat after batch 1 of 3 | queues, run_status, 2 sort batches | 86 s | "Go on with my bookmarks run" was enough: it found the run and went on from batch 2. |

- Not verified: the plugin inside the LM Studio chat window (`lms dev`): the settings field, the rules text before the first message, and the `approve` message in the real chat. `agent.ts` runs the same code, outside the window.
- Not verified: a real export of the owner, and a file of thousands of bookmarks with a model.
- Seen: the model sometimes tells the operator to answer `yes`, not `approve yes`. A plain `yes` goes to the model, which cannot answer for the person.

## Sorting with a local model (2026-11-25)

Measured on a real Edge export, the same 8 batches of 30, with the local Qwen 35B (`qwen3.6-35b-a3b`):

- Chat, thinking on: about 13 minutes for all batches.
- Worker, thinking off (`rig.json` `"plugin": {"work": {"think": false}}`): 137 seconds; every batch passed `sort-ok` at the first answer; 92 of 120 decisions as in the chat run.
- Worker, thinking on: 2.5 to 3 minutes for each batch; 41 of 60 decisions as in the chat run. Stopped after 2 batches.

Two runs with thinking agree less with each other than the fast run agrees with the chat run: many misfiled bookmarks are close calls. So the tool uses thinking off. Code finds the candidates (`bm.candidates`): on 400 filed bookmarks with their folder hidden, the right folder was among the first 4 candidates for 60%.

