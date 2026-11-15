// Generated from wiki.rig (unit album-list, proved 2026-11-12). Do not edit: change the .rig file.

export function album_list(wikitext: string): [string, number][] {
  const out: [string, number][] = [];
  for (const line of wikitext.split("\n")) {
    if (!line.startsWith("*")) continue;
    const m = line.match(/''(.+?)''/);
    if (!m || m.index === undefined) continue;
    const title = m[1].replace(/\[\[(?:[^\]|]*\|)?([^\]]*)\]\]/g, "$1").trim();
    const year = line.slice(m.index + m[0].length).match(/\b(\d{4})\b/);
    out.push([title, year ? Number(year[1]) : 0]);
  }
  return out;
}
