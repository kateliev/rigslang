# Draft proposal: Rig v2 — timeless, domain-agnostic agent orchestration

Status: **Implemented in Rig v2 (2026-11-26).** See [status.md](status.md) and [skills/rig/spec.md](../skills/rig/spec.md).

## Guiding principle: separate the Idea from the World and the Caller

Apps, model APIs, and chat frontends change every year. The procedure, its limits, and its gates should outlive all of them. Rig v2 enforces a strict three-layer split:

```
  THE CALLER (Fronts — swappable as AI interfaces evolve)
  Agent Skill (SKILL.md) | Stdio & HTTP MCP | OpenAPI/REST | Shared local plugin | Web UI (graph + approval)
                                         │
                                         ▼
  THE IDEA (Core — domain-agnostic, long-lived)
  .rig (intent, rules, steps, reason, gates, ends, blocks) + pure-Python engine & gates + rigkit.py
                                         │
                                         ▼
  THE WORLD (Target Adapters — swappable when apps, APIs, or constraints change)
  Local files | Web APIs | Subprocesses | Host-app RPC | Databases | Multiprocess workers
```

**Rule of thumb:** No app quirk (specific timeouts, host API details, reload hacks, UI specifics) ever enters the `.rig` language. When an underlying app or model changes, you swap a thin adapter or recompile fronts; the `.rig` source and pure-Python gates stay intact.

---

## 1. Remove the micro level (focus purely on orchestration)

- Remove `tool` scope (`unit <name>` is always an orchestrated flow; no `tool | agent` modifier).
- Remove micro-level constructs better served by plain Python: `example <arg>* => <value>`, `uses <unit> [file]`, `code <path>` (without prefix), `tool.py call`, `Kit.tool()`, `*.tool.json`, and `templates/tools/`.
- Collapse to **three levels**:
  - **Level 1 — checked:** rules, steps, gates in code, and the runner.
  - **Level 2 — flow:** named ends, regression set, Agent Skill, and MCP front.
  - **Level 3 — production:** permissions (off by default, enforced by a `hard` gate), rollback/restore, human gates or batch review, queues, and project memory.

---

## 2. Make Reason, Intent, and Gate a true triad

Every letter of **R–I–G** becomes an orthogonal, runtime-enforced construct (~28–30 words total):

### Structured `intent`
- Unit-level and `reason`-level `intent` may carry children: `audience`, `style`, and `never` invariants.
- The runner injects unit + local `intent` automatically into every `reason` call and `model` gate.
- `rig.py doctor` tracks `never` clauses so boundaries map to explicit `hard`, `model`, or `human` gates.

### First-class `reason` block (kept distinct from `step ... by model`)

Keep **one word, one meaning** by separating mechanical single-shot LLM calls from genuine deliberative or creative reasoning:

| Construct | Role | Execution | Routing & hardening |
|---|---|---|---|
| `step <id> by steps.fn` | Deterministic work (may touch the world via an adapter) | Python / target adapter | Deterministic code |
| `step <id> by model` | Single-shot structured fill-in (`sees` → `out`, no tools, no exploration) | Fast worker, schema-bound, thinking off by default | Hardening candidate (`by model` → `by steps.fn`); routes to a fast/cheap local model |
| `reason <id>` | Deliberative or creative cognition (`intent`, thinking/creative effort, optional read-only `tools` + `budget`, optional `candidates N`, typed `out`) | Bounded reasoning arena (never mutates the world directly; gates guard the exit) | Meant to stay cognitive (diagnosis, synthesis, exception recovery, design options); routes to a strong/thinking model |
| `gate <id>` | Decision checkpoint (`hard`, `soft`, `model`, `human`) | Code, model judgment, or human sign-off | Provenance (`guessed` + AST-verified coverage) |

- `step ... by model` stays lightweight and fast for bounded choices (classification, sorting among code-found candidates, short structured extraction).
- `reason` carries real cognitive work:
  - `mode careful | creative` (thinking-enabled synthesis/diagnosis vs. divergent exploration).
  - Optional read-only `tools <names>` with a hard `budget <n>` (bounded investigation inside the arena; gates still guard the exit).
  - Optional `candidates <n>` (generate multiple distinct options for a `hard` gate to filter and a `model` or `human` gate to pick).
- This split also enables automatic **two-tier model routing**: `step ... by model` runs on a fast/local worker model while `reason` blocks escalate to a stronger or thinking-enabled model.

### Clean multi-gate repair loops (no new domain keywords)
- Reuse existing `until <path>` + `retry <rule>` + `hard`/`soft` gates + `if <gate>.failed` for multi-fixer repair under one shared round budget (clearing resolved loop-local soft problems on retry).

---

## 3. Universal operational & transactional primitives (domain-agnostic)

These apply equally to web/file tools, code migrations, data pipelines, and GUI host-app automation:

1. **Transactional `rollback` hook:** Alongside `finally`, a flow can declare a `rollback` block (run automatically on hard fail, error, or unattended deferral, and exposed as an explicit `restore` command when present). Soft failures that remain after retries can end cleanly at a named outcome (such as `doubtful`) without discarding valid work.
2. **Pluggable `queue` & chunked unattended batches (`next_batch`):**
   - A unit may declare a `queue` step that discovers pending items from any external source (a folder, database, API, or live application) rather than relying solely on `runs/.waiting.json`.
   - Chunked execution (`batch.size`) runs one chunk unattended, automatically rolls back and defers any item hitting a `step ... by model`, `reason` block, or `model`/`human` gate into `left_for_model` / `waits_for_person`, writes a report, and returns one compact summary line per chunk.
   - Built-in serialized execution lock + consecutive-error/timeout circuit breaker in `rigkit.py`.
3. **Rule-bound UI controls (`ui`) and `brief` step outputs:**
   - Marking a `rule` with `ui` exposes it automatically as a toggle/dropdown/input in compiled UI fronts (local plugin settings, HTTP web UI, viewer), wired to per-run rule overrides.
   - Declaring `brief <keys>` on a `step` makes `rigkit.py` save full payloads to disk and show only compact keys + file path to models (paired with safe read-only artifact inspection).
4. **Target-adapter helpers (outside the language):**
   - Keep `.rig` unaware of host specifics; provide optional stdlib helpers in `rigkit.py` (`step` wrapper, JSON-RPC/HTTP helper, optional parallel worker pool) and a clean "host adapter + pure-Python engine" project template (`rig.py new --template host`).
5. **Ground-truth evaluation (`tool.py eval`):**
   - Complement scripted `regress` with dataset scoring against a saved baseline (measuring quality metrics + wall time across rule or model changes).

---

## 4. Universal caller fronts (surviving frontend churn)

- **Agent Skill (`SKILL.md`):** framed and documented for any skill-capable coding agent (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode).
- **MCP (Stdio + Streamable HTTP) & OpenAPI 3.1 (`tool.py serve-http`):** one stdlib HTTP/MCP front that works across desktop chat apps, IDEs, Open WebUI, AnythingLLM, Jan, and workflow engines — eliminating per-tool TypeScript/Node copies.
- **Universal human gates & batch review UI:**
  - Support MCP Elicitation (`elicitation/create`) where available.
  - Serve a built-in localhost approval & visual review page (`/approve/<run>`, plus gallery/diff rendering for batch reports and visual artifacts) so human sign-off works in any frontend without terminal copy-paste.
- **Pluggable worker backends:** stdlib adapters in `rigkit.py` for OpenAI-compatible (`/v1/chat/completions`), Ollama (`/api/chat`), and Anthropic APIs.
