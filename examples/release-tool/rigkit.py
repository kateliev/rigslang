#!/usr/bin/env python3
"""rigkit: the runtime of a Rig project (language version 2). Standard library only. Python 3.

A tool keeps its own copy of this file (rig.py new copies it), so the tool installs alone.

It reads a catalogue (rig.py compile json) and gives a tool five things:

    Rules     the values of the catalogue; code reads a number with R('group.name')
    Kit       binds the code of the steps and gates, and walks the flow
    runs      a run is one item on its way through the flow; it has its own folder, with a
              pinned copy of the flow, the answers of the model and of the person, and the
              state at each top line (for rerun); it refuses an answer for another node
    cli       run, batch, next-batch, queues, answer, work, approve, restore, artifact,
              status, resume, drop, list, prune, rerun, replay, rules, flow, regress,
              eval, serve-stdio, serve-http, mcp: one JSON line each
    adapters  step wrapper, rpc_call, http_json, and WorkerPool for target adapters

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
import contextlib
import copy
import datetime
import html as _html
import http.server
import json
import mimetypes
import os
import re
import shutil
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
try:
	import fcntl
except ImportError:
	fcntl = None

PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
GATES = ('hard', 'soft', 'model', 'human')
WORK_RULES = '\n'.join([
	'You do one job of a tool. Code did the rest of the work and checks your answer.',
	'Read the job and the data. Decide each item on its own, in the order of the data.',
	'Answer only with JSON in the given form. Use only ids, names and numbers from the data. Do not invent.',
])


def _work_job_text(w):
	parts = []
	intent = w.get('intent')
	if isinstance(intent, dict):
		if intent.get('text'):
			parts.append('Intent:\n' + intent['text'])
		if intent.get('local'):
			parts.append('Local intent:\n' + intent['local'])
		if intent.get('audience'):
			parts.append('Audience: ' + intent['audience'])
		if intent.get('style'):
			parts.append('Style: ' + intent['style'])
		if intent.get('never'):
			parts.append('Never:\n- ' + '\n- '.join(nv['text'] if isinstance(nv, dict) else str(nv) for nv in intent['never']))
	parts.append('The job:\n' + (w.get('do') or ''))
	if w.get('mode'):
		parts.append('Mode: ' + w['mode'])
	if w.get('candidates'):
		parts.append('Generate {} distinct candidates as a JSON list.'.format(w['candidates']))
	parts.append('The data:\n' + json.dumps(w.get('sees') or {}, ensure_ascii=False))
	if w.get('problems'):
		parts.append('Your last answer for this job failed for these reasons. Fix them:\n- ' + '\n- '.join(str(p) for p in w['problems']))
	if w.get('candidates'):
		parts.append('Answer with {{"result": [...]}} containing {} distinct items of form {}.'.format(w['candidates'], w.get('out') or 'of the schema'))
	else:
		parts.append('Answer with {{"result": ...}}, where the result has the form {}.'.format(w.get('out') or 'of the schema'))
	return '\n\n'.join(parts)


def _combined_intent(catalogue, node, R):
	'''Merge unit-level and node-level structured intent with rule values filled in.'''
	u_text = R.fill(catalogue.get('intent') or '').strip()
	u_spec = catalogue.get('intent_spec') or {}
	n_text = R.fill(node.get('intent') or '').strip()
	n_spec = node.get('intent_spec') or {}
	out = {}
	if u_text:
		out['text'] = u_text
	if n_text:
		out['local'] = n_text
	aud = R.fill(n_spec.get('audience') or u_spec.get('audience') or '').strip()
	if aud:
		out['audience'] = aud
	sty = R.fill(n_spec.get('style') or u_spec.get('style') or '').strip()
	if sty:
		out['style'] = sty
	nevers = []
	for src in (u_spec.get('never') or [], n_spec.get('never') or []):
		for nv in src:
			d = {'text': R.fill(nv['text'])}
			if nv.get('gate'):
				d['gate'] = nv['gate']
			if d not in nevers:
				nevers.append(d)
	if nevers:
		out['never'] = nevers
	return out or None


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


def _elicitation_request(res):
	'''Build an MCP Elicitation (elicitation/create) payload for a waiting human gate.'''
	w = res.get('waiting') if isinstance(res, dict) else None
	if not isinstance(w, dict) or w.get('kind') != 'human':
		return None
	msg_parts = [w.get('name') or 'Human approval required']
	if w.get('check'):
		msg_parts.append(w['check'])
	if w.get('sees'):
		msg_parts.append(json.dumps(w['sees'], ensure_ascii=False, default=str)[:1500])
	if w.get('options'):
		schema = {
			'type': 'object',
			'properties': {
				'choice': {'type': 'string', 'enum': list(w['options']), 'default': w['options'][0]},
				'note': {'type': 'string', 'description': 'Optional note'},
			},
			'required': ['choice'],
		}
	else:
		schema = {
			'type': 'object',
			'properties': {
				'approve': {'type': 'boolean', 'description': 'true to approve, false to reject'},
				'note': {'type': 'string', 'description': 'Optional reason'},
			},
			'required': ['approve'],
		}
	return {'method': 'elicitation/create', 'params': {'message': '\n\n'.join(msg_parts), 'requestedSchema': schema}}


def _mcp_decorate(res, has_worker, approve_base_url=None, supports_elicitation=False):
	'''Tailor a waiting response for MCP: drop CLI-only waiting.answer, add waiting.next_action,
	and attach approve_url / elicitation payload for human gates.'''
	if not isinstance(res, dict) or not isinstance(res.get('waiting'), dict):
		return res
	res = dict(res)
	w = dict(res['waiting'])
	w.pop('answer', None)
	kind = w.get('kind')
	run_id = res.get('run')
	if kind == 'human':
		if approve_base_url and run_id:
			w['approve_url'] = approve_base_url.rstrip('/') + '/approve/' + urllib.parse.quote(str(run_id))
		if supports_elicitation:
			el = _elicitation_request({'run': run_id, 'waiting': w})
			if el:
				w['elicitation'] = el
		w['next_action'] = {'call': 'NONE', 'show_verbatim': w.get('say', '')}
		if w.get('approve_url'):
			w['next_action']['approve_url'] = w['approve_url']
	elif kind == 'model':
		w['next_action'] = {'call': 'answer_gate', 'args': {'run': run_id, 'pass': '<true|false>', 'why': '<one sentence>'}}
	elif kind in ('step', 'reason'):
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


def _call_provider(provider, api_url, model, api_key, system_prompt, messages, schema=None, think=False, temperature=0.2, max_tokens=4000, timeout_s=120, request_fn=None):
	'''Call openai, ollama, or anthropic chat endpoints using standard library only.
	-> {"content": str|None, "tokens": int|None, "finish_reason": str|None}.'''
	prov = (provider or 'openai').strip().lower()
	send = request_fn or _http_post
	base = api_url.rstrip('/')
	if prov == 'ollama':
		url = base if base.endswith('/api/chat') else base + '/api/chat'
		headers = {'Content-Type': 'application/json'}
		payload = {
			'model': model,
			'messages': [{'role': 'system', 'content': system_prompt}] + list(messages),
			'stream': False,
			'think': bool(think),
			'options': {'temperature': temperature, 'num_predict': max_tokens},
		}
		if schema and not think:
			payload['format'] = schema
		resp = send(url, headers, payload, timeout_s)
		msg = resp.get('message') if isinstance(resp, dict) else None
		content = msg.get('content') if isinstance(msg, dict) else None
		tokens = resp.get('eval_count') if isinstance(resp, dict) else None
		finish = resp.get('done_reason') if isinstance(resp, dict) else None
		return {'content': content, 'tokens': tokens, 'finish_reason': 'length' if finish == 'length' else finish}
	if prov == 'anthropic':
		url = base if base.endswith('/messages') else (base + '/messages' if base.endswith('/v1') else base + '/v1/messages')
		headers = {'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'}
		if api_key:
			headers['x-api-key'] = str(api_key)
		payload = {
			'model': model,
			'system': system_prompt,
			'messages': list(messages),
			'max_tokens': max_tokens,
		}
		if think:
			payload['thinking'] = {'type': 'enabled', 'budget_tokens': max(1024, min(max_tokens // 2, 2048))}
		else:
			payload['temperature'] = temperature
		resp = send(url, headers, payload, timeout_s)
		blocks = resp.get('content') if isinstance(resp, dict) else None
		texts = [b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text'] if isinstance(blocks, list) else []
		content = '\n'.join(t for t in texts if t).strip() or None
		usage = resp.get('usage') if isinstance(resp, dict) else None
		tokens = usage.get('output_tokens') if isinstance(usage, dict) else None
		stop = resp.get('stop_reason') if isinstance(resp, dict) else None
		return {'content': content, 'tokens': tokens, 'finish_reason': 'length' if stop == 'max_tokens' else stop}
	# Default: OpenAI-compatible /chat/completions
	url = base if base.endswith('/chat/completions') else base + '/chat/completions'
	headers = {'Content-Type': 'application/json'}
	if api_key:
		headers['Authorization'] = 'Bearer ' + str(api_key)
	payload = {
		'model': model,
		'messages': [{'role': 'system', 'content': system_prompt}] + list(messages),
		'max_tokens': max_tokens,
		'temperature': temperature,
	}
	if schema and not think:
		payload['response_format'] = {
			'type': 'json_schema',
			'json_schema': {
				'name': 'rig_job',
				'strict': True,
				'schema': schema,
			},
		}
	resp = send(url, headers, payload, timeout_s)
	choices = resp.get('choices') if isinstance(resp, dict) else None
	choice = choices[0] if isinstance(choices, list) and choices else {}
	finish = choice.get('finish_reason') if isinstance(choice, dict) else None
	usage = resp.get('usage') if isinstance(resp, dict) else None
	tokens = usage.get('completion_tokens') if isinstance(usage, dict) and 'completion_tokens' in usage else None
	msg = choice.get('message') if isinstance(choice, dict) else None
	content = msg.get('content') if isinstance(msg, dict) else None
	return {'content': content, 'tokens': tokens, 'finish_reason': finish}


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


# - Target-adapter helpers (outside the language) -------
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


def http_json(url, method='GET', body=None, headers=None, timeout_s=30):
	'''Minimal stdlib HTTP/JSON helper for target adapters.'''
	hdrs = {'Accept': 'application/json'}
	if headers:
		hdrs.update(headers)
	data = None
	if body is not None:
		hdrs.setdefault('Content-Type', 'application/json')
		data = json.dumps(body, ensure_ascii=False).encode('utf-8')
	req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
	with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
		raw = resp.read().decode('utf-8')
		return json.loads(raw) if raw.strip() else None


def rpc_call(url, method, params=None, headers=None, timeout_s=30, rpc_id=1, request_fn=None):
	'''Minimal stdlib JSON-RPC 2.0 over HTTP helper for host-app adapters.'''
	payload = {'jsonrpc': '2.0', 'id': rpc_id, 'method': method}
	if params is not None:
		payload['params'] = params
	hdrs = {'Content-Type': 'application/json'}
	if headers:
		hdrs.update(headers)
	resp = request_fn(url, hdrs, payload, float(timeout_s)) if request_fn else _http_post(url, hdrs, payload, float(timeout_s))
	if not isinstance(resp, dict):
		raise RuntimeError('JSON-RPC invalid response: {!r}'.format(resp))
	if 'error' in resp and resp['error'] is not None:
		err = resp['error']
		msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
		raise RuntimeError('JSON-RPC error ({}): {}'.format(method, msg))
	return resp.get('result')


class WorkerPool(object):
	'''Optional stdlib parallel worker pool for CPU-bound or I/O-bound target adapters.'''

	def __init__(self, max_workers=4, processes=False):
		self.max_workers = max(1, int(max_workers))
		self.processes = bool(processes)

	def map(self, fn, items, timeout_s=None):
		'''Run fn on each item. -> list of {"ok": True, "result": ...} or {"ok": False, "error": ...}.'''
		items = list(items)
		if not items:
			return []
		exec_cls = concurrent.futures.ProcessPoolExecutor if self.processes else concurrent.futures.ThreadPoolExecutor
		out = [None] * len(items)
		with exec_cls(max_workers=min(self.max_workers, len(items))) as pool:
			futs = {pool.submit(fn, item): i for i, item in enumerate(items)}
			for fut, idx in futs.items():
				try:
					out[idx] = {'ok': True, 'result': fut.result(timeout=timeout_s)}
				except Exception as e:
					out[idx] = {'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}
		return out



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
		self.start, self.rollback, self.final = c.get('start'), c.get('rollback'), c.get('finally')
		self.queue = c.get('queue')


# - Kit -----------------------------------------------
class Kit(object):
	def __init__(self, catalogue, runs=None, errors_stop=2):
		'''catalogue: the path of a compiled catalogue, or the catalogue itself.
		runs: a folder for the run folders (None: runs live in memory only).
		errors_stop: a batch stops after this many errors in a row (the host may be down).
		A rule "run.errors_stop" or "run.sees_max" of the catalogue replaces the value.'''
		self.catalogue = read_json(catalogue) if isinstance(catalogue, str) else catalogue
		if self.catalogue and self.catalogue.get('rig', 0) < 2:
			raise ValueError('This catalogue is of language version {}. Build the tool again: rig.py build'.format(self.catalogue.get('rig', 0)))
		self.rules = Rules(self.catalogue)
		self.view = View(self.catalogue)
		self.start = self.view.start
		self.runs = runs
		self.errors_stop = self.rules('run.errors_stop') if 'run.errors_stop' in self.rules.by_id else errors_stop
		self.sees_max = self.rules('run.sees_max') if 'run.sees_max' in self.rules.by_id else 6000  # characters of one "sees" text
		self.code, self.files, self.views, self.count = {}, {}, {}, 0
		self._lock = threading.RLock()

	# - Binding the code
	def bind(self, prefix, source):
		'''Give the functions of a module (or a dict) the names "prefix.function", as in the "by" lines.'''
		items = source.items() if isinstance(source, dict) else ((k, getattr(source, k)) for k in dir(source) if not k.startswith('_'))
		for name, fn in items:
			if callable(fn):
				self.code[prefix + '.' + name] = fn
		return self

	def missing(self):
		'''The names of "by", "tools", and "queue" lines that have no function here.'''
		out = []
		for n in self.view.nodes.values():
			for b in list(n.get('by', [])) + list(n.get('tools', [])):
				if self.fn_of(b) is None and b not in out:
					out.append(b)
		if self.view.queue:
			for b in self.view.queue.get('by', []):
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

	def _put_artifact(self, run_id, name, data):
		'''Save full payload for a step/reason with "brief" keys. -> relative artifact path.'''
		rel = 'artifacts/{}.json'.format(name)
		if self.runs is None:
			with self._lock:
				self.files[(run_id, 'artifact:' + name)] = copy.deepcopy(data)
		else:
			write_json(os.path.join(self.folder(run_id), 'artifacts', name + '.json'), data)
		return rel

	def _get_artifact(self, run_id, name):
		if not re.match(r'^[\w.-]+$', name or ''):
			raise Refused('Bad artifact name {!r}.'.format(name))
		if self.runs is None:
			with self._lock:
				if (run_id, 'artifact:' + name) not in self.files:
					raise Refused('Run {} has no artifact "{}".'.format(run_id, name))
				return copy.deepcopy(self.files[(run_id, 'artifact:' + name)])
		p = os.path.join(self.folder(run_id), 'artifacts', name + '.json')
		if not os.path.exists(p):
			raise Refused('Run {} has no artifact "{}".'.format(run_id, name))
		return read_json(p)

	def artifact(self, run_id, name, path=None, offset=0, limit=4000):
		'''Safe read-only inspection of a saved "brief" step artifact, confined to runs/<run>/artifacts/.'''
		self.load(run_id)
		data = self._get_artifact(run_id, name)
		val = self.see(data, path, cut=False) if path else data
		offset = max(0, int(offset))
		limit = max(1, int(limit))
		text = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, default=str)
		total = len(text)
		truncated = (offset > 0) or (total > offset + limit)
		out = {'run': run_id, 'artifact': name, 'total_chars': total, 'truncated': truncated}
		if path:
			out['path'] = path
		if truncated:
			out['offset'] = offset
			out['value'] = text[offset:offset + limit]
		else:
			out['value'] = val
		return out

	@contextlib.contextmanager
	def _batch_lock(self):
		'''Serialized execution lock across threads and processes (runs/.batch.lock).'''
		with self._lock:
			if self.runs is None or fcntl is None:
				yield
				return
			os.makedirs(self.runs, exist_ok=True)
			lock_path = os.path.join(self.runs, '.batch.lock')
			with open(lock_path, 'a+', encoding='utf-8') as fh:
				fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
				try:
					yield
				finally:
					fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

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
		run = {'id': run_id or self.new_id(), 'unit': self.catalogue.get('unit'), 'rig': 2, 'started': now(),
			'inputs': inputs, 'rules': dict(rules or {}), 'preset': preset, 'state': copy.deepcopy(state) if state is not None else dict(inputs),
			'at': at or self.start, 'trace': [], 'problems': [], 'guessed': [], 'left': [], 'waiting': None, 'since': None,
			'error': None, 'outcome': None, 'ended': None, 'in_finally': False, 'in_rollback': False, 'rolled_back': False,
			'loops': {}, 'rounds': {}, 'retries': {}, 'answered': {}, 'loop_soft': {}, 'arena_used': 0, 'artifacts': {}}
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
				if run.get('in_rollback'):
					run['in_rollback'] = False
					run['rolled_back'] = True
					if run.get('ended') is not None:
						if V.final:
							run['in_finally'], run['at'] = True, V.final
							continue
						run['outcome'] = run['ended']
						break
					break
				if run['in_finally']:
					run['outcome'] = run['ended']
					break
				self.finish(run, V, {'end': None, 'label': 'stopped: the flow ran past its last line'})
				continue
			if not run['loops'] and not run['rounds'] and not run['in_finally'] and not run.get('in_rollback') and not self.has_mark(run['id'], x):
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
				if last and last['kind'] in ('step', 'reason') and not run['in_finally'] and not run.get('in_rollback'):
					run['result_of'] = last['node']
				run['trace'].append({'node': nid, 'kind': 'end'})
				need_rb = bool(run.pop('need_rollback', False))
				self.finish(run, V, {'end': nid, 'label': R.fill(node.get('name', nid))}, rollback=need_rb)
				continue
			timed = run.pop('timed_out', None)
			if timed and kind in ('hard', 'soft', 'model'):  # the step before gave no result in time: the gate fails
				self.after_gate(run, V, R, node, self.verdict(node, {'pass': False, 'when': 'timeout', 'problems': ['"{}" gave no result in time'.format(timed)]}))
				continue
			fns = self.node_code(node)
			if kind in ('model', 'human', 'reason') or fns is None:
				run['since'] = run.get('since') or now()
				run['waiting'] = self.waiting(node, R, run)
				break
			try:
				if kind == 'step':
					for fn in fns:
						run['state'][nid] = run_code(fn, run['state'], R, node.get('timeout'))
					if node.get('brief'):
						run.setdefault('artifacts', {})[nid] = self._put_artifact(run['id'], nid, run['state'][nid])
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
				self.finish(run, V, {'end': 'error', 'label': 'error at "{}": {}'.format(nid, text)}, rollback=True)
		self.save(run)
		return self.report(run)

	def finish(self, run, V, outcome, rollback=False):
		'''The run reached an end, an error or a stop. Runs "rollback" (when triggered) then "finally", once.'''
		if run.get('in_rollback'):
			if outcome.get('end') == 'error' or outcome.get('end') is None:
				run['problems'].append('rollback: ' + outcome['label'])
			run['in_rollback'] = False
			run['rolled_back'] = True
			if run.get('ended') is not None:
				if V.final:
					run['in_finally'], run['at'] = True, V.final
				else:
					run['outcome'] = run['ended']
			return
		if run['in_finally']:
			if outcome.get('end') == 'error' or outcome.get('end') is None:
				run['problems'].append('finally: ' + outcome['label'])
			run['outcome'] = run['ended']
			return
		if rollback and V.rollback and not run.get('rolled_back'):
			run['ended'], run['in_rollback'], run['at'] = outcome, True, V.rollback
			run['loops'], run['rounds'], run['retries'] = {}, {}, {}
			return
		if V.final:
			run['ended'], run['in_finally'], run['at'] = outcome, True, V.final
			run['loops'], run['rounds'], run['retries'] = {}, {}, {}
		else:
			run['outcome'] = outcome
			if outcome.get('end') is None:
				run['problems'].append(outcome['label'])

	def _run_rollback(self, run):
		'''Execute the rollback block synchronously on a run (e.g. unattended deferral or explicit restore).'''
		V = self.view_of(run)
		if not V.rollback or run.get('rolled_back'):
			return False
		saved_at, saved_waiting, saved_outcome, saved_ended = run.get('at'), run.get('waiting'), run.get('outcome'), run.get('ended')
		run['outcome'] = None
		run['ended'] = None
		run['in_rollback'] = True
		run['at'] = V.rollback
		self.walk(run)
		run['in_rollback'] = False
		run['rolled_back'] = True
		run['at'] = saved_at
		run['waiting'] = saved_waiting
		run['outcome'] = saved_outcome
		run['ended'] = saved_ended
		self.save(run)
		return True

	def restore(self, run_id):
		'''Explicitly execute the unit's "rollback" block on a run.'''
		run = self.load(run_id)
		V = self.view_of(run)
		if not V.rollback:
			raise Refused('This unit has no rollback block.')
		run['rolled_back'] = False
		self._run_rollback(run)
		out = self.report(self.load(run_id))
		out['restored'] = True
		return out

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
				run.get('loop_soft', {}).pop(bid, None)
				run['trace'].append({'node': bid, 'kind': 'until', 'pass': True})
				run['at'] = b.get('next')
				return
			if r >= self.count_of(b.get('retry'), R):
				del run['rounds'][bid]
				run.get('loop_soft', {}).pop(bid, None)
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
		# Clear loop-local soft problem for this gate when re-evaluated inside an active "until" loop
		active_until = list(run.get('rounds', {}).keys())[-1] if run.get('rounds') else None
		if node['kind'] == 'soft' and active_until is not None:
			lsoft = run.setdefault('loop_soft', {}).setdefault(active_until, {})
			prev_msg = lsoft.pop(nid, None)
			if prev_msg is not None:
				for idx in range(len(run['problems']) - 1, -1, -1):
					if run['problems'][idx] == prev_msg:
						del run['problems'][idx]
						for ak, av in list(run.get('answered', {}).items()):
							if av > idx:
								run['answered'][ak] = av - 1
						break
		if v['pass']:
			run['retries'].pop(nid, None)
			run['at'] = node.get('next')
			return
		why = '; '.join(v.get('problems', [])) or v.get('when') or v.get('why') or 'failed'
		prob_msg = '{}: {}'.format(nid, why)
		run['problems'].append(prob_msg)
		if node['kind'] == 'soft':  # reported; the flow goes on
			if active_until is not None:
				run.setdefault('loop_soft', {}).setdefault(active_until, {})[nid] = prob_msg
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
			if node['kind'] == 'hard':
				run['need_rollback'] = True
			run['at'] = edge['to']

	def _effective_schema(self, node, R):
		'''Effective JSON schema for a step or reason node (wrapping array when candidates is set).'''
		base = node.get('schema')
		if node.get('kind') == 'reason' and node.get('candidates') is not None:
			cand = self.count_of(node['candidates'], R)
			s = {'type': 'array', 'minItems': cand, 'maxItems': cand}
			if base:
				s['items'] = base
			return s
		return base

	# - Waiting and answers
	def waiting(self, node, R, run):
		kind = node['kind']
		V = self.view_of(run)
		w = {'node': node['id'], 'kind': 'model' if kind in ('hard', 'soft') else kind}
		if node.get('name'):
			w['name'] = R.fill(node['name'])
		if kind in ('reason', 'model'):
			ci = _combined_intent(V.c, node, R)
			if ci:
				w['intent'] = ci
		if kind == 'reason':
			w['mode'] = node.get('mode', 'careful')
			if node.get('tools'):
				w['tools'] = list(node['tools'])
			if node.get('budget') is not None:
				b = self.count_of(node['budget'], R)
				w['budget'] = b
				w['budget_remaining'] = max(0, b - int(run.get('arena_used', 0)))
			if node.get('candidates') is not None:
				w['candidates'] = self.count_of(node['candidates'], R)
		for k in ('do', 'check'):
			if node.get(k):
				w[k] = R.fill(node[k])
		if node.get('by'):
			w['by'] = node['by']
		if node.get('sees'):
			seen_map = {}
			for p in node['sees']:
				v = self.see(run['state'], p)
				if v is None:
					continue
				src_node = V.nodes.get(p)
				if src_node and src_node.get('brief') and isinstance(v, dict):
					compact = dict((k, v[k]) for k in src_node['brief'] if k in v)
					art = (run.get('artifacts') or {}).get(p)
					if art:
						compact['_artifact'] = art
						compact['_artifact_name'] = p
					seen_map[p] = compact
				else:
					seen_map[p] = v
			w['sees'] = seen_map
		if kind in ('hard', 'soft'):
			w['no_code'] = 'No code decides this gate yet. Decide it yourself; the result is a guess.'
		if node.get('options'):
			w['options'], w['default'] = node['options'], node['options'][0]
		eff_schema = self._effective_schema(node, R)
		if eff_schema:
			w['out'], w['schema'] = node.get('out'), eff_schema
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
		elif kind == 'reason':
			w['answer'] = '{"result": [<distinct candidates matching out>]}' if node.get('candidates') is not None else '{"result": <what the reason block gave>}'
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

	def arena_call(self, run_id, tool_name, args=None):
		'''Invoke a read-only tool inside a waiting "reason" arena, enforcing its hard budget and state isolation.'''
		run = self.load(run_id)
		if run['outcome'] is not None:
			raise Refused('Run {} ended at "{}".'.format(run_id, run['outcome'].get('end')))
		V, R = self.view_of(run), self.rules_of(run)
		cur = V.nodes.get(run['at'])
		if cur is None or cur.get('kind') != 'reason':
			raise Refused('Run {} is not waiting at a reason block.'.format(run_id))
		allowed = cur.get('tools') or []
		if tool_name not in allowed:
			raise Refused('Tool "{}" is not allowed at reason "{}": allowed tools are {}.'.format(tool_name, cur['id'], ', '.join(allowed) or 'none'))
		budget = self.count_of(cur.get('budget'), R) if cur.get('budget') is not None else None
		used = int(run.get('arena_used', 0))
		if budget is not None and used >= budget:
			raise Refused('Reason "{}" exhausted its tool budget ({} of {}). Return your final result now.'.format(cur['id'], used, budget))
		fn = self.fn_of(tool_name)
		if fn is None:
			raise Refused('Tool "{}" has no bound function.'.format(tool_name))
		# Deep copy state so arena tools can never mutate run['state']
		state_copy = copy.deepcopy(run['state'])
		import inspect
		nparams = len(inspect.signature(fn).parameters)
		res = fn(state_copy, R, args or {}) if nparams >= 3 else fn(state_copy, R)
		run['arena_used'] = used + 1
		run['waiting'] = self.waiting(cur, R, run)
		self.save(run)
		out = {'run': run_id, 'node': cur['id'], 'tool': tool_name, 'result': res, 'used': run['arena_used']}
		if budget is not None:
			out['budget_remaining'] = max(0, budget - run['arena_used'])
		return out

	def expire(self, run):
		'''A node that waits longer than its timeout: a step or reason gives no result, a gate fails with the
		reason "timeout". -> True when the run went on.'''
		if run['outcome'] is not None or not run.get('since'):
			return False
		V = self.view_of(run)
		node = V.nodes.get(run['at'])
		if not node or not node.get('timeout') or age(run['since']) <= node['timeout']:
			return False
		R = self.rules_of(run)
		run['since'] = None
		if node['kind'] in ('step', 'reason'):
			run['answered'][node['id']] = len(run['problems'])  # when the node waits again, it shows why
			run['state'][node['id']] = None
			run['arena_used'] = 0
			run['timed_out'] = node['id']
			run['trace'].append({'node': node['id'], 'kind': node['kind'], 'timeout': True})
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
		if kind in ('step', 'reason') and 'result' not in answer:
			raise Refused('"{}" is a {}: answer with {{"result": ...}}.'.format(nid, kind))
		options = kind == 'human' and cur.get('options')
		if kind not in ('step', 'reason') and not options and not isinstance(answer.get('pass'), bool):
			raise Refused('"{}" is a gate: answer with {{"pass": true}} or {{"pass": false}}.'.format(nid))
		log = self.get(run_id, 'answers', []) or []
		entry = {'node': nid, 'who': who, 'answer': answer, 'time': now(), 'item': dict((b, lp['i']) for b, lp in run['loops'].items())}
		if meta:
			entry['meta'] = dict(meta)
		log.append(entry)
		self.put(run_id, 'answers', log)
		run['since'] = None
		if kind in ('step', 'reason'):
			eff_schema = self._effective_schema(cur, R)
			bad = schema_problems(answer['result'], eff_schema)
			if bad:  # not the form of "out": the node waits again, with the problems
				run['answered'][nid] = len(run['problems'])
				err = str(meta['error']).strip() if isinstance(meta, dict) and meta.get('error') else ''
				detail = '{}; {}'.format(err, '; '.join(bad)) if err else '; '.join(bad)
				run['problems'].append('{}: the result does not have the form of out {}: {}'.format(nid, cur.get('out'), detail))
				run['trace'].append({'node': nid, 'kind': kind, 'by': who, 'pass': False})
				return self.walk(run)
			run['state'][nid] = answer['result']
			if cur.get('brief'):
				run.setdefault('artifacts', {})[nid] = self._put_artifact(run['id'], nid, answer['result'])
			run['arena_used'] = 0
			tr = {'node': nid, 'kind': kind, 'by': who}
			if kind == 'reason':
				tr['mode'] = cur.get('mode', 'careful')
			run['trace'].append(tr)
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

	def work(self, run_id, api_url=None, model=None, api_key=None, provider=None, reason_api_url=None, reason_model=None, reason_api_key=None, reason_provider=None, think=False, max_tokens=4000, max_calls=50, timeout_s=120, on_progress=None, request_fn=None):
		'''Run model steps and reason blocks of one run in isolated contexts with two-tier model routing
		and pluggable providers (openai, ollama, anthropic). Standard library only.'''
		api_url = (api_url or os.environ.get('RIG_API_URL') or '').strip()
		model = (model or os.environ.get('RIG_MODEL') or '').strip()
		api_key = api_key if api_key is not None else os.environ.get('RIG_API_KEY')
		provider = (provider or os.environ.get('RIG_PROVIDER') or 'openai').strip().lower()
		r_api_url = (reason_api_url or os.environ.get('RIG_REASON_API_URL') or api_url).strip()
		r_model = (reason_model or os.environ.get('RIG_REASON_MODEL') or model).strip()
		r_api_key = reason_api_key if reason_api_key is not None else (os.environ.get('RIG_REASON_API_KEY') if os.environ.get('RIG_REASON_API_KEY') is not None else api_key)
		r_provider = (reason_provider or os.environ.get('RIG_REASON_PROVIDER') or provider).strip().lower()
		if not api_url and not r_api_url:
			raise Refused('work needs --api-url URL (or RIG_API_URL).')
		if not model and not r_model:
			raise Refused('work needs --model NAME (or RIG_MODEL).')
		max_tokens = int(max_tokens)
		max_calls = int(max_calls)
		timeout_s = float(timeout_s)
		r = self.status(run_id)
		done = []
		same, last = 0, ''
		for n in range(max_calls):
			w = r.get('waiting')
			if not (isinstance(w, dict) and w.get('kind') in ('step', 'reason') and w.get('schema')):
				break
			is_reason = w.get('kind') == 'reason'
			use_url = r_api_url if is_reason else api_url
			use_model = r_model if is_reason else model
			use_key = r_api_key if is_reason else api_key
			use_prov = r_provider if is_reason else provider
			if not use_url or not use_model:
				raise Refused('work needs --api-url and --model (or --reason-api-url and --reason-model).')
			where = '{} {}'.format(w['node'], json.dumps(w.get('item') or {}, sort_keys=True))
			same = same + 1 if where == last else 0
			last = where
			if same >= 5:
				break
			if on_progress is not None:
				suffix = ' ' + json.dumps(w['item'], ensure_ascii=False) if w.get('item') else ''
				on_progress('{}: job {}{}'.format(w['node'], n + 1, suffix))
			node_think = True if (is_reason and w.get('mode', 'careful') == 'careful') else bool(think)
			temp = 0.85 if (is_reason and w.get('mode') == 'creative') else (0.6 if node_think else 0.2)
			wrap_schema = {
				'type': 'object',
				'properties': {'result': w['schema']},
				'required': ['result'],
				'additionalProperties': False,
			}
			job_text = _work_job_text(w)
			arena_tools = w.get('tools') or [] if is_reason else []
			if arena_tools:
				job_text += '\n\nRead-only tools available (budget {}): {}. To call one, reply with {{"tool": "<name>", "args": {{...}}}}. When ready, reply with {{"result": ...}}.'.format(
					w.get('budget_remaining', w.get('budget', 1)), ', '.join(arena_tools))
			messages = [{'role': 'user', 'content': job_text}]
			t0 = time.monotonic()
			parsed_result = None
			got_result = False
			total_tokens = None
			error_reason = None
			arena_rounds = int(w.get('budget_remaining', w.get('budget', 0))) if arena_tools else 0
			try:
				for ar in range(arena_rounds + 1):
					can_tool = bool(arena_tools) and ar < arena_rounds
					call_schema = None if can_tool else wrap_schema
					res = _call_provider(
						use_prov, use_url, use_model, use_key, WORK_RULES, messages,
						schema=call_schema, think=node_think, temperature=temp,
						max_tokens=max_tokens, timeout_s=timeout_s, request_fn=request_fn,
					)
					if isinstance(res.get('tokens'), int):
						total_tokens = (total_tokens or 0) + res['tokens']
					raw_content = res.get('content')
					hit_cap = (res.get('finish_reason') == 'length') or (isinstance(res.get('tokens'), int) and res['tokens'] >= max_tokens)
					if not isinstance(raw_content, str) or not raw_content.strip():
						error_reason = (
							'hit max_tokens ({}) before finishing valid JSON; keep values shorter'.format(max_tokens)
							if hit_cap else 'model returned empty content'
						)
						break
					text = _json_in(re.sub(r'<think>.*?</think>', '', raw_content, flags=re.S)) if (node_think or can_tool or use_prov == 'anthropic') else raw_content
					try:
						parsed = json.loads(text)
					except ValueError:
						error_reason = (
							'hit max_tokens ({}) before finishing valid JSON; keep values shorter'.format(max_tokens)
							if hit_cap else 'response was not valid JSON'
						)
						break
					if isinstance(parsed, dict) and 'tool' in parsed and can_tool:
						tname = str(parsed['tool'])
						targs = parsed.get('args') if isinstance(parsed.get('args'), dict) else {}
						try:
							tres = self.arena_call(run_id, tname, targs)
						except Refused as e:
							tres = {'refused': str(e)}
						messages.append({'role': 'assistant', 'content': raw_content})
						messages.append({'role': 'user', 'content': 'Tool result:\n' + json.dumps(tres, ensure_ascii=False, default=str)})
						continue
					if isinstance(parsed, dict) and 'result' in parsed:
						parsed_result = parsed['result']
						got_result = True
						break
					error_reason = (
						'hit max_tokens ({}) before finishing valid JSON; keep values shorter'.format(max_tokens)
						if hit_cap else 'response JSON had no "result" field'
					)
					break
			except Exception as e:
				error_reason = 'model call failed: {}: {}'.format(type(e).__name__, e)
			seconds = round(time.monotonic() - t0, 1)
			meta = {'model': use_model, 'provider': use_prov, 'tier': 'reason' if is_reason else 'worker', 'seconds': seconds}
			if total_tokens is not None:
				meta['tokens'] = total_tokens
			if error_reason:
				meta['error'] = error_reason
			r = self.answer(run_id, {'result': parsed_result}, node=w['node'], meta=meta)
			entry = {'node': w['node'], 'tier': meta['tier'], 'model': use_model, 'seconds': seconds, 'ok': got_result}
			if 'item' in w:
				entry['item'] = w['item']
			if total_tokens is not None:
				entry['tokens'] = total_tokens
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
		if run.get('rolled_back'):
			out['rolled_back'] = True
		if run.get('artifacts'):
			out['artifacts'] = dict(run['artifacts'])
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
			'left_for_model': [r['run'] for r in rows if r.get('waiting', {}).get('kind') in ('model', 'step', 'reason')],
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

	def discover_queue(self, rules=None, preset=None):
		'''Discover pending items from a unit's declared "queue" step.'''
		q = self.view.queue
		if not q or not q.get('by'):
			return None
		R = Rules(self.catalogue, self.rules.session)
		if preset:
			R.preset(preset)
		for rid, v in (rules or {}).items():
			R.set(rid, v)
		fns = [self.fn_of(b) for b in q['by']]
		if not fns or not all(fns):
			raise Refused('queue function is not bound: {}'.format(', '.join(q['by'])))
		out = []
		for fn in fns:
			res = fn({}, R)
			if isinstance(res, list):
				out.extend(res)
		return out

	def next_batch(self, items=None, size=None, rules=None, preset=None, report=None):
		'''Run one chunk unattended under a serialized lock with circuit breaker.
		Items hitting a model step, reason block, model gate or human gate are rolled back (when a
		rollback block exists) and deferred to left_for_model / waits_for_person.'''
		with self._batch_lock():
			R = Rules(self.catalogue, self.rules.session)
			if preset:
				R.preset(preset)
			for rid, v in (rules or {}).items():
				R.set(rid, v)
			if items is None:
				items = self.discover_queue(rules=rules, preset=preset)
				if items is None:
					raise Refused('next-batch needs an items list or a declared "queue" step.')
			if not isinstance(items, list):
				raise Refused('next-batch: items must be a JSON list.')
			chunk_size = int(size) if size is not None else (int(R('batch.size')) if 'batch.size' in R.by_id else 10)
			chunk_size = max(1, chunk_size)
			chunk = items[:chunk_size]
			remaining = max(0, len(items) - len(chunk))
			rows, in_row, stopped = [], 0, None
			for item in chunk:
				try:
					r = self.run(item, rules=rules, preset=preset)
					if 'waiting' in r:
						run_obj = self.load(r['run'])
						if self.view_of(run_obj).rollback and not run_obj.get('rolled_back'):
							self._run_rollback(run_obj)
						run_obj = self.load(r['run'])
						run_obj['deferred'] = True
						self.save(run_obj)
					row = self.row(r, item)
					is_trip = ('error' in row) or any('timeout' in str(p).lower() for p in row.get('problems', []))
				except Refused as e:
					row = {'run': None, 'inputs': item, 'problems': [], 'refused': str(e)}
					is_trip = False
				rows.append(row)
				in_row = in_row + 1 if is_trip else 0
				if in_row >= self.errors_stop:
					stopped = 'circuit breaker tripped after {} consecutive errors/timeouts: {} of {} chunk items started'.format(in_row, len(rows), len(chunk))
					break
			ends = {}
			for row in rows:
				if 'end' in row:
					ends[row['end']] = ends.get(row['end'], 0) + 1
			left_model = [r['run'] for r in rows if r.get('waiting', {}).get('kind') in ('model', 'step', 'reason')]
			waits_person = [r['run'] for r in rows if r.get('waiting', {}).get('kind') == 'human']
			errs = [{'run': r['run'], 'error': r['error']} for r in rows if 'error' in r]
			refs = [{'inputs': r['inputs'], 'refused': r['refused']} for r in rows if 'refused' in r]
			ends_text = ', '.join('{} {}'.format(n, e) for e, n in sorted(ends.items())) or '0 ended'
			summary = 'chunk {}/{} ({} remaining): {}; {} deferred ({} model, {} person); {} errors'.format(
				len(rows), len(chunk), remaining, ends_text, len(left_model) + len(waits_person), len(left_model), len(waits_person), len(errs))
			if stopped:
				summary += ' [STOPPED]'
			out = {
				'items': len(items), 'chunk': len(chunk), 'started': len(rows), 'remaining': remaining,
				'ends': ends, 'left_for_model': left_model, 'waits_for_person': waits_person,
				'errors': errs, 'refused': refs, 'summary': summary,
			}
			if stopped:
				out['stopped'] = stopped
			if report:
				self.write_report(report, rows, out)
				out['report'] = report
			return out

	def queues(self):
		'''The runs that did not end, by who must act: the model or a person (plus external queue if declared).'''
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
		if self.view.queue:
			try:
				out['pending'] = self.discover_queue() or []
			except Exception as e:
				out['pending_error'] = '{}: {}'.format(type(e).__name__, e)
		return out

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

	def evaluate(self, dataset, rules=None, preset=None, baseline=None, worker_opts=None):
		'''Score a ground-truth dataset (quality metrics + wall time), optionally comparing against a saved baseline.'''
		keep, self.runs = self.runs, None
		per_case = []
		t_all = time.monotonic()
		try:
			for i, case in enumerate(dataset):
				cname = case.get('name') or 'case-{}'.format(i + 1)
				merged_rules = dict(rules or {})
				merged_rules.update(case.get('rules') or {})
				use_preset = case.get('preset') if case.get('preset') is not None else preset
				pending = []
				for nid, v in (case.get('answers') or {}).items():
					for a in (v if isinstance(v, list) else [v]):
						a = dict(a)
						pending.append({'node': nid, 'who': 'person' if a.pop('person', False) else 'model', 'answer': a})
				t0 = time.monotonic()
				r = self.play(self.run(case.get('inputs'), rules=merged_rules, preset=use_preset), pending)
				if 'waiting' in r and worker_opts and (worker_opts.get('api_url') or worker_opts.get('reason_api_url')):
					r = self.work(r['run'], **worker_opts)
					if pending and 'waiting' in r:
						r = self.play(r, pending)
				wall = round(time.monotonic() - t0, 4)
				got_end = (r.get('outcome') or {}).get('end')
				checks, hits = 0, 0
				if 'expect_end' in case:
					checks += 1
					if got_end == case['expect_end']:
						hits += 1
				if 'expect_result' in case:
					checks += 1
					if r.get('result') == case['expect_result']:
						hits += 1
				if isinstance(case.get('expect_fields'), dict):
					run_state = self.load(r['run'])['state']
					for k, want in case['expect_fields'].items():
						checks += 1
						actual = self.see(run_state, k, cut=False)
						if actual == want:
							hits += 1
				if checks == 0:
					passed_case = got_end not in (None, 'error')
					score = 1.0 if passed_case else 0.0
				else:
					score = round(hits / float(checks), 4)
					passed_case = hits == checks
				per_case.append({'name': cname, 'end': got_end, 'passed': passed_case, 'score': score, 'wall_s': wall})
		finally:
			self.runs = keep
		total_wall = round(time.monotonic() - t_all, 4)
		n = len(per_case)
		n_pass = sum(1 for c in per_case if c['passed'])
		pass_rate = round(n_pass / float(n), 4) if n else 1.0
		avg_score = round(sum(c['score'] for c in per_case) / float(n), 4) if n else 1.0
		out = {
			'cases': n, 'passed': n_pass, 'pass_rate': pass_rate,
			'avg_score': avg_score, 'wall_s': total_wall, 'per_case': per_case,
		}
		if isinstance(baseline, dict):
			prev_map = dict((c['name'], c) for c in baseline.get('per_case', []))
			regs = [c['name'] for c in per_case if prev_map.get(c['name'], {}).get('passed') and not c['passed']]
			imps = [c['name'] for c in per_case if c['name'] in prev_map and not prev_map[c['name']].get('passed') and c['passed']]
			out['comparison'] = {
				'pass_rate_delta': round(pass_rate - float(baseline.get('pass_rate', 0)), 4),
				'score_delta': round(avg_score - float(baseline.get('avg_score', 0)), 4),
				'wall_s_delta': round(total_wall - float(baseline.get('wall_s', 0)), 4),
				'regressions': regs,
				'improvements': imps,
			}
		return out

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
			if req_argv and req_argv[0] in ('serve-stdio', 'serve-http', 'mcp'):
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
		'''Build the MCP tool list. Never exposes a tool for human gates.'''
		tools = []
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
			model_steps = [n for n in flow_nodes if (n.get('kind') == 'step' and n.get('lane') == 'model') or n.get('kind') == 'reason']
			if model_steps:
				names_text = ', '.join(n['id'] for n in model_steps)
				if has_worker:
					tools.append({
						'name': 'work_run',
						'description': 'Do the model steps and reason blocks of a run ({}) in isolated worker contexts until the run needs you or a person.'.format(names_text),
						'inputSchema': {
							'type': 'object',
							'properties': {'run': run_prop},
							'required': ['run'],
						},
					})
				else:
					tools.append({
						'name': 'answer_step',
						'description': 'Give the result of a model step or reason block ({}) when "waiting" has kind "step" or "reason".'.format(names_text),
						'inputSchema': {
							'type': 'object',
							'properties': {
								'run': run_prop,
								'result': {'description': 'The result matching "waiting.schema".'},
								'node': {'type': 'string', 'description': 'Optional node id to guard against stale calls.'},
							},
							'required': ['run', 'result'],
						},
					})
			if any(n.get('kind') == 'reason' and n.get('tools') for n in flow_nodes):
				tools.append({
					'name': 'arena_call',
					'description': 'Call a read-only tool listed in "waiting.tools" during a waiting "reason" block, within its hard budget.',
					'inputSchema': {
						'type': 'object',
						'properties': {
							'run': run_prop,
							'tool': {'type': 'string', 'description': 'Name of the read-only tool from waiting.tools.'},
							'args': {'type': 'object', 'description': 'Optional JSON arguments for the read-only tool.'},
						},
						'required': ['run', 'tool'],
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
			tools.append({
				'name': 'next_batch',
				'description': 'Run one unattended chunk of pending items (from items list or declared queue), deferring items needing a model or person.',
				'inputSchema': {
					'type': 'object',
					'properties': {
						'items': {'type': 'array', 'items': in_schema, 'description': 'Optional list of input objects (omitted to use declared queue).'},
						'size': {'type': 'integer', 'description': 'Optional chunk size (defaults to batch.size rule or 10).'},
					},
					'required': [],
				},
			})
			if self.view.rollback:
				tools.append({
					'name': 'restore_run',
					'description': 'Run the unit rollback block to restore state for a run.',
					'inputSchema': {'type': 'object', 'properties': {'run': run_prop}, 'required': ['run']},
				})
			if any(n.get('brief') for n in flow_nodes):
				tools.append({
					'name': 'read_artifact',
					'description': 'Inspect a saved full payload from a step with "brief" outputs (read-only).',
					'inputSchema': {
						'type': 'object',
						'properties': {
							'run': run_prop,
							'name': {'type': 'string', 'description': 'Artifact name (step id).'},
							'path': {'type': 'string', 'description': 'Optional dot-path inside the artifact.'},
							'offset': {'type': 'integer', 'description': 'Character offset (default 0).'},
							'limit': {'type': 'integer', 'description': 'Max characters (default 4000).'},
						},
						'required': ['run', 'name'],
					},
				})
		return tools

	def _mcp_dispatch(self, req, tools, exposed, worker_cfg, client_caps=None, approve_base_url=None):
		'''Handle one JSON-RPC 2.0 MCP message (shared by stdio MCP and Streamable HTTP MCP).
		-> response dict, or None for notifications (no "id").'''
		if not isinstance(req, dict):
			return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid Request'}}
		if 'id' not in req:
			return None
		req_id = req['id']
		method = req.get('method')
		params = req.get('params')
		if params is None:
			params = {}
		has_worker = bool((worker_cfg.get('api_url') and worker_cfg.get('model')) or (worker_cfg.get('reason_api_url') and worker_cfg.get('reason_model')))
		supports_elicit = bool(isinstance(client_caps, dict) and 'elicitation' in client_caps and client_caps['elicitation'] is not None and client_caps['elicitation'] is not False)
		if method == 'initialize':
			proto = params.get('protocolVersion') if isinstance(params, dict) else None
			if isinstance(params, dict) and isinstance(params.get('capabilities'), dict) and isinstance(client_caps, dict):
				client_caps.update(params['capabilities'])
			return {
				'jsonrpc': '2.0',
				'id': req_id,
				'result': {
					'protocolVersion': proto or '2025-03-26',
					'capabilities': {'tools': {}},
					'serverInfo': {'name': self.catalogue.get('unit') or 'rig', 'version': '2'},
				},
			}
		if method == 'ping':
			return {'jsonrpc': '2.0', 'id': req_id, 'result': {}}
		if method == 'tools/list':
			return {'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': tools}}
		if method == 'tools/call':
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
					res = self.work(args['run'], **worker_cfg)
				elif name == 'answer_step':
					if 'result' not in args:
						raise Refused('answer_step requires "result".')
					res = self.answer(args['run'], {'result': args['result']}, node=args.get('node'))
				elif name == 'arena_call':
					res = self.arena_call(args['run'], args['tool'], args.get('args'))
				elif name == 'run_status':
					res = self.status(args['run'])
				elif name == 'start_batch':
					items = args['items']
					if not isinstance(items, list):
						raise Refused('start_batch: "items" must be a list.')
					res = self.batch(items, workers=args.get('workers', 1))
				elif name == 'next_batch':
					res = self.next_batch(items=args.get('items'), size=args.get('size'))
				elif name == 'queues':
					res = self.queues()
				elif name == 'drop_run':
					res = self.drop(args['run'], args.get('reason'))
				elif name == 'restore_run':
					res = self.restore(args['run'])
				elif name == 'read_artifact':
					res = self.artifact(args['run'], args['name'], path=args.get('path'), offset=args.get('offset', 0), limit=args.get('limit', 4000))
				else:
					raise Refused('Unknown tool {}.'.format(name))
			except (Refused, ValueError, KeyError) as e:
				res = {'refused': str(e)}
			res = _mcp_decorate(res, has_worker, approve_base_url=approve_base_url, supports_elicitation=supports_elicit)
			return {
				'jsonrpc': '2.0',
				'id': req_id,
				'result': {
					'content': [{'type': 'text', 'text': json.dumps(res, ensure_ascii=False, default=str)}],
					'isError': False,
				},
			}
		return {'jsonrpc': '2.0', 'id': req_id, 'error': {'code': -32601, 'message': 'Method not found'}}

	def mcp(self, api_url=None, model=None, api_key=None, provider=None, reason_api_url=None, reason_model=None, reason_api_key=None, reason_provider=None, approve_url=None, think=False, max_tokens=4000, max_calls=50, timeout_s=120, stdin=None, stdout=None):
		'''Run a newline-delimited JSON-RPC 2.0 MCP server over stdin/stdout. Standard library only.'''
		inp = stdin if stdin is not None else sys.stdin
		out_stream = stdout if stdout is not None else sys.stdout
		worker_cfg = {
			'api_url': (api_url or os.environ.get('RIG_API_URL') or '').strip() or None,
			'model': (model or os.environ.get('RIG_MODEL') or '').strip() or None,
			'api_key': api_key if api_key is not None else os.environ.get('RIG_API_KEY'),
			'provider': provider or os.environ.get('RIG_PROVIDER') or 'openai',
			'reason_api_url': (reason_api_url or os.environ.get('RIG_REASON_API_URL') or '').strip() or None,
			'reason_model': (reason_model or os.environ.get('RIG_REASON_MODEL') or '').strip() or None,
			'reason_api_key': reason_api_key if reason_api_key is not None else os.environ.get('RIG_REASON_API_KEY'),
			'reason_provider': reason_provider or os.environ.get('RIG_REASON_PROVIDER'),
			'think': think, 'max_tokens': max_tokens, 'max_calls': max_calls, 'timeout_s': timeout_s,
		}
		has_worker = bool((worker_cfg['api_url'] and worker_cfg['model']) or (worker_cfg['reason_api_url'] and worker_cfg['reason_model']))
		tools = self._mcp_tools(has_worker)
		exposed = set(t['name'] for t in tools)
		client_caps = {}
		approve_base = approve_url or os.environ.get('RIG_APPROVE_URL')

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
			resp = self._mcp_dispatch(req, tools, exposed, worker_cfg, client_caps=client_caps, approve_base_url=approve_base)
			if resp is not None:
				send(resp)
		return 0

	def openapi_spec(self, server_url='http://127.0.0.1:8780'):
		'''Build an OpenAPI 3.1.0 specification for this unit's HTTP front.'''
		unit = self.catalogue.get('unit') or 'rig'
		in_schema = _input_schema(self.catalogue.get('in', []))
		paths = {
			'/api/run': {
				'post': {
					'operationId': 'start_run',
					'summary': 'Start a run for one item',
					'requestBody': {'required': True, 'content': {'application/json': {'schema': {
						'type': 'object',
						'properties': {
							'inputs': in_schema,
							'rules': {'type': 'object', 'additionalProperties': True},
							'preset': {'type': 'string'},
						},
					}}}},
					'responses': {'200': {'description': 'Run report JSON'}},
				},
			},
			'/api/runs': {'get': {'operationId': 'list_runs', 'summary': 'List runs', 'responses': {'200': {'description': 'Runs list'}}}},
			'/api/runs/{run}': {'get': {'operationId': 'run_status', 'summary': 'Get run status', 'parameters': [{'name': 'run', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'Run status'}}}},
			'/api/runs/{run}/answer': {'post': {'operationId': 'answer_run', 'summary': 'Answer waiting model step, reason block, or model gate', 'parameters': [{'name': 'run', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'Updated run report'}}}},
			'/api/runs/{run}/approve': {'post': {'operationId': 'approve_run', 'summary': 'Approve or reject a waiting human gate', 'parameters': [{'name': 'run', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'Updated run report'}}}},
			'/api/runs/{run}/drop': {'post': {'operationId': 'drop_run', 'summary': 'Drop a waiting run', 'parameters': [{'name': 'run', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'Dropped run report'}}}},
			'/api/batch': {'post': {'operationId': 'start_batch', 'summary': 'Run a batch of items', 'responses': {'200': {'description': 'Batch summary'}}}},
			'/api/next-batch': {'post': {'operationId': 'next_batch', 'summary': 'Run one unattended chunk', 'responses': {'200': {'description': 'Chunk summary'}}}},
			'/api/queues': {'get': {'operationId': 'queues', 'summary': 'List waiting and pending queues', 'responses': {'200': {'description': 'Queues JSON'}}}},
			'/api/rules': {'get': {'operationId': 'rules', 'summary': 'List rules, ui controls, and presets', 'responses': {'200': {'description': 'Rules JSON'}}}},
			'/api/flow': {'get': {'operationId': 'flow', 'summary': 'Describe flow nodes and blocks', 'responses': {'200': {'description': 'Flow JSON'}}}},
			'/mcp': {'post': {'operationId': 'mcp_rpc', 'summary': 'Streamable HTTP MCP JSON-RPC 2.0 endpoint', 'responses': {'200': {'description': 'JSON-RPC response'}}}},
		}
		if self.view.rollback:
			paths['/api/runs/{run}/restore'] = {'post': {'operationId': 'restore_run', 'summary': 'Execute rollback block for a run', 'parameters': [{'name': 'run', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'Restored run report'}}}}
		if any(n.get('brief') for n in self.catalogue.get('flow', [])):
			paths['/api/runs/{run}/artifacts/{name}'] = {'get': {'operationId': 'read_artifact', 'summary': 'Inspect saved brief step artifact', 'parameters': [{'name': 'run', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}, {'name': 'name', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'Artifact excerpt'}}}}
		return {
			'openapi': '3.1.0',
			'info': {'title': unit, 'version': '2.0.0', 'description': self.rules.fill(self.catalogue.get('intent') or '')},
			'servers': [{'url': server_url}],
			'paths': paths,
		}

	def _render_ui_rules_html(self):
		ui_rules = [r for r in self.catalogue.get('rules', []) if r.get('ui')]
		if not ui_rules:
			return ''
		rows = []
		for r in ui_rules:
			rid, lbl, ctrl, val = r['id'], r.get('label', r['id']), r['ui'], self.rules(r['id'])
			erid, elbl = _html.escape(rid), _html.escape(str(lbl))
			if ctrl == 'toggle' or r.get('type') == 'switch':
				chk = ' checked' if val else ''
				inp = '<input type="checkbox" data-rule="{}" data-type="switch"{}>'.format(erid, chk)
			elif ctrl == 'select' and r.get('options'):
				opts = ''.join('<option value="{0}"{1}>{0}</option>'.format(_html.escape(str(o)), ' selected' if o == val else '') for o in r['options'])
				inp = '<select data-rule="{}" data-type="choice">{}</select>'.format(erid, opts)
			elif ctrl in ('slider', 'number') or r.get('type') == 'number':
				mn = ' min="{}"'.format(r['min']) if 'min' in r else ''
				mx = ' max="{}"'.format(r['max']) if 'max' in r else ''
				itype = 'range' if (ctrl == 'slider' and 'min' in r and 'max' in r) else 'number'
				inp = '<input type="{}" data-rule="{}" data-type="number" value="{}"{}{}>'.format(itype, erid, _html.escape(str(val)), mn, mx)
			else:
				inp = '<input type="text" data-rule="{}" data-type="text" value="{}">'.format(erid, _html.escape(str(val)))
			rows.append('<label class="rule-row"><span><strong>{}</strong> <small>{}</small></span>{}</label>'.format(elbl, erid, inp))
		return '<section class="card"><h2>Rule Controls</h2><div id="ui-rules">{}</div></section>'.format(''.join(rows))

	def _render_sees_html(self, sees, base_dir=None):
		'''Render sees values, including visual image galleries and before/after diffs when present.'''
		if not sees:
			return '<p class="muted">No context values.</p>'
		blocks = []
		img_exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')
		for key, val in sees.items():
			ekey = _html.escape(str(key))
			if isinstance(val, str) and val.lower().endswith(img_exts):
				blocks.append('<div class="media-card"><h4>{}</h4><img src="/media?path={}" alt="{}"></div>'.format(ekey, urllib.parse.quote(val), ekey))
			elif isinstance(val, dict) and ('before' in val or 'after' in val or 'diff' in val):
				parts = ['<h4>{}</h4>'.format(ekey)]
				if 'before' in val and 'after' in val:
					b, a = val['before'], val['after']
					if isinstance(b, str) and b.lower().endswith(img_exts) and isinstance(a, str) and a.lower().endswith(img_exts):
						parts.append('<div class="gallery"><figure><figcaption>Before</figcaption><img src="/media?path={}"></figure><figure><figcaption>After</figcaption><img src="/media?path={}"></figure></div>'.format(urllib.parse.quote(b), urllib.parse.quote(a)))
					else:
						parts.append('<div class="diff-grid"><pre class="diff-before">{}</pre><pre class="diff-after">{}</pre></div>'.format(_html.escape(str(b)), _html.escape(str(a))))
				if 'diff' in val:
					parts.append('<pre class="diff-box">{}</pre>'.format(_html.escape(str(val['diff']))))
				blocks.append('<div class="sees-block">{}</div>'.format(''.join(parts)))
			else:
				blocks.append('<div class="sees-block"><h4>{}</h4><pre>{}</pre></div>'.format(ekey, _html.escape(json.dumps(val, ensure_ascii=False, indent=2, default=str))))
		return ''.join(blocks)

	def _http_page(self, title, body):
		css = (
			'body{font-family:system-ui,-apple-system,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#111;background:#fafafa}'
			'a{color:#0b57d0} .card{background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:16px 20px;margin:16px 0}'
			'.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;background:#eef2ff;color:#1e3a8a;margin-right:6px}'
			'.never{background:#fef2f2;color:#991b1b} .muted{color:#666;font-size:14px}'
			'pre{background:#f5f5f5;padding:12px;border-radius:8px;overflow:auto;font-size:13px}'
			'.rule-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #eee;gap:12px}'
			'.btn{display:inline-block;padding:10px 18px;border-radius:8px;border:1px solid #ccc;background:#fff;cursor:pointer;font-size:14px;margin-right:8px}'
			'.btn-ok{background:#0b57d0;color:#fff;border-color:#0b57d0} .btn-no{background:#b91c1c;color:#fff;border-color:#b91c1c}'
			'.gallery,.diff-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px} img{max-width:100%;border:1px solid #ddd;border-radius:6px}'
		)
		return '<!doctype html><html><head><meta charset="utf-8"><title>{}</title><style>{}</style></head><body>{}</body></html>'.format(
			_html.escape(title), css, body)

	def make_http_server(self, host='127.0.0.1', port=8780, reports_dir=None, worker_cfg=None):
		'''Create a threaded stdlib HTTP server serving Streamable HTTP MCP (/mcp), OpenAPI 3.1 (/openapi.json),
		REST API (/api/*), rule-bound UI controls (/), approval UI (/approve/<run>), and reports (/reports).'''
		kit = self
		wcfg = dict(worker_cfg or {})
		base_dir = os.path.dirname(os.path.abspath(self.runs)) if self.runs else os.getcwd()
		rep_dir = os.path.abspath(reports_dir) if reports_dir else os.path.join(base_dir, 'reports')
		has_worker = bool((wcfg.get('api_url') and wcfg.get('model')) or (wcfg.get('reason_api_url') and wcfg.get('reason_model')))
		tools = self._mcp_tools(has_worker)
		exposed = set(t['name'] for t in tools)
		sessions = {}

		class Handler(http.server.BaseHTTPRequestHandler):
			def send_body(self, code, data, ctype='application/json; charset=utf-8', extra_headers=None):
				raw = data.encode('utf-8') if isinstance(data, str) else data
				self.send_response(code)
				self.send_header('Content-Type', ctype)
				self.send_header('Content-Length', str(len(raw)))
				self.send_header('Cache-Control', 'no-store')
				for k, v in (extra_headers or {}).items():
					self.send_header(k, v)
				self.end_headers()
				self.wfile.write(raw)

			def read_body(self):
				n = int(self.headers.get('Content-Length', '0') or '0')
				return self.rfile.read(n).decode('utf-8') if n > 0 else ''

			def read_json_body(self):
				raw = self.read_body()
				return json.loads(raw) if raw.strip() else {}

			def server_base_url(self):
				return 'http://{}:{}'.format(host, self.server.server_port)

			def do_DELETE(self):
				parsed = urllib.parse.urlsplit(self.path)
				if parsed.path == '/mcp':
					sid = self.headers.get('Mcp-Session-Id')
					if sid:
						sessions.pop(sid, None)
					return self.send_body(200, json.dumps({'closed': True}))
				return self.send_body(404, json.dumps({'error': 'not found'}))

			def do_GET(self):
				parsed = urllib.parse.urlsplit(self.path)
				p = parsed.path
				qs = urllib.parse.parse_qs(parsed.query)
				try:
					if p == '/openapi.json':
						return self.send_body(200, json.dumps(kit.openapi_spec(self.server_base_url()), ensure_ascii=False, indent=2))
					if p == '/api/runs':
						lim = int(qs.get('limit', ['50'])[0])
						return self.send_body(200, json.dumps({'runs': kit.list_runs(limit=lim)}, ensure_ascii=False, default=str))
					if p == '/api/queues':
						return self.send_body(200, json.dumps(kit.queues(), ensure_ascii=False, default=str))
					if p == '/api/rules':
						return self.send_body(200, json.dumps({'rules': kit.rules.values(), 'ui_rules': [r for r in kit.catalogue.get('rules', []) if r.get('ui')], 'presets': sorted(kit.catalogue.get('presets', {}))}, ensure_ascii=False, default=str))
					if p == '/api/flow':
						return self.send_body(200, json.dumps({'start': kit.start, 'rollback': kit.view.rollback, 'finally': kit.view.final, 'flow': kit.catalogue.get('flow', []), 'blocks': kit.catalogue.get('blocks', [])}, ensure_ascii=False, default=str))
					m_art = re.match(r'^/api/runs/([\w.-]+)/artifacts/([\w.-]+)$', p)
					if m_art:
						res = kit.artifact(m_art.group(1), m_art.group(2), path=qs.get('path', [None])[0], offset=int(qs.get('offset', ['0'])[0]), limit=int(qs.get('limit', ['4000'])[0]))
						return self.send_body(200, json.dumps(res, ensure_ascii=False, default=str))
					m_run = re.match(r'^/api/runs/([\w.-]+)$', p)
					if m_run:
						return self.send_body(200, json.dumps(kit.status(m_run.group(1)), ensure_ascii=False, default=str))
					if p == '/media':
						rel = (qs.get('path') or [''])[0]
						cand = os.path.normpath(os.path.join(base_dir, rel)) if not os.path.isabs(rel) else os.path.normpath(rel)
						if not cand.startswith(os.path.normpath(base_dir) + os.sep) or not os.path.isfile(cand):
							return self.send_body(404, json.dumps({'error': 'not found'}))
						ctype = mimetypes.guess_type(cand)[0] or 'application/octet-stream'
						with open(cand, 'rb') as fh:
							return self.send_body(200, fh.read(), ctype)
					m_app = re.match(r'^/approve/([\w.-]+)$', p)
					if m_app:
						rid = m_app.group(1)
						st = kit.status(rid)
						w = st.get('waiting')
						unit = kit.catalogue.get('unit') or 'rig'
						if not isinstance(w, dict) or w.get('kind') != 'human':
							end_txt = (st.get('outcome') or {}).get('end') or 'waiting at {}'.format(st.get('at'))
							body = '<p><a href="/">&larr; Dashboard</a></p><div class="card"><h1>Run {}</h1><p>This run is not waiting for human approval (state: <strong>{}</strong>).</p><pre>{}</pre></div>'.format(
								_html.escape(rid), _html.escape(str(end_txt)), _html.escape(json.dumps(st, ensure_ascii=False, indent=2, default=str)))
							return self.send_body(200, kit._http_page('Approve ' + rid, body), 'text/html; charset=utf-8')
						opts = w.get('options')
						if opts:
							btns = ''.join('<button class="btn{}" type="submit" name="decision" value="{}">{}</button>'.format(
								' btn-ok' if i == 0 else '', _html.escape(str(o)), _html.escape(str(o))) for i, o in enumerate(opts))
							if kit.view.nodes.get(w['node'], {}).get('fail') and 'no' not in [str(o) for o in opts]:
								btns += '<button class="btn btn-no" type="submit" name="decision" value="no">no</button>'
						else:
							btns = '<button class="btn btn-ok" type="submit" name="decision" value="yes">Approve (yes)</button><button class="btn btn-no" type="submit" name="decision" value="no">Reject (no)</button>'
						sees_html = kit._render_sees_html(w.get('sees'), base_dir)
						body = (
							'<p><a href="/">&larr; Dashboard</a></p>'
							'<div class="card"><h1>{unit} — Approve {rid}</h1>'
							'<p><strong>{q}</strong></p><p class="muted">{chk}</p>'
							'{sees}'
							'<form method="post" action="/approve/{rid}" style="margin-top:16px">'
							'<p><input type="text" name="note" placeholder="Optional note or custom reply" style="width:100%;padding:8px;box-sizing:border-box"></p>'
							'<div>{btns}</div></form></div>'
						).format(unit=_html.escape(unit), rid=_html.escape(rid), q=_html.escape(w.get('name') or w['node']), chk=_html.escape(w.get('check') or ''), sees=sees_html, btns=btns)
						return self.send_body(200, kit._http_page('Approve ' + rid, body), 'text/html; charset=utf-8')
					if p == '/reports':
						files = sorted(f for f in os.listdir(rep_dir) if f.endswith('.md')) if os.path.isdir(rep_dir) else []
						items_html = ''.join('<li><a href="/reports/{0}">{0}</a></li>'.format(_html.escape(f)) for f in files) or '<li class="muted">No reports yet.</li>'
						return self.send_body(200, kit._http_page('Reports', '<p><a href="/">&larr; Dashboard</a></p><div class="card"><h1>Batch Reports</h1><ul>{}</ul></div>'.format(items_html)), 'text/html; charset=utf-8')
					m_rep = re.match(r'^/reports/([\w.-]+\.md)$', p)
					if m_rep:
						rp = os.path.join(rep_dir, m_rep.group(1))
						if not os.path.isfile(rp):
							return self.send_body(404, json.dumps({'error': 'report not found'}))
						with open(rp, encoding='utf-8') as fh:
							md = fh.read()
						return self.send_body(200, kit._http_page(m_rep.group(1), '<p><a href="/reports">&larr; Reports</a></p><div class="card"><h1>{}</h1><pre>{}</pre></div>'.format(_html.escape(m_rep.group(1)), _html.escape(md))), 'text/html; charset=utf-8')
					if p == '/':
						unit = kit.catalogue.get('unit') or 'rig'
						intent = kit.rules.fill(kit.catalogue.get('intent') or '')
						q = kit.queues()
						h_items = ''.join('<li><a href="/approve/{0}"><strong>{0}</strong></a> — {1}</li>'.format(_html.escape(x['run']), _html.escape(x.get('name') or x['node'])) for x in q.get('waits_for_person', [])) or '<li class="muted">None</li>'
						m_items = ''.join('<li><strong>{}</strong> — {}</li>'.format(_html.escape(x['run']), _html.escape(x.get('name') or x['node'])) for x in q.get('left_for_model', [])) or '<li class="muted">None</li>'
						ispec = kit.catalogue.get('intent_spec') or {}
						badges = ''
						if ispec.get('audience'):
							badges += '<span class="badge">Audience: {}</span>'.format(_html.escape(ispec['audience']))
						if ispec.get('style'):
							badges += '<span class="badge">Style: {}</span>'.format(_html.escape(ispec['style']))
						for nv in ispec.get('never', []):
							badges += '<span class="badge never">Never: {}</span>'.format(_html.escape(nv['text']))
						body = (
							'<div class="card"><h1>{unit}</h1><p>{intent}</p><div>{badges}</div>'
							'<p class="muted"><a href="/openapi.json">OpenAPI 3.1</a> · <a href="/reports">Reports</a> · MCP endpoint: <code>POST /mcp</code></p></div>'
							'{ui_rules}'
							'<div class="card"><h2>Waiting for Human Approval</h2><ul>{h}</ul></div>'
							'<div class="card"><h2>Waiting for Model</h2><ul>{m}</ul></div>'
						).format(unit=_html.escape(unit), intent=_html.escape(intent), badges=badges, ui_rules=kit._render_ui_rules_html(), h=h_items, m=m_items)
						return self.send_body(200, kit._http_page(unit, body), 'text/html; charset=utf-8')
					return self.send_body(404, json.dumps({'error': 'not found'}))
				except Refused as e:
					return self.send_body(400, json.dumps({'refused': str(e)}, ensure_ascii=False))
				except Exception as e:
					return self.send_body(500, json.dumps({'error': '{}: {}'.format(type(e).__name__, e)}, ensure_ascii=False))

			def do_POST(self):
				parsed = urllib.parse.urlsplit(self.path)
				p = parsed.path
				try:
					if p == '/mcp':
						raw = self.read_body()
						try:
							payload = json.loads(raw)
						except ValueError:
							return self.send_body(400, json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}))
						sid = self.headers.get('Mcp-Session-Id') or uuid.uuid4().hex
						caps = sessions.setdefault(sid, {})
						base_url = self.server_base_url()
						if isinstance(payload, list):
							resps = [r for r in (kit._mcp_dispatch(item, tools, exposed, wcfg, client_caps=caps, approve_base_url=base_url) for item in payload) if r is not None]
							if not resps:
								return self.send_body(202, '', extra_headers={'Mcp-Session-Id': sid})
							return self.send_body(200, json.dumps(resps, ensure_ascii=False, default=str), extra_headers={'Mcp-Session-Id': sid})
						resp = kit._mcp_dispatch(payload, tools, exposed, wcfg, client_caps=caps, approve_base_url=base_url)
						if resp is None:
							return self.send_body(202, '', extra_headers={'Mcp-Session-Id': sid})
						return self.send_body(200, json.dumps(resp, ensure_ascii=False, default=str), extra_headers={'Mcp-Session-Id': sid})
					if p == '/api/run':
						body = self.read_json_body()
						inputs = body.get('inputs', body) if isinstance(body, dict) and 'inputs' in body else body
						rules = body.get('rules') if isinstance(body, dict) and 'inputs' in body else None
						preset = body.get('preset') if isinstance(body, dict) and 'inputs' in body else None
						return self.send_body(200, json.dumps(kit.run(inputs, rules=rules, preset=preset), ensure_ascii=False, default=str))
					if p == '/api/batch':
						body = self.read_json_body()
						return self.send_body(200, json.dumps(kit.batch(body['items'], rules=body.get('rules'), preset=body.get('preset'), workers=body.get('workers', 1)), ensure_ascii=False, default=str))
					if p == '/api/next-batch':
						body = self.read_json_body()
						return self.send_body(200, json.dumps(kit.next_batch(items=body.get('items'), size=body.get('size'), rules=body.get('rules'), preset=body.get('preset')), ensure_ascii=False, default=str))
					m_ans = re.match(r'^/api/runs/([\w.-]+)/answer$', p)
					if m_ans:
						body = self.read_json_body()
						ans = body.get('answer', body) if isinstance(body, dict) and 'answer' in body else body
						return self.send_body(200, json.dumps(kit.answer(m_ans.group(1), ans, node=body.get('node') if isinstance(body, dict) else None, meta=body.get('meta') if isinstance(body, dict) else None), ensure_ascii=False, default=str))
					m_app_api = re.match(r'^/api/runs/([\w.-]+)/approve$', p)
					if m_app_api:
						body = self.read_json_body()
						words = body.get('words')
						if isinstance(words, str):
							words = words.split()
						elif words is None:
							dec = body.get('decision') or ('yes' if body.get('approve') else 'no')
							words = str(dec).split() + ([str(body['note'])] if body.get('note') else [])
						return self.send_body(200, json.dumps(kit.approve(m_app_api.group(1), words), ensure_ascii=False, default=str))
					m_rst = re.match(r'^/api/runs/([\w.-]+)/restore$', p)
					if m_rst:
						return self.send_body(200, json.dumps(kit.restore(m_rst.group(1)), ensure_ascii=False, default=str))
					m_drp = re.match(r'^/api/runs/([\w.-]+)/drop$', p)
					if m_drp:
						body = self.read_json_body()
						return self.send_body(200, json.dumps(kit.drop(m_drp.group(1), body.get('reason')), ensure_ascii=False, default=str))
					m_app = re.match(r'^/approve/([\w.-]+)$', p)
					if m_app:
						rid = m_app.group(1)
						form = urllib.parse.parse_qs(self.read_body())
						dec = (form.get('decision') or [''])[0].strip()
						note = (form.get('note') or [''])[0].strip()
						words = ([dec] if dec else []) + ([note] if note else [])
						res = kit.approve(rid, words)
						body = '<p><a href="/">&larr; Dashboard</a></p><div class="card"><h1>Decision recorded for {}</h1><pre>{}</pre></div>'.format(
							_html.escape(rid), _html.escape(json.dumps(res, ensure_ascii=False, indent=2, default=str)))
						return self.send_body(200, kit._http_page('Approved ' + rid, body), 'text/html; charset=utf-8')
					return self.send_body(404, json.dumps({'error': 'not found'}))
				except (Refused, ValueError, KeyError) as e:
					return self.send_body(400, json.dumps({'refused': str(e)}, ensure_ascii=False))
				except Exception as e:
					return self.send_body(500, json.dumps({'error': '{}: {}'.format(type(e).__name__, e)}, ensure_ascii=False))

			def log_message(self, *a):
				pass

		class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
			daemon_threads = True
			allow_reuse_address = True

			def server_bind(self):
				socketserver.TCPServer.server_bind(self)
				self.server_name, self.server_port = host, self.socket.getsockname()[1]

		return ThreadedServer((host, int(port)), Handler)

	def serve_http(self, host='127.0.0.1', port=8780, reports_dir=None, **worker_cfg):
		'''Serve Streamable HTTP MCP, OpenAPI 3.1, REST API, and built-in localhost approval UI.'''
		srv = self.make_http_server(host=host, port=port, reports_dir=reports_dir, worker_cfg=worker_cfg)
		print('serving {} at http://{}:{}/  (MCP: /mcp, OpenAPI: /openapi.json, Ctrl+C stops)'.format(self.catalogue.get('unit') or 'rig', host, srv.server_port), flush=True)
		try:
			srv.serve_forever()
		except KeyboardInterrupt:
			pass
		finally:
			srv.server_close()
		return 0

	# - Command line: one JSON line for each call
	def cli(self, argv, out=None):
		'''run [JSON] [--preset N] [--set id=value]... | batch ITEMS [--report PATH] [--workers N] [--preset N] [--set id=value]...
		| next-batch [ITEMS] [--size N] [--report PATH] [--preset N] [--set id=value]...
		| queues | answer RUN JSON [--node ID] [--meta JSON] | arena RUN TOOL [JSON]
		| work RUN [--api-url URL] [--model NAME] [--api-key KEY] [--provider openai|ollama|anthropic] [--reason-api-url URL] [--reason-model NAME] [--reason-provider P] [--think] [--max-tokens N] [--max-calls N]
		| approve RUN [yes|no|WORDS] | restore RUN | artifact RUN NAME [--path KEY] [--offset N] [--limit N]
		| resume RUN | status RUN | drop RUN [REASON...] | list [--limit N] | prune [--keep N]
		| rerun RUN --from ID [--set id=value]... | replay RUN | rules | flow
		| regress FILE [--baseline] | eval FILE [--baseline PATH] [--save-baseline]
		| serve-stdio | serve-http [--host 127.0.0.1] [--port 8780] [--reports DIR]
		| mcp [--api-url URL] [--model NAME] [--provider P] [--approve-url URL]'''
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
			elif cmd == 'next-batch':
				report, preset, size = take('--report'), take('--preset'), take('--size')
				ch = changes()
				items = None
				if argv:
					items = read_json(argv[0]) if os.path.exists(argv[0]) else json.loads(argv[0])
				res = self.next_batch(items=items, size=int(size) if size is not None else None, rules=ch, preset=preset, report=report)
			elif cmd == 'restore':
				res = self.restore(argv[0])
			elif cmd == 'artifact':
				path = take('--path')
				offset = take('--offset')
				limit = take('--limit')
				res = self.artifact(argv[0], argv[1], path=path, offset=int(offset) if offset is not None else 0, limit=int(limit) if limit is not None else 4000)
			elif cmd == 'eval':
				baseline_path = take('--baseline')
				save_baseline = '--save-baseline' in argv
				if save_baseline:
					argv.remove('--save-baseline')
				preset = take('--preset')
				api_url, model, api_key, provider = take('--api-url'), take('--model'), take('--api-key'), take('--provider')
				r_api_url, r_model, r_api_key, r_provider = take('--reason-api-url'), take('--reason-model'), take('--reason-api-key'), take('--reason-provider')
				ch = changes()
				dataset = read_json(argv[0])
				base_data = read_json(baseline_path) if (baseline_path and os.path.exists(baseline_path) and not save_baseline) else None
				w_opts = {'api_url': api_url, 'model': model, 'api_key': api_key, 'provider': provider,
					'reason_api_url': r_api_url, 'reason_model': r_model, 'reason_api_key': r_api_key, 'reason_provider': r_provider} if (api_url or r_api_url) else None
				res = self.evaluate(dataset, rules=ch, preset=preset, baseline=base_data, worker_opts=w_opts)
				if save_baseline and baseline_path:
					write_json(baseline_path, res)
					res['baseline'] = 'written'
			elif cmd == 'queues':
				res = self.queues()
			elif cmd == 'answer':
				node = take('--node')
				meta_raw = take('--meta')
				meta = json.loads(meta_raw) if meta_raw is not None else None
				if meta is not None and not isinstance(meta, dict):
					raise Refused('answer: --meta must be a JSON object.')
				res = self.answer(argv[0], json.loads(argv[1]), node=node, meta=meta)
			elif cmd == 'arena':
				res = self.arena_call(argv[0], argv[1], json.loads(argv[2]) if len(argv) > 2 else {})
			elif cmd == 'work':
				api_url = take('--api-url')
				model = take('--model')
				api_key = take('--api-key')
				provider = take('--provider')
				reason_api_url = take('--reason-api-url')
				reason_model = take('--reason-model')
				reason_api_key = take('--reason-api-key')
				reason_provider = take('--reason-provider')
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
					provider=provider,
					reason_api_url=reason_api_url,
					reason_model=reason_model,
					reason_api_key=reason_api_key,
					reason_provider=reason_provider,
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
			elif cmd == 'serve-http':
				host = take('--host') or '127.0.0.1'
				port = int(take('--port') or 8780)
				reports_dir = take('--reports')
				api_url = take('--api-url')
				model = take('--model')
				api_key = take('--api-key')
				provider = take('--provider')
				r_api_url = take('--reason-api-url')
				r_model = take('--reason-model')
				r_api_key = take('--reason-api-key')
				r_provider = take('--reason-provider')
				think = '--think' in argv
				if think:
					argv.remove('--think')
				max_tokens = take('--max-tokens')
				max_calls = take('--max-calls')
				return self.serve_http(
					host=host, port=port, reports_dir=reports_dir,
					api_url=api_url, model=model, api_key=api_key, provider=provider,
					reason_api_url=r_api_url, reason_model=r_model, reason_api_key=r_api_key, reason_provider=r_provider,
					think=think,
					max_tokens=int(max_tokens) if max_tokens is not None else 4000,
					max_calls=int(max_calls) if max_calls is not None else 50,
				)
			elif cmd == 'mcp':
				api_url = take('--api-url')
				model = take('--model')
				api_key = take('--api-key')
				provider = take('--provider')
				r_api_url = take('--reason-api-url')
				r_model = take('--reason-model')
				r_api_key = take('--reason-api-key')
				r_provider = take('--reason-provider')
				approve_url = take('--approve-url')
				think = '--think' in argv
				if think:
					argv.remove('--think')
				max_tokens = take('--max-tokens')
				max_calls = take('--max-calls')
				return self.mcp(
					api_url=api_url,
					model=model,
					api_key=api_key,
					provider=provider,
					reason_api_url=r_api_url,
					reason_model=r_model,
					reason_api_key=r_api_key,
					reason_provider=r_provider,
					approve_url=approve_url,
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
