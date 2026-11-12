// Generated from wiki.rig (unit wiki, observed 2026-11-12). Do not edit: change the .rig file.

import catalogue from "./wiki.json" with { type: "json" };
import { wiki_title } from "./wiki-title.ts";
import { album_list } from "./album-list.ts";

const rule: Record<string, any> = Object.fromEntries(catalogue.rules.map((r) => [r.id, r.value]));
const API = "https://en.wikipedia.org/w/api.php?format=json&formatversion=2&redirects=1&action=parse";

type Out = {
  end: "done" | "error";
  reason?: string;
  title?: string;
  url?: string;
  summary?: string;
  albums?: [string, number][];
};

async function get(url: string): Promise<Response> {
  return fetch(url, {
    signal: AbortSignal.timeout(rule["http.timeout"] * 1000),
    headers: { "User-Agent": "bandsearch-example/0.1" },
  });
}

export async function wiki(url: string): Promise<Out> {
  // gate title (hard)
  const title = wiki_title(url);
  if (!title) return { end: "error", reason: "not an English Wikipedia article" };
  try {
    // step summary
    const res = await get("https://en.wikipedia.org/api/rest_v1/page/summary/" + encodeURIComponent(title));
    const page = res.ok ? await res.json() : null;
    // gate has-summary (hard)
    if (!page?.extract) return { end: "error", reason: "no such article" };
    // step section
    const q = "&page=" + encodeURIComponent(page.title);
    const sections = (await (await get(API + "&prop=sections" + q)).json()).parse?.sections ?? [];
    const found = sections.find((s: { line: string }) => s.line.trim().toLowerCase() === "discography");
    let wikitext = "";
    if (found) {
      wikitext = (await (await get(API + "&prop=wikitext&section=" + found.index + q)).json()).parse?.wikitext ?? "";
    }
    // step albums
    return {
      end: "done",
      title: page.title,
      url: page.content_urls?.desktop?.page,
      summary: page.extract,
      albums: album_list(wikitext),
    };
  } catch {
    return { end: "error", reason: "no such article" };
  }
}
