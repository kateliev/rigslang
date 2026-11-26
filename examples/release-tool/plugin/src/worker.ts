// The worker: code gives the model one small job at a time. The same file for every tool.
//
// A run that waits at a step of the model with an "out" type (a schema) does not need a chat.
// The worker reads what the run waits for, asks the loaded model one time in a new, empty context,
// with the answer bound to the schema, and gives the answer to the driver. Then it reads the run
// again, and goes on until the run waits for something else: a person, a judgment, or the end.
//
// Why: a small local model that carries a long chat gets slow and loses its place, and with its
// thinking turned off it can repeat a token without end. A new context for each job leaves no room
// for the first; a cap on the tokens ends the second. The gates of the tool still check every answer.
//
// Two modes ("work" in front.json, from rig.json "plugin": {"work": {...}}):
//   think: true   the model thinks first, at most max_tokens in all; the worker reads the JSON
//                 after the thinking. Slower, and better for a judgment that needs knowledge.
//   think: false  the answer is bound to the schema from its first token, so the model cannot
//                 think. Fast; a small model then often takes the easy answer.

import { Chat, type LLM } from "@lmstudio/sdk";
import { driver, front } from "./bridge.ts";

const RULES = [
  "You do one job of a tool. Code did the rest of the work and checks your answer.",
  "Read the job and the data. Decide each item on its own, in the order of the data.",
  "Answer only with JSON in the given form. Use only ids, names and numbers from the data. Do not invent.",
].join("\n");

type Waiting = { node: string; kind: string; do?: string; out?: string; schema?: Record<string, unknown>; sees?: unknown; problems?: string[]; item?: unknown };

/** The run waits at a job for the worker: a step of the model with an "out" type. */
export function isJob(w: Waiting | undefined): w is Waiting {
  return !!w && w.kind === "step" && !!w.schema;
}

/** The one message that the model gets for one job. */
export function jobText(w: Waiting): string {
  let text = `The job:\n${w.do ?? ""}\n\nThe data:\n${JSON.stringify(w.sees ?? {})}`;
  if (w.problems?.length) text += `\n\nYour last answer for this job failed for these reasons. Fix them:\n- ${w.problems.join("\n- ")}`;
  return text + `\n\nAnswer with {"result": ...}, where the result has the form ${w.out ?? "of the schema"}.`;
}

/** The JSON object in a text: from the first "{" to the last "}" (a model may put a code fence around it). */
export function jsonIn(text: string): string {
  const a = text.indexOf("{"), b = text.lastIndexOf("}");
  return a >= 0 && b > a ? text.slice(a, b + 1) : text;
}

/** Do the jobs of one run. -> the last result of the driver as JSON, with "work": what the worker did. */
export async function work(model: LLM, run: string, rootSetting?: string, status?: (text: string) => void): Promise<string> {
  const limits = { max_calls: 50, max_tokens: 4000, think: false, ...(front.work ?? {}) };
  const done: { node: string; item?: unknown; seconds: number; tokens?: number; ok: boolean }[] = [];
  let line = await driver(["status", run], rootSetting);
  let same = 0, last = "";
  for (let n = 0; n < limits.max_calls; n++) {
    let r: { waiting?: Waiting; refused?: string; error?: string };
    try { r = JSON.parse(line); } catch { break; }
    const w = r.waiting;
    if (!isJob(w)) break;
    const where = `${w.node} ${JSON.stringify(w.item ?? {})}`;
    same = where === last ? same + 1 : 0;
    last = where;
    if (same >= 5) break; // the same job failed five times in a row: leave it to the operator
    status?.(`${w.node}: job ${n + 1}${w.item ? " " + JSON.stringify(w.item) : ""}`);
    const t = Date.now();
    const schema = { type: "object", properties: { result: w.schema }, required: ["result"] };
    const chat = Chat.from([{ role: "system", content: RULES }, { role: "user", content: jobText(w) }]);
    let answer: unknown = undefined;
    let tokens: number | undefined;
    let errorReason: string | undefined;
    try {
      let rawText: string;
      if (limits.think) {
        const p = await model.respond(chat, { maxTokens: limits.max_tokens, temperature: 0.6 });
        tokens = p.stats?.predictedTokensCount;
        rawText = jsonIn(p.nonReasoningContent);
      } else {
        const p = await model.respond(chat, { structured: { type: "json", jsonSchema: schema }, maxTokens: limits.max_tokens, temperature: 0.2 });
        tokens = p.stats?.predictedTokensCount;
        rawText = p.content;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(rawText);
      } catch {
        errorReason = tokens !== undefined && tokens >= limits.max_tokens
          ? `hit max_tokens (${limits.max_tokens}) before finishing valid JSON; keep values shorter`
          : "response was not valid JSON";
      }
      if (errorReason === undefined) {
        if (parsed && typeof parsed === "object" && "result" in parsed && (parsed as { result?: unknown }).result !== undefined) {
          answer = (parsed as { result?: unknown }).result;
        } else {
          errorReason = tokens !== undefined && tokens >= limits.max_tokens
            ? `hit max_tokens (${limits.max_tokens}) before finishing valid JSON; keep values shorter`
            : 'response JSON had no "result" field';
        }
      }
    } catch (e) {
      errorReason = tokens !== undefined && tokens >= limits.max_tokens
        ? `hit max_tokens (${limits.max_tokens}) before finishing valid JSON; keep values shorter`
        : `model call failed: ${e instanceof Error ? e.message : String(e)}`;
    }
    const seconds = Math.round((Date.now() - t) / 100) / 10;
    const meta: Record<string, unknown> = {
      model: model.identifier ?? "local",
      seconds,
      ...(tokens !== undefined ? { tokens } : {}),
      ...(errorReason ? { error: errorReason } : {}),
    };
    line = await driver(["answer", run, JSON.stringify({ result: answer ?? null }), "--node", w.node, "--meta", JSON.stringify(meta)], rootSetting);
    done.push({ node: w.node, item: w.item, seconds, tokens, ok: answer !== undefined });
  }
  try {
    const r = JSON.parse(line);
    r.work = { jobs: done.length, seconds: Math.round(done.reduce((s, d) => s + d.seconds, 0)), each: done };
    return JSON.stringify(r);
  } catch {
    return line;
  }
}
