#!/usr/bin/env python3
"""rigkit: the runtime of a Rig project (language version 1). Standard library only. Python 3.

A tool keeps its own copy of this file (rig.py new copies it), so the tool installs alone.

It reads a catalogue (rig.py compile json) and gives a tool five things:

    Rules     the values of the catalogue; code reads a number with R('group.name')
    Kit       binds the code of the steps and gates, and walks the flow
    runs      a run is one item on its way through the flow; it has its own folder, with a
              pinned copy of the flow, the answers of the model and of the person, and the
              state at each top line (for rerun); it refuses an answer for another node
    cli       run, batch, queues, answer, approve, status, resume, rerun, replay, rules, flow,
              call, regress: one JSON line each
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
import copy
import datetime
import json
import os
import re
import sys
import threading
import traceback

PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
GATES = ('hard', 'soft', 'model', 'human')


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
	tmp = path + '.tmp'
	with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
		json.dump(data, f, ensure_ascii=False, indent=1, default=str)
		f.write('\n')
	os.replace(tmp, path)


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
	rig.py writes for an "out" type). -> a list of short texts.'''
	if not s:
		return []
	if 'anyOf' in s:
		return [] if any(not schema_problems(v, x, where) for x in s['anyOf']) else ['{}: not the right form'.format(where)]
	if 'enum' in s:
		return [] if v in s['enum'] else ['{}: one of {}'.format(where, ', '.join(json.dumps(x) for x in s['enum']))]
	t = s.get('type')
	ok = {'string': lambda x: isinstance(x, str), 'integer': lambda x: isinstance(x, int) and not isinstance(x, bool),
		'number': lambda x: isinstance(x, (int, float)) and not isinstance(x, bool), 'boolean': lambda x: isinstance(x, bool),
		'array': lambda x: isinstance(x, list), 'object': lambda x: isinstance(x, dict)}.get(t)
	if ok and not ok(v):
		return ['{}: {}'.format(where, {'string': 'a text', 'integer': 'a whole number', 'number': 'a number', 'boolean': 'true or false', 'array': 'a list', 'object': 'an object'}.get(t, t))]
	out = []
	if t == 'array':
		for i, x in enumerate(v):
			out += schema_problems(x, s.get('items', {}), '{}[{}]'.format(where, i))
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
			self.files[(run_id, name)] = copy.deepcopy(data)
		else:
			write_json(os.path.join(self.folder(run_id), name + '.json'), data)

	def get(self, run_id, name, default=None):
		if self.runs is None:
			return copy.deepcopy(self.files.get((run_id, name), default))
		p = os.path.join(self.folder(run_id), name + '.json')
		return read_json(p) if os.path.exists(p) else default

	def new_id(self):
		self.count += 1
		return datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-{:02d}'.format(self.count)

	def load(self, run_id):
		run = self.get(run_id, 'run')
		if run is None:
			raise Refused('No run {}.'.format(run_id))
		return run

	def save(self, run):
		self.put(run['id'], 'run', run)

	def view_of(self, run):
		'''The flow that a run walks: its pinned copy. The source may have changed since.'''
		v = self.views.get(run['id'])
		if v is None:
			pinned = self.get(run['id'], 'flow')
			v = self.views[run['id']] = View(pinned) if pinned else self.view
		return v

	def all_runs(self):
		if self.runs is None:
			return [v for (rid, name), v in sorted(self.files.items()) if name == 'run']
		if not os.path.isdir(self.runs):
			return []
		out = []
		for n in sorted(os.listdir(self.runs)):
			p = os.path.join(self.runs, n, 'run.json')
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
		names = [x['name'] for x in self.catalogue.get('in', [])]
		need = [x['name'] for x in self.catalogue.get('in', []) if not (x.get('type') or '').startswith('(maybe')]
		bad = [k for k in inputs if names and k not in names] + ['missing ' + k for k in need if k not in inputs]
		if bad:
			raise Refused('Inputs: {}. This unit takes: {}.'.format(', '.join(bad), ', '.join(names) or 'nothing'))
		run = {'id': run_id or self.new_id(), 'unit': self.catalogue.get('unit'), 'rig': 1, 'started': now(),
			'inputs': inputs, 'rules': dict(rules or {}), 'preset': preset, 'state': copy.deepcopy(state) if state is not None else dict(inputs),
			'at': at or self.start, 'trace': [], 'problems': [], 'guessed': [], 'left': [], 'waiting': None, 'since': None,
			'error': None, 'outcome': None, 'ended': None, 'in_finally': False, 'loops': {}, 'rounds': {}, 'retries': {}, 'answered': {}}
		if origin:
			run['from'] = origin
		R = Rules(self.catalogue, self.rules.session)
		if preset:
			R.preset(preset)
		for rid, v in run['rules'].items():
			R.set(rid, v)  # refuse a bad rule value before the run exists
		self.put(run['id'], 'flow', self.catalogue)  # pin: resume walks this copy, also when the source changes
		self.put(run['id'], 'rules', R.values())
		self.put(run['id'], 'answers', [])
		self.views[run['id']] = self.view
		return self.walk(run)

	def walk(self, run):
		V, R = self.view_of(run), self.rules_of(run)
		run['waiting'] = None
		marks = self.get(run['id'], 'marks', {}) or {}
		known = len(marks)
		while run['outcome'] is None:
			x = run['at']
			if x is None:
				if run['in_finally']:
					run['outcome'] = run['ended']
					break
				self.finish(run, V, {'end': None, 'label': 'stopped: the flow ran past its last line'})
				continue
			if not run['loops'] and not run['rounds'] and not run['in_finally'] and x not in marks:
				marks[x] = copy.deepcopy(run['state'])  # the state before this line: "rerun --from" starts here
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
		if len(marks) != known:
			self.put(run['id'], 'marks', marks)
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

	def answer(self, run_id, answer, who='model', node=None):
		'''Give the answer for the node that the run waits at, then walk on.
		who: "model" or "person". Only a person answers a human gate.'''
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
		log.append({'node': nid, 'who': who, 'answer': answer, 'time': now(), 'item': dict((b, lp['i']) for b, lp in run['loops'].items())})
		self.put(run_id, 'answers', log)
		run['since'] = None
		if kind == 'step':
			bad = schema_problems(answer['result'], cur.get('schema'))
			if bad:  # not the form of "out": the step waits again, with the problems
				run['answered'][nid] = len(run['problems'])
				run['problems'].append('{}: the result does not have the form of out {}: {}'.format(nid, cur.get('out'), '; '.join(bad)))
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
			run['state'][nid] = {'pass': v['pass'], 'why': answer.get('why')}
			self.after_gate(run, V, R, cur, v)
			run['answered'][nid] = len(run['problems'])
		return self.walk(run)

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

	def rerun(self, run_id, node, changes=None):
		'''A new run with the state of an old run before one of its top lines; changed rules for it.'''
		old = self.load(run_id)
		marks = self.get(run_id, 'marks', {}) or {}
		if node not in marks:
			raise Refused('Run {} has no state before "{}". It has one before each line outside a loop that it reached: {}.'.format(run_id, node, ', '.join(marks) or 'none'))
		if node not in self.view.nodes and node not in self.view.blocks:
			raise Refused('The flow has no line "{}" now.'.format(node))
		rules = dict(old.get('rules', {}))
		rules.update(changes or {})
		return self.run(old['inputs'], rules=rules, preset=old.get('preset'), state=marks[node], at=node, origin={'run': run_id, 'from': node})

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
		pinned = self.get(run['id'], 'flow')
		if pinned and pinned != self.catalogue and run['outcome'] is None:
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

	def batch(self, items, rules=None, preset=None, report=None):
		'''Start a run for each item of a list. -> a short summary. An item that needs the model or a
		person does not stop the batch: its run waits, and "queues" lists it.'''
		rows, in_row, stopped = [], 0, None
		for inputs in items:
			try:
				row = self.row(self.run(inputs, rules=rules, preset=preset), inputs)
			except Refused as e:
				row = {'run': None, 'inputs': inputs, 'problems': [], 'refused': str(e)}
			rows.append(row)
			in_row = in_row + 1 if 'error' in row else 0
			if in_row >= self.errors_stop:
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
		for run in self.all_runs():
			if run.get('outcome') is not None:
				continue
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
		names = [x['name'] for x in c.get('in', [])]
		need = [x['name'] for x in c.get('in', []) if not (x.get('type') or '').startswith('(maybe')]
		bad = [k for k in args if k not in names] + ['missing ' + k for k in need if k not in args]
		if bad:
			raise Refused('{}: {}. It takes: {}.'.format(name, ', '.join(bad), ', '.join(names) or 'nothing'))
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
		marks = self.get(run_id, 'marks', {}) or {}
		start = (old.get('from') or {}).get('from')
		state = marks.get(start) if start else None
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

	# - Command line: one JSON line for each call
	def cli(self, argv, out=None):
		'''run [JSON] [--preset N] [--set id=value]... | batch ITEMS [--report PATH] [--preset N] [--set id=value]...
		| queues | answer RUN JSON [--node ID] | approve RUN [yes|no|WORDS] | resume RUN | status RUN
		| rerun RUN --from ID [--set id=value]... | replay RUN | rules | flow | call TOOL [JSON]
		| regress FILE [--baseline]        ITEMS: a JSON list of inputs, or a file with one'''
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
				ch = changes()
				if cmd == 'batch':
					items = read_json(argv[0]) if os.path.exists(argv[0]) else json.loads(argv[0])
					if not isinstance(items, list):
						raise Refused('batch: a JSON list of inputs, or a file that holds one')
					res = self.batch(items, rules=ch, preset=preset, report=report)
				else:
					res = self.run(json.loads(argv[0]) if argv else {}, rules=ch, preset=preset)
			elif cmd == 'queues':
				res = self.queues()
			elif cmd == 'answer':
				node = take('--node')
				res = self.answer(argv[0], json.loads(argv[1]), node=node)
			elif cmd == 'approve':
				res = self.approve(argv[0], argv[1:])
			elif cmd == 'resume':
				res = self.resume(argv[0])
			elif cmd == 'status':
				res = self.status(argv[0])
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
