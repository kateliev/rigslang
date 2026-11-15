#!/usr/bin/env python3
"""rigkit: the runtime of a Rig project. Standard library only. Python 3.

A tool keeps its own copy of this file (rig.py new copies it), so the tool installs alone.

It reads a catalogue (rig.py compile json) and gives a tool five things:

    Rules     the values of the catalogue; code reads a number with R('group.name')
    Kit       binds the code of the steps and gates, and walks the flow
    runs      a run is one item on its way through the flow; it is saved as a file,
              it keeps its trace, and it refuses an answer for another node
    cli       run, batch, queues, answer, approve, status, rules, flow, call, regress:
              one JSON line each
    step      a wrapper for code that runs inside a host application

Code does the steps and decides the hard and soft gates. At a judge gate, a human gate,
or a step with no code, the run stops and waits. The model never decides a gate that
code decides, and never answers for a person.

The code of a step:  def name(state, R) -> a value (it goes to state[<step id>])
The code of a gate:  def name(state, R) -> True, False, or a dict with "pass" and,
                     when you want them, "when" (which fail line), "problems", and facts
"""
import datetime
import json
import os
import re
import sys
import traceback

PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
GATES = ('hard', 'soft', 'judge', 'human')


class Refused(Exception):
	'''A call that the flow does not allow now. It is a result, not a crash, and it is final.'''


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


# - Kit -----------------------------------------------
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


class Kit(object):
	def __init__(self, catalogue, runs=None, max_visits=10, errors_stop=2):
		'''catalogue: the path of a compiled catalogue, or the catalogue itself.
		runs: a folder for the run files (None: runs live in memory only).
		max_visits: a run that enters one node more often stops (a loop in the flow).
		errors_stop: a batch stops after this many errors in a row (the host may be down).
		A rule "run.max_visits" or "run.errors_stop" of the catalogue replaces the value.'''
		self.catalogue = read_json(catalogue) if isinstance(catalogue, str) else catalogue
		self.rules = Rules(self.catalogue)
		self.flow = dict((n['id'], n) for n in self.catalogue.get('flow', []))
		self.start = self.catalogue.get('start')
		self.runs = runs
		self.max_visits = self.rules('run.max_visits') if 'run.max_visits' in self.rules.by_id else max_visits
		self.errors_stop = self.rules('run.errors_stop') if 'run.errors_stop' in self.rules.by_id else errors_stop
		self.sees_max = self.rules('run.sees_max') if 'run.sees_max' in self.rules.by_id else 6000  # characters of one "sees" text
		self.code, self.tools, self.memory, self.count = {}, {}, {}, 0

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
		'''The names of "by" lines that have no function here. A node that the model does (a step
		whose "by" names a tool of the model) is in this list too: that is not an error.'''
		out = []
		for n in self.flow.values():
			for b in n.get('by', []):
				if self.fn_of(b) is None and b not in out:
					out.append(b)
		return out

	def fn_of(self, name):
		return self.code.get(name) or self.code.get(name.replace('-', '_')) or self.code.get(name.rsplit('.', 1)[0] + '.' + name.rsplit('.', 1)[-1].replace('-', '_'))

	def node_code(self, node):
		fns = [self.fn_of(b) for b in node.get('by', [])]
		return fns if fns and all(fns) else None

	# - Verdicts
	def verdict(self, node, result, guessed=False):
		'''The result of a gate as a verdict: who decided, pass or fail, and the next node.'''
		if not isinstance(result, dict):
			result = {'pass': bool(result)}
		ok = bool(result.get('pass'))
		v = {'gate': node['id'], 'kind': node['kind'], 'pass': ok}
		if result.get('problems'):
			v['problems'] = list(result['problems'])
		facts = dict((k, x) for k, x in result.items() if k not in ('pass', 'problems', 'when'))
		if facts:
			v['facts'] = facts
		if guessed:
			v['guessed'] = True
		edges = node.get('pass', []) if ok else node.get('fail', [])
		edge = None
		if not ok and result.get('when'):
			edge = next((e for e in edges if e.get('when') == result['when']), None)
			v['when'] = result['when']
		edge = edge or (edges[0] if edges else None)
		if edge is None and not ok and node['kind'] == 'soft' and node.get('pass'):
			edge = node['pass'][0]  # a soft fail with no fail line: report it and go on
		if edge and 'when' in edge and 'when' not in v and not ok:
			v['when'] = edge['when']
		v['next'] = edge['to'] if edge else None
		return v

	# - Runs
	def new_id(self):
		self.count += 1
		return datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-{:02d}'.format(self.count)

	def path_of(self, run_id):
		if not re.match(r'^[\w.-]+$', run_id):
			raise Refused('Bad run id {!r}.'.format(run_id))
		return os.path.join(self.runs, run_id + '.json')

	def load(self, run_id):
		if self.runs is None:
			if run_id not in self.memory:
				raise Refused('No run {}.'.format(run_id))
			return self.memory[run_id]
		if not os.path.exists(self.path_of(run_id)):
			raise Refused('No run {}.'.format(run_id))
		return read_json(self.path_of(run_id))

	def save(self, run):
		if self.runs is None:
			self.memory[run['id']] = run
		else:
			write_json(self.path_of(run['id']), run)

	def run(self, inputs=None, run_id=None, rules=None, preset=None):
		'''Start a run for one item and walk it as far as code can.'''
		if self.start is None:
			raise Refused('This unit has no flow.')
		inputs = dict(inputs or {})
		names = [x['name'] for x in self.catalogue.get('in', [])]
		need = [x['name'] for x in self.catalogue.get('in', []) if not (x.get('type') or '').startswith('(maybe')]
		bad = [k for k in inputs if names and k not in names] + ['missing ' + k for k in need if k not in inputs]
		if bad:
			raise Refused('Inputs: {}. This unit takes: {}.'.format(', '.join(bad), ', '.join(names) or 'nothing'))
		run = {'id': run_id or self.new_id(), 'unit': self.catalogue.get('unit'), 'started': datetime.datetime.now().isoformat(timespec='seconds'),
			'inputs': inputs, 'rules': dict(rules or {}), 'preset': preset, 'state': dict(inputs), 'at': self.start,
			'visits': {}, 'trace': [], 'problems': [], 'guessed': [], 'waiting': None, 'error': None, 'outcome': None}
		self.rules_of(run)  # refuse a bad rule value before the run exists
		return self.walk(run)

	def rules_of(self, run):
		R = Rules(self.catalogue, self.rules.session)
		if run.get('preset'):
			R.preset(run['preset'])
		for rid, v in run.get('rules', {}).items():
			R.set(rid, v)
		return R

	def walk(self, run):
		R = self.rules_of(run)
		run['waiting'], run['error'] = None, None
		while run['outcome'] is None:
			node = self.flow.get(run['at'])
			if node is None:
				run['outcome'] = {'end': None, 'label': 'the flow has no node "{}"'.format(run['at'])}
				break
			nid, kind = node['id'], node['kind']
			run['visits'][nid] = run['visits'].get(nid, 0) + 1
			if run['visits'][nid] > self.max_visits:
				run['outcome'] = {'end': None, 'label': 'stopped: the run entered "{}" more than {} times'.format(nid, self.max_visits)}
				run['problems'].append(run['outcome']['label'])
				break
			if kind == 'end':
				run['trace'].append({'node': nid, 'kind': 'end'})
				run['outcome'] = {'end': nid, 'label': node.get('name', nid)}
				break
			fns = self.node_code(node)
			if kind in ('judge', 'human') or fns is None:
				run['waiting'] = self.waiting(node, R, run['state'])
				break
			run['state']['_visits'] = run['visits']  # how often the run entered each node: for a gate that limits rounds
			try:
				if kind == 'step':
					for fn in fns:
						run['state'][nid] = fn(run['state'], R)
					self.after_step(run, node, {'node': nid, 'kind': 'step'})
				else:
					result = {'pass': True}
					for fn in fns:
						result = fn(run['state'], R)
						if not (result.get('pass') if isinstance(result, dict) else result):
							break
					self.after_gate(run, self.verdict(node, result))
			except Refused:
				raise
			except Exception as e:
				run['error'] = {'node': nid, 'error': '{}: {}'.format(type(e).__name__, e), 'trace': traceback.format_exc(limit=3)}
				run['visits'][nid] -= 1
				break
		self.save(run)
		return self.report(run)

	def see(self, state, path):
		'''One "sees" path in the state of a run: a step id or an input, then keys. A long text is cut.'''
		v = state
		for key in path.split('.'):
			if not isinstance(v, dict) or key not in v:
				return None
			v = v[key]
		if isinstance(v, str) and len(v) > self.sees_max:
			v = v[:self.sees_max] + ' … (cut: {} of {} characters)'.format(self.sees_max, len(v))
		return v

	def waiting(self, node, R, state=None):
		kind = node['kind']
		w = {'node': node['id'], 'kind': 'judge' if kind in ('hard', 'soft') else kind}
		if node.get('name'):
			w['name'] = R.fill(node['name'])
		for k in ('do', 'when', 'ensure', 'brief'):
			if node.get(k):
				w[k] = R.fill(node[k])
		if node.get('by'):
			w['by'] = node['by']
		if node.get('sees') and state is not None:
			w['sees'] = dict((p, v) for p, v in ((p, self.see(state, p)) for p in node['sees']) if v is not None)
		if kind in ('hard', 'soft'):
			w['no_code'] = 'No code decides this gate yet. Decide it yourself; the result is a guess.'
		w['answer'] = {'step': '{"result": <what the step gave>}', 'human': 'a person answers: approve <run> yes|no'}.get(w['kind'], '{"pass": true or false, "why": "<one sentence>"}')
		return w

	def after_step(self, run, node, entry):
		run['trace'].append(entry)
		edges = node.get('next', [])
		if not edges:
			run['outcome'] = {'end': None, 'label': 'stopped: step "{}" has no next node'.format(node['id'])}
		else:
			run['at'] = edges[0]['to']

	def after_gate(self, run, v):
		entry = {'node': v['gate'], 'kind': v['kind'], 'pass': v['pass']}
		for k in ('when', 'problems', 'facts', 'guessed', 'by', 'why'):
			if k in v:
				entry[k] = v[k]
		run['trace'].append(entry)
		if v.get('guessed') and v['gate'] not in run['guessed']:
			run['guessed'].append(v['gate'])
		if not v['pass']:
			run['problems'].append('{}: {}'.format(v['gate'], '; '.join(v.get('problems', [])) or v.get('when') or v.get('why') or 'failed'))
		if v['next'] is None:
			run['outcome'] = {'end': None, 'label': 'stopped: gate "{}" {} and has no line for that'.format(v['gate'], 'passed' if v['pass'] else 'failed')}
		else:
			run['at'] = v['next']

	def answer(self, run_id, answer, who='model', node=None):
		'''Give the answer for the node that the run waits at, then walk on.
		who: "model" or "person". Only a person answers a human gate.'''
		run = self.load(run_id)
		if run['outcome'] is not None:
			raise Refused('Run {} ended at "{}". Start a new run.'.format(run_id, run['outcome']['end']))
		cur = self.flow[run['at']]
		if node and node != cur['id']:
			raise Refused('Run {} waits at "{}", not at "{}".'.format(run_id, cur['id'], node))
		if run.get('error') and run['error']['node'] == cur['id'] and self.node_code(cur) is not None:
			raise Refused('Run {} stopped with an error at "{}". Fix the cause, then call resume.'.format(run_id, cur['id']))
		kind = cur['kind']
		if kind == 'human' and who != 'person':
			raise Refused('"{}" is a human gate: a person decides it. Ask the person; they answer with approve.'.format(cur['id']))
		if kind in ('step', 'hard', 'soft') and self.node_code(cur) is not None:
			raise Refused('"{}" is done by code. Do not answer it.'.format(cur['id']))
		if not isinstance(answer, dict):
			raise Refused('The answer must be a JSON object.')
		if kind == 'step':
			if 'result' not in answer:
				raise Refused('"{}" is a step: answer with {{"result": ...}}.'.format(cur['id']))
			run['state'][cur['id']] = answer['result']
			self.after_step(run, cur, {'node': cur['id'], 'kind': 'step', 'by': who})
		else:
			if not isinstance(answer.get('pass'), bool):
				raise Refused('"{}" is a gate: answer with {{"pass": true}} or {{"pass": false}}.'.format(cur['id']))
			v = self.verdict(cur, dict((k, answer[k]) for k in ('pass', 'when', 'problems') if k in answer), guessed=(who != 'person'))
			v['by'] = who
			if answer.get('why'):
				v['why'] = str(answer['why'])
			run['state'][cur['id']] = {'pass': v['pass'], 'why': answer.get('why')}
			self.after_gate(run, v)
		return self.walk(run)

	def resume(self, run_id):
		'''Walk on after an error was fixed. A run that waits for an answer stays where it is.'''
		run = self.load(run_id)
		return self.report(run) if run['outcome'] is not None else self.walk(run)

	def status(self, run_id):
		return self.report(self.load(run_id))

	def report(self, run):
		out = {'run': run['id'], 'at': run['at']}
		for k in ('outcome', 'waiting', 'error'):
			if run.get(k):
				out[k] = dict(run[k])
		if 'error' in out:
			out['error'].pop('trace', None)
		if 'outcome' in out:
			# The result of a run: the value of the step that leads to the end. A run that a gate ended has none.
			before = run['trace'][-2] if len(run['trace']) > 1 and run['trace'][-1]['kind'] == 'end' else None
			if before and before['kind'] == 'step' and run['state'].get(before['node']) is not None:
				out['result'] = run['state'][before['node']]
		out['problems'], out['guessed'] = run['problems'], run['guessed']
		out['path'] = [t['node'] for t in run['trace']]
		return out

	# - Batches and queues: code runs the list; the model gets a summary and the runs that wait
	def row(self, r, inputs):
		row = {'run': r['run'], 'inputs': inputs, 'problems': r['problems']}
		if 'outcome' in r:
			row['end'] = r['outcome']['end'] or r['outcome']['label']
		elif 'error' in r:
			row['error'] = r['error']['error']
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
			'left_for_model': [r['run'] for r in rows if r.get('waiting', {}).get('kind') in ('judge', 'step')],
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
		L = ['# Batch report: {}'.format(self.catalogue.get('unit')), '', datetime.datetime.now().isoformat(timespec='seconds'), '',
			'{} of {} items started. Ends: {}. Left for the model: {}. Waits for a person: {}. Errors: {}.'.format(summary['started'], summary['items'],
				', '.join('{} {}'.format(n, e) for e, n in sorted(summary['ends'].items())) or 'none', len(summary['left_for_model']), len(summary['waits_for_person']), len(summary['errors'])), '']
		if summary.get('stopped'):
			L += ['**{}**'.format(summary['stopped']), '']
		for title, part in (('Errors and refused items', bad), ('Items with problems', problems), ('Items that wait, with no problem so far', waits), ('Items with no problem', clean)):
			if not part:
				continue
			L += ['## ' + title, '', '| Run | Inputs | State | Problems |', '|---|---|---|---|']
			for r in part:
				state = r.get('end') and 'end: ' + str(r['end']) or r.get('error') or r.get('refused') or 'waits at {} ({})'.format(r['waiting']['node'], r['waiting']['kind'])
				L.append('| {} | {} | {} | {} |'.format(r['run'] or '-', cell(json.dumps(r['inputs'], ensure_ascii=False)), cell(state), cell('; '.join(r.get('problems', [])))))
			L.append('')
		os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
		with open(path, 'w', encoding='utf-8', newline='\n') as f:
			f.write('\n'.join(L))

	def all_runs(self):
		if self.runs is None:
			return list(self.memory.values())
		if not os.path.isdir(self.runs):
			return []
		return [read_json(os.path.join(self.runs, n)) for n in sorted(os.listdir(self.runs)) if n.endswith('.json')]

	def queues(self):
		'''The runs that did not end, by who must act: the model, a person, or nobody until an error is fixed.'''
		out = {'left_for_model': [], 'waits_for_person': [], 'errors': []}
		for run in self.all_runs():
			if run.get('outcome') is not None:
				continue
			node = self.flow.get(run['at'], {})
			entry = {'run': run['id'], 'node': run['at'], 'inputs': run['inputs']}
			if node.get('name'):
				entry['name'] = node['name']
			if run.get('error'):
				entry['error'] = run['error']['error']
				out['errors'].append(entry)
			elif node.get('kind') == 'human':
				out['waits_for_person'].append(entry)
			else:
				out['left_for_model'].append(entry)
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

	# - Regression: play the answers of the model from a file
	def regress(self, cases):
		'''cases: [{"name", "inputs", "answers": {node: answer or [answers]}, "rules", "preset", "expect": {"end", "path"}}].
		-> (results, differences). A person answer is written as {"person": true, "pass": ...}.'''
		keep, self.runs = self.runs, None
		results, diffs = [], []
		try:
			for case in cases:
				pending = dict((k, list(v) if isinstance(v, list) else [v]) for k, v in case.get('answers', {}).items())
				r = self.run(case.get('inputs'), rules=case.get('rules'), preset=case.get('preset'))
				while 'waiting' in r and pending.get(r['waiting']['node']):
					a = dict(pending[r['waiting']['node']].pop(0))
					who = 'person' if a.pop('person', False) else 'model'
					r = self.answer(r['run'], a, who=who)
				got = {'end': (r.get('outcome') or {}).get('end'), 'path': r['path']}
				if 'waiting' in r:
					got['waiting'] = r['waiting']['node']
				if 'error' in r:
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
		| queues | answer RUN JSON | approve RUN yes|no [NOTE] | resume RUN | status RUN | rules | flow
		| call TOOL [JSON] | regress FILE [--baseline]        ITEMS: a JSON list of inputs, or a file with one'''
		out = out or (lambda text: print(text))
		argv = list(argv)
		cmd = argv.pop(0) if argv else ''
		try:
			if cmd in ('run', 'batch'):
				preset, changes, report = None, {}, None
				while '--report' in argv:
					i = argv.index('--report')
					report = argv[i + 1]
					del argv[i:i + 2]
				while '--preset' in argv:
					i = argv.index('--preset')
					preset = argv[i + 1]
					del argv[i:i + 2]
				while '--set' in argv:
					i = argv.index('--set')
					rid, _, v = argv[i + 1].partition('=')
					try:
						v = json.loads(v)
					except ValueError:
						pass
					changes[rid] = v
					del argv[i:i + 2]
				if cmd == 'batch':
					items = read_json(argv[0]) if os.path.exists(argv[0]) else json.loads(argv[0])
					if not isinstance(items, list):
						raise Refused('batch: a JSON list of inputs, or a file that holds one')
					res = self.batch(items, rules=changes, preset=preset, report=report)
				else:
					res = self.run(json.loads(argv[0]) if argv else {}, rules=changes, preset=preset)
			elif cmd == 'queues':
				res = self.queues()
			elif cmd == 'answer':
				res = self.answer(argv[0], json.loads(argv[1]))
			elif cmd == 'approve':
				word = argv[1].strip().lower()
				if word not in ('yes', 'no'):
					raise Refused('approve RUN yes|no [NOTE]')
				a = {'pass': word == 'yes'}
				if len(argv) > 2:
					a['why'] = ' '.join(argv[2:])
				res = self.answer(argv[0], a, who='person')
			elif cmd == 'resume':
				res = self.resume(argv[0])
			elif cmd == 'status':
				res = self.status(argv[0])
			elif cmd == 'rules':
				res = {'rules': self.rules.values(), 'presets': sorted(self.catalogue.get('presets', {}))}
			elif cmd == 'flow':
				res = {'start': self.start, 'coverage': self.catalogue.get('coverage'), 'model_or_person': self.missing(),
					'flow': [dict((k, n[k]) for k in ('id', 'kind', 'name', 'by') if k in n) for n in self.catalogue.get('flow', [])]}
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
