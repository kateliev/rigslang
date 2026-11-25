// Generated from search.rig (unit search, observed 2026-11-12). Do not edit: change the .rig file.

import catalogue from "./search.json" with { type: "json" };
import { ddg_results } from "./ddg-results.ts";

const rule: Record<string, any> = Object.fromEntries(catalogue.rules.map((r) => [r.id, r.value]));

type Out = { end: "done" | "error"; reason?: string; results: [string, string][] };

export async function search(query: string): Promise<Out> {
  // step fetch
  let res: Response;
  try {
    res = await fetch("https://html.duckduckgo.com/html/?q=" + encodeURIComponent(query), {
      signal: AbortSignal.timeout(rule["http.timeout"] * 1000),
      headers: { "User-Agent": "bandsearch-example/0.1" },
    });
  } catch {
    return { end: "error", reason: "blocked or offline", results: [] };
  }
  // gate ok (hard)
  if (!res.ok || !(res.headers.get("content-type") ?? "").includes("text/html")) {
    return { end: "error", reason: "blocked or offline", results: [] };
  }
  // step parse
  const results = ddg_results(await res.text(), rule["results.max"]);
  // gate any (soft): an empty list is reported, and the flow ends at done
  if (results.length === 0) return { end: "done", reason: "give back an empty list", results };
  return { end: "done", results };
}
