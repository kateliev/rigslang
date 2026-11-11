#!/usr/bin/env python3
"""rig.py: reference tool for the Rig language, version 0. Standard library only.

    python rig.py check FILE...               validate; show the status of every unit
    python rig.py hash FILE                   print the matrix and body hashes of every unit
    python rig.py prove FILE [UNIT] [--stamp] run the examples and the `check py` lines
                                              against the py cast; --stamp writes the
                                              hashes and the date when all pass
    python rig.py stamp FILE UNIT LANG        write the hashes and today's date into a cast,
                                              ONLY after you proved it in its own runtime
    python rig.py json FILE                   the parsed tree as JSON
    python rig.py compile json FILE [UNIT]    the unit as a catalogue: rules, presets and flow,
                                              the JSON that a code runner reads
    python rig.py compile skill FILE [UNIT]   the unit as a SKILL.md for an agent that follows
                                              instructions; --rules PATH: refer to the values
                                              in that JSON file instead of writing them in
        compile options: --preset NAME (use the values of a preset), -o OUT (write a file)
    python rig.py from-json FILE.json         a catalogue back to Rig (the same meaning)
    python rig.py serve FILE [UNIT]           the viewer for FILE on 127.0.0.1; Save writes FILE
        [--port 8765] [--json OUT] [--skill OUT] [--rules-ref]
                                              and compiles it again to OUT; --rules-ref makes
                                              the skill read its values from the JSON

The language is defined in spec.md (same folder). `prove` runs the code of the file on
your machine: use it only on files you trust. On macOS use python3.
"""
import datetime
import hashlib
import json
import math
import re
import sys
import unicodedata

MATRIX = ('in', 'out', 'intent', 'example', 'ensure')
FLOW = ('step', 'gate', 'end')
GATE_KINDS = ('hard', 'soft', 'judge')
SCOPES = ('snippet', 'tool', 'agent')
CHILDREN = {
	'unit': {'in', 'out', 'intent', 'example', 'ensure', 'note', 'uses', 'rule', 'preset', 'cast', 'step', 'gate', 'end'},
	'ensure': {'check', 'note'},
	'preset': {'set'},
	'note': {'evidence'},
	'rule': {'min', 'max', 'options', 'unit', 'label', 'note'},
	'step': {'do', 'by', 'reads', 'next', 'note'},
	'gate': {'when', 'reads', 'ensure', 'by', 'brief', 'pass', 'fail', 'note'},
	'end': {'note'},
}
NUMBER = re.compile(r'^-?\d+(\.\d+)?$')
RULE_ID = re.compile(r'^[A-Za-z_][\w-]*(\.[\w-]+)+$')
PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
PROSE_NUMBER = re.compile(r'(?<![\w.#{-])\d+(?:\.\d+)?(?![\w}])')
PROSE = ('when', 'do', 'ensure', 'brief')


class RigError(Exception):
	def __init__(self, line, text):
		Exception.__init__(self, 'line {}: {}'.format(line, text))
		self.line = line


class Node(object):
	def __init__(self, head, args, line, indent):
		self.head, self.args, self.line, self.indent = head, args, line, indent
		self.children = []
		self.body = None  # raw lines, cast only

	def word(self, i, default=None):
		return self.args[i][1] if len(self.args) > i else default

	def kids(self, head):
		return [c for c in self.children if c.head == head]


# - Parsing ------------------------------------------
def tokenize(s, line):
	'''One line (without its indentation) -> a list of args: (kind, text) or ('list', [...]).'''
	out, stack, i, n = [], [], 0, len(s)
	while i < n:
		c = s[i]
		if c in ' \t':
			i += 1
			continue
		if c == ';':
			break
		if c == '"':
			j = i + 1
			while j < n and s[j] != '"':
				j += 2 if s[j] == '\\' else 1
			if j >= n:
				raise RigError(line, 'the string is not closed')
			out.append(('str', s[i:j + 1]))
			i = j + 1
			continue
		if c == '(':
			stack.append(out)
			out = []
			i += 1
			continue
		if c == ')':
			if not stack:
				raise RigError(line, 'a ")" without "("')
			inner, out = out, stack.pop()
			out.append(('list', inner))
			i += 1
			continue
		if c == '/':
			j = i + 1
			while j < n and s[j] != '/':
				j += 2 if s[j] == '\\' else 1
			if j < n and (j + 1 == n or s[j + 1] in ' \t)'):
				out.append(('re', s[i:j + 1]))
				i = j + 1
				continue
		j = i
		while j < n and s[j] not in ' \t();':
			j += 1
		w = s[i:j]
		out.append(('num' if NUMBER.match(w) else 'word', w))
		i = j
	if stack:
		raise RigError(line, 'a "(" is not closed')
	return out


def ser(arg):
	kind, v = arg
	return '(' + ' '.join(ser(a) for a in v) + ')' if kind == 'list' else v


def parse(text):
	'''Text -> the root node (head "file"). Raises RigError.'''
	lines = text.replace('\r\n', '\n').split('\n')
	root = Node('file', [], 0, -1)
	stack = [root]
	i = 0
	while i < len(lines):
		raw, line = lines[i], i + 1
		body = raw.lstrip(' \t')
		if not body.strip() or body.startswith(';'):
			i += 1
			continue
		lead = raw[:len(raw) - len(body)]
		if '\t' in lead:
			raise RigError(line, 'a tab in the indentation: indent with spaces')
		indent = len(lead)
		while stack[-1].indent >= indent:
			stack.pop()
		toks = tokenize(body, line)
		if not toks:
			i += 1
			continue
		if toks[0][0] != 'word':
			raise RigError(line, 'a line must start with a word')
		node = Node(toks[0][1], toks[1:], line, indent)
		stack[-1].children.append(node)
		i += 1
		if node.head == 'cast':
			cast = []
			while i < len(lines):
				r = lines[i]
				if r.strip() and len(r) - len(r.lstrip(' \t')) <= indent:
					break
				cast.append(r)
				i += 1
			while cast and not cast[-1].strip():
				cast.pop()
			node.body = cast
			continue
		stack.append(node)
	return root


# - Hashes -------------------------------------------
def h8(text):
	return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]


def canon(node, depth):
	return '  ' * depth + ' '.join([node.head] + [ser(a) for a in node.args])


def matrix_text(unit):
	out = []

	def walk(n, d):
		out.append(canon(n, d))
		for c in n.children:
			walk(c, d + 1)
	for c in unit.children:
		if c.head in MATRIX:
			walk(c, 0)
	return '\n'.join(out)


def body_text(lines):
	lines = [l.rstrip() for l in lines or []]
	while lines and not lines[0]:
		lines.pop(0)
	while lines and not lines[-1]:
		lines.pop()
	full = [l for l in lines if l]
	cut = min(len(l) - len(l.lstrip(' \t')) for l in full) if full else 0
	return '\n'.join(l[cut:] for l in lines)


def matrix_hash(unit):
	return '#' + h8(matrix_text(unit))


def body_hash(cast):
	return '#' + h8(body_text(cast.body))


def cast_info(cast):
	words = [ser(a) for a in cast.args]
	hashes = [w for w in words if w.startswith('#')]
	proved = words[words.index('proved') + 1] if 'proved' in words and words.index('proved') + 1 < len(words) else None
	return {'lang': words[0] if words else '?', 'matrix': hashes[0] if hashes else None,
			'body': hashes[1] if len(hashes) > 1 else None, 'proved': proved}


# - Status and check ---------------------------------
def units(root):
	return [u for u in root.children if u.head == 'unit']


def unit_status(unit):
	'''A short list of status strings for one unit.'''
	out = []
	m = matrix_hash(unit)
	for c in unit.kids('cast'):
		info = cast_info(c)
		if not info['matrix']:
			out.append('unproved {} (no hashes yet)'.format(info['lang']))
		elif info['matrix'] != m:
			out.append('remelted {} (the matrix changed)'.format(info['lang']))
		elif info['body'] != body_hash(c):
			out.append('stale {} (the code changed: prove it again)'.format(info['lang']))
		else:
			out.append('proved {}{}'.format(info['lang'], ' ' + info['proved'] if info['proved'] else ''))
	gates = unit.kids('gate')
	if gates:
		code = [g for g in gates if g.word(1) in ('hard', 'soft') and g.kids('by')]
		judge = [g for g in gates if g.word(1) == 'judge']
		out.append('flow: {} gates, coverage {:.0%} ({} by code, {} judge)'.format(len(gates), float(len(code)) / len(gates), len(code), len(judge)))
	elif unit.kids('step'):
		out.append('flow: {} steps, no gates'.format(len(unit.kids('step'))))
	if not unit.kids('cast') and any(c.head in MATRIX for c in unit.children) and not (gates or unit.kids('step')):
		out.append('hole')
	return out or ['empty']


# - Rules, placeholders, presets --------------------
def walk_strings(n, skip=('check', 'example', 'cast')):
	'''Every string argument of n and its descendants -> list of (node, text).'''
	out = []

	def args(node, aa):
		for a in aa:
			if a[0] == 'str':
				out.append((node, value(a)))
			elif a[0] == 'list':
				args(node, a[1])

	def walk(node):
		if node.head in skip:
			return
		args(node, node.args)
		for c in node.children:
			walk(c)
	walk(n)
	return out


def placeholders(n):
	'''The rule ids named as {group.name} in the strings of n, in order, without repeats.'''
	out = []
	for _, t in walk_strings(n):
		for m in PLACE.finditer(t):
			if m.group(1) not in out:
				out.append(m.group(1))
	return out


def node_reads(f):
	'''The rules that a step or gate reads: its "reads" lines and the rules named in its strings.'''
	out = []
	for c in f.kids('reads'):
		for a in c.args:
			if a[1] not in out:
				out.append(a[1])
	for rid in placeholders(f):
		if rid not in out:
			out.append(rid)
	return out


def rule_type(r):
	a = r.args[1] if len(r.args) > 1 else None
	if r.kids('options'):
		return 'choice'
	if a is None:
		return 'text'
	if a[0] == 'word' and a[1] in ('on', 'off'):
		return 'switch'
	return {'num': 'number', 're': 'pattern', 'list': 'list'}.get(a[0], 'text')


def rule_problem(r, a):
	'''Is the value token a valid value for rule r? -> None or a short text.'''
	t = rule_type(r)
	if a is None:
		return 'no value'
	if t == 'switch' and not (a[0] == 'word' and a[1] in ('on', 'off')):
		return 'use on or off'
	if t == 'choice':
		opts = [ser(o) for o in r.kids('options')[0].args]
		if ser(a) not in opts and value(a) not in [value(o) for o in r.kids('options')[0].args]:
			return 'use one of: ' + ', '.join(opts)
	if t == 'number':
		if a[0] != 'num':
			return 'use a number'
		v = value(a)
		for k, bad in (('min', lambda lim: v < lim), ('max', lambda lim: v > lim)):
			lim = r.kids(k)
			if lim and lim[0].args and lim[0].args[0][0] == 'num' and bad(value(lim[0].args[0])):
				return 'the value is {} {}'.format('below min' if k == 'min' else 'above max', ser(lim[0].args[0]))
	return None


def check(root):
	'''-> (errors, warnings): lists of (line, text).'''
	err, warn = [], []
	names = set()
	for top in root.children:
		if top.head != 'unit':
			err.append((top.line, '"{}" at the top level: only "unit" is allowed'.format(top.head)))
	for u in units(root):
		name = u.word(0)
		if not name:
			err.append((u.line, 'a unit without a name'))
		elif name in names:
			err.append((u.line, 'unit "{}" is defined twice'.format(name)))
		names.add(name)
		if u.word(1) and u.word(1) not in SCOPES:
			err.append((u.line, 'scope "{}": use snippet, tool or agent'.format(u.word(1))))

		def walk(n):
			allowed = CHILDREN.get(n.head)
			for c in n.children:
				if allowed is not None and c.head not in allowed:
					warn.append((c.line, '"{}" is not a known word inside "{}"'.format(c.head, n.head)))
				walk(c)
		walk(u)
		for e in u.kids('example'):
			if '=>' not in [ser(a) for a in e.args]:
				err.append((e.line, 'an example needs "=>"'))
		langs = [cast_info(c)['lang'] for c in u.kids('cast')]
		for lang in set(langs):
			if langs.count(lang) > 1:
				err.append((u.line, 'two casts in "{}"'.format(lang)))
		rules = set(r.word(0) for r in u.kids('rule'))
		byrule = dict((r.word(0), r) for r in u.kids('rule'))
		for r in u.kids('rule'):
			rid = r.word(0)
			if not rid or not RULE_ID.match(rid):
				err.append((r.line, 'rule id "{}": write it as group.name'.format(rid or '')))
			else:
				bad = rule_problem(r, r.args[1] if len(r.args) > 1 else None)
				if bad:
					err.append((r.line, 'rule "{}": {}'.format(rid, bad)))
		for n, t in walk_strings(u):
			for m in PLACE.finditer(t):
				if m.group(1) not in rules:
					err.append((n.line, '{{{}}} names a rule that is not defined in this unit'.format(m.group(1))))
		pnames = set()
		for p in u.kids('preset'):
			pn = p.word(0)
			if not pn:
				err.append((p.line, 'a preset needs a name'))
			elif pn in pnames:
				err.append((p.line, 'preset "{}" is defined twice'.format(pn)))
			pnames.add(pn)
			for s in p.kids('set'):
				rid = s.word(0)
				if rid not in byrule:
					err.append((s.line, 'preset "{}" sets "{}", which is not a rule of this unit'.format(pn, rid)))
				else:
					bad = rule_problem(byrule[rid], s.args[1] if len(s.args) > 1 else None)
					if bad:
						err.append((s.line, 'preset "{}", rule "{}": {}'.format(pn, rid, bad)))
		flow = [c for c in u.children if c.head in FLOW]
		ids = {}
		for f in flow:
			fid = f.word(0)
			if not fid:
				err.append((f.line, '"{}" needs an id'.format(f.head)))
			elif fid in ids:
				err.append((f.line, 'id "{}" is used twice'.format(fid)))
			ids[fid] = f
		read = set()
		edges = {}
		for f in flow:
			fid = f.word(0)
			edges[fid] = []
			read.update(node_reads(f))
			for c in f.children:
				if c.head == 'reads':
					for a in c.args:
						if a[1] not in rules:
							err.append((c.line, 'rule "{}" is not defined in this unit'.format(a[1])))
				if c.head in PROSE:
					for _, t in walk_strings(c):
						if PROSE_NUMBER.search(PLACE.sub('', t)):
							warn.append((c.line, 'a number in the text of "{}": make it a rule and write {{group.name}}'.format(fid)))
							break
				if c.head in ('next', 'pass', 'fail'):
					if c.word(0) != '->' or not c.word(1):
						err.append((c.line, 'write "{} -> <id>"'.format(c.head)))
					elif c.word(1) not in ids:
						err.append((c.line, '"{}" leads to "{}", which does not exist'.format(fid, c.word(1))))
					else:
						edges[fid].append(c.word(1))
			if f.head == 'gate':
				kind = f.word(1)
				if kind not in GATE_KINDS:
					err.append((f.line, 'gate "{}": the kind must be hard, soft or judge'.format(fid)))
				elif kind in ('hard', 'soft') and not f.kids('by'):
					warn.append((f.line, 'gate "{}" is {} but no code decides it: add "by", or make it judge'.format(fid, kind)))
				elif kind == 'judge' and not f.kids('brief'):
					warn.append((f.line, 'judge gate "{}" has no brief'.format(fid)))
				if not f.kids('pass'):
					warn.append((f.line, 'gate "{}" has no "pass"'.format(fid)))
		if flow:
			seen = set()
			starts = [f for f in flow if f.head != 'end']
			todo = [starts[0].word(0)] if starts else []
			while todo:
				x = todo.pop()
				if x in seen:
					continue
				seen.add(x)
				todo.extend(edges.get(x, []))
			for f in flow:
				if f.word(0) not in seen:
					warn.append((f.line, '"{}" cannot be reached from the start'.format(f.word(0))))
			for r in u.kids('rule'):
				if r.word(0) not in read:
					warn.append((r.line, 'rule "{}" is not read by any step or gate'.format(r.word(0))))
	return err, warn


# - Values and proof ---------------------------------
def value(arg):
	kind, v = arg
	if kind == 'str':
		out, i = [], 1
		while i < len(v) - 1:
			if v[i] == '\\' and i + 1 < len(v) - 1:
				nxt = v[i + 1]
				out.append({'n': '\n', 't': '\t'}.get(nxt, nxt))
				i += 2
			else:
				out.append(v[i])
				i += 1
		return ''.join(out)
	if kind == 'num':
		return float(v) if '.' in v else int(v)
	if kind == 'list':
		return [value(a) for a in v]
	if kind == 're':
		return v[1:-1]
	return {'true': True, 'false': False, 'on': True, 'off': False, 'none': None}.get(v, v)


def prove(unit, path):
	'''Run the py cast of one unit. -> (ok, lines of report).'''
	report = []
	casts = [c for c in unit.kids('cast') if cast_info(c)['lang'] == 'py']
	if not casts:
		return None, ['no py cast: prove it in its own runtime, then use "stamp"']
	ns = {'__name__': 'rig_cast'}
	try:
		exec(compile(body_text(casts[0].body), '{}:{}'.format(path, unit.word(0)), 'exec'), ns)
	except Exception as e:
		return False, ['the cast does not run: {}: {}'.format(type(e).__name__, e)]
	fname = re.sub(r'\W', '_', unit.word(0))
	fn = ns.get(fname)
	if not callable(fn):
		return False, ['the cast defines no function "{}"'.format(fname)]
	inputs = [i.word(0) for i in unit.kids('in')]
	checks = []
	for e in unit.kids('ensure'):
		for c in e.kids('check'):
			if c.word(0) == 'py' and len(c.args) > 1:
				checks.append((e, value(c.args[1])))
			elif c.word(0) != 'py':
				report.append('skip: check in "{}" (line {})'.format(c.word(0), c.line))
	examples = unit.kids('example')
	if not examples:
		report.append('warning: no examples, so the proof is weak')
	ok = True
	for ex in examples:
		words = [ser(a) for a in ex.args]
		k = words.index('=>')
		args = [value(a) for a in ex.args[:k]]
		want = value(ex.args[k + 1]) if k + 1 < len(ex.args) else None
		try:
			got = fn(*args)
		except Exception as e:
			ok = False
			report.append('FAIL line {}: raised {}: {}'.format(ex.line, type(e).__name__, e))
			continue
		if got != want:
			ok = False
			report.append('FAIL line {}: {!r} gave {!r}, expected {!r}'.format(ex.line, args, got, want))
			continue
		bad = []
		env = {'re': re, 'math': math, 'unicodedata': unicodedata, 'json': json, 'result': got}
		env.update(zip(inputs, args))
		for e, expr in checks:
			try:
				if not eval(expr, env):
					bad.append('line {}'.format(e.line))
			except Exception as err:
				bad.append('line {} ({}: {})'.format(e.line, type(err).__name__, err))
		if bad:
			ok = False
			report.append('FAIL line {}: {!r} broke ensure at {}'.format(ex.line, args, ', '.join(bad)))
		else:
			report.append('ok   line {}: {!r} => {!r}'.format(ex.line, args, got))
	return ok, report


def stamp(path, text, unit, lang):
	'''Write the current hashes and today's date into the cast line of one unit.'''
	casts = [c for c in unit.kids('cast') if cast_info(c)['lang'] == lang]
	if not casts:
		raise SystemExit('unit "{}" has no "{}" cast'.format(unit.word(0), lang))
	c = casts[0]
	lines = text.split('\n')
	old = lines[c.line - 1]
	cr = '\r' if old.endswith('\r') else ''
	lines[c.line - 1] = '{}cast {} {} {} proved {}{}'.format(' ' * c.indent, lang, matrix_hash(unit), body_hash(c), datetime.date.today().isoformat(), cr)
	with open(path, 'w', encoding='utf-8', newline='') as f:
		f.write('\n'.join(lines))
	return lines[c.line - 1].strip()


# - Compile: catalogue (JSON) ------------------------
def text_of(n):
	'''The arguments of a node as one text: strings without quotes, joined by one space.'''
	return ' '.join(value(a) if a[0] == 'str' else ser(a) for a in n.args)


def name_of(f):
	'''The display name of a step, gate or end: its string argument.'''
	a = f.args[2] if f.head == 'gate' and len(f.args) > 2 else (f.args[1] if f.head != 'gate' and len(f.args) > 1 else None)
	if a is None:
		return ''
	return value(a) if a[0] == 'str' else ser(a)


def notes_of(n):
	return [{'text': text_of(x), 'evidence': [text_of(e) for e in x.kids('evidence')]} for x in n.kids('note')]


def rule_info(r, token=None):
	'''One rule as a catalogue entry. token: a preset value that replaces the value.'''
	a = r.args[1] if len(r.args) > 1 else None
	d = {'id': r.word(0), 'group': r.word(0).split('.')[0], 'label': text_of(r.kids('label')[0]) if r.kids('label') else r.word(0),
		'type': rule_type(r), 'value': value(token if token is not None else a) if (token or a) else None,
		'default': value(a) if a else None}
	for k in ('min', 'max'):
		if r.kids(k) and r.kids(k)[0].args:
			d[k] = value(r.kids(k)[0].args[0])
	if r.kids('options'):
		d['options'] = [value(o) for o in r.kids('options')[0].args]
	if r.kids('unit'):
		d['unit'] = text_of(r.kids('unit')[0])
	ns = notes_of(r)
	if ns:
		d['note'] = ' '.join(x['text'] for x in ns)
		ev = [e for x in ns for e in x['evidence']]
		if ev:
			d['evidence'] = ', '.join(ev)
	return d


def presets_of(u):
	return dict((p.word(0), dict((x.word(0), value(x.args[1])) for x in p.kids('set') if len(x.args) > 1)) for p in u.kids('preset'))


def preset_tokens(u, preset):
	if not preset:
		return {}
	for p in u.kids('preset'):
		if p.word(0) == preset:
			return dict((x.word(0), x.args[1]) for x in p.kids('set') if len(x.args) > 1)
	raise SystemExit('unit "{}" has no preset "{}"'.format(u.word(0), preset))


def links(f, head):
	out = []
	for c in f.kids(head):
		d = {'to': c.word(1)}
		if len(c.args) > 2:
			d['when'] = value(c.args[2]) if c.args[2][0] == 'str' else ser(c.args[2])
		out.append(d)
	return out


def flow_info(f):
	d = {'id': f.word(0), 'kind': f.word(1) if f.head == 'gate' else f.head}
	nm = name_of(f)
	if nm:
		d['name'] = nm
	for k in PROSE:
		xs = f.kids(k)
		if xs:
			d[k] = ' '.join(text_of(x) for x in xs)
	if f.kids('by'):
		d['by'] = [x.word(0) for x in f.kids('by')]
	rd = node_reads(f)
	if rd:
		d['reads'] = rd
	for k in ('next', 'pass', 'fail'):
		ls = links(f, k)
		if ls:
			d[k] = ls
	ns = notes_of(f)
	if ns:
		d['notes'] = ns
	return d


def catalog(u, preset=None):
	'''A unit as a catalogue: the JSON that a code runner reads.'''
	toks = preset_tokens(u, preset)
	flow = [c for c in u.children if c.head in FLOW]
	starts = [f for f in flow if f.head != 'end']
	gates = u.kids('gate')
	code = [g for g in gates if g.word(1) in ('hard', 'soft') and g.kids('by')]
	return {
		'rig': 0, 'unit': u.word(0), 'scope': u.word(1, 'snippet'), 'preset': preset,
		'intent': ' '.join(text_of(x) for x in u.kids('intent')),
		'notes': notes_of(u), 'uses': [x.word(0) for x in u.kids('uses')],
		'in': [{'name': x.word(0), 'type': x.word(1)} for x in u.kids('in')],
		'out': u.kids('out')[0].word(0) if u.kids('out') else None,
		'start': starts[0].word(0) if starts else None,
		'coverage': {'gates': len(gates), 'code': len(code), 'judge': len([g for g in gates if g.word(1) == 'judge'])},
		'presets': presets_of(u),
		'rules': [rule_info(r, toks.get(r.word(0))) for r in u.kids('rule')],
		'flow': [flow_info(f) for f in flow],
	}


# - Compile: skill (Markdown) -------------------------
def show(tok):
	'''A value token as the text a person reads.'''
	if tok is None:
		return ''
	return value(tok) if tok[0] == 'str' else ser(tok)


def skill(u, rules_path=None, preset=None):
	'''A unit as a SKILL.md for an agent that follows instructions.
	rules_path: refer to that JSON file for the values, instead of writing them in.'''
	toks = preset_tokens(u, preset)
	byrule = dict((r.word(0), r) for r in u.kids('rule'))

	def val(rid):
		r = byrule[rid]
		return show(toks.get(rid, r.args[1] if len(r.args) > 1 else None))

	def fill(t):
		if rules_path:
			return PLACE.sub(lambda m: '`{' + m.group(1) + '}`' if m.group(1) in byrule else m.group(0), t)
		return PLACE.sub(lambda m: val(m.group(1)) if m.group(1) in byrule else m.group(0), t)

	def cell(t):
		return t.replace('|', '\\|')
	c = catalog(u, preset)
	intent = fill(c['intent'])
	out = ['---', 'name: ' + u.word(0), 'description: ' + intent, '---', '', '# ' + u.word(0), '']
	if intent:
		out += [intent, '']
	for n in c['notes']:
		out.append('Note: ' + fill(n['text']) + (' (evidence: ' + ', '.join(n['evidence']) + ')' if n['evidence'] else ''))
	if c['notes']:
		out.append('')
	if c['rules']:
		out += ['## Rules', '']
		if rules_path:
			out += ['Read the value of each rule from `' + rules_path + '`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.', '',
				'| Rule | Meaning |', '|---|---|']
		else:
			out += ['| Rule | Value | Meaning |', '|---|---|---|']
		for r in u.kids('rule'):
			info = rule_info(r)
			lim = []
			for k in ('min', 'max'):
				if r.kids(k) and r.kids(k)[0].args:
					lim.append(k + ' ' + ser(r.kids(k)[0].args[0]))
			if r.kids('options'):
				lim.append('one of: ' + ', '.join(ser(o) for o in r.kids('options')[0].args))
			mean = info['label'] + (' (' + info['unit'] + ')' if 'unit' in info else '') + ('; ' + ', '.join(lim) if lim else '')
			if 'note' in info:
				mean += '. Note: ' + info['note']
			if rules_path:
				out.append('| `{}` | {} |'.format(info['id'], cell(mean)))
			else:
				out.append('| `{}` | `{}` | {} |'.format(info['id'], cell(val(info['id'])), cell(mean)))
		out.append('')
	if c['flow']:
		out += ['## Flow', '', 'Start at `{}`. Go from node to node as written. Do not skip a gate.'.format(c['start']), '']

		def go(l):
			return 'go to `{}`'.format(l['to']) + (' ({})'.format(fill(l['when'])) if 'when' in l else '')
		for f in c['flow']:
			k = f['kind']
			label = {'step': 'step', 'end': 'end'}.get(k, k + ' gate')
			out += ['### `{}`{} ({})'.format(f['id'], ' ' + fill(f['name']) if f.get('name') else '', label), '']
			for key, title in (('when', 'When'), ('do', 'Do'), ('ensure', 'Check')):
				if key in f:
					out.append('- {}: {}'.format(title, fill(f[key])))
			if 'reads' in f:
				out.append('- Rules: ' + ', '.join('`{}`'.format(r) if rules_path or r not in byrule else '`{}` = {}'.format(r, val(r)) for r in f['reads']))
			by = ', '.join('`{}`'.format(b) for b in f.get('by', []))
			guess = '- No code decides this gate yet: decide it yourself and label the result as a guess.'
			if k == 'step' and by:
				out.append('- Code: run {}.'.format(by))
			elif k == 'hard':
				out.append('- Decided by code: run {} and obey its result. Do not decide this gate yourself.'.format(by) if by else guess)
			elif k == 'soft':
				out.append('- Decided by code: run {}. If it fails, report it and go on as written below.'.format(by) if by else guess)
			elif k == 'judge':
				out.append('- Judge: {}. Label the result as a guess.'.format(fill(f['brief'])) if 'brief' in f else '- Judge: decide it yourself. Label the result as a guess.')
			for n in f.get('notes', []):
				out.append('- Note: ' + fill(n['text']))
			for key, title in (('next', 'Next'), ('pass', 'Pass'), ('fail', 'Fail')):
				for l in f.get(key, []):
					out.append('- {}: {}.'.format(title, go(l)))
			if k == 'end':
				out.append('- Stop here.')
			out.append('')
	return '\n'.join(out).rstrip('\n') + '\n'


# - Decompile: catalogue (JSON) -> Rig ---------------
def quote(t):
	return '"' + str(t).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def token(v, t='text'):
	if isinstance(v, bool):
		return 'on' if v else 'off'
	if isinstance(v, (int, float)):
		return repr(v)
	if isinstance(v, list):
		return '(' + ' '.join(token(x) for x in v) + ')'
	if t == 'pattern':
		return '/' + v + '/'
	if t == 'choice' and re.match(r'^[A-Za-z_][\w.-]*$', v):
		return v
	return quote(v)


def from_catalog(c):
	'''A catalogue (as made by catalog()) -> Rig text. Not the original layout; the same meaning.'''
	out = ['unit {} {}'.format(c['unit'], c.get('scope', 'agent'))]
	if c.get('intent'):
		out.append('  intent ' + quote(c['intent']))
	for x in c.get('uses', []):
		out.append('  uses ' + x)
	for x in c.get('in', []):
		out.append('  in ' + x['name'] + (' ' + x['type'] if x.get('type') else ''))
	if c.get('out'):
		out.append('  out ' + c['out'])

	def notes(ns, ind):
		for n in ns:
			out.append(ind + 'note ' + quote(n['text']))
			for e in n.get('evidence', []):
				out.append(ind + '  evidence ' + e)
	notes(c.get('notes', []), '  ')
	types = {}
	for r in c.get('rules', []):
		t = r.get('type', 'text')
		types[r['id']] = t
		out.append('  rule {} {}'.format(r['id'], token(r.get('default', r.get('value')), t)))
		if r.get('label') and r['label'] != r['id']:
			out.append('    label ' + quote(r['label']))
		if 'unit' in r:
			out.append('    unit ' + quote(r['unit']))
		for k in ('min', 'max'):
			if k in r:
				out.append('    {} {}'.format(k, token(r[k])))
		if 'options' in r:
			out.append('    options ' + ' '.join(token(o, 'choice') for o in r['options']))
		if 'note' in r:
			out.append('    note ' + quote(r['note']))
			for e in (r['evidence'].split(', ') if r.get('evidence') else []):
				out.append('      evidence ' + e)
	for name, sets in c.get('presets', {}).items():
		out.append('  preset ' + name)
		for rid, v in sets.items():
			out.append('    set {} {}'.format(rid, token(v, types.get(rid, 'text'))))
	for f in c.get('flow', []):
		k = f['kind']
		head = 'gate {} {}'.format(f['id'], k) if k in GATE_KINDS else '{} {}'.format(k, f['id'])
		out.append('  ' + head + (' ' + quote(f['name']) if f.get('name') else ''))
		for key in PROSE:
			if key in f:
				out.append('    {} {}'.format(key, quote(f[key])))
		for b in f.get('by', []):
			out.append('    by ' + b)
		if f.get('reads'):
			out.append('    reads ' + ' '.join(f['reads']))
		notes(f.get('notes', []), '    ')
		for key in ('next', 'pass', 'fail'):
			for l in f.get(key, []):
				out.append('    {} -> {}{}'.format(key, l['to'], ' ' + quote(l['when']) if 'when' in l else ''))
	return '\n'.join(out) + '\n'


# - Command line -------------------------------------
def tree(n):
	d = {'head': n.head, 'args': [ser(a) for a in n.args], 'line': n.line}
	if n.children:
		d['children'] = [tree(c) for c in n.children]
	if n.body is not None:
		d['body'] = body_text(n.body)
	return d


def load(path):
	with open(path, encoding='utf-8', newline='') as f:
		text = f.read()
	try:
		return text, parse(text)
	except RigError as e:
		raise SystemExit('{}: {}'.format(path, e))


def find(root, name):
	for u in units(root):
		if u.word(0) == name:
			return u
	raise SystemExit('no unit "{}"'.format(name))


def pick(root, name=None):
	'''The named unit, or the first unit with a flow, or the first unit.'''
	if name:
		return find(root, name)
	us = units(root)
	if not us:
		raise SystemExit('the file has no unit')
	for u in us:
		if any(c.head in FLOW for c in u.children):
			return u
	return us[0]


def option(rest, name, flag=False):
	'''Take "--name VALUE" (or the flag "--name") out of rest.'''
	if name not in rest:
		return False if flag else None
	i = rest.index(name)
	if flag:
		del rest[i]
		return True
	if i + 1 >= len(rest):
		raise SystemExit('{} needs a value'.format(name))
	v = rest[i + 1]
	del rest[i:i + 2]
	return v


def write(path, text):
	with open(path, 'w', encoding='utf-8', newline='\n') as f:
		f.write(text)


def compile_to(kind, u, preset=None, rules_path=None):
	if kind == 'json':
		return json.dumps(catalog(u, preset), ensure_ascii=False, indent=1) + '\n'
	if kind == 'skill':
		return skill(u, rules_path, preset)
	raise SystemExit('compile json or compile skill')


def outputs(path, unit=None, json_out=None, skill_out=None, rules_ref=False, preset=None):
	'''Compile FILE to the files that agents read. -> the paths written.'''
	text, root = load(path)
	err, _ = check(root)
	if err:
		raise SystemExit('{}: line {}: {}'.format(path, err[0][0], err[0][1]))
	u = pick(root, unit)
	done = []
	if json_out:
		write(json_out, compile_to('json', u, preset))
		done.append(json_out)
	if skill_out:
		ref = None
		if rules_ref and json_out:
			import os
			ref = os.path.relpath(os.path.abspath(json_out), os.path.dirname(os.path.abspath(skill_out))).replace(os.sep, '/')
		write(skill_out, compile_to('skill', u, preset, ref))
		done.append(skill_out)
	return done


def serve(path, port, **outs):
	'''Serve the viewer for one file on 127.0.0.1. Save writes the file and compiles it again.'''
	import http.server
	import os
	here = os.path.dirname(os.path.abspath(__file__))
	pages = [os.path.join(here, 'viewer.html'), os.path.join(here, '..', '..', 'viewer', 'index.html')]
	page = next((p for p in pages if os.path.exists(p)), None)
	if not page:
		raise SystemExit('the viewer is not found: copy viewer/index.html next to rig.py as viewer.html')
	print('wrote: ' + ', '.join(outputs(path, **outs) or ['nothing (add --json or --skill)']))

	class Handler(http.server.BaseHTTPRequestHandler):
		def reply(self, code, body, kind='application/json; charset=utf-8'):
			data = body.encode('utf-8')
			self.send_response(code)
			self.send_header('Content-Type', kind)
			self.send_header('X-Rig-File', os.path.basename(path))
			self.send_header('Content-Length', str(len(data)))
			self.send_header('Cache-Control', 'no-store')
			self.end_headers()
			self.wfile.write(data)

		def do_GET(self):
			if self.path in ('/', '/index.html'):
				self.send_response(302)
				self.send_header('Location', '/viewer?src=/file&save=1')
				self.end_headers()
			elif self.path.startswith('/viewer'):
				with open(page, encoding='utf-8') as f:
					self.reply(200, f.read(), 'text/html; charset=utf-8')
			elif self.path == '/file':
				with open(path, encoding='utf-8', newline='') as f:
					self.reply(200, f.read(), 'text/plain; charset=utf-8')
			else:
				self.reply(404, json.dumps({'error': 'not found'}))

		def do_POST(self):
			if self.path != '/file':
				return self.reply(404, json.dumps({'error': 'not found'}))
			text = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8')
			try:
				err, _ = check(parse(text))
			except RigError as e:
				return self.reply(400, json.dumps({'error': str(e)}))
			if err:
				return self.reply(400, json.dumps({'error': 'line {}: {}'.format(err[0][0], err[0][1])}))
			with open(path, 'w', encoding='utf-8', newline='') as f:
				f.write(text)
			try:
				done = outputs(path, **outs)
			except SystemExit as e:
				return self.reply(400, json.dumps({'error': str(e)}))
			self.reply(200, json.dumps({'saved': os.path.basename(path), 'wrote': done}))

		def log_message(self, *a):
			pass

	srv = http.server.HTTPServer(('127.0.0.1', port), Handler)
	print('serving {} at http://127.0.0.1:{}/  (Ctrl+C stops)'.format(path, port))
	try:
		srv.serve_forever()
	except KeyboardInterrupt:
		pass


def main(argv):
	try:
		sys.stdout.reconfigure(encoding='utf-8', errors='replace')
	except Exception:
		pass
	if len(argv) < 2 or argv[0] not in ('check', 'hash', 'prove', 'stamp', 'json', 'compile', 'from-json', 'serve'):
		print(__doc__)
		return 2
	cmd, rest = argv[0], list(argv[1:])
	if cmd == 'compile':
		kind = rest.pop(0)
		preset, out, rules = option(rest, '--preset'), option(rest, '-o'), option(rest, '--rules')
		if not rest:
			raise SystemExit('compile {} FILE [UNIT]'.format(kind))
		text, root = load(rest[0])
		err, _ = check(root)
		if err:
			raise SystemExit('{}: line {}: {}'.format(rest[0], err[0][0], err[0][1]))
		result = compile_to(kind, pick(root, rest[1] if len(rest) > 1 else None), preset, rules)
		if out:
			write(out, result)
		else:
			sys.stdout.write(result)
		return 0
	if cmd == 'from-json':
		out = option(rest, '-o')
		with open(rest[0], encoding='utf-8') as f:
			result = from_catalog(json.load(f))
		if out:
			write(out, result)
		else:
			sys.stdout.write(result)
		return 0
	if cmd == 'serve':
		port = int(option(rest, '--port') or 8765)
		outs = {'json_out': option(rest, '--json'), 'skill_out': option(rest, '--skill'), 'rules_ref': option(rest, '--rules-ref', True),
			'unit': rest[1] if len(rest) > 1 else None}
		serve(rest[0], port, **outs)
		return 0
	if cmd == 'check':
		bad = 0
		for path in rest:
			text, root = load(path)
			print(path)
			for u in units(root):
				print('  {:<28} {}'.format('{} ({})'.format(u.word(0), u.word(1, 'snippet')), '; '.join(unit_status(u))))
			err, warn = check(root)
			for line, t in sorted(err):
				print('  error   line {}: {}'.format(line, t))
			for line, t in sorted(warn):
				print('  warning line {}: {}'.format(line, t))
			bad += len(err)
		return 1 if bad else 0
	path = rest[0]
	text, root = load(path)
	if cmd == 'json':
		print(json.dumps(tree(root), ensure_ascii=False, indent=1))
	elif cmd == 'hash':
		for u in units(root):
			print('{}  matrix {}'.format(u.word(0), matrix_hash(u)))
			for c in u.kids('cast'):
				print('  cast {}  body {}'.format(cast_info(c)['lang'], body_hash(c)))
	elif cmd == 'stamp':
		if len(rest) < 3:
			raise SystemExit('stamp FILE UNIT LANG')
		print(stamp(path, text, find(root, rest[1]), rest[2]))
	elif cmd == 'prove':
		want = [a for a in rest[1:] if not a.startswith('--')]
		todo = [find(root, want[0])] if want else units(root)
		all_ok = True
		for u in todo:
			ok, report = prove(u, path)
			if ok is None and not want:
				continue
			print('{}: {}'.format(u.word(0), {True: 'proved', False: 'FAILED', None: 'not proved'}[ok]))
			for r in report:
				print('  ' + r)
			if ok and '--stamp' in rest:
				print('  ' + stamp(path, text, u, 'py'))
				text, root = load(path)
			all_ok = all_ok and ok is not False
		return 0 if all_ok else 1
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
