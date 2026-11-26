# Improvement plan (resumable by stage)

This plan tracks the fixes and upgrades from the 2026-11-26 repository review. Each stage is self-contained, leaves all tests and doctors passing, and updates this file when done.

## How to resume in a new session

1. Read this file and find the first unchecked stage (`[ ]`).
2. Check `git status` and run `python3 -m unittest discover -s tests` to confirm the baseline.
3. Execute only that stage (or delegate it to a side agent with the stage block below).
4. Run the stage's verification commands, check off its box (`[x]`), and record a short completion note under **Log**.
5. Continue to the next unchecked stage, or stop cleanly.

## Stage checklist

- [x] **Stage 1 — Correctness, dead code, and cleanup**
- [x] **Stage 2 — Verification and static analysis hardening**
- [x] **Stage 3 — Runtime performance and run lifecycle**
- [x] **Stage 4 — Language ergonomics and lean compiled skills**
- [x] **Stage 5 — Self-directing fronts, warm stdio bridge, and model-agnostic worker**
- [x] **Stage 6 — Stdio MCP server front**
- [x] **Stage 7 — Documentation consolidation, builder cheatsheet, and full verification**

---

## Stage 1 — Correctness, dead code, and cleanup

**Goal:** Fix real validation bugs, remove dead code and stale version-0 metadata, and eliminate test warnings.

**Scope:**
1. Fix `schema_problems()` in [skills/rig/kit/rigkit.py](../skills/rig/kit/rigkit.py):
   - Add `'null': lambda x: x is None` to the type map so `(maybe T)` actually rejects invalid non-null values.
   - Validate `(tuple ...)` schemas (`prefixItems`, `minItems`, `maxItems`).
2. Add runtime input type validation in `Kit.run()` and `Kit.call()`:
   - Emit `schema` on each `in` port in `rig.py` (`port_info` / `catalog`).
   - Validate inputs against those schemas in `Kit.run()` and `Kit.call()` via `schema_problems()`, raising `Refused` on mismatch.
3. Make atomic JSON writes safe for concurrent calls in `rigkit.py:write_json()` using a PID-scoped temp file (`path + f'.{os.getpid()}.tmp'`).
4. Pass `path` into `check(root, path)` inside `rig.py:outputs()` and `rig.py:main()` (`compile` command) so compile catches missing files and functions.
5. Remove dead code and stale leftovers:
   - Remove the unreachable duplicate `if cmd == 'test':` in [skills/rig/rig_project.py](../skills/rig/rig_project.py) and include `plugin` in its error text.
   - Remove unused `bound_levels()`, `GET /levels`, and `GET /file` in [skills/rig/rig.py](../skills/rig/rig.py), and update `test_serve_gives_the_bundle_and_the_runs` in [tests/test_kit.py](../tests/test_kit.py).
   - Remove unused `node` field in [skills/rig/kit/templates/plugin/src/bridge.ts](../skills/rig/kit/templates/plugin/src/bridge.ts).
   - Remove unused `?` token from [editors/build.py](../editors/build.py), rebuild grammars (`python3 editors/build.py`), and update [editors/README.md](../editors/README.md) if it mentions `?`.
   - Update `"rig": 0` to `"rig": 1` in `examples/release-tool/rig.json`, `examples/band-facts/rig.json`, and `examples/bookmarks/rig.json`; warn/fail in `rig_project.manifest()` if `"rig"` is below `1`.
   - Fix unclosed file handles (`ResourceWarning`) in [tests/test_rig.py](../tests/test_rig.py).
6. Rebuild all three examples (`rig.py build`) and add unit tests for `(maybe T)`, `(tuple ...)`, and runtime input type validation.

**Verify:** `python3 -m unittest discover -s tests`, `python3 editors/build.py --check`, `rig.py build --check` and `rig.py doctor` on all three examples.

---

## Stage 2 — Verification and static analysis hardening

**Goal:** Make static checks (`rig.py check`, `rig.py doctor`) match what the spec and rules promise.

**Scope:**
1. Cache file reads per `Ctx` in [skills/rig/rig.py](../skills/rig/rig.py) (`bound_level()`).
2. Upgrade Python verification in `rig.py`:
   - Use `ast` for `.py` files in `bound_level()`: confirm the function is actually defined (`FunctionDef`/`AsyncFunctionDef`) and actually referenced as code (not only in comments or docstrings) in the `test` file. Keep regex fallback for non-Python files.
   - Infer rule reads automatically by AST-scanning `R('group.name')` calls in bound Python files (merging with `{group.name}` placeholders and any explicit `reads` lines).
   - Add a low-noise AST warning in `rig.py check` for hardcoded numeric literals in `gates.py` (ignoring `-1`, `0`, `1`, default values, and subscript indices; excluding `test_` files).
3. Execute `example` lines of `tool` units against their bound Python function in `rig_project.doctor()` (level 1), so `example` lines are proved rather than decorative.
4. Strengthen the level-4 `permissions` check in [skills/rig/rig_project.py](../skills/rig/rig_project.py): verify a `permissions.*` rule exists, defaults to `off` (`False`), and is read by at least one `hard` gate.
5. Add `--json` output mode to `rig.py doctor` for structured agent consumption.
6. Rebuild all examples and add unit tests covering AST gate-test verification, inferred rule reads, `example` execution, `permissions` check, and `doctor --json`.

**Verify:** `python3 -m unittest discover -s tests`, `rig.py doctor` on all three examples, `rig.py new` at levels 1–4 passing doctor.

---

## Stage 3 — Runtime performance and run lifecycle

**Goal:** Faster run operations, short copy-safe run IDs, clean run lifecycle commands, and warm stdio execution.

**Scope:**
1. **Short run IDs:** Change `Kit.new_id()` in [skills/rig/kit/rigkit.py](../skills/rig/kit/rigkit.py) to short sequential IDs (`r1`, `r2`, …) with atomic `os.mkdir` reservation; keep ISO `started` inside `run.json`. Keep backward compatibility in [bridge.ts](../skills/rig/kit/templates/plugin/src/bridge.ts) (`approval()` matches both `r\d+` and legacy `\d{8}-\d{6}-\d+`).
2. **Run lifecycle commands:** Add `drop RUN [REASON]` (marks a waiting run ended with outcome `dropped` so abandoned runs leave `queues`), `list` (lists runs), and `prune [--keep N]` (removes old finished run folders) to `Kit` and `Kit.cli`. Update all `tool.py` docstrings and templates so `tests/test_docs.py` stays green.
3. **O(waiting) queues & O(1) marks & memory caching:**
   - Maintain a lightweight `waiting.json` index in `runs/` (with automatic fallback/reconciliation if missing) so `queues` only reads waiting runs instead of all historical runs.
   - Store checkpoints as `runs/<id>/marks/<node>.json` instead of rewriting monolithic `marks.json` on every step (with read fallback for legacy `marks.json`).
   - Cache pinned catalogue comparison in memory instead of re-reading `flow.json` on every `report()`.
4. **Parallel batch:** Add `--workers N` (default `1`) to `Kit.batch()` and `Kit.cli` using `ThreadPoolExecutor`, preserving `errors_stop`.
5. **Warm stdio server:** Add `serve-stdio` to `Kit.cli` (JSON-lines request/response loop keeping the Python process and loaded modules warm).
6. **Metadata on answers:** Accept optional `--meta '<JSON>'` on `tool.py answer` (recording `model`, `seconds`, `tokens` in `answers.json` when provided).
7. Rebuild all examples and add tests for short IDs, `drop`, `list`, `prune`, waiting index, per-node marks, parallel batch, `serve-stdio`, and `--meta`.

**Verify:** `python3 -m unittest discover -s tests`, `rig.py build --check` and `rig.py doctor` on all three examples.

---

## Stage 4 — Language ergonomics and lean compiled skills

**Goal:** Eliminate confusing flow idioms, remove unused language clutter, and make compiled `SKILL.md` lean for agents.

**Scope:**
1. **Explicit `failed` flag on gate state:** Set `run['state'][nid] = {'pass': v['pass'], 'failed': not v['pass'], 'why': ...}` in `rigkit.py` so `examples/release-tool/release.rig` uses `if tone.failed` instead of relying on `{'pass': False}` being truthy.
2. **Pure gates in bookmarks:** Move `by steps.keep` out of `gate sort-ok` into `step keep by steps.keep` right after `gate sort-ok` in [examples/bookmarks/bookmarks.rig](../examples/bookmarks/bookmarks.rig), update regression baselines and node count test (`<= 23`).
3. **Require `out` on `by model` steps & remove `finish_step`:**
   - Make `rig.py check` warn (and `doctor` level 2 flag) if a `by model` step has no `out <type>`.
   - Remove `finish_step` from `rig_project.front()` and `bridge.ts`; all `by model` steps use `work_run` in the plugin front.
4. **Remove redundant language pieces:**
   - Remove unit-level `check` (keeping gate-level `check` only, so `check` has one meaning).
   - Remove `from-json` (`from_catalog`) from `rig.py` and its CLI/docs.
   - Drop redundant manual `reads` lines in `examples/bookmarks/bookmarks.rig` where AST inference already detects them (keep `reads` accepted as optional in `.rig` for non-Python code).
5. **Lean compiled `SKILL.md` with `--driver`:** When `--driver` is passed to `rig.skill()`, emit a compact skill (~40 lines: driver loop, compact table of model/human nodes and 1-line summary of code stages, `Guessed:` rule) instead of dumping every code-only node in full. Keep the full walkthrough when `--driver` is omitted.
6. Update `spec.md`, `tests/test_rig.py`, `tests/test_kit.py`, `tests/test_docs.py`, and rebuild all examples.

**Verify:** `python3 -m unittest discover -s tests`, `rig.py build --check` and `rig.py doctor` on all three examples.

---

## Stage 5 — Self-directing fronts, warm stdio bridge, and model-agnostic worker

**Goal:** Make fronts faster, clearer to small models, and symmetric between Claude/CLI and local models.

**Scope:**
1. **Self-directing `waiting` JSON in `bridge.ts`:** Add a front-specific `next_action` object on waiting responses (and remove CLI-only `waiting.answer` from plugin responses so small models do not see conflicting instructions).
2. **Warm stdio driver in `bridge.ts`:** Spawn one persistent `tool.py serve-stdio` child process per plugin session with request queuing, timeout handling, and auto-restart/fallback to one-shot spawn.
3. **Chat-scoped active run in `index.ts` / `bridge.ts`:** Track the last run ID returned in the plugin session so `approve yes` resolves cleanly when multiple historical runs exist.
4. **Better `worker.ts` retry feedback & metrics:** Pass actual failure cause (`max_tokens` cut or JSON parse error) via `answer` / retry context instead of silent `{ result: null }`, and pass `--meta` (`seconds`, `tokens`, `model`) to the driver.
5. **Model-agnostic Python worker in `rigkit.py` (`tool.py work RUN`):** Implement a stdlib-only (`urllib.request`) OpenAI-compatible worker command (`--api-url`, `--model`, `--think`, `--max-tokens`, `--max-calls`) so CLI and Claude fronts can also run `by model` + `out` steps in isolated fresh contexts.
6. Rebuild all examples, run `tsc --noEmit` where `node_modules` exists, and add unit tests (mocked HTTP server / unit tests for Python worker + `try.ts` bridge test).

**Verify:** `python3 -m unittest discover -s tests`, `tsc --noEmit` in `examples/bookmarks/plugin` and `examples/band-facts/plugin`, `rig.py build --check` and `rig.py doctor` on all examples.

---

## Stage 6 — Stdio MCP server front

**Goal:** Let any MCP host (Claude Desktop, Claude Code, Cursor, LM Studio, Windsurf) run any Rig tool natively with zero extra dependencies.

**Scope:**
1. Add `mcp` command to `Kit.cli` in [skills/rig/kit/rigkit.py](../skills/rig/kit/rigkit.py):
   - JSON-RPC 2.0 over stdio (`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`).
   - Expose the compiled tool set (`start_run`, `answer_gate` when model gates exist, `work_run` when `--api-url` is configured and model steps exist, `run_status`, `start_batch`, `queues`, `drop_run`, and level-1 `call` tools). Never expose a tool for `human` gates.
   - Annotate `waiting` responses with `next_action` tailored to MCP tool names.
2. Add `rig.py mcp-config DIR` in [skills/rig/rig_project.py](../skills/rig/rig_project.py) to print a ready-to-use MCP server JSON config block for the tool.
3. Update all `tool.py` docstrings/templates, rebuild all examples, and add end-to-end stdio MCP tests in [tests/test_kit.py](../tests/test_kit.py).

**Verify:** `python3 -m unittest discover -s tests`, `rig.py build --check` and `rig.py doctor` on all three examples.

---

## Stage 7 — Documentation consolidation, builder cheatsheet, and full verification

**Goal:** One clear fact in one place, fast onboarding for builder agents, and full end-to-end verification.

**Scope:**
1. Add a 1-page builder quick reference at `skills/rig/cheatsheet.md` (canonical `.rig` grammar, `steps.py`/`gates.py` signatures, return dicts, `rig.json` keys, CLI commands) and link it from [skills/rig/SKILL.md](../skills/rig/SKILL.md).
2. Trim duplicated explanations across `skills/rig/guide/` (keeping all guide links resolving and concise ASD-STE100 style).
3. Update [skills/rig/spec.md](../skills/rig/spec.md), [README.md](../README.md), [docs/logic.md](../docs/logic.md), [docs/status.md](../docs/status.md), [skills/rig/SKILL.md](../skills/rig/SKILL.md), and example READMEs to reflect all changes accurately.
4. Run full verification:
   - `python3 -m unittest discover -s tests`
   - `python3 editors/build.py --check`
   - `rig.py build --check`, `rig.py doctor`, and `rig.py test` on `examples/release-tool`, `examples/band-facts`, and `examples/bookmarks`
   - `rig.py new` at levels 1, 2, 3, 4 in a temp directory + `rig.py doctor` on each
   - `tsc --noEmit` in `examples/bookmarks/plugin` and `examples/band-facts/plugin`
5. Record verified results in [docs/status.md](../docs/status.md) and mark Stage 7 done below.

---

## Log

- **2026-11-26:** Plan created. Starting Stage 1.
- **2026-11-26 (Stage 1 done):** Fixed `schema_problems` (`null`/`(maybe T)` + `tuple`), added runtime input type validation in `Kit.run`/`call`, PID-scoped temp files in `write_json`, passed `path` to `check()` in compile/outputs/serve, removed dead code (`bound_levels`, `/levels`, `/file`, duplicate `cmd == 'test'`, `bridge.ts` `node`, `?` grammar token), updated example `rig.json` to `"rig": 1`, fixed `ResourceWarning`s. 103/104 tests pass (only sandbox localhost serve test skipped/blocked), all 3 examples pass `build --check` and `doctor`, `tsc --noEmit` passes. Starting Stage 2.
- **2026-11-26 (Stage 2 done):** Added `Ctx` file/AST cache, AST-based `bound_level` (comments/docstrings no longer count as tested), AST rule-read inference (`R('...')`/`R.get('...')`), low-noise gate hardcoded-number warnings, tool `example` execution in `doctor`, strengthened level-4 `permissions` check (`off` default + read by `hard` gate), and `rig.py doctor --json`. 109/110 tests pass (only sandbox localhost serve test blocked), 0 warnings, all 3 examples pass `build --check` and `doctor`. Starting Stage 3.
- **2026-11-26 (Stage 3 done):** Switched to short sequential run IDs (`r1`, `r2`, …) with legacy ID compatibility in `bridge.ts`; added `drop`, `list`, `prune`, `serve-stdio`, `--workers N` parallel batch, and `--meta` on `answer`; added `.waiting.json` O(waiting) queue index, per-node `marks/<node>.json` checkpoints (with legacy fallback), and cached pinned-flow comparison in `report()`. 118/119 tests pass (only sandbox localhost serve test blocked), 0 warnings, all 3 examples pass `build --check` and `doctor`, `tsc --noEmit` passes. Starting Stage 4.
- **2026-11-26 (Stage 4 done):** Added explicit `failed` boolean on gate state (`release.rig` now uses `if tone.failed`); moved `steps.keep` out of `gate sort-ok` into pure `step keep` in `bookmarks.rig` and dropped AST-inferred manual `reads`; required `out` on `by model` steps and removed `finish_step`; removed unit-level `check` and `from-json`; compiled lean driver `SKILL.md` (~56–65 lines). 119/120 tests pass (only sandbox localhost serve test blocked), 0 warnings, all 3 examples and `tsc --noEmit` pass. Starting Stage 5.
- **2026-11-26 (Stage 5 done):** Added self-directing `waiting.next_action` (and stripped CLI `waiting.answer`) in `bridge.ts`; switched `bridge.ts` to persistent warm `serve-stdio` driver with auto-restart/fallback and clean `closeDriver()` shutdown; added chat-scoped `activeRunByRoot` disambiguation for `approve`; propagated `worker.ts` error reasons and `--meta` metrics (`model`, `seconds`, `tokens`) into `answers.json` and `waiting.problems`; added stdlib OpenAI-compatible Python worker `tool.py work`. 121/122 tests pass (only sandbox localhost serve test blocked), 0 warnings, all 3 examples and `tsc --noEmit` pass. Starting Stage 6.
- **2026-11-26 (Stage 6 done):** Added zero-dependency JSON-RPC 2.0 stdio MCP server (`tool.py mcp`) with MCP `next_action` decoration, `work_run` vs `answer_step` switching, and no human-gate tool; added `rig.py mcp-config DIR` command; updated all `tool.py` docstrings and rebuilt all 3 examples. 124/125 tests pass (only sandbox localhost serve test blocked), 0 warnings, all 3 examples and `tsc --noEmit` pass. Starting Stage 7.
- **2026-11-26 (Stage 7 done — all stages complete):** Added 1-page builder reference (`skills/rig/cheatsheet.md`), consolidated duplicated guide tables, updated `spec.md`, `README.md`, `docs/logic.md`, `docs/status.md`, `SKILL.md`, plugin README template, and all 3 example READMEs. Full verification: all 125/125 unit tests pass with 0 warnings, `editors/build.py --check` OK, all 3 examples pass `build --check` + `doctor` + `test` (12/12, 18/18, 30/30), `rig.py new` L1–L4 all pass `doctor`, `tsc --noEmit` OK.
