// The bridge between a model and the Rig tool. The same file for every tool: do not edit it
// for one tool. Everything about the tool comes from gen/front.json (rig.py build).
//
// No LM Studio objects here, so that a test can call the same code (try.ts).
// The model gives only data. The command names are fixed here, the arguments travel as one
// JSON string, and the driver starts without a shell: the words of the model cannot become code.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import frontJson from "./gen/front.json" with { type: "json" };

export type FrontTool = {
  name: string;
  kind: string; // run | batch | queues | answer_gate | finish_step | status | call
  unit?: string; // kind "call": the name of the tool unit
  node?: string; // kind "finish_step": the one step that this tool answers (its schema is the "out" type)
  description: string;
  parameters: { type: string; properties: Record<string, unknown>; required: string[] };
};
export type Front = { name: string; prompt: string; driver: string[]; timeout_s: number; tools: FrontTool[] };

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
export function argvFor(tool: FrontTool, p: Record<string, unknown>): string[] {
  const run = String(p.run ?? "");
  if (tool.kind === "run") return ["run", JSON.stringify(p)];
  if (tool.kind === "answer_gate") return ["answer", run, JSON.stringify(p.why ? { pass: p.pass === true, why: String(p.why) } : { pass: p.pass === true })];
  if (tool.kind === "finish_step") return ["answer", run, JSON.stringify({ result: p.result }), ...(tool.node ? ["--node", tool.node] : [])];
  if (tool.kind === "status") return ["status", run];
  if (tool.kind === "queues") return ["queues"];
  if (tool.kind === "batch") return ["batch", JSON.stringify(Array.isArray(p.items) ? p.items : []), "--report", `reports/batch-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.md`];
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

/** A run that waits for a person: add the exact command for the operator, with the tool folder.
 *  The model cannot answer a human gate; it only passes this text on. */
export function withCommand(line: string, root: string): string {
  try {
    const r = JSON.parse(line);
    if (r?.waiting?.kind !== "human" || !r.run) return line;
    r.waiting.command = `cd ${quote(root)} && ${front.driver.map(quote).join(" ")} approve ${r.run} yes`;
    return JSON.stringify(r);
  } catch {
    return line;
  }
}

/** Run the driver with these arguments in the tool folder. -> its last JSON line, or an error as JSON. */
async function drive(args: string[], root: string): Promise<string> {
  let r = await start([...front.driver, ...args], root, front.timeout_s);
  // "python3" is "python" on some computers.
  if (r.missing && front.driver[0] === "python3") r = await start(["python", ...front.driver.slice(1), ...args], root, front.timeout_s);
  const lines = r.out.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("{"));
  if (lines.length) return withCommand(lines[lines.length - 1], root);
  return JSON.stringify({ ok: false, error: (r.err || r.out || "the driver gave no result").trim().slice(-400) });
}

/** Run one tool call. The answer is always one JSON text: a result, a refusal or an error. */
export async function callTool(tool: FrontTool, params: Record<string, unknown>, rootSetting?: string): Promise<string> {
  const root = toolRoot(rootSetting);
  if (!root) return refused("The tool folder is not found. The operator must set \"Tool folder\" in the plugin settings: the folder that holds rig.json.");
  return drive(argvFor(tool, params), root);
}

/** The words of a message of the operator that answers a human gate: "approve [RUN] [WORDS]".
 *  The words are "yes" or "no", or, at a gate with options, the words of the answer ("yes" or
 *  nothing: the first option). A run id has the form 20261125-101500-01. -> [run or "", words] or null. */
export function approval(text: string): [string, string[]] | null {
  const m = text.trim().match(/^approve(?:\s+(\d{8}-\d{6}-\d+))?(?:\s+(.*))?$/is);
  if (!m) return null;
  return [m[1] ?? "", (m[2] ?? "").split(/\s+/).filter(Boolean)];
}

/** A message of the operator that starts with "approve" answers the human gate as the person.
 *  Only the operator's own message can do this: it is no tool, so the model cannot call it.
 *  Without a run id, the one run that waits for a person is meant. -> the result as JSON, or null
 *  when the message is no approval. */
export async function operatorAnswer(text: string, rootSetting?: string): Promise<string | null> {
  const a = approval(text);
  if (!a) return null;
  const root = toolRoot(rootSetting);
  if (!root) return refused("The tool folder is not found. Set \"Tool folder\" in the plugin settings.");
  let [run, words] = a;
  if (!run) {
    let waits: { run: string }[] = [];
    try { waits = JSON.parse(await drive(["queues"], root)).waits_for_person ?? []; } catch { /* no list */ }
    if (waits.length !== 1) return refused(`${waits.length} runs wait for a person. Write the run id: approve <run id> ${words.join(" ")}. They are: ${waits.map((w) => w.run).join(", ") || "none"}.`);
    run = waits[0].run;
  }
  return drive(["approve", run, ...words], root);
}

/** What the model reads in place of an approval message of the operator. */
export function forModel(message: string, result: string): string {
  return `The operator answered a human gate with "${message.trim()}". The result of the tool: ${result}\nRead it and go on as the rules say.`;
}
