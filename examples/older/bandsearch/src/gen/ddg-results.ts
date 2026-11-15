// Generated from search.rig (unit ddg-results, proved 2026-11-12). Do not edit: change the .rig file.

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'", "#x27": "'", nbsp: " " };

function decodeEntities(s: string): string {
  return s.replace(/&(#?\w+);/g, (m, e) => ENTITIES[e] ?? m);
}

export function ddg_results(html: string, limit: number): [string, string][] {
  const out: [string, string][] = [];
  for (const m of html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)) {
    if (out.length >= limit) break;
    const attrs = m[1];
    if (!/class="[^"]*\bresult__a\b/.test(attrs)) continue;
    const href = attrs.match(/href="([^"]*)"/);
    if (!href) continue;
    let url = decodeEntities(href[1]);
    const redirect = url.match(/[?&]uddg=([^&]+)/);
    if (redirect) url = decodeURIComponent(redirect[1]);
    if (url.startsWith("//")) url = "https:" + url;
    if (!url.startsWith("http")) continue;
    const title = decodeEntities(m[2].replace(/<[^>]*>/g, "")).trim();
    out.push([title, url]);
  }
  return out;
}
