#!/usr/bin/env python3
"""rigkit: the runtime of a Rig project (language version 1). Standard library only. Python 3.

A tool keeps its own copy of this file (rig.py new copies it), so the tool installs alone.

It reads a catalogue (rig.py compile json) and gives a tool five things:

    Rules     the values of the catalogue; code reads a number with R('group.name')
    Kit       binds the code of the steps and gates, and walks the flow
    runs      a run is one item on its way through the flow; it has its own folder, with a
              pinned copy of the flow, the answers of the model and of the person, and the
              state at each top line (for rerun); it refuses an answer for another node
    cli       run, batch, queues, answer, work, approve, status, resume, drop, list, prune,
              rerun, replay, rules, flow, call, regress, serve-stdio, mcp: one JSON line each
    step      a wrapper for code that runs inside a host application

Code does the steps and decides the hard and soft gates. At a model gate, a human gate,
or a step that the model does, the run stops and waits. The model never decides a gate
that code decides, and never answers for a person.

The lines run in order. Blocks: "for" runs its body once for each item of a list, "until"
runs it again until a path is true, "if" and "else" choose a body, "finally" runs after the
end, also after an error. The flow never jumps back, except to the start of a loop body and
to the step before a gate that has "retry".

The code of a step:  def name(state, R) -> a value (it goes to state[<step id>])
The code of a gate:  def name(state, R) -> True, False, or a dict with "pass" and,
                     when you want them, "when" (which fail line), "problems", and facts.
The code of a human gate with options reads the answer of the person in
state[<gate id>]["answer"] and returns like a gate: a fail means "not understood", and the
gate asks again.
"""
import concurrent.futures
import copy
import datetime
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request

PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
GATES = ('hard', 'soft', 'model', 'human')
WORK_RULES = '\n'.join([
	'You do one job of a tool. Code did the rest of the work and checks your answer.',
	'Read the job and the data. Decide each item on its own, in the order of the data.',
	'Answer only with JSON in the given form. Use only ids, names and numbers from the data. Do not invent.',
])


def _work_job_text(w):
	text = 'The job:\n{}\n\nThe data:\n{}'.format(w.get('do') or '', json.dumps(w.get('sees') or {}, ensure_ascii=False))
	if w.get('problems'):
		text += '\n\nYour last answer for this job failed for these reasons. Fix them:\n- ' + '\n- '.join(str(p) for p in w['problems'])
	return text + '\n\nAnswer with {{"result": ...}}, where the result has the form {}.'.format(w.get('out') or 'of the schema')


def _json_in(text):
	a, b = text.find('{'), text.rfind('}')
	return text[a:b + 1] if a >= 0 and b > a else text


def _input_schema(ports):
	'''Build a JSON Schema object from catalogue "in" ports.'''
	props, req = {}, []
	for p in ports or []:
		s = copy.deepcopy(p.get('schema')) if p.get('schema') else {}
		if p.get('text'):
			s['description'] = p['text']
		props[p['name']] = s
		if not (p.get('type') or '').startswith('(maybe'):
			req.append(p['name'])
	return {'type': 'object', 'properties': props, 'required': req}


def _mcp_decorate(res, has_worker):
	'''Tailor a waiting response for MCP: drop CLI-only waiting.answer and add waiting.next_action.'''
	if not isinstance(res, dict) or not isinstance(res.get('waiting'), dict):
		return res
	res = dict(res)
	w = dict(res['waiting'])
	w.pop('answer', None)
	kind = w.get('kind')
	run_id = res.get('run')
	if kind == 'human':
		w['next_action'] = {'call': 'NONE', 'show_verbatim': w.get('say', '')}
	elif kind == 'model':
		w['next_action'] = {'call': 'answer_gate', 'args': {'run': run_id, 'pass': '<true|false>', 'why': '<one sentence>'}}
	elif kind == 'step':
		if has_worker:
			w['next_action'] = {'call': 'work_run', 'args': {'run': run_id}}
		else:
			w['next_action'] = {'call': 'answer_step', 'args': {'run': run_id, 'result': '<value matching schema>'}}
	res['waiting'] = w
	return res


def _http_post(url, headers, payload, timeout_s):
	data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
	req = urllib.request.Request(url, data=data, headers=headers, method='POST')
	with urllib.request.urlopen(req, timeout=timeout_s) as resp:
		return json.loads(resp.read().decode('utf-8'))


class Refused(Exception):
	'''A call that the flow does not allow now. It is a result, not a crash, and it is final.'''


class Timeout(Exception):
	'''Code that ran longer than the timeout of its node.'''


# - Rules ---------------------------------------------
def check_value(rule, value):
	'''The value in the type of the rule, or ValueError.'''
	t, rid = rule.get('type', 'text'), rule['id']
	if t == 'switch':
		if isinstance(value, bool):
			return value
		text = str(value).strip().lower()
		if text in ('1', 'true', 'on', 'yes'):
			return True
		if text in ('0', 'false', 'off', 'no'):
			return False
		raise ValueError('{}: on or off, not {!r}'.format(rid, value))
	if t == 'choice':
		if value not in rule.get('options', []):
			raise ValueError('{}: one of {}, not {!r}'.format(rid, ', '.join(str(o) for o in rule.get('options', [])), value))
		return value
	if t == 'number':
		if isinstance(value, bool):
			raise ValueError('{}: a number, not {!r}'.format(rid, value))
		v = float(value)
		if v == int(v) and isinstance(rule.get('default'), int):
			v = int(v)
		if 'min' in rule and v < rule['min']:
			raise ValueError('{}: at least {}'.format(rid, rule['min']))
		if 'max' in rule and v > rule['max']:
			raise ValueError('{}: at most {}'.format(rid, rule['max']))
		return v
	if t == 'list':
		if not isinstance(value, list):
			raise ValueError('{}: a list'.format(rid))
		return value
	return str(value)


class Rules(object):
	'''The values of one catalogue, plus changes for one session or one run.'''

	def __init__(self, catalogue, changes=None):
		self.catalogue = catalogue
		self.by_id = dict((r['id'], r) for r in catalogue.get('rules', []))
		self.session = {}
		for rid, v in (changes or {}).items():
			self.set(rid, v)

	def __call__(self, rid):
		if rid in self.session:
			return self.session[rid]
		if rid not in self.by_id:
			raise KeyError('Unknown rule {}. Add it to the .rig file, then build.'.format(rid))
		return self.by_id[rid]['value']

	get = __call__

	def set(self, rid, value):
		'''Change a rule for this session only. The source does not change.'''
		if rid not in self.by_id:
			raise KeyError('Unknown rule {}.'.format(rid))
		self.session[rid] = check_value(self.by_id[rid], value)
		return self.session[rid]

	def preset(self, name):
		if name not in self.catalogue.get('presets', {}):
			raise KeyError('Unknown preset {}.'.format(name))
		for rid, v in self.catalogue['presets'][name].items():
			self.set(rid, v)

	def values(self):
		return dict((rid, self(rid)) for rid in self.by_id)

	def fill(self, text):
		'''Write the value of each rule in place of {group.name}.'''
		def show(m):
			if m.group(1) not in self.by_id:
				return m.group(0)
			v = self(m.group(1))
			return ('on' if v else 'off') if isinstance(v, bool) else str(v)
		return PLACE.sub(show, text or '')


# - Step wrapper for code inside a host application -----
def step(fn):
	'''Wrap a function that an agent calls inside a host (through an MCP server, for example).
	It prints one JSON line and returns it: {"ok", "step", "result"}, or "error", or "refused".'''
	def run(*args, **kwargs):
		try:
			out = {'ok': True, 'step': fn.__name__, 'result': fn(*args, **kwargs)}
		except Refused as e:
			out = {'ok': False, 'step': fn.__name__, 'refused': str(e)}
		except Exception as e:
			out = {'ok': False, 'step': fn.__name__, 'error': '{}: {}'.format(type(e).__name__, e)}
		print(json.dumps(out, ensure_ascii=False, default=str))
		return out
	run.__name__, run.__doc__, run.__wrapped__ = fn.__name__, fn.__doc__, fn
	return run



# - Small helpers -------------------------------------
def read_json(path):
	with open(path, encoding='utf-8') as f:
		return json.load(f)


def write_json(path, data):
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	tmp = '{}.{}.{}.tmp'.format(path, os.getpid(), threading.get_ident())
	with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
		json.dump(data, f, ensure_ascii=False, indent=1, default=str)
		f.write('\n')
	os.replace(tmp, path)


def run_sort_key(run_id):
	'''Order short sequential ids (r1, r2, ..., r10) numerically, and legacy timestamp ids chronologically.'''
	m = re.match(r'^r(\d+)$', run_id or '')
	return (1, int(m.group(1)), '') if m else (0, 0, run_id or '')


def now():
	return datetime.datetime.now().isoformat(timespec='seconds')


def age(stamp):
	'''Seconds since an ISO time.'''
	try:
		return (datetime.datetime.now() - datetime.datetime.fromisoformat(stamp)).total_seconds()
	except (TypeError, ValueError):
		return 0


def truthy(v):
	'''The test of "if" and "until": a path is true when it is not empty and not false.'''
	return not (v is None or v is False or v == '' or v == [] or v == {})


def passed(result):
	return bool(result.get('pass')) if isinstance(result, dict) else bool(result)


def schema_problems(v, s, where='result'):
	'''The places where the value v does not have the form of the JSON Schema s (the subset that
	rig.py writes for an "in" or "out" type). -> a list of short texts.'''
	if not s:
		return []
	if 'anyOf' in s:
		return [] if any(not schema_problems(v, x, where) for x in s['anyOf']) else ['{}: not the right form'.format(where)]
	if 'enum' in s:
		return [] if v in s['enum'] else ['{}: one of {}'.format(where, ', '.join(json.dumps(x) for x in s['enum']))]
	t = s.get('type')
	ok = {'string': lambda x: isinstance(x, str), 'integer': lambda x: isinstance(x, int) and not isinstance(x, bool),
		'number': lambda x: isinstance(x, (int, float)) and not isinstance(x, bool), 'boolean': lambda x: isinstance(x, bool),
		'null': lambda x: x is None, 'array': lambda x: isinstance(x, list), 'object': lambda x: isinstance(x, dict)}.get(t)
	if ok and not ok(v):
		return ['{}: {}'.format(where, {'string': 'a text', 'integer': 'a whole number', 'number': 'a number', 'boolean': 'true or false', 'null': 'null', 'array': 'a list', 'object': 'an object'}.get(t, t))]
	out = []
	if t == 'array':
		if 'minItems' in s and len(v) < s['minItems']:
			out.append('{}: at least {} items'.format(where, s['minItems']))
		if 'maxItems' in s and len(v) > s['maxItems']:
			out.append('{}: at most {} items'.format(where, s['maxItems']))
		prefix = s.get('prefixItems')
		if prefix is not None:
			for i, (x, ps) in enumerate(zip(v, prefix)):
				out += schema_problems(x, ps, '{}[{}]'.format(where, i))
				if len(out) > 5:
					break
		if 'items' in s and len(out) <= 5:
			start = len(prefix) if prefix is not None else 0
			for i, x in enumerate(v[start:], start):
				out += schema_problems(x, s['items'], '{}[{}]'.format(where, i))
				if len(out) > 5:
					break
	if t == 'object':
		for k in s.get('required', []):
			if k not in v:
				out.append('{}: "{}" is missing'.format(where, k))
		if s.get('additionalProperties') is False:
			for k in v:
				if k not in s.get('properties', {}):
					out.append('{}: "{}" is not a field'.format(where, k))
		for k, x in s.get('properties', {}).items():
			if k in v:
				out += schema_problems(v[k], x, '{}.{}'.format(where, k))
	return out[:6]


def run_code(fn, state, R, seconds=None):
	'''Call the code of a node. With seconds: stop waiting after that time (the code may go on
	in the background; its result is not used).'''
	if not seconds:
		return fn(state, R)
	box = {}

	def go():
		try:
			box['value'] = fn(state, R)
		except BaseException as e:  # noqa: B902 - passed on below
			box['error'] = e
	t = threading.Thread(target=go, daemon=True)
	t.start()
	t.join(seconds)
	if t.is_alive():
		raise Timeout('ran longer than its timeout ({} s)'.format(seconds))
	if 'error' in box:
		raise box['error']
	return box.get('value')


class View(object):
	'''The flow of one catalogue: nodes and blocks by id.'''

	def __init__(self, c):
		self.c = c
		self.nodes = dict((n['id'], n) for n in c.get('flow', []))
		self.blocks = dict((b['id'], b) for b in c.get('blocks', []))
		self.start, self.final = c.get('start'), c.get('finally')


# - Kit -----------------------------------------------
class Kit(object):
	def __init__(self, catalogue, runs=None, errors_stop=2):
		'''catalogue: the path of a compiled catalogue, or the catalogue itself.
		runs: a folder for the run folders (None: runs live in memory only).
		errors_stop: a batch stops after this many errors in a row (the host may be down).
		A rule "run.errors_stop" or "run.sees_max" of the catalogue replaces the value.'''
		self.catalogue = read_json(catalogue) if isinstance(catalogue, str) else catalogue
		if self.catalogue and self.catalogue.get('rig', 0) < 1:
			raise ValueError('This catalogue is of language version 0. Build the tool again: rig.py build')
		self.rules = Rules(self.catalogue)
		self.view = View(self.catalogue)
		self.start = self.view.start
		self.runs = runs
		self.errors_stop = self.rules('run.errors_stop') if 'run.errors_stop' in self.rules.by_id else errors_stop
		self.sees_max = self.rules('run.sees_max') if 'run.sees_max' in self.rules.by_id else 6000  # characters of one "sees" text
		self.code, self.tools, self.files, self.views, self.count = {}, {}, {}, {}, 0
		self._lock = threading.RLock()

	# - Binding the code
	def bind(self, prefix, source):
		'''Give the functions of a module (or a dict) the names "prefix.function", as in the "by" lines.'''
		items = source.items() if isinstance(source, dict) else ((k, getattr(source, k)) for k in dir(source) if not k.startswith('_'))
		for name, fn in items:
			if callable(fn):
				self.code[prefix + '.' + name] = fn
		return self

	def tool(self, catalogue, fn):
		'''A tool unit: its catalogue (path or dict) and its function. "call" runs it.'''
		c = read_json(catalogue) if isinstance(catalogue, str) else catalogue
		self.tools[c['unit']] = (c, fn)
		return self

	def missing(self):
		'''The names of "by" lines that have no function here.'''
		out = []
		for n in self.view.nodes.values():
			for b in n.get('by', []):
				if self.fn_of(b) is None and b not in out:
					out.append(b)
		return out

	def fn_of(self, name):
		return self.code.get(name) or self.code.get(name.replace('-', '_')) or self.code.get(name.rsplit('.', 1)[0] + '.' + name.rsplit('.', 1)[-1].replace('-', '_'))

	def node_code(self, node):
		fns = [self.fn_of(b) for b in node.get('by', [])]
		return fns if fns and all(fns) else None

	# - The files of a run: run, flow (pinned), rules (pinned), answers, marks
	def folder(self, run_id):
		if not re.match(r'^[\w.-]+$', run_id or ''):
			raise Refused('Bad run id {!r}.'.format(run_id))
		return os.path.join(self.runs, run_id)

	def put(self, run_id, name, data):
		if self.runs is None:
			with self._lock:
				self.files[(run_id, name)] = copy.deepcopy(data)
		else:
			write_json(os.path.join(self.folder(run_id), name + '.json'), data)

	def get(self, run_id, name, default=None):
		if self.runs is None:
			with self._lock:
				return copy.deepcopy(self.files.get((run_id, name), default))
		p = os.path.join(self.folder(run_id), name + '.json')
		return read_json(p) if os.path.exists(p) else default

	def _mark_file(self, run_id, node):
		return os.path.join(self.folder(run_id), 'marks', urllib.parse.quote(node, safe='._-') + '.json')

	def has_mark(self, run_id, node):
		if self.runs is None:
			with self._lock:
				return (run_id, 'mark:' + node) in self.files
		return os.path.exists(self._mark_file(run_id, node))

	def put_mark(self, run_id, node, state):
		if self.runs is None:
			with self._lock:
				self.files[(run_id, 'mark:' + node)] = copy.deepcopy(state)
		else:
			write_json(self._mark_file(run_id, node), state)

	def get_mark(self, run_id, node):
		if self.runs is None:
			with self._lock:
				if (run_id, 'mark:' + node) in self.files:
					return copy.deepcopy(self.files[(run_id, 'mark:' + node)])
				legacy = self.files.get((run_id, 'marks'))
				return copy.deepcopy(legacy[node]) if isinstance(legacy, dict) and node in legacy else None
		p = self._mark_file(run_id, node)
		if os.path.exists(p):
			return read_json(p)
		legacy = self.get(run_id, 'marks')
		return legacy[node] if isinstance(legacy, dict) and node in legacy else None

	def mark_names(self, run_id):
		if self.runs is None:
			with self._lock:
				names = [name[5:] for (rid, name) in self.files if rid == run_id and name.startswith('mark:')]
				legacy = self.files.get((run_id, 'marks'))
				if isinstance(legacy, dict):
					for k in legacy:
						if k not in names:
							names.append(k)
				return names
		names = []
		mdir = os.path.join(self.folder(run_id), 'marks')
		if os.path.isdir(mdir):
			for f in sorted(os.listdir(mdir)):
				if f.endswith('.json'):
					names.append(urllib.parse.unquote(f[:-5]))
		legacy = self.get(run_id, 'marks')
		if isinstance(legacy, dict):
			for k in legacy:
				if k not in names:
					names.append(k)
		return names

	def new_id(self):
		'''A short sequential run id (r1, r2, ...) that no run has. With a runs folder, its folder is
		reserved atomically here (os.mkdir fails when it exists).'''
		with self._lock:
			if self.runs is not None and self.count == 0 and os.path.isdir(self.runs):
				top = 0
				for n in os.listdir(self.runs):
					m = re.match(r'^r(\d+)$', n)
					if m:
						top = max(top, int(m.group(1)))
				self.count = top
			while True:
				self.count += 1
				rid = 'r{}'.format(self.count)
				if self.runs is None:
					if (rid, 'run') not in self.files:
						return rid
					continue
				try:
					os.makedirs(self.runs, exist_ok=True)
					os.mkdir(os.path.join(self.runs, rid))
					return rid
				except FileExistsError:
					continue

	def load(self, run_id):
		run = self.get(run_id, 'run')
		if run is None:
			raise Refused('No run {}.'.format(run_id))
		return run

	def _waiting_entry(self, run):
		w = run.get('waiting')
		kind = w.get('kind') if isinstance(w, dict) else self.view_of(run).nodes.get(run.get('at'), {}).get('kind')
		return {'node': run.get('at'), 'kind': kind, 'started': run.get('started')}

	def _rebuild_waiting_index(self):
		idx = {}
		for r in self.all_runs():
			if r.get('outcome') is None:
				idx[r['id']] = self._waiting_entry(r)
		if self.runs is not None and os.path.isdir(self.runs):
			write_json(os.path.join(self.runs, '.waiting.json'), idx)
		return idx

	def _update_waiting_index(self, run):
		if self.runs is None:
			return
		path = os.path.join(self.runs, '.waiting.json')
		with self._lock:
			idx = None
			if os.path.exists(path):
				try:
					data = read_json(path)
					if isinstance(data, dict):
						idx = data
				except (OSError, ValueError):
					idx = None
			if idx is None:
				idx = {}
				for r in self.all_runs():
					if r.get('outcome') is None:
						idx[r['id']] = self._waiting_entry(r)
			if run.get('outcome') is None:
				idx[run['id']] = self._waiting_entry(run)
			else:
				idx.pop(run['id'], None)
			write_json(path, idx)

	def save(self, run):
		self.put(run['id'], 'run', run)
		self._update_waiting_index(run)

	def view_of(self, run):
		'''The flow that a run walks: its pinned copy. The source may have changed since.'''
		with self._lock:
			v = self.views.get(run['id'])
			if v is None:
				pinned = self.get(run['id'], 'flow')
				v = self.views[run['id']] = View(pinned) if pinned else self.view
			return v

	def all_runs(self):
		if self.runs is None:
			with self._lock:
				return [copy.deepcopy(v) for (rid, name), v in sorted(self.files.items(), key=lambda kv: run_sort_key(kv[0][0])) if name == 'run']
		if not os.path.isdir(self.runs):
			return []
		out = []
		for n in sorted(os.listdir(self.runs), key=run_sort_key):
			if n.startswith('.'):
				continue
			d = os.path.join(self.runs, n)
			if not os.path.isdir(d):
				continue
			p = os.path.join(d, 'run.json')
			if os.path.exists(p):
				out.append(read_json(p))
		return out

	# - Rules of a run
	def rules_of(self, run):
		R = Rules(self.view_of(run).c, self.rules.session)
		if run.get('preset'):
			R.preset(run['preset'])
		for rid, v in run.get('rules', {}).items():
			R.set(rid, v)
		return R

	def count_of(self, n, R):
		'''The value of "retry": a number, or the id of a number rule.'''
		if n is None:
			return 0
		return int(R(n)) if isinstance(n, str) else int(n)

	# - Runs
	def run(self, inputs=None, run_id=None, rules=None, preset=None, state=None, at=None, origin=None):
		'''Start a run for one item and walk it as far as code can.'''
		if self.start is None:
			raise Refused('This unit has no flow.')
		inputs = dict(inputs or {})
		ports = self.catalogue.get('in', [])
		names = [x['name'] for x in ports]
		need = [x['name'] for x in ports if not (x.get('type') or '').startswith('(maybe')]
		bad = [k for k in inputs if names and k not in names] + ['missing ' + k for k in need if k not in inputs]
		if bad:
			raise Refused('Inputs: {}. This unit takes: {}.'.format(', '.join(bad), ', '.join(names) or 'nothing'))
		schemas = dict((x['name'], x['schema']) for x in ports if x.get('schema'))
		type_bad = [p for k, v in inputs.items() if k in schemas for p in schema_problems(v, schemas[k], where=k)]
		if type_bad:
			raise Refused('Inputs: {}.'.format('; '.join(type_bad)))
		R = Rules(self.catalogue, self.rules.session)
		if preset:
			R.preset(preset)
		for rid, v in (rules or {}).items():
			R.set(rid, v)  # refuse a bad rule value before the run exists, also before its id is reserved
		run = {'id': run_id or self.new_id(), 'unit': self.catalogue.get('unit'), 'rig': 1, 'started': now(),
			'inputs': inputs, 'rules': dict(rules or {}), 'preset': preset, 'state': copy.deepcopy(state) if state is not None else dict(inputs),
			'at': at or self.start, 'trace': [], 'problems': [], 'guessed': [], 'left': [], 'waiting': None, 'since': None,
			'error': None, 'outcome': None, 'ended': None, 'in_finally': False, 'loops': {}, 'rounds': {}, 'retries': {}, 'answered': {}}
		if origin:
			run['from'] = origin
		self.put(run['id'], 'flow', self.catalogue)  # pin: resume walks this copy, also when the source changes
		self.put(run['id'], 'rules', R.values())
		self.put(run['id'], 'answers', [])
		with self._lock:
			self.views[run['id']] = self.view
		return self.walk(run)

	def walk(self, run):
		V, R = self.view_of(run), self.rules_of(run)
		run['waiting'] = None
		while run['outcome'] is None:
			x = run['at']
			if x is None:
				if run['in_finally']:
					run['outcome'] = run['ended']
					break
				self.finish(run, V, {'end': None, 'label': 'stopped: the flow ran past its last line'})
				continue
			if not run['loops'] and not run['rounds'] and not run['in_finally'] and not self.has_mark(run['id'], x):
				self.put_mark(run['id'], x, run['state'])  # the state before this line: "rerun --from" starts here
			if x in V.blocks:
				self.control(run, V, R, V.blocks[x])
				continue
			node = V.nodes.get(x)
			if node is None:
				self.finish(run, V, {'end': None, 'label': 'stopped: the flow has no node "{}"'.format(x)})
				continue
			nid, kind = node['id'], node['kind']
			if node.get('if') and not truthy(self.see(run['state'], node['if'], cut=False)):
				run['trace'].append({'node': nid, 'kind': kind, 'skipped': True})
				run['at'] = node.get('next')
				continue
			if kind == 'end':
				last = next((t for t in reversed(run['trace']) if not t.get('skipped')), None)
				if last and last['kind'] == 'step' and not run['in_finally']:
					run['result_of'] = last['node']
				run['trace'].append({'node': nid, 'kind': 'end'})
				self.finish(run, V, {'end': nid, 'label': R.fill(node.get('name', nid))})
				continue
			timed = run.pop('timed_out', None)
			if timed and kind in ('hard', 'soft', 'model'):  # the step before gave no result in time: the gate fails
				self.after_gate(run, V, R, node, self.verdict(node, {'pass': False, 'when': 'timeout', 'problems': ['"{}" gave no result in time'.format(timed)]}))
				continue
			fns = self.node_code(node)
			if kind in ('model', 'human') or fns is None:
				run['since'] = run.get('since') or now()
				run['waiting'] = self.waiting(node, R, run)
				break
			try:
				if kind == 'step':
					for fn in fns:
						run['state'][nid] = run_code(fn, run['state'], R, node.get('timeout'))
					run['trace'].append({'node': nid, 'kind': 'step'})
					run['at'] = node.get('next')
				else:
					result = {'pass': True}
					for fn in fns:
						result = run_code(fn, run['state'], R)
						if not passed(result):
							break
					self.after_gate(run, V, R, node, self.verdict(node, result))
			except Refused:
				raise
			except Exception as e:
				text = '{}: {}'.format(type(e).__name__, e)
				run['error'] = {'node': nid, 'error': text, 'trace': traceback.format_exc(limit=3)}
				run['trace'].append({'node': nid, 'kind': kind, 'error': text})
				run['problems'].append('{}: {}'.format(nid, text))
				self.finish(run, V, {'end': 'error', 'label': 'error at "{}": {}'.format(nid, text)})
		self.save(run)
		return self.report(run)

	def finish(self, run, V, outcome):
		'''The run reached an end, an error or a stop. Then "finally" runs, once.'''
		if run['in_finally']:
			if outcome.get('end') == 'error' or outcome.get('end') is None:
				run['problems'].append('finally: ' + outcome['label'])
			run['outcome'] = run['ended']
			return
		if V.final:
			run['ended'], run['in_finally'], run['at'] = outcome, True, V.final
			run['loops'], run['rounds'], run['retries'] = {}, {}, {}
		else:
			run['outcome'] = outcome
			if outcome.get('end') is None:
				run['problems'].append(outcome['label'])

	def control(self, run, V, R, b):
		'''The head of a block: for, until or if.'''
		bid, k = b['id'], b['kind']
		if k == 'for':
			lp = run['loops'].get(bid)
			if lp is None:
				items = self.see(run['state'], b['path'], cut=False)
				if items is not None and not isinstance(items, list):
					run['problems'].append('{}: "{}" is not a list'.format(bid, b['path']))
				items = items if isinstance(items, list) else []
				lp = run['loops'][bid] = {'i': -1, 'n': len(items), 'items': items, 'left': 0}
			lp['i'] += 1
			if lp['i'] < lp['n']:
				run['state'][b['item']] = lp['items'][lp['i']]
				run['trace'].append({'node': bid, 'kind': 'for', 'item': lp['i']})
				run['at'] = b['first']
				self.save(run)  # the progress: a run that stops here goes on from this item
				return
			del run['loops'][bid]
			run['state'].pop(b['item'], None)
			n, left = lp['n'], lp['left']
			entry = {'node': bid, 'kind': 'for', 'done': n, 'left': left}
			if 'tolerate' in b and n and left * 100.0 / n > b['tolerate']:
				entry['pass'] = False
				run['problems'].append('{}: {} of {} items were left, more than {}%'.format(bid, left, n, b['tolerate']))
				run['at'] = b['fail'][0]['to'] if b.get('fail') else b.get('next')
			else:
				run['at'] = b.get('next')
			run['trace'].append(entry)
			return
		if k == 'until':
			r = run['rounds'].get(bid)
			if r is None:
				run['rounds'][bid] = 0
				run['trace'].append({'node': bid, 'kind': 'until', 'round': 0})
				run['at'] = b['first']
				return
			if truthy(self.see(run['state'], b['path'], cut=False)):
				del run['rounds'][bid]
				run['trace'].append({'node': bid, 'kind': 'until', 'pass': True})
				run['at'] = b.get('next')
				return
			if r >= self.count_of(b.get('retry'), R):
				del run['rounds'][bid]
				run['trace'].append({'node': bid, 'kind': 'until', 'pass': False})
				run['problems'].append('{}: "{}" is not true after {} rounds'.format(bid, b['path'], r + 1))
				run['at'] = b['fail'][0]['to'] if b.get('fail') else b.get('next')
				return
			run['rounds'][bid] = r + 1
			run['trace'].append({'node': bid, 'kind': 'until', 'round': r + 1})
			run['at'] = b['first']
			self.save(run)
			return
		if k == 'if':
			ok = truthy(self.see(run['state'], b['path'], cut=False))
			run['trace'].append({'node': bid, 'kind': 'if', 'pass': ok})
			run['at'] = b.get('first') if ok else b.get('else')
			return
		run['at'] = b.get('first')  # section, else, finally: straight into the body

	def see(self, state, path, cut=True):
		'''One path in the state of a run: a step id, an input or a loop item, then keys. A long text is cut.'''
		v = state
		for key in path.split('.'):
			if isinstance(v, dict) and key in v:
				v = v[key]
			elif isinstance(v, list) and key.isdigit() and int(key) < len(v):
				v = v[int(key)]
			else:
				return None
		if cut and isinstance(v, str) and len(v) > self.sees_max:
			v = v[:self.sees_max] + ' … (cut: {} of {} characters)'.format(self.sees_max, len(v))
		return v

	# - Gates
	def verdict(self, node, result, guessed=False):
		'''The result of a gate as a verdict: who decided, pass or fail, and which fail line.'''
		if not isinstance(result, dict):
			result = {'pass': bool(result)}
		v = {'gate': node['id'], 'kind': node['kind'], 'pass': bool(result.get('pass'))}
		if result.get('problems'):
			v['problems'] = [str(p) for p in result['problems']]
		facts = dict((k, x) for k, x in result.items() if k not in ('pass', 'problems', 'when'))
		if facts:
			v['facts'] = facts
		if guessed:
			v['guessed'] = True
		if not v['pass']:
			edges = node.get('fail', [])
			edge = next((e for e in edges if result.get('when') and e.get('when') == result['when']), None) or (edges[0] if edges else None)
			if result.get('when'):
				v['when'] = result['when']
			elif edge and 'when' in edge:
				v['when'] = edge['when']
			v['edge'] = edge
		return v

	def after_gate(self, run, V, R, node, v):
		entry = {'node': v['gate'], 'kind': v['kind'], 'pass': v['pass']}
		for k in ('when', 'problems', 'facts', 'guessed', 'by', 'why'):
			if k in v:
				entry[k] = v[k]
		run['trace'].append(entry)
		nid = node['id']
		cur = run['state'].get(nid)
		if node.get('options') and isinstance(cur, dict) and 'answer' in cur and v['pass']:
			st = dict(cur)
			st['pass'] = v['pass']
			st['failed'] = not v['pass']
		else:
			st = {'pass': v['pass'], 'failed': not v['pass']}
		if 'why' in v:
			st['why'] = v['why']
		run['state'][nid] = st
		if v.get('guessed') and nid not in run['guessed']:
			run['guessed'].append(nid)
		if v['pass']:
			run['retries'].pop(nid, None)
			run['at'] = node.get('next')
			return
		why = '; '.join(v.get('problems', [])) or v.get('when') or v.get('why') or 'failed'
		run['problems'].append('{}: {}'.format(nid, why))
		if node['kind'] == 'soft':  # reported; the flow goes on
			run['at'] = node.get('next')
			return
		left = self.count_of(node.get('retry'), R) - run['retries'].get(nid, 0)
		if left > 0 and node.get('back'):
			run['retries'][nid] = run['retries'].get(nid, 0) + 1
			entry['retry'] = run['retries'][nid]
			run['at'] = node['back']  # do the step before the gate again
			return
		run['retries'].pop(nid, None)
		edge = v.get('edge')
		if edge is None:
			self.finish(run, V, {'end': None, 'label': 'stopped: gate "{}" failed and has no fail line'.format(nid)})
		elif edge.get('continue'):
			lp = run['loops'].get(edge['to'])
			if lp is not None:
				lp['left'] += 1
				run['left'].append({'block': edge['to'], 'item': lp['i'], 'gate': nid, 'why': why})
			run['at'] = edge['to']
		else:
			run['at'] = edge['to']

	# - Waiting and answers
	def waiting(self, node, R, run):
		kind = node['kind']
		w = {'node': node['id'], 'kind': 'model' if kind in ('hard', 'soft') else kind}
		if node.get('name'):
			w['name'] = R.fill(node['name'])
		for k in ('do', 'check'):
			if node.get(k):
				w[k] = R.fill(node[k])
		if node.get('by'):
			w['by'] = node['by']
		if node.get('sees'):
			w['sees'] = dict((p, v) for p, v in ((p, self.see(run['state'], p)) for p in node['sees']) if v is not None)
		if kind in ('hard', 'soft'):
			w['no_code'] = 'No code decides this gate yet. Decide it yourself; the result is a guess.'
		if node.get('options'):
			w['options'], w['default'] = node['options'], node['options'][0]
		if node.get('schema'):
			w['out'], w['schema'] = node.get('out'), node['schema']
		if node.get('timeout'):
			w['timeout'] = node.get('timeout_text')
			w['since'] = run.get('since')
		pos = dict((b, lp['i']) for b, lp in run['loops'].items())
		if pos:
			w['item'] = pos
		mark = run.get('answered', {}).get(node['id'])
		if mark is not None and run['problems'][mark:]:
			w['problems'] = run['problems'][mark:]  # what failed after the last answer at this node: fix it
		if kind == 'step':
			w['answer'] = '{"result": <what the step gave>}'
		elif kind == 'human':
			w['answer'] = 'a person answers: approve <run> ' + ('<words>; only "approve <run>" or "yes" takes the default "{}"'.format(node['options'][0]) if node.get('options') else 'yes|no')
			run_id = run.get('id', '<run>')  # with the run id: when more than one run waits, a message without it is refused
			replies = ['approve {} {}'.format(run_id, o) for o in node['options']] if node.get('options') else ['approve {} yes'.format(run_id), 'approve {} no'.format(run_id)]
			if node.get('options') and node.get('fail') and 'no' not in [str(o) for o in node['options']]:
				replies.append('approve {} no'.format(run_id))
			w['say'] = 'To answer, write one of these messages: {}.'.format(', '.join(replies)) + \
				(' The first one is the default.' if node.get('options') else '')  # the exact words for the person: a model shows them as they are
		else:
			w['answer'] = '{"pass": true or false, "why": "<one sentence>"}'
		return w

	def expire(self, run):
		'''A node that waits longer than its timeout: a step gives no result, a gate fails with the
		reason "timeout". -> True when the run went on.'''
		if run['outcome'] is not None or not run.get('since'):
			return False
		V = self.view_of(run)
		node = V.nodes.get(run['at'])
		if not node or not node.get('timeout') or age(run['since']) <= node['timeout']:
			return False
		R = self.rules_of(run)
		run['since'] = None
		if node['kind'] == 'step':
			run['answered'][node['id']] = len(run['problems'])  # when the step waits again, it shows why
			run['state'][node['id']] = None
			run['timed_out'] = node['id']
			run['trace'].append({'node': node['id'], 'kind': 'step', 'timeout': True})
			run['problems'].append('{}: no result in {}'.format(node['id'], node.get('timeout_text')))
			run['at'] = node.get('next')
		else:
			self.after_gate(run, V, R, node, self.verdict(node, {'pass': False, 'when': 'timeout', 'problems': ['no answer in {}'.format(node.get('timeout_text'))]}))
		self.walk(run)
		return True

	def answer(self, run_id, answer, who='model', node=None, meta=None):
		'''Give the answer for the node that the run waits at, then walk on.
		who: "model" or "person". Only a person answers a human gate.'''
		if meta is not None and not isinstance(meta, dict):
			raise Refused('meta must be a JSON object.')
		run = self.load(run_id)
		if run['outcome'] is not None:
			raise Refused('Run {} ended at "{}". Start a new run.'.format(run_id, run['outcome']['end']))
		if self.expire(run):
			raise Refused('The time of "{}" ran out before this answer: the run went on without it. Call status.'.format(node or 'the node'))
		V, R = self.view_of(run), self.rules_of(run)
		cur = V.nodes.get(run['at'])
		if cur is None:
			raise Refused('Run {} does not wait for an answer. Call status.'.format(run_id))
		if node and node != cur['id']:
			raise Refused('Run {} waits at "{}", not at "{}".'.format(run_id, cur['id'], node))
		kind = cur['kind']
		if kind == 'human' and who != 'person':
			raise Refused('"{}" is a human gate: a person decides it. Ask the person; they answer with approve.'.format(cur['id']))
		if kind in ('step', 'hard', 'soft') and self.node_code(cur) is not None:
			raise Refused('"{}" is done by code. Do not answer it.'.format(cur['id']))
		if not isinstance(answer, dict):
			raise Refused('The answer must be a JSON object.')
		nid = cur['id']
		if kind == 'step' and 'result' not in answer:
			raise Refused('"{}" is a step: answer with {{"result": ...}}.'.format(nid))
		options = kind == 'human' and cur.get('options')
		if kind != 'step' and not options and not isinstance(answer.get('pass'), bool):
			raise Refused('"{}" is a gate: answer with {{"pass": true}} or {{"pass": false}}.'.format(nid))
		log = self.get(run_id, 'answers', []) or []
		entry = {'node': nid, 'who': who, 'answer': answer, 'time': now(), 'item': dict((b, lp['i']) for b, lp in run['loops'].items())}
		if meta:
			entry['meta'] = dict(meta)
		log.append(entry)
		self.put(run_id, 'answers', log)
		run['since'] = None
		if kind == 'step':
			bad = schema_problems(answer['result'], cur.get('schema'))
			if bad:  # not the form of "out": the step waits again, with the problems
				run['answered'][nid] = len(run['problems'])
				err = str(meta['error']).strip() if isinstance(meta, dict) and meta.get('error') else ''
				detail = '{}; {}'.format(err, '; '.join(bad)) if err else '; '.join(bad)
				run['problems'].append('{}: the result does not have the form of out {}: {}'.format(nid, cur.get('out'), detail))
				run['trace'].append({'node': nid, 'kind': 'step', 'by': who, 'pass': False})
				return self.walk(run)
			run['state'][nid] = answer['result']
			run['trace'].append({'node': nid, 'kind': 'step', 'by': who})
			run['answered'][nid] = len(run['problems'])
			run['at'] = cur.get('next')
		elif options:
			if answer.get('pass') is False and cur.get('fail'):
				v = self.verdict(cur, {'pass': False, 'when': answer.get('when')})
				v['by'] = who
				self.after_gate(run, V, R, cur, v)
			else:
				text = str(answer.get('answer') or '').strip() or cur['options'][0]  # "only accept": the default
				run['state'][nid] = {'answer': text}
				result = {'pass': True}
				for fn in self.node_code(cur) or []:
					result = run_code(fn, run['state'], R)
					if not passed(result):
						break
				v = self.verdict(cur, result)
				v['by'] = who
				if v['pass']:
					run['state'][nid] = dict(run['state'][nid], **(v.get('facts') or {}))
					self.after_gate(run, V, R, cur, v)
				else:  # not understood: ask again
					run['answered'][nid] = len(run['problems'])
					run['problems'].append('{}: the answer "{}" is not understood: {}'.format(nid, text, '; '.join(v.get('problems', [])) or 'ask again'))
					run['trace'].append({'node': nid, 'kind': kind, 'pass': False, 'by': who, 'again': True})
					return self.walk(run)
			run['answered'][nid] = len(run['problems'])
		else:
			v = self.verdict(cur, dict((k, answer[k]) for k in ('pass', 'when', 'problems') if k in answer), guessed=(who != 'person'))
			v['by'] = who
			if answer.get('why'):
				v['why'] = str(answer['why'])
			self.after_gate(run, V, R, cur, v)
			run['answered'][nid] = len(run['problems'])
		return self.walk(run)

	def work(self, run_id, api_url=None, model=None, api_key=None, think=False, max_tokens=4000, max_calls=50, timeout_s=120, on_progress=None, request_fn=None):
		'''Run model steps (kind "step" with a schema) of one run in isolated fresh contexts via an
		OpenAI-compatible /chat/completions endpoint. Standard library only.'''
		api_url = (api_url or os.environ.get('RIG_API_URL') or '').strip()
		model = (model or os.environ.get('RIG_MODEL') or '').strip()
		api_key = api_key if api_key is not None else os.environ.get('RIG_API_KEY')
		if not api_url:
			raise Refused('work needs --api-url URL (or RIG_API_URL).')
		if not model:
			raise Refused('work needs --model NAME (or RIG_MODEL).')
		max_tokens = int(max_tokens)
		max_calls = int(max_calls)
		timeout_s = float(timeout_s)
		url = api_url.rstrip('/') + '/chat/completions'
		headers = {'Content-Type': 'application/json'}
		if api_key:
			headers['Authorization'] = 'Bearer ' + str(api_key)
		send = request_fn or _http_post
		r = self.status(run_id)
		done = []
		same, last = 0, ''
		for n in range(max_calls):
			w = r.get('waiting')
			if not (isinstance(w, dict) and w.get('kind') == 'step' and w.get('schema')):
				break
			where = '{} {}'.format(w['node'], json.dumps(w.get('item') or {}, sort_keys=True))
			same = same + 1 if where == last else 0
			last = where
			if same >= 5:
				break
			if on_progress is not None:
				suffix = ' ' + json.dumps(w['item'], ensure_ascii=False) if w.get('item') else ''
				on_progress('{}: job {}{}'.format(w['node'], n + 1, suffix))
			payload = {
				'model': model,
				'messages': [
					{'role': 'system', 'content': WORK_RULES},
					{'role': 'user', 'content': _work_job_text(w)},
				],
				'max_tokens': max_tokens,
				'temperature': 0.6 if think else 0.2,
			}
			if not think:
				payload['response_format'] = {
					'type': 'json_schema',
					'json_schema': {
						'name': 'rig_job',
						'strict': True,
						'schema': {
							'type': 'object',
							'properties': {'result': w['schema']},
							'required': ['result'],
							'additionalProperties': False,
						},
					},
				}
			t0 = time.monotonic()
			parsed_result = None
			got_result = False
			tokens = None
			error_reason = None
			try:
				resp = send(url, headers, payload, timeout_s)
				choices = resp.get('choices') if isinstance(resp, dict) else None
				choice = choices[0] if isinstance(choices, list) and choices else {}
				finish_reason = choice.get('finish_reason') if isinstance(choice, dict) else None
				usage = resp.get('usage') if isinstance(resp, dict) else None
				if isinstance(usage, dict) and 'completion_tokens' in usage:
					tokens = usage['completion_tokens']
				msg = choice.get('message') if isinstance(choice, dict) else None
				raw_content = msg.get('content') if isinstance(msg, dict) else None
				hit_cap = (finish_reason == 'length') or (isinstance(tokens, int) and tokens >= max_tokens)
				if not isinstance(raw_content, str) or not raw_content.strip():
					error_reason = (
						'hit max_tokens ({}) before finishing valid JSON; keep values shorter'.format(max_tokens)
						if hit_cap else 'model returned empty content'
					)
				else:
					text = _json_in(re.sub(r'<think>.*?</think>', '', raw_content, flags=re.S)) if think else raw_content
					try:
						parsed = json.loads(text)
					except ValueError:
						error_reason = (
							'hit max_tokens ({}) before finishing valid JSON; keep values shorter'.format(max_tokens)
							if hit_cap else 'response was not valid JSON'
						)
					else:
						if isinstance(parsed, dict) and 'result' in parsed:
							parsed_result = parsed['result']
							got_result = True
						else:
							error_reason = (
								'hit max_tokens ({}) before finishing valid JSON; keep values shorter'.format(max_tokens)
								if hit_cap else 'response JSON had no "result" field'
							)
			except Exception as e:
				error_reason = 'model call failed: {}: {}'.format(type(e).__name__, e)
			seconds = round(time.monotonic() - t0, 1)
			meta = {'model': model, 'seconds': seconds}
			if tokens is not None:
				meta['tokens'] = tokens
			if error_reason:
				meta['error'] = error_reason
			r = self.answer(run_id, {'result': parsed_result}, node=w['node'], meta=meta)
			entry = {'node': w['node'], 'seconds': seconds, 'ok': got_result}
			if 'item' in w:
				entry['item'] = w['item']
			if tokens is not None:
				entry['tokens'] = tokens
			done.append(entry)
		out = dict(r)
		out['work'] = {'jobs': len(done), 'seconds': round(sum(d['seconds'] for d in done), 1), 'each': done}
		return out

	def approve(self, run_id, words):
		'''The answer of a person: "yes" or "no" for a yes/no gate; for a gate with options, the
		words of the answer ("yes" or nothing: the default; "no": the fail line, when there is one).'''
		run = self.load(run_id)
		node = self.view_of(run).nodes.get(run['at'], {})
		text = ' '.join(words).strip()
		if node.get('options'):
			low = text.lower()
			if low == 'no' and node.get('fail'):
				return self.answer(run_id, {'pass': False}, who='person')
			return self.answer(run_id, {'answer': '' if low in ('', 'yes') else text}, who='person')
		word = (words[0] if words else '').strip().lower()
		if word not in ('yes', 'no'):
			raise Refused('approve RUN yes|no [NOTE]')
		a = {'pass': word == 'yes'}
		if len(words) > 1:
			a['why'] = ' '.join(words[1:])
		return self.answer(run_id, a, who='person')

	def resume(self, run_id):
		'''Walk on after a stop of the process. A run that waits for an answer stays where it is.'''
		run = self.load(run_id)
		if run['outcome'] is not None:
			return self.report(run)
		if self.expire(run):
			return self.report(self.load(run_id))
		return self.walk(run)

	def status(self, run_id):
		run = self.load(run_id)
		if self.expire(run):
			run = self.load(run_id)
		node = self.view_of(run).nodes.get(run['at'])
		if run['outcome'] is None and run.get('waiting') and node:
			run['waiting'] = self.waiting(node, self.rules_of(run), run)  # composed again: a fixed text of the runner reaches a waiting run too
		return self.report(run)

	def drop(self, run_id, reason=None):
		'''End a waiting run as dropped so it leaves the queues.'''
		run = self.load(run_id)
		if run['outcome'] is not None:
			raise Refused('Run {} already ended at "{}".'.format(run_id, run['outcome'].get('end')))
		why = (reason or '').strip() or 'dropped'
		run['outcome'] = {'end': 'dropped', 'label': why}
		run['waiting'] = None
		run['since'] = None
		run['trace'].append({'node': 'dropped', 'kind': 'end', 'why': why})
		self.save(run)
		return self.report(run)

	def list_runs(self, limit=50):
		'''List runs, newest first.'''
		limit = max(0, int(limit))
		runs = sorted(self.all_runs(), key=lambda r: (r.get('started') or '', run_sort_key(r.get('id'))), reverse=True)
		out = []
		for r in runs[:limit]:
			ended = r.get('outcome') is not None
			entry = {'run': r['id'], 'started': r.get('started'), 'state': 'ended' if ended else 'waiting', 'inputs': r.get('inputs', {})}
			if ended:
				entry['end'] = r['outcome'].get('end') or r['outcome'].get('label')
			else:
				w = r.get('waiting')
				if isinstance(w, dict):
					entry['waiting'] = {'node': w.get('node', r.get('at')), 'kind': w.get('kind')}
				else:
					node = self.view_of(r).nodes.get(r.get('at'), {})
					entry['waiting'] = {'node': r.get('at'), 'kind': node.get('kind')}
			out.append(entry)
		return out

	def prune(self, keep=20):
		'''Remove finished runs beyond the newest "keep" finished runs. Never removes waiting runs.'''
		keep = max(0, int(keep))
		runs = self.all_runs()
		waiting = [r for r in runs if r.get('outcome') is None]
		finished = sorted([r for r in runs if r.get('outcome') is not None],
			key=lambda r: (r.get('started') or '', run_sort_key(r.get('id'))), reverse=True)
		to_keep, to_remove = finished[:keep], finished[keep:]
		removed = []
		with self._lock:
			for r in to_remove:
				rid = r['id']
				if self.runs is None:
					for k in [k for k in self.files if k[0] == rid]:
						del self.files[k]
				else:
					shutil.rmtree(self.folder(rid), ignore_errors=True)
				self.views.pop(rid, None)
				removed.append(rid)
		return {'removed': removed, 'kept': len(to_keep) + len(waiting)}

	def rerun(self, run_id, node, changes=None):
		'''A new run with the state of an old run before one of its top lines; changed rules for it.'''
		old = self.load(run_id)
		state = self.get_mark(run_id, node)
		if state is None:
			names = self.mark_names(run_id)
			raise Refused('Run {} has no state before "{}". It has one before each line outside a loop that it reached: {}.'.format(run_id, node, ', '.join(names) or 'none'))
		if node not in self.view.nodes and node not in self.view.blocks:
			raise Refused('The flow has no line "{}" now.'.format(node))
		rules = dict(old.get('rules', {}))
		rules.update(changes or {})
		return self.run(old['inputs'], rules=rules, preset=old.get('preset'), state=state, at=node, origin={'run': run_id, 'from': node})

	def report(self, run):
		out = {'run': run['id'], 'at': run['at']}
		for k in ('outcome', 'waiting'):
			if run.get(k):
				out[k] = dict(run[k])
		if run.get('error'):
			out['error'] = dict((k, v) for k, v in run['error'].items() if k != 'trace')
		if 'outcome' in out and run.get('result_of') and run['state'].get(run['result_of']) is not None:
			out['result'] = run['state'][run['result_of']]  # the value of the step before the end
		out['problems'], out['guessed'] = run['problems'], run['guessed']
		if run.get('left'):
			out['left'] = run['left']
		if run.get('from'):
			out['from'] = run['from']
		if run['outcome'] is None:
			pinned = self.view_of(run).c
			if pinned and pinned != self.catalogue:
				out['note'] = 'The flow changed since this run started. The run goes on with its own copy of the flow.'
		out['path'] = [t['node'] for t in run['trace'] if not t.get('skipped')]
		return out

	# - Batches and queues: code runs the list; the model gets a summary and the runs that wait
	def row(self, r, inputs):
		row = {'run': r['run'], 'inputs': inputs, 'problems': r['problems']}
		if 'outcome' in r:
			if r['outcome'].get('end') == 'error':
				row['error'] = (r.get('error') or {}).get('error') or r['outcome']['label']
			row['end'] = r['outcome']['end'] or r['outcome']['label']
		elif 'waiting' in r:
			row['waiting'] = {'node': r['waiting']['node'], 'kind': r['waiting']['kind']}
		return row

	def batch(self, items, rules=None, preset=None, report=None, workers=1):
		'''Start a run for each item of a list. -> a short summary. An item that needs the model or a
		person does not stop the batch: its run waits, and "queues" lists it.'''
		rows, in_row, stopped = [], 0, None
		workers = int(workers)
		def one(inputs):
			try:
				return self.row(self.run(inputs, rules=rules, preset=preset), inputs)
			except Refused as e:
				return {'run': None, 'inputs': inputs, 'problems': [], 'refused': str(e)}
		if workers <= 1:
			for inputs in items:
				row = one(inputs)
				rows.append(row)
				in_row = in_row + 1 if 'error' in row else 0
				if in_row >= self.errors_stop:
					stopped = 'stopped after {} errors in a row: {} of {} items started'.format(in_row, len(rows), len(items))
					break
		else:
			with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
				for start in range(0, len(items), workers):
					chunk = items[start:start + workers]
					futs = [pool.submit(one, item) for item in chunk]
					hit_stop = False
					for fut in futs:
						row = fut.result()
						rows.append(row)
						in_row = in_row + 1 if 'error' in row else 0
						if in_row >= self.errors_stop:
							hit_stop = True
					if hit_stop:
						stopped = 'stopped after {} errors in a row: {} of {} items started'.format(in_row, len(rows), len(items))
						break
		ends = {}
		for row in rows:
			if 'end' in row:
				ends[row['end']] = ends.get(row['end'], 0) + 1
		out = {'items': len(items), 'started': len(rows), 'ends': ends,
			'left_for_model': [r['run'] for r in rows if r.get('waiting', {}).get('kind') in ('model', 'step')],
			'waits_for_person': [r['run'] for r in rows if r.get('waiting', {}).get('kind') == 'human'],
			'errors': [{'run': r['run'], 'error': r['error']} for r in rows if 'error' in r],
			'refused': [{'inputs': r['inputs'], 'refused': r['refused']} for r in rows if 'refused' in r]}
		if stopped:
			out['stopped'] = stopped
		if report:
			self.write_report(report, rows, out)
			out['report'] = report
		return out

	def write_report(self, path, rows, summary):
		'''A batch report as Markdown: what failed first, then what waits, then the rest.'''
		def cell(v):
			return str(v).replace('|', '\\|').replace('\n', ' ')
		bad = [r for r in rows if 'error' in r or 'refused' in r]
		problems = [r for r in rows if r.get('problems') and r not in bad]
		waits = [r for r in rows if 'waiting' in r and r not in problems]
		clean = [r for r in rows if r not in bad and r not in problems and r not in waits]
		L = ['# Batch report: {}'.format(self.catalogue.get('unit')), '', now(), '',
			'{} of {} items started. Ends: {}. Left for the model: {}. Waits for a person: {}. Errors: {}.'.format(summary['started'], summary['items'],
				', '.join('{} {}'.format(n, e) for e, n in sorted(summary['ends'].items())) or 'none', len(summary['left_for_model']), len(summary['waits_for_person']), len(summary['errors'])), '']
		if summary.get('stopped'):
			L += ['**{}**'.format(summary['stopped']), '']
		for title, part in (('Errors and refused items', bad), ('Items with problems', problems), ('Items that wait, with no problem so far', waits), ('Items with no problem', clean)):
			if not part:
				continue
			L += ['## ' + title, '', '| Run | Inputs | State | Problems |', '|---|---|---|---|']
			for r in part:
				state = r.get('error') or r.get('end') and 'end: ' + str(r['end']) or r.get('refused') or 'waits at {} ({})'.format(r['waiting']['node'], r['waiting']['kind'])
				L.append('| {} | {} | {} | {} |'.format(r['run'] or '-', cell(json.dumps(r['inputs'], ensure_ascii=False)), cell(state), cell('; '.join(r.get('problems', [])))))
			L.append('')
		os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
		with open(path, 'w', encoding='utf-8', newline='\n') as f:
			f.write('\n'.join(L))

	def queues(self):
		'''The runs that did not end, by who must act: the model or a person.'''
		out = {'left_for_model': [], 'waits_for_person': []}
		if self.runs is None:
			runs = [r for r in self.all_runs() if r.get('outcome') is None]
		else:
			path = os.path.join(self.runs, '.waiting.json')
			idx = None
			if os.path.exists(path):
				try:
					data = read_json(path)
					if isinstance(data, dict):
						idx = data
				except (OSError, ValueError):
					idx = None
			if idx is None:
				idx = self._rebuild_waiting_index()
			runs, stale = [], []
			for rid in sorted(idx, key=run_sort_key):
				run = self.get(rid, 'run')
				if run is None or run.get('outcome') is not None:
					stale.append(rid)
					continue
				runs.append(run)
			if stale:
				with self._lock:
					for rid in stale:
						idx.pop(rid, None)
					write_json(path, idx)
		for run in runs:
			if self.expire(run):
				run = self.load(run['id'])
				if run.get('outcome') is not None:
					continue
			node = self.view_of(run).nodes.get(run['at'], {})
			entry = {'run': run['id'], 'node': run['at'], 'inputs': run['inputs']}
			if node.get('name'):
				entry['name'] = node['name']
			(out['waits_for_person'] if node.get('kind') == 'human' else out['left_for_model']).append(entry)
		return out

	# - Tools (units with one function)
	def call(self, name, args):
		if name not in self.tools:
			raise Refused('No tool {}. Tools: {}.'.format(name, ', '.join(sorted(self.tools)) or 'none'))
		c, fn = self.tools[name]
		ports = c.get('in', [])
		names = [x['name'] for x in ports]
		need = [x['name'] for x in ports if not (x.get('type') or '').startswith('(maybe')]
		bad = [k for k in args if k not in names] + ['missing ' + k for k in need if k not in args]
		if bad:
			raise Refused('{}: {}. It takes: {}.'.format(name, ', '.join(bad), ', '.join(names) or 'nothing'))
		schemas = dict((x['name'], x['schema']) for x in ports if x.get('schema'))
		type_bad = [p for k, v in args.items() if k in schemas for p in schema_problems(v, schemas[k], where=k)]
		if type_bad:
			raise Refused('{}: {}.'.format(name, '; '.join(type_bad)))
		return fn(**args)

	# - Flow tests: play recorded or written answers, with no model
	def play(self, r, pending):
		'''Answer what waits from a list of {"node", "who", "answer"}, in order, until none fits.'''
		while 'waiting' in r:
			at = r['waiting']['node']
			k = next((i for i, a in enumerate(pending) if a['node'] == at), None)
			if k is None:
				break
			a = pending.pop(k)
			r = self.answer(r['run'], a['answer'], who=a.get('who', 'model'))
		return r

	def replay(self, run_id):
		'''Run the flow of an old run again, with the current code, and its recorded answers. -> the
		differences of the end and the path. A flow test: no model, no person.'''
		old = self.load(run_id)
		answers = self.get(run_id, 'answers', []) or []
		start = (old.get('from') or {}).get('from')
		state = self.get_mark(run_id, start) if start else None
		if old.get('from') and state is None:
			raise Refused('Run {} has no saved state for its start "{}".'.format(run_id, start))
		want = self.report(old)
		keep, self.runs = self.runs, None
		try:
			r = self.play(self.run(old['inputs'], rules=old.get('rules'), preset=old.get('preset'), state=state, at=start), [dict(a) for a in answers])
		finally:
			self.runs = keep
		got_end = (r.get('outcome') or {}).get('end')
		want_end = (want.get('outcome') or {}).get('end')
		diffs = []
		if got_end != want_end:
			diffs.append('end: {!r}, recorded {!r}'.format(got_end, want_end))
		if r['path'] != want['path']:
			k = next((i for i, (a, b) in enumerate(zip(r['path'], want['path'])) if a != b), min(len(r['path']), len(want['path'])))
			diffs.append('path: they part after {} lines: now {}, recorded {}'.format(k, r['path'][k:k + 3], want['path'][k:k + 3]))
		if 'waiting' in r:
			diffs.append('waits at "{}": no recorded answer fits'.format(r['waiting']['node']))
		return {'run': run_id, 'answers': len(answers), 'end': got_end, 'path': len(r['path']), 'differences': diffs}

	def regress(self, cases):
		'''cases: [{"name", "inputs", "answers": {node: answer or [answers]}, "rules", "preset", "expect": {"end", "path"}}].
		-> (results, differences). A person answer is written as {"person": true, "pass": ...}.'''
		keep, self.runs = self.runs, None
		results, diffs = [], []
		try:
			for case in cases:
				pending = []
				for nid, v in case.get('answers', {}).items():
					for a in (v if isinstance(v, list) else [v]):
						a = dict(a)
						pending.append({'node': nid, 'who': 'person' if a.pop('person', False) else 'model', 'answer': a})
				r = self.play(self.run(case.get('inputs'), rules=case.get('rules'), preset=case.get('preset')), pending)
				got = {'end': (r.get('outcome') or {}).get('end'), 'path': r['path']}
				if 'waiting' in r:
					got['waiting'] = r['waiting']['node']
				if r.get('error'):
					got['error'] = r['error']['error']
				results.append({'name': case.get('name'), 'got': got})
				for k, want in (case.get('expect') or {}).items():
					if got.get(k) != want:
						diffs.append('{}: {} is {!r}, expected {!r}'.format(case.get('name'), k, got.get(k), want))
		finally:
			self.runs = keep
		return results, diffs

	def serve_stdio(self, stdin=None, out=None):
		'''JSON-lines request/response loop over stdin/stdout, keeping this process and loaded modules warm.'''
		inp = stdin if stdin is not None else sys.stdin

		def emit(obj):
			line = json.dumps(obj, ensure_ascii=False, default=str)
			if out is not None:
				out(line)
			else:
				sys.stdout.write(line + '\n')
				sys.stdout.flush()

		for raw in inp:
			if not raw.strip():
				continue
			try:
				req = json.loads(raw)
			except ValueError:
				emit({'id': None, 'code': 1, 'result': {'refused': 'Bad request JSON'}})
				continue
			if not isinstance(req, dict) or not isinstance(req.get('argv'), list) or not all(isinstance(a, str) for a in req['argv']):
				emit({'id': req.get('id') if isinstance(req, dict) else None, 'code': 1, 'result': {'refused': 'Bad request JSON'}})
				continue
			req_id, req_argv = req.get('id'), req['argv']
			if req_argv and req_argv[0] in ('serve-stdio', 'mcp'):
				emit({'id': req_id, 'code': 0, 'result': {'refused': 'Already in serve-stdio.'}})
				continue
			captured = []
			code = self.cli(req_argv, out=captured.append)
			parsed = None
			for line in reversed(captured):
				s = line.strip()
				if not s:
					continue
				try:
					parsed = json.loads(s)
				except ValueError:
					parsed = s
				break
			emit({'id': req_id, 'code': code, 'result': parsed})
		return 0

	def _mcp_tools(self, has_worker):
		'''Build the MCP tool list and level-1 call map. Never exposes a tool for human gates.'''
		tools, call_map = [], {}
		if self.start is not None:
			flow_nodes = self.catalogue.get('flow', [])
			in_schema = _input_schema(self.catalogue.get('in', []))
			intent = self.rules.fill(self.catalogue.get('intent') or '')
			run_prop = {'type': 'string', 'description': 'The run id: "run" in the result of start_run.'}
			tools.append({
				'name': 'start_run',
				'description': 'Start a run for one item{}. Code does the work and stops when it needs you.'.format(': ' + intent if intent else ''),
				'inputSchema': in_schema,
			})
			has_model_gate = any(
				n.get('kind') == 'model' or (n.get('kind') in ('hard', 'soft') and not n.get('by'))
				for n in flow_nodes
			)
			if has_model_gate:
				tools.append({
					'name': 'answer_gate',
					'description': 'Answer the gate that a run waits at, when "waiting" has kind "model". Decide what its "check" says.',
					'inputSchema': {
						'type': 'object',
						'properties': {
							'run': run_prop,
							'pass': {'type': 'boolean', 'description': 'true: the gate passes. false: it fails.'},
							'why': {'type': 'string', 'description': 'The reason, in one sentence.'},
						},
						'required': ['run', 'pass'],
					},
				})
			model_steps = [n for n in flow_nodes if n.get('kind') == 'step' and n.get('lane') == 'model']
			if model_steps:
				names_text = ', '.join(n['id'] for n in model_steps)
				if has_worker:
					tools.append({
						'name': 'work_run',
						'description': 'Do the model steps of a run ({}) in isolated worker contexts until the run needs you or a person.'.format(names_text),
						'inputSchema': {
							'type': 'object',
							'properties': {'run': run_prop},
							'required': ['run'],
						},
					})
				else:
					tools.append({
						'name': 'answer_step',
						'description': 'Give the result of a model step ({}) when "waiting" has kind "step".'.format(names_text),
						'inputSchema': {
							'type': 'object',
							'properties': {
								'run': run_prop,
								'result': {'description': 'The step result matching "waiting.schema".'},
								'node': {'type': 'string', 'description': 'Optional step id to guard against stale calls.'},
							},
							'required': ['run', 'result'],
						},
					})
			tools.append({
				'name': 'run_status',
				'description': 'Show a run again: where it is and what it waits for.',
				'inputSchema': {'type': 'object', 'properties': {'run': run_prop}, 'required': ['run']},
			})
			tools.append({
				'name': 'start_batch',
				'description': 'Start a run for each item of a list. Gives a short summary.',
				'inputSchema': {
					'type': 'object',
					'properties': {
						'items': {'type': 'array', 'items': in_schema, 'description': 'One object for each item, with the inputs of start_run.'},
						'workers': {'type': 'integer', 'description': 'Parallel worker threads (default 1).'},
					},
					'required': ['items'],
				},
			})
			tools.append({
				'name': 'queues',
				'description': 'The runs that did not end: left_for_model and waits_for_person.',
				'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
			})
			tools.append({
				'name': 'drop_run',
				'description': 'Mark a waiting run as dropped so it leaves the queues.',
				'inputSchema': {
					'type': 'object',
					'properties': {
						'run': run_prop,
						'reason': {'type': 'string', 'description': 'Optional reason for dropping the run.'},
					},
					'required': ['run'],
				},
			})
		for unit_name, (c, _) in self.tools.items():
			tool_name = unit_name.replace('-', '_')
			desc = c.get('intent') or unit_name
			ret = c.get('out') or {}
			if ret.get('text'):
				desc = desc + '. It gives back: ' + ret['text']
			call_map[tool_name] = unit_name
			tools.append({
				'name': tool_name,
				'description': desc,
				'inputSchema': _input_schema(c.get('in', [])),
			})
		return tools, call_map

	def mcp(self, api_url=None, model=None, api_key=None, think=False, max_tokens=4000, max_calls=50, timeout_s=120, stdin=None, stdout=None):
		'''Run a newline-delimited JSON-RPC 2.0 MCP server over stdin/stdout. Standard library only.'''
		inp = stdin if stdin is not None else sys.stdin
		out_stream = stdout if stdout is not None else sys.stdout
		eff_api_url = (api_url or os.environ.get('RIG_API_URL') or '').strip()
		eff_model = (model or os.environ.get('RIG_MODEL') or '').strip()
		eff_api_key = api_key if api_key is not None else os.environ.get('RIG_API_KEY')
		has_worker = bool(eff_api_url and eff_model)
		tools, call_map = self._mcp_tools(has_worker)
		exposed = set(t['name'] for t in tools)

		def send(obj):
			line = json.dumps(obj, ensure_ascii=False, default=str)
			if callable(out_stream):
				out_stream(line)
			else:
				out_stream.write(line + '\n')
				out_stream.flush()

		for raw in inp:
			if not raw.strip():
				continue
			try:
				req = json.loads(raw)
			except ValueError:
				send({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}})
				continue
			if not isinstance(req, dict):
				send({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid Request'}})
				continue
			if 'id' not in req:
				continue
			req_id = req['id']
			method = req.get('method')
			params = req.get('params')
			if params is None:
				params = {}
			if method == 'initialize':
				proto = params.get('protocolVersion') if isinstance(params, dict) else None
				send({
					'jsonrpc': '2.0',
					'id': req_id,
					'result': {
						'protocolVersion': proto or '2024-11-05',
						'capabilities': {'tools': {}},
						'serverInfo': {'name': self.catalogue.get('unit') or 'rig', 'version': '1'},
					},
				})
			elif method == 'ping':
				send({'jsonrpc': '2.0', 'id': req_id, 'result': {}})
			elif method == 'tools/list':
				send({'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': tools}})
			elif method == 'tools/call':
				try:
					if not isinstance(params, dict):
						raise Refused('tools/call params must be an object.')
					name = params['name']
					args = params.get('arguments')
					if args is None:
						args = {}
					if not isinstance(args, dict):
						raise Refused('Tool arguments must be an object.')
					if name not in exposed:
						raise Refused('Unknown tool {}.'.format(name))
					if name == 'start_run':
						res = self.run(args)
					elif name == 'answer_gate':
						ans = {'pass': args['pass']}
						if args.get('why') is not None:
							ans['why'] = args['why']
						res = self.answer(args['run'], ans)
					elif name == 'work_run':
						res = self.work(
							args['run'],
							api_url=eff_api_url,
							model=eff_model,
							api_key=eff_api_key,
							think=think,
							max_tokens=max_tokens,
							max_calls=max_calls,
							timeout_s=timeout_s,
						)
					elif name == 'answer_step':
						if 'result' not in args:
							raise Refused('answer_step requires "result".')
						res = self.answer(args['run'], {'result': args['result']}, node=args.get('node'))
					elif name == 'run_status':
						res = self.status(args['run'])
					elif name == 'start_batch':
						items = args['items']
						if not isinstance(items, list):
							raise Refused('start_batch: "items" must be a list.')
						res = self.batch(items, workers=args.get('workers', 1))
					elif name == 'queues':
						res = self.queues()
					elif name == 'drop_run':
						res = self.drop(args['run'], args.get('reason'))
					elif name in call_map:
						res = {'ok': True, 'tool': call_map[name], 'result': self.call(call_map[name], args)}
					else:
						raise Refused('Unknown tool {}.'.format(name))
				except (Refused, ValueError, KeyError) as e:
					res = {'refused': str(e)}
				res = _mcp_decorate(res, has_worker)
				send({
					'jsonrpc': '2.0',
					'id': req_id,
					'result': {
						'content': [{'type': 'text', 'text': json.dumps(res, ensure_ascii=False, default=str)}],
						'isError': False,
					},
				})
			else:
				send({'jsonrpc': '2.0', 'id': req_id, 'error': {'code': -32601, 'message': 'Method not found'}})
		return 0

	# - Command line: one JSON line for each call
	def cli(self, argv, out=None):
		'''run [JSON] [--preset N] [--set id=value]... | batch ITEMS [--report PATH] [--workers N] [--preset N] [--set id=value]...
		| queues | answer RUN JSON [--node ID] [--meta JSON] | work RUN [--api-url URL] [--model NAME] [--api-key KEY] [--think] [--max-tokens N] [--max-calls N]
		| approve RUN [yes|no|WORDS] | resume RUN | status RUN | drop RUN [REASON...] | list [--limit N] | prune [--keep N]
		| rerun RUN --from ID [--set id=value]... | replay RUN | rules | flow | call TOOL [JSON]
		| regress FILE [--baseline] | serve-stdio | mcp [--api-url URL] [--model NAME] [--api-key KEY] [--think] [--max-tokens N] [--max-calls N]        ITEMS: a JSON list of inputs, or a file with one'''
		raw_out = out
		out = out or (lambda text: print(text))
		argv = list(argv)
		cmd = argv.pop(0) if argv else ''

		def take(flag):
			if flag not in argv:
				return None
			i = argv.index(flag)
			v = argv[i + 1]
			del argv[i:i + 2]
			return v

		def changes():
			ch = {}
			while '--set' in argv:
				rid, _, v = take('--set').partition('=')
				try:
					v = json.loads(v)
				except ValueError:
					pass
				ch[rid] = v
			return ch
		try:
			if cmd in ('run', 'batch'):
				report, preset = take('--report'), take('--preset')
				workers = take('--workers') if cmd == 'batch' else None
				ch = changes()
				if cmd == 'batch':
					items = read_json(argv[0]) if os.path.exists(argv[0]) else json.loads(argv[0])
					if not isinstance(items, list):
						raise Refused('batch: a JSON list of inputs, or a file that holds one')
					res = self.batch(items, rules=ch, preset=preset, report=report, workers=int(workers) if workers is not None else 1)
				else:
					res = self.run(json.loads(argv[0]) if argv else {}, rules=ch, preset=preset)
			elif cmd == 'queues':
				res = self.queues()
			elif cmd == 'answer':
				node = take('--node')
				meta_raw = take('--meta')
				meta = json.loads(meta_raw) if meta_raw is not None else None
				if meta is not None and not isinstance(meta, dict):
					raise Refused('answer: --meta must be a JSON object.')
				res = self.answer(argv[0], json.loads(argv[1]), node=node, meta=meta)
			elif cmd == 'work':
				api_url = take('--api-url')
				model = take('--model')
				api_key = take('--api-key')
				think = '--think' in argv
				if think:
					argv.remove('--think')
				max_tokens = take('--max-tokens')
				max_calls = take('--max-calls')
				res = self.work(
					argv[0],
					api_url=api_url,
					model=model,
					api_key=api_key,
					think=think,
					max_tokens=int(max_tokens) if max_tokens is not None else 4000,
					max_calls=int(max_calls) if max_calls is not None else 50,
				)
			elif cmd == 'approve':
				res = self.approve(argv[0], argv[1:])
			elif cmd == 'resume':
				res = self.resume(argv[0])
			elif cmd == 'status':
				res = self.status(argv[0])
			elif cmd == 'drop':
				res = self.drop(argv[0], ' '.join(argv[1:]) or None)
			elif cmd == 'list':
				limit = take('--limit')
				res = {'runs': self.list_runs(limit=int(limit) if limit is not None else 50)}
			elif cmd == 'prune':
				keep = take('--keep')
				res = self.prune(keep=int(keep) if keep is not None else 20)
			elif cmd == 'serve-stdio':
				return self.serve_stdio(out=raw_out)
			elif cmd == 'mcp':
				api_url = take('--api-url')
				model = take('--model')
				api_key = take('--api-key')
				think = '--think' in argv
				if think:
					argv.remove('--think')
				max_tokens = take('--max-tokens')
				max_calls = take('--max-calls')
				return self.mcp(
					api_url=api_url,
					model=model,
					api_key=api_key,
					think=think,
					max_tokens=int(max_tokens) if max_tokens is not None else 4000,
					max_calls=int(max_calls) if max_calls is not None else 50,
					stdout=raw_out,
				)
			elif cmd == 'rerun':
				node = take('--from')
				if not node:
					raise Refused('rerun RUN --from ID [--set id=value]')
				res = self.rerun(argv[0], node, changes())
			elif cmd == 'replay':
				res = self.replay(argv[0])
				out(json.dumps(res, ensure_ascii=False, default=str))
				return 1 if res['differences'] else 0
			elif cmd == 'rules':
				res = {'rules': self.rules.values(), 'presets': sorted(self.catalogue.get('presets', {}))}
			elif cmd == 'flow':
				res = {'start': self.start, 'coverage': self.catalogue.get('coverage'), 'model_or_person': [n['id'] for n in self.view.nodes.values() if n.get('lane') in ('model', 'person')],
					'flow': [dict((k, n[k]) for k in ('id', 'kind', 'lane', 'name', 'by', 'block') if k in n) for n in self.catalogue.get('flow', [])],
					'blocks': [dict((k, b[k]) for k in ('id', 'kind', 'path', 'item', 'body') if k in b) for b in self.catalogue.get('blocks', [])]}
			elif cmd == 'call':
				res = {'ok': True, 'tool': argv[0], 'result': self.call(argv[0], json.loads(argv[1]) if len(argv) > 1 else {})}
			elif cmd == 'regress':
				baseline = '--baseline' in argv
				path = [a for a in argv if a != '--baseline'][0]
				cases = read_json(path)
				results, diffs = self.regress(cases)
				if baseline:
					for case, r in zip(cases, results):
						case['expect'] = dict(r['got'])
					write_json(path, cases)
					diffs = []
				res = {'cases': len(cases), 'differences': diffs, 'baseline': 'written' if baseline else None}
				out(json.dumps(res, ensure_ascii=False, default=str))
				return 1 if diffs else 0
			else:
				out(self.cli.__doc__)
				return 2
		except Refused as e:
			out(json.dumps({'refused': str(e)}, ensure_ascii=False))
			return 0
		except (IndexError, ValueError, KeyError) as e:
			out(json.dumps({'refused': 'Bad call: {}'.format(e if not isinstance(e, IndexError) else 'an argument is missing')}, ensure_ascii=False))
			return 0
		except Exception as e:
			out(json.dumps({'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}, ensure_ascii=False))
			return 1
		out(json.dumps(res, ensure_ascii=False, default=str))
		return 0


if __name__ == '__main__':
	print(__doc__)
	sys.exit(0)
