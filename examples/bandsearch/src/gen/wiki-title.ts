// Generated from wiki.rig (unit wiki-title, proved 2026-11-12). Do not edit: change the .rig file.

export function wiki_title(url: string): string {
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return "";
  }
  if (!/^en\.(m\.)?wikipedia\.org$/.test(u.hostname)) return "";
  if (!u.pathname.startsWith("/wiki/")) return "";
  const title = u.pathname.slice("/wiki/".length);
  try {
    return decodeURIComponent(title);
  } catch {
    return title;
  }
}
