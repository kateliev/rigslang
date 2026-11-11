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
	'unit': {'in', 'out', 'intent', 'example', 'ensure', 'reason', 'note', 'uses', 'rule', 'cast', 'step', 'gate', 'end'},
	'ensure': {'check', 'note'},
	'reason': {'evidence'},
	'rule': {'min', 'max', 'options', 'unit', 'label', 'reason', 'evidence', 'note'},
	'step': {'do', 'by', 'reads', 'next', 'note', 'reason'},
	'gate': {'when', 'reads', 'ensure', 'by', 'brief', 'pass', 'fail', 'note', 'reason'},
	'end': {'note'},
}
NUMBER = re.compile(r'^-?\d+(\.\d+)?$')


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
		for r in u.kids('reason'):
			if r.word(0) == '?':
				warn.append((r.line, 'the reason is unknown: ask the human'))
		langs = [cast_info(c)['lang'] for c in u.kids('cast')]
		for lang in set(langs):
			if langs.count(lang) > 1:
				err.append((u.line, 'two casts in "{}"'.format(lang)))
		rules = set(r.word(0) for r in u.kids('rule'))
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
			for c in f.children:
				if c.head == 'reads':
					for a in c.args:
						read.add(a[1])
						if a[1] not in rules:
							err.append((c.line, 'rule "{}" is not defined in this unit'.format(a[1])))
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


def main(argv):
	try:
		sys.stdout.reconfigure(encoding='utf-8', errors='replace')
	except Exception:
		pass
	if len(argv) < 2 or argv[0] not in ('check', 'hash', 'prove', 'stamp', 'json'):
		print(__doc__)
		return 2
	cmd, rest = argv[0], argv[1:]
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
