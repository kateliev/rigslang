// The bridge between a model and the RIGS tool. The same file for every tool: do not edit it
// for one tool. Everything about the tool comes from gen/front.json (rig.py build).
//
// No LM Studio objects here, so that a test can call the same code (try.ts).
// The model gives only data. The command names are fixed here, the arguments travel as one
// JSON string, and the driver starts without a shell: the words of the model cannot become code.

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import frontJson from "./gen/front.json" with { type: "json" };

export type FrontTool = {
  name: string;
  kind: string; // run | batch | queues | answer_gate | work | status | call
  unit?: string; // kind "call": the name of the tool unit
  description: string;
  parameters: { type: string; properties: Record<string, unknown>; required: string[] };
};
export type UiRule = {
  id: string;
  group: string;
  label: string;
  type: string;
  ui: string;
  value: unknown;
  default: unknown;
  min?: number;
  max?: number;
  length?: number;
  options?: string[];
  note?: string;
};
export type RunOverrides = {
  preset?: string;
  set?: Record<string, string>;
};
export type Front = {
  name: string;
  prompt: string;
  driver: string[];
  timeout_s: number;
  work?: { max_calls?: number; max_tokens?: number; think?: boolean };
  presets?: string[];
  ui_rules?: UiRule[];
  tools: FrontTool[];
};

export const front = frontJson as Front;

const refused = (text: string) => JSON.stringify({ refused: text });

/** The folder that holds rig.json: the setting, else RIG_TOOL_ROOT, else the folder above the plugin. */
export function toolRoot(setting?: string): string | null {
  for (const p of [setting, process.env.RIG_TOOL_ROOT, resolve(process.cwd(), ".."), process.cwd()]) {
    if (p && existsSync(join(p, "rig.json"))) return resolve(p);
  }
  return null;
}

/** The arguments of the driver for one tool call. */
export function argvFor(tool: FrontTool, p: Record<string, unknown>, overrides?: RunOverrides): string[] {
  const run = String(p.run ?? "");
  const extra = (): string[] => {
    const out: string[] = [];
    if (overrides?.preset) out.push("--preset", overrides.preset);
    if (overrides?.set) {
      for (const [rid, val] of Object.entries(overrides.set)) {
        out.push("--set", `${rid}=${val}`);
      }
    }
    return out;
  };
  if (tool.kind === "run") return ["run", JSON.stringify(p), ...extra()];
  if (tool.kind === "answer_gate") return ["answer", run, JSON.stringify(p.why ? { pass: p.pass === true, why: String(p.why) } : { pass: p.pass === true })];
  if (tool.kind === "status") return ["status", run];
  if (tool.kind === "queues") return ["queues"];
  if (tool.kind === "batch") return ["batch", JSON.stringify(Array.isArray(p.items) ? p.items : []), "--report", `reports/batch-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.md`, ...extra()];
  return ["call", tool.unit ?? tool.name, JSON.stringify(p)];
}

function start(command: string[], cwd: string, seconds: number): Promise<{ code: number | null; out: string; err: string; missing: boolean }> {
  return new Promise((done) => {
    let out = "", err = "", missing = false;
    const child = spawn(command[0], command.slice(1), { cwd, shell: false, windowsHide: true });
    const timer = setTimeout(() => { err += `\nstopped after ${seconds} seconds`; child.kill(); }, seconds * 1000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", (e: NodeJS.ErrnoException) => { missing = e.code === "ENOENT"; err += e.message; });
    child.on("close", (code) => { clearTimeout(timer); done({ code, out, err, missing }); });
  });
}

const quote = (s: string) => (/^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);

/** Decorate a driver response for the plugin front: remove CLI-only waiting.answer,
 *  add a front-specific waiting.next_action, and add waiting.command on human gates. */
export function decorate(line: string, root: string): string {
  try {
    const r = JSON.parse(line);
    if (!r || typeof r !== "object" || !r.waiting || typeof r.waiting !== "object") return line;
    delete r.waiting.answer;
    if (r.run) {
      if (r.waiting.kind === "human") {
        r.waiting.command = `cd ${quote(root)} && ${front.driver.map(quote).join(" ")} approve ${r.run} yes`;
        r.waiting.next_action = { call: "NONE", show_verbatim: r.waiting.say ?? "" };
      } else if (r.waiting.kind === "step") {
        r.waiting.next_action = { call: "work_run", args: { run: r.run } };
      } else if (r.waiting.kind === "model") {
        r.waiting.next_action = { call: "answer_gate", args: { run: r.run, pass: "<true|false>", why: "<one sentence>" } };
      }
    }
    return JSON.stringify(r);
  } catch {
    return line;
  }
}

export const withCommand = decorate;

const activeRunByRoot = new Map<string, string>();

function finishLine(line: string, root: string): string {
  try {
    const r = JSON.parse(line);
    if (r && typeof r === "object" && typeof r.run === "string" && r.run) {
      if (r.waiting) activeRunByRoot.set(root, r.run);
      else if (r.outcome && activeRunByRoot.get(root) === r.run) activeRunByRoot.delete(root);
    }
  } catch { /* not JSON */ }
  return decorate(line, root);
}

type StdioPending = {
  id: number;
  resolve: (line: string) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};

type StdioSession = {
  root: string;
  child: ChildProcessWithoutNullStreams | null;
  cmd: string[] | null;
  buf: string;
  nextId: number;
  pending: StdioPending | null;
  queue: Promise<void>;
};

const sessions = new Map<string, StdioSession>();

function setRef(handle: unknown, on: boolean): void {
  const h = handle as { ref?: () => void; unref?: () => void } | null;
  if (on) h?.ref?.();
  else h?.unref?.();
}

function setSessionRef(session: StdioSession, on: boolean): void {
  const c = session.child;
  if (!c) return;
  setRef(c, on);
  setRef(c.stdin, on);
  setRef(c.stdout, on);
  setRef(c.stderr, on);
}

function killSession(session: StdioSession, reason?: Error): void {
  const p = session.pending;
  if (p) {
    clearTimeout(p.timer);
    session.pending = null;
    p.reject(reason ?? new Error("driver closed"));
  }
  const c = session.child;
  session.child = null;
  session.buf = "";
  if (!c) return;
  try { c.stdin.end(); } catch { /* ignore */ }
  try { c.stdout.destroy(); } catch { /* ignore */ }
  try { c.stderr.destroy(); } catch { /* ignore */ }
  try { c.kill(); } catch { /* ignore */ }
  setRef(c, false);
}

/** Shut down warm driver child processes cleanly (call on CLI exit). */
export function closeDriver(root?: string): void {
  if (root !== undefined) {
    const key = resolve(root);
    const s = sessions.get(key);
    if (s) { killSession(s); sessions.delete(key); }
    return;
  }
  for (const s of sessions.values()) killSession(s);
  sessions.clear();
}

function spawnChild(session: StdioSession): ChildProcessWithoutNullStreams {
  const cmd = session.cmd ?? front.driver;
  const child = spawn(cmd[0], [...cmd.slice(1), "serve-stdio"], { cwd: session.root, shell: false, windowsHide: true });
  session.child = child;
  session.buf = "";
  child.stdin.on("error", () => {});
  child.stderr.on("data", () => {});
  child.stdout.on("data", (chunk: Buffer | string) => {
    if (session.child !== child) return;
    session.buf += typeof chunk === "string" ? chunk : chunk.toString("utf8");
    let nl: number;
    while ((nl = session.buf.indexOf("\n")) >= 0) {
      const raw = session.buf.slice(0, nl).trim();
      session.buf = session.buf.slice(nl + 1);
      if (!raw) continue;
      const p = session.pending;
      if (!p) continue;
      try {
        const msg = JSON.parse(raw) as { id?: unknown; code?: unknown; result?: unknown };
        if (msg && typeof msg === "object" && msg.id === p.id && msg.result !== null && typeof msg.result === "object") {
          clearTimeout(p.timer);
          session.pending = null;
          setSessionRef(session, false);
          p.resolve(JSON.stringify(msg.result));
          continue;
        }
      } catch { /* malformed */ }
      killSession(session, new Error("malformed serve-stdio output"));
      break;
    }
  });
  child.on("error", (e: NodeJS.ErrnoException) => {
    if (session.child !== child) return;
    if (e.code === "ENOENT" && cmd[0] === "python3") {
      session.cmd = ["python", ...front.driver.slice(1)];
      const err = new Error("ENOENT_PYTHON3") as Error & { retryPython?: boolean };
      err.retryPython = true;
      killSession(session, err);
      return;
    }
    killSession(session, e);
  });
  child.on("close", (code) => {
    if (session.child !== child) return;
    killSession(session, new Error(`serve-stdio exited (${code ?? "signal"})`));
  });
  return child;
}

function sendOnce(session: StdioSession, args: string[]): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = session.child ?? spawnChild(session);
    const id = ++session.nextId;
    const timer = setTimeout(() => {
      const err = new Error(`stopped after ${front.timeout_s} seconds`) as Error & { timeout?: boolean };
      err.timeout = true;
      killSession(session, err);
    }, front.timeout_s * 1000);
    session.pending = { id, resolve: resolvePromise, reject: rejectPromise, timer };
    setSessionRef(session, true);
    try {
      child.stdin.write(JSON.stringify({ id, argv: args }) + "\n");
    } catch (e) {
      killSession(session, e instanceof Error ? e : new Error(String(e)));
    }
  });
}

function requestStdio(root: string, args: string[]): Promise<string> {
  let session = sessions.get(root);
  if (!session) {
    session = { root, child: null, cmd: null, buf: "", nextId: 0, pending: null, queue: Promise.resolve() };
    sessions.set(root, session);
  }
  const run = session.queue.then(async () => {
    try {
      return await sendOnce(session, args);
    } catch (e) {
      if ((e as { retryPython?: boolean })?.retryPython) {
        return await sendOnce(session, args);
      }
      throw e;
    }
  });
  session.queue = run.then(() => {}, () => {});
  return run;
}

async function driveOneShot(args: string[], root: string): Promise<string> {
  let r = await start([...front.driver, ...args], root, front.timeout_s);
  // "python3" is "python" on some computers.
  if (r.missing && front.driver[0] === "python3") r = await start(["python", ...front.driver.slice(1), ...args], root, front.timeout_s);
  const lines = r.out.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("{"));
  if (lines.length) return finishLine(lines[lines.length - 1], root);
  return JSON.stringify({ ok: false, error: (r.err || r.out || "the driver gave no result").trim().slice(-400) });
}

/** Run the driver with these arguments in the tool folder. -> its last JSON line, or an error as JSON. */
async function drive(args: string[], root: string): Promise<string> {
  try {
    const line = await requestStdio(root, args);
    return finishLine(line, root);
  } catch (e) {
    if ((e as { timeout?: boolean })?.timeout) {
      return JSON.stringify({ ok: false, error: e instanceof Error ? e.message : String(e) });
    }
    return driveOneShot(args, root);
  }
}

/** Run the driver with these arguments, in the tool folder of the setting. -> one JSON text. */
export async function driver(args: string[], rootSetting?: string): Promise<string> {
  const root = toolRoot(rootSetting);
  if (!root) return refused("The tool folder is not found. Set \"Tool folder\" in LM Studio: in the settings of this plugin.");
  return drive(args, root);
}

/** Run one tool call. The answer is always one JSON text: a result, a refusal or an error. */
export async function callTool(tool: FrontTool, params: Record<string, unknown>, rootSetting?: string, overrides?: RunOverrides): Promise<string> {
  const root = toolRoot(rootSetting);
  if (!root) return refused("The tool folder is not found. The operator must set \"Tool folder\" in LM Studio: in the settings of this plugin, the folder that holds rig.json. It is not a setting of another program.");
  return drive(argvFor(tool, params, overrides), root);
}

/** The words of a message of the operator that answers a human gate: "approve [RUN] [WORDS]".
 *  The words are "yes" or "no", or, at a gate with options, the words of the answer ("yes" or
 *  nothing: the first option). A run id has the form r1 (or legacy 20261125-101500-01). -> [run or "", words] or null. */
export function approval(text: string): [string, string[]] | null {
  const m = text.trim().match(/^approve(?:\s+(r\d+|\d{8}-\d{6}-\d+))?(?:\s+(.*))?$/is);
  if (!m) return null;
  return [m[1] ?? "", (m[2] ?? "").split(/\s+/).filter(Boolean)];
}

/** A message of the operator that starts with "approve" answers the human gate as the person.
 *  Only the operator's own message can do this: it is no tool, so the model cannot call it.
 *  Without a run id, the one run that waits for a person (or this session's active run) is meant.
 *  -> the result as JSON, or null when the message is no approval. */
export async function operatorAnswer(text: string, rootSetting?: string): Promise<string | null> {
  const a = approval(text);
  if (!a) return null;
  const root = toolRoot(rootSetting);
  if (!root) return refused("The tool folder is not found. Set \"Tool folder\" in LM Studio: in the settings of this plugin.");
  let [run, words] = a;
  if (!run) {
    let waits: { run: string }[] = [];
    try { waits = JSON.parse(await drive(["queues"], root)).waits_for_person ?? []; } catch { /* no list */ }
    if (waits.length === 1) {
      run = waits[0].run;
    } else if (waits.length > 1) {
      const active = activeRunByRoot.get(root);
      if (active && waits.some((w) => w.run === active)) run = active;
    }
    if (!run) {
      return refused(`${waits.length} runs wait for a person. Write the run id: approve <run id> ${words.join(" ")}. They are: ${waits.map((w) => w.run).join(", ") || "none"}.`);
    }
  }
  return drive(["approve", run, ...words], root);
}

/** What the model reads in place of an approval message of the operator. */
export function forModel(message: string, result: string): string {
  let refusal = "";
  try { refusal = JSON.parse(result)?.refused ?? ""; } catch { /* not JSON */ }
  if (refusal) // the message of the operator was not taken: only the operator can fix it, so the model must not call a tool
    return `The operator wrote "${message.trim()}", but the tool did not take it as an answer: ${refusal}\nTell the operator this, word for word, and wait for a new message. Do not call a tool.`;
  return `The operator answered a human gate with "${message.trim()}". The result of the tool: ${result}\nRead it and go on as the rules say.`;
}
