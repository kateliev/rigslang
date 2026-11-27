"use strict";
// RIGS flow & unit viewer client.
// The viewer has no parser. `rig.py serve` (or `tool.py serve-http`) gives it a bundle,
// and all visual styling and graph spacing tokens live in viewer.css.

// - DOM helpers --------------------------------------
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}
const store = {
  get(k) { try { return localStorage.getItem("rig." + k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem("rig." + k, v); } catch (e) { /* private mode */ } },
};
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
function cssNum(prop, fallback) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
  const n = parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

// - Data: the bundle that rig.py compiles -------------
const PLACE = /\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}/g;
const params = new URLSearchParams(location.search);
const S = {
  B: null, text: null, sidecars: {}, dirty: false, changed: new Set(),
  tab: store.get("tab") || "units", unit: null, sel: null, view: null,
  served: params.get("serve") === "1" && location.protocol.startsWith("http"),
  skillRef: store.get("skillRef") === "1",
};
const canEdit = () => S.served && S.B && S.B.text != null && !S.B.readonly;
function msg(t, ok = true) { const m = $("#msg"); m.textContent = t; m.className = t ? (ok ? "ok" : "bad") : ""; }
const units = () => S.B ? S.B.units : [];
const curUnit = () => units().find(u => u.name === S.unit) || units()[0] || null;
const cat = U => U && U.catalogue;
const ruleOf = (U, id) => cat(U) ? cat(U).rules.find(r => r.id === id) : null;
function fmtVal(v, rtype) {
  if (typeof v === "boolean") return v ? "on" : "off";
  if (Array.isArray(v)) {
    if (rtype === "tuple") return "(" + v.map(x => JSON.stringify(x)).join(", ") + (v.length === 1 ? "," : "") + ")";
    return "[" + v.map(x => JSON.stringify(x)).join(", ") + "]";
  }
  if (v && typeof v === "object") {
    return "{" + Object.entries(v).map(([k, x]) => (/^[A-Za-z_][\w-]*$/.test(k) ? k : JSON.stringify(k)) + ": " + JSON.stringify(x)).join(", ") + "}";
  }
  return String(v);
}
function shown(U, id) {  // a rule value as the text a person reads
  const s = U.rules_src[id];
  if (s) return s.shown;
  const r = ruleOf(U, id);
  if (r) return fmtVal(r.value, r.type);
  const d = id.lastIndexOf(".");
  if (d > 0) {
    const base = ruleOf(U, id.slice(0, d)), key = id.slice(d + 1);
    if (base && base.type === "dict" && base.value && has(base.value, key)) return fmtVal(base.value[key]);
  }
  return "?";
}
function resolvePlaceholder(U, ph) {
  const r = ruleOf(U, ph);
  if (r) return { rule: r, id: ph, shown: shown(U, ph) };
  const d = ph.lastIndexOf(".");
  if (d > 0) {
    const baseId = ph.slice(0, d), key = ph.slice(d + 1), base = ruleOf(U, baseId);
    if (base && base.type === "dict" && base.value && has(base.value, key)) return { rule: base, id: baseId, shown: fmtVal(base.value[key]) };
  }
  return null;
}
const fillText = (U, t) => (t || "").replace(PLACE, (m, id) => { const p = resolvePlaceholder(U, id); return p ? p.shown : m; });
const isChanged = (U, id) => S.changed.has(U.name + "/" + id);

function load(B) {
  S.B = B; S.text = B.text; S.sidecars = {}; S.dirty = false; S.changed = new Set(); S.sel = null; S.view = null;
  const fl = units().filter(u => u.flow);
  S.unit = fl.length ? fl[0].name : units().length ? units()[0].name : null;
  render();
}
function fromCatalogue(c, name) {  // a compiled catalogue (gen/<unit>.json), opened without rig.py serve: read only
  return { file: name, text: null, readonly: true, errors: [], warnings: [], units: [{ name: c.unit, status: [], flow: !!(c.flow || []).length,
    catalogue: c, skill: null, skill_ref: null, tool: null, levels: {}, rules_src: {}, presets_src: {} }] };
}
async function fetchBundle() {
  try {
    const r = await fetch("/bundle", { cache: "no-store" }); if (!r.ok) throw new Error(r.status);
    load(await r.json()); loadRuns();
  } catch (e) { msg("Could not load the file: " + e.message, false); render(); }
}
async function fetchCatalogue(url) {
  try {
    const r = await fetch(url, { cache: "no-store" }); if (!r.ok) throw new Error(r.status);
    load(fromCatalogue(await r.json(), url.split("/").pop()));
  } catch (e) { msg("Could not load " + url + ": " + e.message, false); }
}
function postBody() {
  return Object.keys(S.sidecars).length
    ? { headers: { "Content-Type": "application/json; charset=utf-8" }, body: JSON.stringify({ text: S.text, sidecars: S.sidecars }) }
    : { headers: { "Content-Type": "text/plain; charset=utf-8" }, body: S.text };
}
async function recompile() {  // rig.py compiles the changed text; nothing is written
  try {
    const r = await fetch("/compile", { method: "POST", ...postBody() });
    const B = await r.json(); B.text = S.text; S.B = B;
  } catch (e) { msg("Could not compile: " + e.message, false); }
  render();
}

// - Edits: rule values are written into the .rig text (or sidecar JSON) ---
function editRuleSrc(s, id, tokText) {
  if (s.json_file) {
    (S.sidecars[s.json_file] ||= {})[id] = tokText;
    S.dirty = true;
    return;
  }
  const ls = S.text.split("\n"), raw = ls[s.line - 1];
  ls[s.line - 1] = raw.slice(0, s.a) + tokText + raw.slice(s.b);
  S.text = ls.join("\n"); S.dirty = true;
}
async function setRule(U, id, tokText) {
  const s = U.rules_src[id];
  if (!s || !canEdit()) return;
  editRuleSrc(s, id, tokText); S.changed.add(U.name + "/" + id);
  await recompile();
}
async function applyPreset(U, pname) {
  const sets = Object.entries(U.presets_src[pname] || {});
  let n = 0;
  for (const [id, tok] of sets) {  // each rule is on its own line: one edit does not move the columns of another
    const cur = U.rules_src[id];
    if (cur && cur.text !== tok) { editRuleSrc(cur, id, tok); S.changed.add(U.name + "/" + id); n++; }
  }
  await recompile();
  msg(`Preset ${pname} applied: ${n} value${n === 1 ? "" : "s"} changed. Save to keep it.`);
  render();
}
function editor(U, id) {
  const r = ruleOf(U, id), s = U.rules_src[id], lab = r ? r.label : id, off = !canEdit() || !s;
  if (!r) return el("span", {}, "?");
  const title = off ? "Open the file with rig.py serve to change a value" : null;
  if (r.type === "switch") { const e = el("input", { type: "checkbox", "aria-label": lab, disabled: off, title }); e.checked = !!r.value; e.onchange = () => setRule(U, id, e.checked ? "on" : "off"); return e; }
  if (r.type === "choice") {
    const e = el("select", { "aria-label": lab, disabled: off, title });
    for (const o of r.options || []) e.add(new Option(String(o), String(o)));
    e.value = String(r.value); e.onchange = () => setRule(U, id, e.value); return e;
  }
  if (r.type === "number") {
    const e = el("input", { type: "number", class: "num", step: "any", value: r.value, min: has(r, "min") ? r.min : null, max: has(r, "max") ? r.max : null, "aria-label": lab, disabled: off, title });
    e.addEventListener("change", () => {
      const v = Number(e.value.trim()), bad = e.value.trim() === "" || isNaN(v) ? "use a number" : has(r, "min") && v < r.min ? "at least " + r.min : has(r, "max") && v > r.max ? "at most " + r.max : "";
      e.classList.toggle("invalid", !!bad); e.title = bad;
      if (!bad) setRule(U, id, e.value.trim()); else msg(`${id}: ${bad}`, false);
    });
    return e;
  }
  const e = el("input", { type: "text", class: "txt", value: s ? s.text : shown(U, id), title: title || "the value as written in the file (keep quotes and slashes)", "aria-label": lab, disabled: off });
  e.addEventListener("change", () => setRule(U, id, e.value.trim()));
  return e;
}

// - Rendering: frame -----------------------------------
function render() {
  const editable = canEdit();
  document.body.className = document.body.className.replace(/\btab-\w+/g, "").trim() + " tab-" + S.tab;
  $("#fname").textContent = S.B ? S.B.file : "";
  $("#dirty").textContent = S.dirty ? "• changed" : "";
  $("#save").hidden = !editable; $("#save").disabled = !S.dirty || !!(S.B && S.B.errors.length); $("#close").disabled = !S.B;
  $$(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === S.tab)));
  const sel = $("#unit");
  sel.hidden = units().length < 2 || S.tab === "units";
  sel.replaceChildren(...units().map(u => new Option(u.name, u.name)));
  sel.value = S.unit || "";
  const U = curUnit(), pr = $("#preset"), ps = U ? Object.keys(U.presets_src) : [];
  pr.hidden = !ps.length || !editable;
  pr.replaceChildren(new Option("preset…", ""), ...ps.map(p => new Option(p, p)));
  $("#gbar").hidden = S.tab !== "graph" || !U || !cat(U);
  const page = $("#page");
  page.replaceChildren();
  if (!S.B) { document.body.classList.remove("tab-graph"); page.append(emptyView()); return; }
  if (!units().length || !units().some(cat)) { document.body.classList.remove("tab-graph"); page.append(el("main", {}, diagCard() || el("div", { class: "card" }, "The file has no unit."))); return; }
  if (S.tab === "graph") renderGraph();
  else page.append(el("main", {}, S.tab === "skill" ? skillView() : S.tab === "json" ? jsonView() : unitsView()));
}
function emptyView() {
  const examples = ["font-names/gen/font-names.json"];
  const http = location.protocol.startsWith("http");
  return el("div", { class: "empty" },
    el("p", {}, "Run ", el("code", {}, "python3 skills/rig/rig.py serve FILE.rig"), " to see a file and change its rule values."),
    el("p", {}, "Without the server, drop a compiled catalogue (", el("code", {}, "gen/<unit>.json"), ") here, or ", el("button", { onclick: () => $("#file").click() }, "open one"), ". It is read only."),
    http ? el("div", { class: "row" }, "Examples:", examples.map(x => el("button", { onclick: () => fetchCatalogue("../examples/" + x) }, x.split("/")[0]))) : null);
}

// - Units tab ------------------------------------------
function chips(U, text, onPick) {
  const out = []; let last = 0;
  for (const m of (text || "").matchAll(PLACE)) {
    out.push(text.slice(last, m.index)); last = m.index + m[0].length;
    const resolved = resolvePlaceholder(U, m[1]);
    if (!resolved) { out.push(m[0]); continue; }
    const r = resolved.rule, baseId = resolved.id;
    out.push(el("span", { class: "chip" + (isChanged(U, baseId) ? " changed" : ""), title: r.label + ". Click to edit.",
      onclick: () => onPick(baseId), onpointerenter: () => onPick.hover && onPick.hover(baseId), onpointerleave: () => onPick.hover && onPick.hover(null) },
      el("span", { class: "rid" }, m[1]), el("b", {}, resolved.shown)));
  }
  out.push((text || "").slice(last));
  return out;
}
function diagCard() {
  const B = S.B;
  if (!B.errors.length && !B.warnings.length) return null;
  return el("div", { class: "card" }, el("h3", { class: "card-h3" }, "Check"),
    el("ul", { class: "diag" }, B.errors.map(([l, t]) => el("li", { class: "err" }, `error, line ${l}: ${t}`)), B.warnings.map(([l, t]) => el("li", { class: "warn" }, `warning, line ${l}: ${t}`))));
}
function unitsView() {
  const wrap = el("div");
  const d = diagCard(); if (d) wrap.append(d);
  for (const U of units()) wrap.append(unitCard(U));
  return wrap;
}
function unitCard(U) {
  const c = cat(U);
  const card = el("section", { class: "card", id: "u-" + U.name },
    el("h2", {}, U.name,
      U.flow && c ? el("button", { class: "btn-graph", onclick: () => { S.unit = U.name; S.tab = "graph"; store.set("tab", "graph"); render(); } }, "Graph ↗") : null),
    el("div", { class: "chips" }, U.status.map(s => el("span", { class: "st" + (/hole|none|stale|remelted/.test(s) ? " warn" : "") }, s)), c && c.queue ? el("span", { class: "st" }, "queue " + (c.queue.by || []).join(", ")) : null));
  if (!c) { card.append(el("p", { class: "dim" }, U.problem || "This unit does not compile.")); return card; }
  if (c.intent) card.append(el("p", { class: "lead" }, el("b", {}, "intent"), chips(U, c.intent, () => {})));
  const ispec = c.intent_spec || {};
  if (ispec.audience) card.append(el("p", { class: "lead" }, el("b", {}, "audience"), chips(U, ispec.audience, () => {})));
  if (ispec.style) card.append(el("p", { class: "lead" }, el("b", {}, "style"), chips(U, ispec.style, () => {})));
  for (const nv of ispec.never || []) card.append(el("p", { class: "lead" }, el("b", {}, "never"), chips(U, nv.text, () => {}), nv.gate ? el("span", { class: "dim" }, "  → " + nv.gate) : null));
  for (const n of c.notes || []) card.append(el("p", { class: "lead" }, el("b", {}, "note"), chips(U, n.text, () => {}), (n.evidence || []).map(e => el("span", { class: "dim" }, "  (evidence: " + e + ")"))));
  const ins = c.in || [], out = c.out;
  if (ins.length || out) card.append(el("p", { class: "lead" }, el("b", {}, "signature"),
    el("code", {}, "(" + ins.map(i => i.name + (i.type ? ": " + i.type : "")).join(", ") + ")" + (out ? " → " + (out.type || "?") : ""))));
  const described = [...ins.map(i => [i.name, i.text]), ...(out ? [["out", out.text]] : [])].filter(x => x[1]);
  if (described.length) card.append(el("div", { class: "tw" }, el("table", {}, described.map(([k, t]) => el("tr", {}, el("td", { class: "mono" }, k), el("td", {}, t))))));
  if ((c.external || []).length) card.append(el("h3", {}, "External code"), el("div", { class: "tw" }, el("table", {}, c.external.map(x => el("tr", {}, el("td", { class: "mono" }, x.name), el("td", {}, x.text))))));
  if ((c.flow || []).length) card.append(flowTable(U));
  if (c.rules.length) card.append(rulesTable(U));
  const ps = Object.entries(c.presets || {});
  if (ps.length) card.append(el("h3", {}, "Presets"), el("div", { class: "tw" }, el("table", {},
    el("tr", {}, el("th", {}, "preset"), el("th", {}, "values"), el("th", {}, "")),
    ps.map(([p, sets]) => el("tr", {}, el("td", {}, el("b", {}, p)),
      el("td", { class: "mono" }, Object.keys(sets).map(id => el("div", {}, id + " = " + ((U.presets_src[p] || {})[id] ?? JSON.stringify(sets[id]))))),
      el("td", {}, canEdit() ? el("button", { onclick: () => applyPreset(U, p) }, "Apply") : null))))));
  return card;
}
function nodeRef(U, id, onGo) {
  const f = cat(U).flow.find(x => x.id === id);
  return el("a", { onclick: onGo, title: f ? f.name || "" : "" }, el("span", { class: "gid " + (f ? f.kind : "step") }, id), " ", f ? f.name || "" : "?");
}
function flowTable(U) {
  const c = cat(U), rowId = id => "n-" + U.name + "-" + id, blocks = Object.fromEntries((c.blocks || []).map(b => [b.id, b]));
  const go = id => () => { const tr = document.getElementById(rowId(id)); if (!tr) return; tr.scrollIntoView({ block: "center", behavior: "smooth" }); tr.classList.remove("flash"); void tr.offsetWidth; tr.classList.add("flash"); };
  const focusEd = (fid, rid) => { const e = $(`#${CSS.escape(rowId(fid))} [data-rule="${CSS.escape(rid)}"] input, #${CSS.escape(rowId(fid))} [data-rule="${CSS.escape(rid)}"] select`); e && e.focus(); };
  const title = b => ({ for: `for ${b.item} in ${b.path}`, until: `until ${b.path}`, if: `if ${b.path}`, else: "else", section: b.name, rollback: "rollback", finally: "finally" }[b.kind] || b.id);
  const target = x => !x ? el("span", { class: "when" }, "the flow ends") : c.flow.some(f => f.id === x) ? nodeRef(U, x, go(x)) : el("span", { class: "gid" }, x);
  const strip = el("nav", { class: "flowstrip", "aria-label": "Flow" });
  c.flow.forEach((f, i) => { if (i) strip.append(el("span", { class: "arrow" }, "›")); const a = nodeRef(U, f.id, go(f.id)); a.href = "#" + rowId(f.id); a.onclick = e => { e.preventDefault(); go(f.id)(); }; strip.append(a); });
  const rows = [], drawn = new Set();
  const row = f => {
    const leads = el("div", { class: "links" });
    if (f.kind !== "end") leads.append(el("div", { class: "lk pass" }, el("span", { class: "sym" }, "→"), el("span", {}, target(f.next))));
    if (f.back) leads.append(el("div", { class: "lk pass" }, el("span", { class: "sym" }, "↺"), el("span", {}, "retry: ", nodeRef(U, f.back, go(f.back)), el("span", { class: "when" }, ` — at most ${f.retry} times`))));
    for (const l of f.fail || []) leads.append(el("div", { class: "lk fail" }, el("span", { class: "sym" }, "✕"), el("span", {}, l.continue ? "continue (next item)" : nodeRef(U, l.to, go(l.to)), l.when ? el("span", { class: "when" }, " — ", chips(U, l.when, () => {})) : null)));
    if (f.kind === "end") leads.append(el("div", { class: "lk pass" }, el("span", { class: "sym" }, "■"), el("span", { class: "when" }, "the flow stops here")));
    const pick = rid => focusEd(f.id, rid);
    const txt = (key, label) => has(f, key) ? el("div", {}, label ? el("span", { class: "faint" }, label + ": ") : null, chips(U, f[key], pick)) : null;
    const eds = el("div", { class: "eds" }, (f.reads || []).map(rid => {
      const r = ruleOf(U, rid);
      return r ? el("div", { class: "ed" + (isChanged(U, rid) ? " changed" : ""), "data-rule": rid }, el("div", { class: "lab" }, r.label, el("span", { class: "rid" }, rid)), el("div", {}, editor(U, rid))) : null;
    }));
    if (!(f.reads || []).length) eds.append(el("span", { class: "none" }, "no rules"));
    const by = (f.by || []).join(", "), level = U.levels[f.id];
    const who = by ? "by " + by : { model: "decided by the model", human: "decided by a person", reason: "reason (" + (f.mode || "careful") + ")", step: f.lane === "model" ? "by the model" : "", end: "" }[f.kind] ?? "no code yet";
    const extra = [f.if && "only if " + f.if, f.options && "options: " + f.options.join(" | "), f.tools && "tools: " + f.tools.join(", "), f.budget != null && "budget " + f.budget, f.candidates != null && "candidates " + f.candidates, f.brief && "brief: " + f.brief.join(", "), f.out && "out " + f.out, f.timeout_text && "timeout " + f.timeout_text].filter(Boolean);
    return el("tr", { id: rowId(f.id), class: (f.reads || []).some(r => isChanged(U, r)) ? "changed" : "" },
      el("td", {}, el("div", {}, el("span", { class: "gid " + f.kind }, f.id), " ", el("span", { class: "kind" }, kindWord(f.kind))),
        f.name ? el("div", { class: "node-title" }, f.name) : null,
        el("div", { class: "code" }, who),
        level && by && f.kind !== "model" && f.kind !== "human" ? el("div", {}, el("span", { class: "st " + (level === "tested" ? "ok" : level === "none" ? "warn" : "") }, level)) : null,
        (f.notes || []).map(n => el("div", { class: "dim node-note" }, "note: ", chips(U, n.text, pick)))),
      el("td", {}, txt("do"), txt("check", f.kind === "human" ? "ask" : f.kind === "model" ? "decide" : "check"), extra.map(x => el("div", { class: "faint small-note" }, x))),
      el("td", {}, leads), el("td", {}, eds));
  };
  const walk = (ids, depth) => {
    for (const x of ids) {
      const f = c.flow.find(n => n.id === x);
      if (f) { rows.push(row(f)); drawn.add(x); continue; }
      const b = blocks[x];
      if (!b) continue;
      const opts = [b.tolerate != null && "tolerate " + b.tolerate + "%", b.retry != null && "retry " + b.retry, ...(b.fail || []).map(l => "fail → " + l.to)].filter(Boolean).join(" · ");
      rows.push(el("tr", { class: "blockrow" }, el("th", { colspan: 4, style: `padding-left:${8 + 16 * depth}px` }, (b.kind === "for" || b.kind === "until" ? "↻ " : b.kind === "section" ? "§ " : "▸ ") + title(b), opts ? el("span", { class: "faint" }, "  " + opts) : null)));
      walk(b.body, depth + 1);
    }
  };
  walk(c.body || c.flow.map(f => f.id), 0);
  for (const f of c.flow) if (!drawn.has(f.id)) rows.push(row(f));
  return el("div", {}, el("h3", {}, "Flow"), el("p", { class: "dim flow-intro" }, "The lines run in order. A gate that passes goes on to the next line; a fail goes to an end."), strip, el("div", { class: "tw" }, el("table", {},
    el("tr", {}, el("th", { class: "col-node" }, "Node"), el("th", { class: "col-do" }, "Do / check"), el("th", { class: "col-leads" }, "Leads to"), el("th", { class: "col-vals" }, "Values")), rows)));
}
function rulesTable(U) {
  const c = cat(U), readers = {};
  for (const f of c.flow || []) for (const rid of f.reads || []) (readers[rid] ||= []).push(f.id);
  for (const b of c.blocks || []) for (const rid of b.reads || []) (readers[rid] ||= []).push(b.id);
  if (c.queue) for (const rid of c.queue.reads || []) (readers[rid] ||= []).push("queue");
  let group = null;
  const rows = [];
  for (const r of c.rules) {
    if (r.group !== group) { group = r.group; rows.push(el("tr", {}, el("th", { colspan: 4, class: "group-th" }, group))); }
    const lim = [r.type === "tuple" && r.length != null && "tuple[" + r.length + "]", r.type === "dict" && "dict", r.type === "list" && "list", has(r, "min") && "min " + r.min, has(r, "max") && "max " + r.max, has(r, "options") && "options: " + r.options.join(", ")].filter(Boolean).join(" · ");
    rows.push(el("tr", { class: isChanged(U, r.id) ? "changed" : "" },
      el("td", { class: "col-rule" }, el("b", {}, r.label), r.ui ? el("span", { class: "st ui-tag" }, "ui: " + r.ui) : null, el("div", { class: "code" }, r.id),
        r.note ? el("div", { class: "dim small-note" }, r.note) : null, r.evidence ? el("div", { class: "faint small-note" }, "evidence: " + r.evidence) : null),
      el("td", {}, editor(U, r.id)), el("td", { class: "dim" }, lim || "—"),
      el("td", { class: "mono" }, (readers[r.id] || []).join(", ") || el("span", { class: "unused-lbl" }, "unused"))));
  }
  return el("div", {}, el("h3", {}, "Rules"), el("div", { class: "tw" }, el("table", {}, el("tr", {}, el("th", {}, "rule"), el("th", {}, "value"), el("th", {}, "limits"), el("th", {}, "read by")), rows)));
}

// - Skill and JSON tabs --------------------------------
function download(name, text, type) {
  const a = el("a", { href: URL.createObjectURL(new Blob([text], { type })), download: name });
  document.body.append(a); a.click(); a.remove();
}
function copyBtn(text) {
  return el("button", { onclick: async e => { try { await navigator.clipboard.writeText(text); e.target.textContent = "Copied"; } catch (x) { msg("Copy is blocked here: select the text instead.", false); } } }, "Copy");
}
function skillView() {
  const U = curUnit();
  if (!U || !U.skill) return el("div", { class: "card" }, "The skill is compiled by rig.py: open the file with rig.py serve.");
  const text = S.skillRef ? U.skill_ref : U.skill;
  const ref = el("input", { type: "checkbox" }); ref.checked = S.skillRef;
  ref.onchange = () => { S.skillRef = ref.checked; store.set("skillRef", ref.checked ? "1" : "0"); render(); };
  return el("div", { class: "card" },
    el("h2", {}, "Skill", el("span", { class: "scope" }, U.name)),
    el("p", { class: "dim sublead" }, "The unit as instructions for an agent (", el("code", {}, "rig.py compile skill"), "). Save it as ", el("code", {}, "SKILL.md"), " or paste it into a system prompt."),
    el("div", { class: "tool" }, el("label", {}, ref, " read the values from ", el("code", {}, U.name + ".json")), el("span", { class: "spacer" }), copyBtn(text),
      el("button", { onclick: () => download(U.name + ".SKILL.md", text, "text/markdown") }, "Download")),
    el("pre", { class: "out" }, text));
}
function jsonView() {
  const U = curUnit();
  if (!U || !cat(U)) return el("div", { class: "card" }, "No unit.");
  const text = JSON.stringify(cat(U), null, 1) + "\n";
  return el("div", {}, el("div", { class: "card" },
    el("h2", {}, "Catalogue", el("span", { class: "scope" }, U.name)),
    el("p", { class: "dim sublead" }, "The unit as JSON for a code runner (", el("code", {}, "rig.py compile json"), "): rules, presets and flow."),
    el("div", { class: "tool" }, el("span", { class: "spacer" }), copyBtn(text), el("button", { onclick: () => download(U.name + ".json", text, "application/json") }, "Download")),
    el("pre", { class: "out" }, text)));
}

// - Graph tab: the flow in three lanes, with the blocks as boxes ---
let G = { U: null, c: null, nodes: [], edges: [], boxes: [], byId: {}, pos: {} };
const LANES = [["code", "code"], ["model", "the model"], ["person", "a person"]];
const posKey = () => "pos2." + S.B.file + "." + S.unit;
const kindWord = k => (k === "step" || k === "reason" || k === "end") ? k : k + " gate";
function blockTitle(b) {
  return { for: `for ${b.item} in ${b.path}`, until: `until ${b.path}`, if: `if ${b.path}`, else: "else", section: b.name || "section", rollback: "rollback", finally: "finally" }[b.kind] || b.id;
}
function buildGraph(U) {
  const c = cat(U), byId = Object.fromEntries(c.flow.map(f => [f.id, f])), blocks = Object.fromEntries((c.blocks || []).map(b => [b.id, b]));
  const nodes = [], edges = [], order = [], ends = [], depthOf = {};
  const walk = (ids, depth) => {
    for (const x of ids) {
      if (byId[x]) { (byId[x].kind === "end" ? ends : order).push(x); depthOf[x] = depth; }
      else if (blocks[x]) walk(blocks[x].body, depth + 1);
    }
  };
  walk(c.body || [], 0);
  for (const f of c.flow) if (!order.includes(f.id) && !ends.includes(f.id)) (f.kind === "end" ? ends : order).push(f.id);
  order.forEach((id, i) => nodes.push({ id, type: "flow", f: byId[id], col: i }));
  ends.forEach((id, i) => nodes.push({ id, type: "term", f: byId[id], col: order.length, row: i }));
  const entry = x => {
    if (!x) return [];
    if (byId[x]) return [x];
    const b = blocks[x];
    if (!b) return [];
    if (b.kind === "if") return [...new Set([...entry(b.first), ...entry(b.else)])];
    return entry(b.first);
  };
  const inside = (id, bid) => { for (let f = byId[id]; f && f.block;) { if (f.block === bid) return true; const b = blocks[f.block]; f = b ? { block: b.block } : null; } return false; };
  for (const f of c.flow) {
    if (f.kind === "end") continue;
    let nxt = f.next;
    const loop = nxt && blocks[nxt] && (blocks[nxt].kind === "for" || blocks[nxt].kind === "until") && inside(f.id, nxt);
    if (loop) nxt = blocks[nxt].next;
    if (f.if) for (const t of entry(f.next)) edges.push({ from: f.id + ":o:skip", to: t + ":in", cls: "pass skip", src: f.id, dst: t, label: "if not " + f.if });
    entry(nxt).forEach(t => edges.push({ from: f.id + ":o:p", to: t + ":in", cls: "pass" + (loop ? " out" : ""), src: f.id, dst: t, label: loop ? "after the last item" : "" }));
    (f.fail || []).forEach((l, i) => {
      if (l.continue) edges.push({ from: f.id + ":o:f" + i, to: "B:" + l.to, cls: "fail cont", src: f.id, dst: l.to, label: l.when ? "continue: " + l.when : "continue" });
      else entry(l.to).forEach(t => edges.push({ from: f.id + ":o:f" + i, to: t + ":in", cls: "fail", src: f.id, dst: t, label: l.when }));
    });
    if (f.back) edges.push({ from: f.id + ":o:r", to: f.back + ":in", cls: "retry back", src: f.id, dst: f.back, label: "retry " + f.retry });
    for (const rid of f.reads || []) { const r = c.rules.find(x => x.id === rid); if (r) edges.push({ from: "R:" + rid, to: f.id + ":p:" + rid, cls: "param", src: "P:" + r.group, dst: f.id, rule: rid }); }
  }
  for (const b of c.blocks || []) {
    if (b.kind !== "for" && b.kind !== "until") continue;
    (b.fail || []).forEach(l => entry(l.to).forEach(t => edges.push({ from: "B:" + b.id, to: t + ":in", cls: "fail", src: b.id, dst: t, label: b.kind === "for" ? "more than " + b.tolerate + "% left" : "still not " + b.path })));
  }
  const starts = entry(c.start);
  for (const gr of [...new Set(c.rules.map(r => r.group))]) nodes.push({ id: "P:" + gr, type: "params", group: gr, rules: c.rules.filter(r => r.group === gr) });
  const boxes = (c.blocks || []).map(b => {
    const ids = [], add = x => { if (byId[x]) ids.push(x); else if (blocks[x]) blocks[x].body.forEach(add); };
    b.body.forEach(add);
    let inner = 0; const deep = (x, d) => { const bb = blocks[x]; if (!bb) return; inner = Math.max(inner, d); bb.body.forEach(y => deep(y, d + 1)); };
    b.body.forEach(x => deep(x, 1));
    return { b, ids, inner };
  }).filter(x => x.ids.length);
  G = { U, c, nodes, edges, boxes, byId, blocks, starts, depthOf, ends: ends.length, cols: order.length, pos: G.pos };
}
function port(cls, key) { return el("span", { class: "port " + cls, "data-port": key }); }
const fmt = rid => shown(G.U, rid);
const fill = t => fillText(G.U, t);
function byLineOf(f) {
  if ((f.by || []).length) return "by " + f.by.join(", ");
  return { model: "decided by the model: a guess", human: "decided by a person", reason: "reason (" + (f.mode || "careful") + ")", step: f.lane === "model" ? "done by the model" : "", end: "" }[f.kind] ?? "no code yet";
}
function nodeEl(n) {
  const drag = { onpointerdown: e => startDrag(e, n) };
  const U = G.U;
  if (n.type === "term") return el("div", { class: "node term", "data-node": n.id, onclick: () => select(n.id) },
    el("div", { class: "hd", ...drag }, port("in flow f-fail", n.id + ":in"), el("span", { class: "t" }, n.f.name || n.id, " ", el("span", { class: "n" }, "■ " + n.id))));
  if (n.type === "params") {
    const used = new Set([...G.c.flow.flatMap(f => f.reads || []), ...(G.c.blocks || []).flatMap(b => b.reads || []), ...((G.c.queue && G.c.queue.reads) || [])]);
    return el("div", { class: "node params", "data-node": n.id },
      el("div", { class: "hd", ...drag }, el("span", { class: "t" }, n.group), el("span", { class: "kind" }, "rules")),
      n.rules.map(r => el("div", { class: "row" + (used.has(r.id) ? "" : " unused") + (isChanged(U, r.id) ? " changed" : ""), "data-rule": r.id,
          title: r.note || "", onpointerenter: () => hover({ rule: r.id }), onpointerleave: () => hover(null) },
        el("span", { class: "lab" }, el("span", { class: "l" }, r.label), el("span", { class: "rid" }, r.id)),
        el("span", { class: "ctl" }, editor(U, r.id)),
        used.has(r.id) ? port("out p-out", "R:" + r.id) : null)),
      el("div", { class: "foot" }));
  }
  const f = n.f, k = f.kind, txt = f.check || f.do;
  const tags = [f.if ? "if " + f.if : null, f.mode ? "mode " + f.mode : null, f.tools ? "tools " + f.tools.length : null, f.budget != null ? "budget " + f.budget : null, f.candidates != null ? "candidates " + f.candidates : null, f.brief ? "brief " + f.brief.join(" ") : null, f.options ? "options: " + f.options.join(" | ") : null, f.out ? "out " + f.out : null,
    f.retry != null ? "retry " + (typeof f.retry === "string" ? fmt(f.retry) : f.retry) : null, f.timeout_text ? "timeout " + f.timeout_text : null].filter(Boolean);
  return el("div", { class: "node " + k + (G.starts.includes(f.id) ? " start" : ""), "data-node": n.id, onclick: e => { if (!e.target.closest("input,select")) select(n.id); } },
    el("div", { class: "hd", ...drag }, port("in flow", f.id + ":in"), el("span", { class: "gid " + k }, f.id), el("span", { class: "t", title: f.name || "" }, f.name || ""), el("span", { class: "kind" }, k)),
    byLineOf(f) ? el("div", { class: "by" }, byLineOf(f)) : null,
    txt ? el("div", { class: "txt", title: fill(txt) }, fill(txt)) : null,
    tags.length ? el("div", { class: "tags" }, tags.map(t => el("span", {}, t))) : null,
    (f.reads || []).length ? el("div", { class: "sec" }, "inputs") : null,
    (f.reads || []).map(rid => el("div", { class: "row" + (isChanged(U, rid) ? " changed" : ""), "data-rule": rid, onpointerenter: () => hover({ rule: rid }), onpointerleave: () => hover(null) },
      port("in p-in", f.id + ":p:" + rid), el("span", { class: "rid" }, rid), el("span", { class: "v" }, fmt(rid)))),
    el("div", { class: "sec sec-out" }, "outputs"),
    el("div", { class: "row out pass" }, el("span", { class: "when" }, f.next ? "next" : "the flow ends"), el("span", { class: "sym" }, "✓"), port("out flow", f.id + ":o:p")),
    f.if ? el("div", { class: "row out pass" }, el("span", { class: "when" }, "skipped"), el("span", { class: "sym" }, "↷"), port("out flow", f.id + ":o:skip")) : null,
    f.back ? el("div", { class: "row out retry" }, el("span", { class: "when" }, "retry"), el("span", { class: "sym" }, "↺"), port("out flow f-retry", f.id + ":o:r")) : null,
    (f.fail || []).map((l, i) => el("div", { class: "row out fail" }, el("span", { class: "when" }, l.when ? fill(l.when) : (l.continue ? "continue" : "→ " + l.to)), el("span", { class: "sym" }, "✕"), port("out flow f-fail", f.id + ":o:f" + i))),
    el("div", { class: "foot" }));
}
function renderGraph() {
  const U = curUnit(), c = cat(U);
  const world = $("#world");
  $$("#world .node, #world .box, #world .lane").forEach(e => e.remove());
  $("#wires").replaceChildren();
  if (!c || !c.flow.length) {
    document.body.classList.remove("tab-graph");
    $("#page").append(el("main", {}, el("div", { class: "card" }, el("p", {}, "This unit has no flow. The graph shows the steps, gates, ends and rules of agent units."),
      units().filter(x => x.flow).map(x => el("button", { class: "btn-unit", onclick: () => { S.unit = x.name; render(); } }, x.name)))));
    $("#gbar").hidden = true;
    return;
  }
  const cv = c.coverage || { gates: 0, tested: 0, code: 0, model: 0, human: 0, none: 0 };
  $("#cov").replaceChildren(el("b", {}, U.name), " · ", ...(cv.gates ? [el("b", {}, Math.round(100 * cv.tested / cv.gates) + "%"), ` coverage · ${cv.tested} of ${cv.gates} gates by tested code` + (cv.code ? `, ${cv.code} by code with no test` : "") + (cv.model ? `, ${cv.model} by the model` : "") + (cv.human ? `, ${cv.human} by a person` : "") + (cv.none ? `, ${cv.none} with no code` : "")] : ["no gates"]));
  if (!G.U || G.U.name !== U.name || G.name !== S.B.file) { try { G.pos = JSON.parse(store.get(posKey()) || "{}") || {}; } catch (e) { G.pos = {}; } }
  buildGraph(U); G.name = S.B.file;
  if (S.sel && !G.nodes.some(n => n.id === S.sel)) S.sel = null;
  for (const n of G.nodes) { n.el = nodeEl(n); world.append(n.el); }
  layout();
  for (const n of G.nodes) place(n);
  drawLanes(); drawBoxes();
  const first = !S.view;
  if (first) S.view = { x: 40, y: 40, k: 0.7 };
  applyView();
  requestAnimationFrame(() => { if (first) fit(); drawWires(); inspector(); });
}
function layout() {
  const colW = cssNum("--graph-col", 300), gapW = cssNum("--graph-gap", 70), lanePad = cssNum("--graph-lane-pad", 26);
  const flows = G.nodes.filter(n => n.type === "flow"), laneH = {}, top = {};
  for (const [lane] of LANES) laneH[lane] = 120;
  for (const n of flows) laneH[n.f.lane] = Math.max(laneH[n.f.lane], n.el.offsetHeight + 2 * lanePad);
  const maxInner = Math.max(0, ...G.boxes.map(x => x.inner)), head = 46 + 26 * maxInner;
  let y = 0;
  for (const [lane] of LANES) { top[lane] = y; y += laneH[lane]; }
  G.lanes = { top, h: laneH, bottom: y, head, colW, gapW };
  const auto = {};
  for (const n of flows) auto[n.id] = { x: n.col * colW, y: top[n.f.lane] + lanePad };
  let ey = 0;
  for (const n of G.nodes.filter(n => n.type === "term")) { auto[n.id] = { x: n.col * colW + gapW, y: ey + lanePad }; ey += n.el.offsetHeight + 18; }
  const above = {};
  for (const n of G.nodes.filter(n => n.type === "params")) {
    const cols = G.edges.filter(e => e.src === n.id).map(e => (G.nodes.find(m => m.id === e.dst) || {}).col).filter(x => x != null);
    const col = cols.length ? Math.min(...cols) : 0;
    const h = (above[col] || 0) + n.el.offsetHeight + 24;
    above[col] = h; auto[n.id] = { x: col * colW, y: -head - h };
  }
  for (const n of G.nodes) n.auto = auto[n.id] || { x: 0, y: 0 };
}
function place(n) { const p = G.pos[n.id] || n.auto; n.x = p.x; n.y = p.y; n.el.style.transform = `translate(${n.x}px,${n.y}px)`; }
function drawLanes() {
  $$("#world .lane").forEach(e => e.remove());
  const L = G.lanes, width = (G.cols + 1) * L.colW + L.gapW + 40;
  for (const [lane, who] of LANES) {
    $("#world").prepend(el("div", { class: "lane lane-" + lane, style: `transform:translate(-160px,${L.top[lane]}px);width:${width + 160}px;height:${L.h[lane]}px` },
      el("span", { class: "lane-l" }, who)));
  }
}
function drawBoxes() {
  $$("#world .box").forEach(e => e.remove());
  const L = G.lanes, world = $("#world");
  const sorted = [...G.boxes].sort((a, b) => b.inner - a.inner);
  for (const { b, ids, inner } of sorted.reverse()) {
    const ns = ids.map(id => G.nodes.find(n => n.id === id)).filter(Boolean);
    if (!ns.length) continue;
    const pad = 16 + 14 * inner;
    const x0 = Math.min(...ns.map(n => n.x)) - pad, x1 = Math.max(...ns.map(n => n.x + n.el.offsetWidth)) + pad;
    const y0 = Math.min(-26 - 26 * inner, ...ns.map(n => n.y - 30 - 26 * inner)), y1 = Math.max(L.bottom + 8 + 12 * inner, ...ns.map(n => n.y + n.el.offsetHeight + pad));
    const tags = [b.tolerate != null ? "tolerate " + b.tolerate + "%" : null, b.retry != null ? "retry " + b.retry : null].filter(Boolean).join(" · ");
    const box = el("div", { class: "box box-" + b.kind, "data-box": b.id, title: b.id, style: `transform:translate(${x0}px,${y0}px);width:${x1 - x0}px;height:${y1 - y0}px`, onclick: e => { if (e.target === box || e.target.closest(".box-l")) select(b.id); } },
      el("span", { class: "box-l" }, el("b", {}, b.kind === "section" ? "§ " : b.kind === "for" || b.kind === "until" ? "↻ " : ""), blockTitle(b), tags ? el("span", { class: "box-t" }, " · " + tags) : null),
      port("out flow f-fail box-port", "B:" + b.id));
    world.prepend(box);
  }
  for (const e of $$("#world .lane")) world.prepend(e);
}
function portXY(key) {
  const p = document.querySelector(`[data-port="${CSS.escape(key)}"]`);
  if (!p) return null;
  const r = p.getBoundingClientRect(), w = $("#world").getBoundingClientRect();
  return { x: (r.left + r.width / 2 - w.left) / S.view.k, y: (r.top + r.height / 2 - w.top) / S.view.k };
}
function curve(a, b, back) {
  const dx = Math.max(60, Math.abs(b.x - a.x) * 0.45);
  if (back) { const lift = Math.min(a.y, b.y) - 90 - Math.abs(a.x - b.x) * 0.05; return `M${a.x},${a.y} C${a.x + 90},${a.y} ${a.x + 90},${lift} ${(a.x + b.x) / 2},${lift} S${b.x - 90},${b.y} ${b.x},${b.y}`; }
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
}
function drawWires() {
  const svg = $("#wires"); svg.replaceChildren();
  for (const e of G.edges) {
    const a = portXY(e.from), b = portXY(e.to);
    if (!a || !b) { e.path = null; continue; }
    e.path = document.createElementNS(NS, "path");
    e.path.setAttribute("d", curve(a, b, e.cls.includes("back") || b.x < a.x - 10));
    e.path.setAttribute("class", "w " + e.cls);
    svg.append(e.path);
    if (e.cls !== "param" && e.label) {
      const t = document.createElementNS(NS, "text"), L = e.path.getTotalLength(), m = e.path.getPointAtLength(L / 2);
      t.setAttribute("x", m.x); t.setAttribute("y", m.y - 6); t.setAttribute("text-anchor", "middle"); t.setAttribute("class", "wl");
      const lab = fill(e.label); t.textContent = lab.length > 42 ? lab.slice(0, 40) + "…" : lab;
      e.text = t; svg.append(t);
    } else e.text = null;
  }
  applyFocus();
}
let hov = null;
let TRACE = null;
function traceEdges() {
  const t = (TRACE.trace || []).filter(x => G.byId[x.node] && !x.skipped), out = new Set();
  t.forEach((a, i) => {
    const b = t[i + 1] ? t[i + 1].node : (TRACE.outcome ? null : TRACE.at);
    if (!b) return;
    const flow = G.edges.filter(e => e.cls !== "param" && e.src === a.node && e.dst === b);
    const same = flow.filter(e => a.retry ? e.cls.includes("retry") : e.cls.startsWith(a.pass === false ? "fail" : "pass"));
    const e = same.find(e => a.when && e.label === a.when) || same[0] || flow[0];
    if (e) out.add(e);
  });
  return out;
}
function applyTrace(on) {
  document.body.classList.toggle("tracing", on);
  for (const n of G.nodes) if (n.el) { n.el.classList.remove("tr", "tr-fail", "tr-wait"); n.el.removeAttribute("data-trace"); }
  for (const e of G.edges) { e.path && e.path.classList.remove("tr"); e.text && e.text.classList.remove("tr"); }
  if (!TRACE) return;
  const seen = {};
  (TRACE.trace || []).forEach((t, i) => { if (!t.skipped) (seen[t.node] = seen[t.node] || []).push(i + 1); });
  for (const n of G.nodes) {
    if (!n.el || !seen[n.id]) continue;
    n.el.classList.add("tr");
    n.el.setAttribute("data-trace", seen[n.id].length > 3 ? seen[n.id].length + "×" : seen[n.id].join(" · "));
    if ((TRACE.trace || []).some(t => t.node === n.id && t.pass === false)) n.el.classList.add("tr-fail");
  }
  if (!TRACE.outcome) { const n = G.nodes.find(n => n.id === TRACE.at); if (n && n.el) n.el.classList.add("tr", "tr-wait"); }
  for (const e of traceEdges()) { e.path && e.path.classList.add("tr"); e.text && e.text.classList.add("tr"); }
}
function traceInfo(f) {
  const T = TRACE, j = v => JSON.stringify(v);
  if (!f) {
    const state = T.outcome ? "ended at " + (T.outcome.end || T.outcome.label) + (T.outcome.end === "error" && T.error ? ": " + T.error.error : "") : "waits at " + T.at;
    return el("div", {}, el("div", { class: "k" }, "Run " + T.id), el("p", {}, state),
      el("p", { class: "hint" }, "inputs: " + j(T.inputs)),
      T.from ? el("p", { class: "hint" }, `a rerun of ${T.from.run}, from ${T.from.from}`) : null,
      (T.problems || []).length ? [el("div", { class: "k" }, "Problems"), T.problems.map(x => el("p", { class: "hint" }, x))] : null,
      (T.left || []).length ? [el("div", { class: "k" }, "Items left (continue)"), T.left.map(x => el("p", { class: "hint" }, `${x.block} item ${x.item}: ${x.gate}, ${x.why}`))] : null,
      (T.guessed || []).length ? el("p", { class: "hint" }, "Guessed by the model: " + T.guessed.join(", ")) : null,
      el("p", { class: "hint" }, "The numbers on the nodes are the order of the path. Click a node to see what happened there."));
  }
  const rows = (T.trace || []).map((t, i) => [t, i + 1]).filter(([t]) => t.node === f.id);
  if (!rows.length) return el("div", {}, el("div", { class: "k" }, "In run " + T.id), el("p", { class: "hint" }, !T.outcome && T.at === f.id ? "The run waits here." : "The run did not come here."));
  return el("div", {}, el("div", { class: "k" }, "In run " + T.id), rows.slice(0, 40).map(([t, n]) => el("div", { class: "trow" },
    el("b", {}, "#" + n + " "), t.skipped ? "skipped (if)" : t.kind === "step" || t.kind === "end" || t.kind === "for" || t.kind === "until" ? t.kind + (t.item != null ? " item " + t.item : "") : el("span", { class: t.pass ? "ok" : "no" }, t.pass ? "pass" : "fail"),
    t.by ? " · by the " + t.by : "", t.guessed ? " · a guess" : "", t.retry ? " · retry " + t.retry : "", t.timeout ? " · timeout" : "", t.error ? el("div", { class: "no" }, t.error) : null,
    t.when ? el("div", {}, "→ " + t.when) : null, t.why ? el("div", {}, "why: " + t.why) : null,
    (t.problems || []).map(x => el("div", { class: "no" }, x)), t.facts ? el("div", { class: "dim" }, j(t.facts)) : null)));
}
async function loadRuns() {
  const sel = $("#run");
  try {
    const r = await fetch("/runs", { cache: "no-store" });
    const runs = r.ok ? await r.json() : [];
    sel.hidden = !runs.length;
    const keep = sel.value;
    sel.replaceChildren(el("option", { value: "" }, "run…"), ...runs.map(x => el("option", { value: x.id }, x.id + " · " + x.state)));
    sel.value = runs.some(x => x.id === keep) ? keep : "";
  } catch (e) { sel.hidden = true; }
}
async function pickRun(id) {
  TRACE = null;
  if (id) { try { const r = await fetch("/runs/" + encodeURIComponent(id), { cache: "no-store" }); if (r.ok) TRACE = await r.json(); } catch (e) { /* no run */ } }
  if (G.U) { inspector(); applyFocus(); }
}
function hover(h) { hov = h; applyFocus(); }
function applyFocus() {
  const f = hov || (S.sel ? { node: S.sel } : null);
  document.body.classList.toggle("focus", !!f);
  applyTrace(!!TRACE && !f);
  for (const n of G.nodes) n.el && n.el.classList.remove("on", "sel");
  for (const e of G.edges) { e.path && e.path.classList.remove("on"); e.text && e.text.classList.remove("on"); }
  if (S.sel) { const n = G.nodes.find(n => n.id === S.sel); n && n.el.classList.add("sel"); }
  if (!f) return;
  const lit = new Set();
  for (const e of G.edges) {
    const on = f.rule ? e.rule === f.rule : (e.src === f.node || e.dst === f.node);
    if (!on) continue;
    e.path && e.path.classList.add("on"); e.text && e.text.classList.add("on");
    lit.add(e.src); lit.add(e.dst);
  }
  if (f.node) lit.add(f.node);
  if (f.rule) { const r = G.c.rules.find(x => x.id === f.rule); r && lit.add("P:" + r.group); }
  for (const n of G.nodes) if (lit.has(n.id)) n.el.classList.add("on");
}
function svgLegend(color, dash) {
  const s = document.createElementNS(NS, "svg"); s.setAttribute("width", 28); s.setAttribute("height", 10);
  const l = document.createElementNS(NS, "line"); l.setAttribute("x1", 1); l.setAttribute("x2", 27); l.setAttribute("y1", 5); l.setAttribute("y2", 5);
  l.setAttribute("stroke", color); l.setAttribute("stroke-width", 2); if (dash) l.setAttribute("stroke-dasharray", dash); s.append(l); return s;
}
function inspector() {
  const a = $("#insp"), U = G.U, f = S.sel && G.byId[S.sel], b = S.sel && G.blocks[S.sel];
  const pickRule = rid => { const r = G.c.rules.find(x => x.id === rid); if (r) goTo("P:" + r.group, rid); };
  pickRule.hover = rid => hover(rid ? { rule: rid } : null);
  const link = id => el("a", { class: "insp-link", onclick: () => { select(id); goTo(id); } }, el("span", { class: "gid " + (G.byId[id] ? G.byId[id].kind : "") }, id), " ", G.byId[id] ? G.byId[id].name || "" : "");
  const sec = (title, body) => body ? [el("div", { class: "k" }, title), el("p", {}, body)] : null;
  if (b) {
    a.replaceChildren(el("div", {}, el("div", {}, el("span", { class: "gid" }, b.kind), " ", el("span", { class: "kind" }, "block")),
      el("h2", {}, blockTitle(b)),
      el("p", { class: "hint" }, { for: `The lines of this box run once for each item of ${b.path}. The item is ${b.item}. The runner saves the run after each item.`,
        until: `The lines of this box run, then again until ${b.path} is true: at most ${b.retry} more times.`,
        if: `The lines of this box run only when ${b.path} is not empty and not false.`, else: "The lines of this box run when the if before did not.",
        section: "A heading: it has no effect on a run.", rollback: "The lines of this box run on hard fail, error, unattended deferral, or explicit restore.", finally: "The lines of this box run after the run ends, also after an error." }[b.kind]),
      b.tolerate != null ? sec("Tolerate", `more than ${b.tolerate}% of the items left: the block fails`) : null,
      (b.fail || []).length ? [el("div", { class: "k" }, "Fail"), b.fail.map(l => el("div", { class: "lk fail" }, el("span", { class: "sym" }, "✕"), link(l.to), l.when ? el("span", { class: "when" }, fill(l.when)) : null))] : null,
      el("div", { class: "k" }, "Lines"), b.body.map(x => el("div", { class: "lk" }, G.byId[x] ? link(x) : el("span", { class: "gid" }, x)))));
    return;
  }
  if (!f) {
    a.replaceChildren(el("h2", {}, U.name), el("p", { class: "dim" }, chips(U, G.c.intent || "", pickRule)),
      el("div", { class: "legend" }, svgLegend("var(--pass)", ""), "next line", svgLegend("var(--fail)", "6 5"), "fail: to an end, or continue", svgLegend("var(--accent)", "2 5"), "retry: the step again", svgLegend("var(--wire-p)", ""), "rule → node input"),
      el("div", { class: "k" }, "Lanes"),
      el("p", { class: "hint" }, "Each node stands in the lane of who decides it: code, the model, or a person. The columns are the order of the lines. The ends stand at the right."),
      el("div", { class: "k" }, "Boxes"),
      el("p", { class: "hint" }, "A box is a block: ↻ for and until run their lines again; if and else choose; § a section is a heading; finally runs after the end. Click the title of a box to read it."),
      el("div", { class: "k" }, "Kinds"),
      el("p", { class: "hint" }, el("span", { class: "gid hard" }, "hard"), " code decides; a fail goes to an end. ", el("span", { class: "gid soft" }, "soft"), " code decides; a fail is reported. ", el("span", { class: "gid model" }, "model"), " the model decides; the result is a guess. ", el("span", { class: "gid human" }, "human"), " a person decides; the flow waits. ", el("span", { class: "gid" }, "step"), " work. ", el("span", { class: "gid end" }, "end"), " the flow stops."),
      el("div", { class: "k" }, "Use"),
      el("p", { class: "hint" }, "Click a node to read it here. Hover a rule to see where it goes. Change a value in a rule box; Save writes it into the file. Drag a node by its header, drag the background to pan, wheel to zoom. ", el("kbd", {}, "F"), " fits, ", el("kbd", {}, "Esc"), " clears."),
      el("div", { class: "k" }, "Wiring"),
      el("p", { class: "hint" }, "The wires are read-only: change the order of the lines in the .rig file."));
    if (TRACE) a.prepend(traceInfo(null));
    return;
  }
  const from = G.edges.filter(e => e.dst === f.id && e.cls !== "param").map(e => e.src).filter(id => G.byId[id]);
  const chain = []; for (let x = f.block; x && G.blocks[x]; x = G.blocks[x].block) chain.unshift(blockTitle(G.blocks[x]));
  a.replaceChildren(el("div", {},
    el("div", {}, el("span", { class: "gid " + f.kind }, f.id), " ", el("span", { class: "kind" }, kindWord(f.kind)), " · ", el("span", { class: "kind" }, f.kind === "end" ? "" : "lane: " + (f.lane === "person" ? "a person" : f.lane === "model" ? "the model" : "code"))),
    el("h2", {}, f.name || f.id),
    chain.length ? el("p", { class: "hint" }, "in: " + chain.join(" › ")) : null,
    byLineOf(f) ? el("p", { class: "code" }, byLineOf(f)) : null,
    sec("Only if", f.if && el("code", {}, f.if)), sec("Do", f.do && chips(U, f.do, pickRule)),
    sec(f.kind === "human" ? "Ask the person" : f.kind === "model" ? "The model decides" : "Check", f.check && chips(U, f.check, pickRule)),
    sec("Options (the first is the default)", f.options && f.options.join(" | ")), sec("The answer has the type", f.out && el("code", {}, f.out)),
    sec("Retry", f.back && `on fail, do ${f.back} again, at most ${typeof f.retry === "string" ? fmt(f.retry) + " times (" + f.retry + ")" : f.retry + " times"}`), sec("Timeout", f.timeout_text),
    (f.notes || []).length ? [el("div", { class: "k" }, "Notes"), f.notes.map(n => el("p", { class: "hint" }, chips(U, n.text, pickRule)))] : null,
    (f.sees || []).length ? [el("div", { class: "k" }, "Sees"), el("p", { class: "code" }, f.sees.join(", "))] : null,
    (f.reads || []).length ? [el("div", { class: "k" }, "Reads"), el("p", {}, f.reads.map(rid => [chips(U, "{" + rid + "}", pickRule), " "]))] : null,
    f.kind !== "end" ? el("div", { class: "k" }, "Leads to") : null,
    f.kind !== "end" ? el("div", { class: "lk pass" }, el("span", { class: "sym" }, "✓"), f.next ? (G.byId[f.next] ? link(f.next) : el("span", { class: "gid" }, f.next)) : "the flow ends") : null,
    (f.fail || []).map(l => el("div", { class: "lk fail" }, el("span", { class: "sym" }, "✕"), l.continue ? "continue: the next item of " + l.to : link(l.to), l.when ? el("span", { class: "when" }, fill(l.when)) : null)),
    f.kind === "end" ? el("p", { class: "hint" }, "The flow stops here." + (G.c.finally ? " Then the block finally runs." : "")) : null,
    from.length ? [el("div", { class: "k" }, "Reached from"), [...new Set(from)].map(id => el("div", { class: "lk" }, link(id)))] : null));
  if (TRACE) a.append(traceInfo(f));
}
function select(id) { S.sel = id; inspector(); applyFocus(); }
function applyView() {
  const v = S.view; $("#world").style.transform = `translate(${v.x}px,${v.y}px) scale(${v.k})`;
  const V = $("#view"); V.style.backgroundSize = `${22 * v.k}px ${22 * v.k}px`; V.style.backgroundPosition = `${v.x}px ${v.y}px`;
}
function fit() {
  if (!G.nodes.length) return;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of G.nodes) { if (!n.el || n.el.offsetParent === null) continue; x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x + n.el.offsetWidth); y1 = Math.max(y1, n.y + n.el.offsetHeight); }
  if (!isFinite(x0)) return;
  x0 -= 170; y1 = Math.max(y1, G.lanes ? G.lanes.bottom : y1) + 60;
  const r = $("#view").getBoundingClientRect(), pad = 30;
  const k = Math.min(1.2, Math.max(0.08, Math.min((r.width - 2 * pad) / (x1 - x0), (r.height - 2 * pad) / (y1 - y0))));
  S.view = { k, x: pad - x0 * k + ((r.width - 2 * pad) - (x1 - x0) * k) / 2, y: pad - y0 * k };
  applyView();
}
function savePos() { store.set(posKey(), JSON.stringify(G.pos)); }
function startDrag(e, n) {
  if (e.button !== 0 || e.target.closest("input,select,button")) return;
  e.stopPropagation(); e.preventDefault();
  const sx = e.clientX, sy = e.clientY, ox = n.x, oy = n.y; let moved = false;
  const mv = ev => { moved = true; G.pos[n.id] = { x: ox + (ev.clientX - sx) / S.view.k, y: oy + (ev.clientY - sy) / S.view.k }; place(n); drawBoxes(); drawWires(); };
  const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); if (moved) savePos(); else if (n.type !== "params") select(n.id); };
  addEventListener("pointermove", mv); addEventListener("pointerup", up);
}
function goTo(id, rule) {
  const n = G.nodes.find(n => n.id === id); if (!n) return;
  const r = $("#view").getBoundingClientRect();
  S.view.k = Math.max(S.view.k, 0.8);
  S.view.x = r.width / 2 - (n.x + n.el.offsetWidth / 2) * S.view.k; S.view.y = r.height / 3 - n.y * S.view.k; applyView();
  if (rule) { const row = n.el.querySelector(`.row[data-rule="${CSS.escape(rule)}"]`); const inp = row && row.querySelector("input,select"); inp && inp.focus(); }
}
(() => {
  const V = $("#view");
  V.addEventListener("pointerdown", e => {
    if (e.target.closest(".node") || e.button !== 0) return;
    const sx = e.clientX, sy = e.clientY, ox = S.view.x, oy = S.view.y; let moved = false;
    V.classList.add("panning");
    const mv = ev => { moved = moved || Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 3; S.view.x = ox + ev.clientX - sx; S.view.y = oy + ev.clientY - sy; applyView(); };
    const up = () => { V.classList.remove("panning"); removeEventListener("pointermove", mv); removeEventListener("pointerup", up); if (!moved) select(null); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  V.addEventListener("wheel", e => {
    e.preventDefault();
    const r = V.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, v = S.view;
    const k = Math.min(2, Math.max(0.1, v.k * Math.exp(-e.deltaY * 0.0015)));
    v.x = mx - (mx - v.x) * k / v.k; v.y = my - (my - v.y) * k / v.k; v.k = k; applyView();
  }, { passive: false });
})();

// - Events ---------------------------------------------
function readFile(file) {
  const fr = new FileReader();
  fr.onload = () => {
    try { const c = JSON.parse(String(fr.result)); if (!c.flow && !c.rules) throw new Error("not a catalogue"); load(fromCatalogue(c, file.name)); }
    catch (e) { msg(file.name + ": open a compiled catalogue (gen/<unit>.json). For a .rig file, run rig.py serve.", false); }
  };
  fr.readAsText(file);
}
$("#open").addEventListener("click", () => $("#file").click());
$("#file").addEventListener("change", e => { if (e.target.files[0]) readFile(e.target.files[0]); e.target.value = ""; });
$("#close").addEventListener("click", () => { if (S.dirty && !confirm("Close without saving your changes?")) return; S.B = null; S.served = false; render(); });
$("#save").addEventListener("click", async () => {
  if (!canEdit()) return;
  try {
    const res = await fetch("/file", { method: "POST", ...postBody() });
    const j = await res.json();
    if (!res.ok) { msg(j.error || "not saved", false); return; }
    S.B = j.bundle; S.text = j.bundle.text; S.sidecars = {}; S.dirty = false; S.changed = new Set(); render();
    msg(`Saved ${j.saved}` + (j.wrote && j.wrote.length ? `; compiled ${j.wrote.map(p => p.split(/[\\/]/).pop()).join(", ")}` : "") + ".");
  } catch (e) { msg("Not saved: " + e.message, false); }
});
$$(".tabs button").forEach(b => b.addEventListener("click", () => { S.tab = b.dataset.tab; store.set("tab", S.tab); render(); }));
$("#unit").addEventListener("change", e => { S.unit = e.target.value; S.sel = null; S.view = null; render(); });
$("#preset").addEventListener("change", e => { if (e.target.value && curUnit()) applyPreset(curUnit(), e.target.value); e.target.value = ""; });
$("#t-param").onchange = e => document.body.classList.toggle("no-param", !e.target.checked);
$("#t-fail").onchange = e => { document.body.classList.toggle("no-fail", !e.target.checked); drawWires(); };
$("#t-anim").onchange = e => document.body.classList.toggle("anim", e.target.checked);
$("#relayout").onclick = () => { G.pos = {}; savePos(); for (const n of G.nodes) place(n); drawBoxes(); drawWires(); fit(); };
$("#fit").onclick = fit;
$("#run").onchange = e => pickRun(e.target.value);
$("#run").onpointerdown = () => { loadRuns(); };
addEventListener("keydown", e => {
  if (S.tab !== "graph" || (e.target.closest && e.target.closest("input,select,textarea"))) return;
  if (e.key === "f" || e.key === "F") fit();
  if (e.key === "Escape") select(null);
});
document.addEventListener("dragover", e => { e.preventDefault(); document.body.classList.add("drag"); });
document.addEventListener("dragleave", e => { if (!e.relatedTarget) document.body.classList.remove("drag"); });
document.addEventListener("drop", e => { e.preventDefault(); document.body.classList.remove("drag"); const f = e.dataTransfer.files[0]; if (f) readFile(f); });
addEventListener("beforeunload", e => { if (S.dirty) { e.preventDefault(); e.returnValue = ""; } });
let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (S.tab === "graph" && S.B) drawWires(); }, 120); });

if (!["units", "graph", "skill", "json"].includes(S.tab)) S.tab = "units";
if (S.served) fetchBundle(); else if (params.get("src")) fetchCatalogue(params.get("src")); else render();
