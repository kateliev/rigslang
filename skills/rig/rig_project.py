"""Project commands of rig.py: new, build, doctor, test. Standard library only.

A project is a folder with one rig.json file:

    {
      "rig": 0,
      "name": "release",
      "level": 4,                      1 tools, 2 checked, 3 flow, 4 production (guide/levels.md)
      "source": "release.rig",         one .rig file, or a list of them
      "unit": "release",               the unit with the flow (not needed at level 1)
      "driver": "python3 tool.py",     the command line of the runner
      "build": {"gen": "gen", "skill": "skill/SKILL.md"},
      "kit": "rigkit.py",              the tool's own copy of kit/rigkit.py
      "tests": "python3 -m unittest discover -s tests",
      "regression": "tests/regression-set.json",
      "plugin": {"folder": "plugin", "owner": "local", "timeout_s": 120}   made by: rig.py plugin DIR
    }

build compiles the source to the files that the fronts read. doctor checks the project
against the list of its level and prints what is missing.
"""
import json
import os
import re
import shlex
import subprocess
import sys

import rig

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, 'kit', 'rigkit.py')
TEMPLATES = os.path.join(HERE, 'kit', 'templates')
LEVELS = {1: 'tools', 2: 'checked', 3: 'flow', 4: 'production'}


def read(path):
	with open(path, encoding='utf-8', newline='') as f:
		return f.read()


def manifest(folder):
	path = os.path.join(folder, 'rig.json')
	if not os.path.exists(path):
		raise SystemExit('{}: no rig.json here. Make a project with: rig.py new DIR NAME'.format(folder))
	with open(path, encoding='utf-8') as f:
		m = json.load(f)
	m.setdefault('level', 1)
	m.setdefault('build', {})
	m['sources'] = m['source'] if isinstance(m.get('source'), list) else [m.get('source')]
	if not m['sources'][0]:
		raise SystemExit('rig.json: "source" names no .rig file')
	return m


def loaded(folder, m):
	'''-> [(path, root, ctx)] for each source file.'''
	out = []
	for s in m['sources']:
		path = os.path.join(folder, s)
		_, root = rig.load(path)
		out.append((path, root, rig.Ctx(root, path)))
	return out


def main_unit(m, files):
	for _, root, _ in files:
		for u in rig.units(root):
			if (m.get('unit') and u.word(0) == m['unit']) or (not m.get('unit') and any(c.head in rig.FLOW for c in u.children)):
				return u
	return None


# - build ----------------------------------------------
def outputs(folder, m):
	'''-> {relative path: text} of every compiled file.'''
	files = loaded(folder, m)
	for path, root, _ in files:
		err, _ = rig.check(root, path)
		if err:
			raise SystemExit('{}: line {}: {}'.format(path, err[0][0], err[0][1]))
	gen = m['build'].get('gen', 'gen')
	out = {}
	main = main_unit(m, files)
	for _, root, ctx in files:
		for u in rig.units(root):
			name = u.word(0)
			if any(c.head in rig.FLOW for c in u.children) or u.kids('rule') or u.word(1) in ('tool', 'agent'):
				out[os.path.join(gen, name + '.json')] = rig.compile_to('json', u, ctx=ctx)
			if u.kids('in') and u.word(1) == 'tool':
				out[os.path.join(gen, name + '.tool.json')] = rig.compile_to('tool', u)
	if main is not None and m['build'].get('skill'):
		skill_path = m['build']['skill']
		ref = os.path.relpath(os.path.join(folder, gen, main.word(0) + '.json'), os.path.dirname(os.path.join(folder, skill_path))).replace(os.sep, '/')
		out[skill_path] = rig.skill(main, ref, None, m.get('driver'))
	if m.get('kit'):
		out[m['kit']] = read(KIT)
	if m.get('plugin'):
		sub = m['plugin'].get('folder', 'plugin')
		out[os.path.join(sub, 'src', 'gen', 'front.json')] = json.dumps(front(m, files, main), ensure_ascii=False, indent=1) + '\n'
		for rel in ('src/bridge.ts', 'src/index.ts', 'src/tools.ts', 'try.ts', 'agent.ts', 'tsconfig.json'):  # the same code for every tool: keep each copy current
			out[os.path.join(sub, *rel.split('/'))] = read(os.path.join(TEMPLATES, 'plugin', *rel.split('/')))
	return out


# - The front for a model that calls tools (the plugin) ---
def front(m, files, main):
	'''What the plugin of a local model needs: the tools, the short rules text, and the driver.
	The plugin has no knowledge of its own: it reads this file.'''
	driver = m.get('driver', 'python3 tool.py')
	tools, rules = [], []
	flow = main is not None and any(c.head in rig.FLOW for c in main.children)
	if flow:
		d = rig.tool_def(main)
		run = {'type': 'string', 'description': 'The run id: "run" in the result of start_run.'}
		tools.append({'name': 'start_run', 'kind': 'run', 'parameters': d['parameters'],
			'description': 'Start a run for one item: {}. Code does the work and stops when it needs you.'.format(d['description'])})
		model_gates = any(g.word(1) == 'judge' or (g.word(1) in ('hard', 'soft') and not g.kids('by')) for g in main.kids('gate'))
		if model_gates:  # a flow with no gate for the model gets no tool for it: one tool less to choose wrongly
			tools.append({'name': 'answer_gate', 'kind': 'answer_gate',
				'description': 'Answer the gate that a run waits at, when "waiting" has kind "judge". Decide as its "brief" says.',
				'parameters': {'type': 'object', 'properties': {'run': run, 'pass': {'type': 'boolean', 'description': 'true: the gate passes. false: it fails.'},
					'why': {'type': 'string', 'description': 'The reason, in one sentence.'}}, 'required': ['run', 'pass']}})
		model_steps = [f.word(0) for f in main.kids('step') if not f.kids('by') or any(rig.by_target(b.word(0), main) != 'bound' for b in f.kids('by'))]
		if model_steps:
			tools.append({'name': 'finish_step', 'kind': 'finish_step',
				'description': 'Give the result of the step that a run waits at, when "waiting" has kind "step". Do what its "do" says first.',
				'parameters': {'type': 'object', 'properties': {'run': run, 'result': {'description': 'What the step gave: a text, a number or an object.'}}, 'required': ['run', 'result']}})
		tools.append({'name': 'run_status', 'kind': 'status', 'description': 'Show a run again: where it is and what it waits for.',
			'parameters': {'type': 'object', 'properties': {'run': run}, 'required': ['run']}})
		tools.append({'name': 'start_batch', 'kind': 'batch', 'description': 'Start a run for each item of a list. Gives a short summary and the path of the report. Use it for more than one item.',
			'parameters': {'type': 'object', 'properties': {'items': {'type': 'array', 'items': d['parameters'], 'description': 'One object for each item, with the inputs of start_run.'}}, 'required': ['items']}})
		tools.append({'name': 'queues', 'kind': 'queues', 'description': 'The runs that did not end: left_for_model (you answer them), waits_for_person (the operator answers), errors.',
			'parameters': {'type': 'object', 'properties': {}, 'required': []}})
		inputs = ', '.join(x.word(0) for x in main.kids('in')) or 'no input'
		rules = ['To work on one item, call start_run ({}). Work on one item at a time.'.format(inputs),
			'Read each result. It is JSON.',
			'"outcome": the run ended. Tell the operator the end and the "problems". Then go to the next item.']
		if model_gates:
			rules.append('"waiting" with kind "judge": decide what "brief" asks. Call answer_gate with the run id, pass true or false, and why in one sentence.')
		if model_steps:
			rules.append('"waiting" with kind "step": do what "do" says. Call finish_step with the run id and the result.')
		rules.append('"waiting" has "problems": your last answer at that node failed for these reasons. Fix them in the new answer.')
		if any(g.word(1) == 'human' for g in main.kids('gate')):
			rules.append('"waiting" with kind "human": you cannot answer. Show the operator what "brief" asks. The operator answers with a chat message: approve yes (or no), and the words of the answer, if any. In a terminal, the command in "command" does the same. Stop, and wait for the result of that answer.')
		rules.append('More than one item: call start_batch with the list. Show only its summary and the report path. Then, for each run in "left_for_model": call run_status, and answer it as in the rules above. Tell the operator the list "waits_for_person". To continue earlier work, call queues.')
		rules += ['"refused": the call was wrong. It is final. Do not repeat it. Call run_status to see where the run is.',
			'"error": tell the operator the error text. Do not answer the run.',
			'Do not invent names or numbers. Use only values from a result.',
			'When a run ends and its "guessed" list is not empty, write one last line: Guessed: and the names in that list.']
	for _, root, _ in files:
		for u in rig.units(root):
			if u.word(1) == 'tool' and u.kids('in'):
				d = rig.tool_def(u)
				text = d.get('returns', {}).get('description')
				tools.append({'name': u.word(0).replace('-', '_'), 'kind': 'call', 'unit': u.word(0), 'parameters': d['parameters'],
					'description': d['description'] + ('. It gives back: ' + text if text else '')})
	prompt = ''
	if rules:
		intent = ' '.join(rig.text_of(x) for x in main.kids('intent'))
		prompt = 'Rules for the tool {}{}:\n'.format(m.get('name', main.word(0)), ' (' + rig.fill_values(main, intent) + ')' if intent else '') + '\n'.join('{}. {}'.format(i + 1, r) for i, r in enumerate(rules))
	return {'name': m.get('name'), 'prompt': prompt, 'driver': shlex.split(driver), 'timeout_s': m['plugin'].get('timeout_s', 120), 'tools': tools}


def plugin(folder, owner):
	'''Add the plugin folder (the front for a local model in LM Studio) to a project.'''
	m = manifest(folder)
	sub = (m.get('plugin') or {}).get('folder', 'plugin')
	target = os.path.join(folder, sub)
	if os.path.exists(target) and os.listdir(target):
		raise SystemExit('{} exists and is not empty'.format(target))
	base = os.path.join(TEMPLATES, 'plugin')
	words = {'__NAME__': m.get('name', 'tool'), '__OWNER__': owner}
	for dirpath, _, names in os.walk(base):
		for n in sorted(names):
			src = os.path.join(dirpath, n)
			rel = os.path.relpath(src, base)
			if rel.endswith('.tmpl'):
				rel = os.path.join(os.path.dirname(rel), '.' + os.path.basename(rel)[:-5])
			text = read(src)
			for k, v in words.items():
				text = text.replace(k, v)
			os.makedirs(os.path.dirname(os.path.join(target, rel)), exist_ok=True)
			rig.write(os.path.join(target, rel), text)
	with open(os.path.join(folder, 'rig.json'), encoding='utf-8') as f:
		data = json.load(f)
	data['plugin'] = {'folder': sub, 'owner': owner, 'timeout_s': 120}
	rig.write(os.path.join(folder, 'rig.json'), json.dumps(data, ensure_ascii=False, indent=1) + '\n')
	build(folder)
	print('\nMade {}. Next: cd {} && npm install && node --no-warnings try.ts'.format(target, target))
	return 0


def build(folder, check=False):
	m = manifest(folder)
	stale = []
	for rel, text in sorted(outputs(folder, m).items()):
		path = os.path.join(folder, rel)
		same = os.path.exists(path) and read(path).replace('\r\n', '\n') == text
		if same:
			continue
		stale.append(rel)
		if not check:
			os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
			rig.write(path, text)
			print('wrote ' + rel)
	if check:
		for rel in stale:
			print('stale: ' + rel)
		print('All compiled files are current.' if not stale else 'Run: rig.py build')
		return 1 if stale else 0
	if not stale:
		print('Nothing to do: all compiled files are current.')
	return 0


# - test -----------------------------------------------
def run_cmd(folder, cmd):
	'''Run a command of rig.json in the folder. "python3" means this Python. -> (code, output)'''
	args = shlex.split(cmd)
	if args and args[0] in ('python', 'python3'):
		args[0] = sys.executable
	try:
		r = subprocess.run(args, cwd=folder, capture_output=True, text=True, timeout=600)
	except (OSError, subprocess.TimeoutExpired) as e:
		return 1, str(e)
	return r.returncode, (r.stdout + r.stderr).strip()


def test(folder):
	m = manifest(folder)
	if not m.get('tests'):
		print('rig.json has no "tests" command')
		return 1
	code, out = run_cmd(folder, m['tests'])
	print(out)
	return code


# - doctor ---------------------------------------------
def doctor(folder, run_tests=True):
	'''Check the project against the list of its level. -> 0 when nothing is missing.'''
	m = manifest(folder)
	level = int(m['level'])
	rows = []  # (level, 'ok' | 'MISS' | 'note', text)

	def add(lv, ok, text, detail=None, soft=False):
		if lv <= level:
			rows.append((lv, 'ok' if ok else ('note' if soft else 'MISS'), text + ('' if ok or not detail else ': ' + detail)))
	try:
		files = loaded(folder, m)
	except SystemExit as e:
		print('MISS  the source does not parse: {}'.format(e))
		return 1
	errs, warns, units = [], [], []
	for path, root, ctx in files:
		e, w = rig.check(root, path)
		errs += ['{} line {}: {}'.format(os.path.basename(path), ln, t) for ln, t in sorted(e)]
		warns += ['{} line {}: {}'.format(os.path.basename(path), ln, t) for ln, t in sorted(w)]
		units += [(u, ctx) for u in rig.units(root)]
	main = main_unit(m, files)

	# Level 1: tools
	add(1, not errs, 'the source has no errors', '; '.join(errs[:3]))
	holes = [u.word(0) for u, ctx in units if 'hole' in rig.unit_status(u, ctx)]
	add(1, not holes, 'every unit has code (a "code" line or a cast)', ', '.join(holes))
	bare = [u.word(0) for u, _ in units if not u.kids('intent')]
	add(1, not bare, 'every unit has an intent', ', '.join(bare))
	untyped = ['{}.{}'.format(u.word(0), x.word(0)) for u, _ in units for x in u.kids('in') if rig.in_parts(x)[1] is None or not rig.in_parts(x)[2]]
	add(1, not untyped, 'every input has a type and a text', ', '.join(untyped))
	try:
		stale = [rel for rel, text in outputs(folder, m).items() if not os.path.exists(os.path.join(folder, rel)) or read(os.path.join(folder, rel)).replace('\r\n', '\n') != text] if not errs else []
		add(1, not stale and not errs, 'the compiled files are current (rig.py build)', ', '.join(sorted(stale)) or 'fix the errors first')
	except SystemExit as e:
		add(1, False, 'the compiled files are current (rig.py build)', str(e))
	numbers = [w for w in warns if 'a number in the text' in w]
	add(1, not numbers, 'no number in the text of a node: every number is a rule', '; '.join(numbers[:3]))
	add(1, bool(m.get('tests')), 'rig.json names the tests command')
	if m.get('tests') and run_tests:
		code, out = run_cmd(folder, m['tests'])
		add(1, code == 0, 'the tests pass', (out.splitlines() or ['no output'])[-1])

	# Level 2: checked
	gates = [(u, g, rig.gate_level(g, u, ctx, (u.word(0),))) for u, ctx in units for g in u.kids('gate')]
	add(2, bool(gates), 'the tool has at least one gate')
	for name, bad in (('none', 'every hard or soft gate names code that exists'), ('code', 'a test names the code of every gate')):
		got = ['{}.{}'.format(u.word(0), g.word(0)) for u, g, lv in gates if lv == name]
		add(2, not got, bad, ', '.join(got))
	unread = [w for w in warns if 'is not read by any step or gate' in w]
	add(2, not unread, 'every rule is read by a step or a gate', '; '.join(unread[:3]))
	nobrief = [w for w in warns if 'has no brief' in w]
	add(2, not nobrief, 'every judge and human gate has a brief', '; '.join(nobrief))
	rules = [r for u, _ in units for r in u.kids('rule')]
	bare_rules = [r.word(0) for r in rules if rig.rule_type(r) == 'number' and not r.kids('note')]
	add(2, not bare_rules, 'every number rule has a note that says where the value comes from', ', '.join(bare_rules), soft=True)
	if gates:
		cv = rig.coverage(main, [c for u, c in units if u is main][0]) if main is not None else None
		if cv:
			rows.append((2, 'note', 'coverage: {} of {} gates by proved or tested code, {} by the model, {} by a person'.format(cv['proved'] + cv['tested'], cv['gates'], cv['judge'], cv['human'])))

	# Level 3: flow
	add(3, main is not None, 'a unit has a flow')
	if main is not None:
		ends = [e.word(0) for e in main.kids('end')]
		add(3, bool(ends), 'the flow has an end node')
		lost = [w for w in warns if 'cannot be reached' in w]
		add(3, not lost, 'every node can be reached', '; '.join(lost))
		onefail = [g.word(0) for g in main.kids('gate') if not g.kids('fail') or not g.kids('pass')]
		add(3, not onefail, 'every gate has a pass line and a fail line', ', '.join(onefail))
		add(3, bool(m.get('driver')), 'rig.json names the driver: the runner command')
		add(3, bool(m['build'].get('skill')), 'the skill is compiled (build.skill in rig.json)')
		reg = m.get('regression')
		cases = None
		if reg and os.path.exists(os.path.join(folder, reg)):
			with open(os.path.join(folder, reg), encoding='utf-8') as f:
				cases = json.load(f)
		add(3, cases is not None, 'a regression set exists (rig.json "regression")')
		if cases is not None:
			add(3, all(c.get('expect') for c in cases), 'every regression case has an expected result (driver regress FILE --baseline)')
			seen = set(n for c in cases for n in (c.get('expect') or {}).get('path', []))
			noend = [e for e in ends if e not in seen]
			add(3, not noend, 'every end node is the end of a regression case', ', '.join(noend))
			nogate = [g.word(0) for g in main.kids('gate') if g.word(0) not in seen]
			add(3, not nogate, 'every gate is on the path of a regression case', ', '.join(nogate), soft=True)
			if m.get('driver') and run_tests:
				code, out = run_cmd(folder, m['driver'] + ' regress ' + reg)
				add(3, code == 0, 'the regression set passes', (out.splitlines() or ['no output'])[-1][:300])

	# Level 4: production
	for rel, why in (('README.md', 'how to set up and run the tool'), ('notes/project-facts.md', 'what is true about the project, for an agent on any computer'),
			('notes/failures-log.md', 'what failed and why'), ('bugs-and-fixes.md', 'every code bug: symptom, cause, fix'), ('reports', 'the reports of the runs')):
		add(4, os.path.exists(os.path.join(folder, rel)), '{} exists ({})'.format(rel, why))
	perms = [r.word(0) for r in rules if r.word(0).startswith('permissions.')]
	add(4, bool(perms), 'a rule of the group "permissions" guards every change that cannot be undone')
	humans = [g.word(0) for u, g, lv in gates if lv == 'human']
	add(4, bool(humans) or bool(m.get('human')), 'a human gate holds the judgment of the person (or rig.json "human" says why none is needed)')

	missing = 0
	print('{} — level {} ({})'.format(m.get('name', os.path.basename(os.path.abspath(folder))), level, LEVELS.get(level, '?')))
	for lv, state, text in rows:
		print('  {:<5} L{}  {}'.format(state, lv, text))
		missing += state == 'MISS'
	other = [w for w in warns if not any(k in w for k in ('a number in the text', 'is not read by', 'has no brief', 'cannot be reached', 'no test names'))]
	for w in other:
		print('  note      ' + w)
	print('Nothing is missing for level {}.'.format(level) if not missing else '{} missing for level {}.'.format(missing, level))
	return 1 if missing else 0


# - new ------------------------------------------------
def rig_source(name, level):
	L = ['; {}: made by rig.py new, level {} ({}). Replace each TODO, then: rig.py build . && rig.py doctor .'.format(name, level, LEVELS[level]), '']
	if level == 1:
		L += ['unit {} tool'.format(name),
			'  intent "TODO: say what the tool does, in one sentence; the model reads this as the description"',
			'  in text str "the text to measure"',
			'  out (record words int characters int) "the counts"',
			'  code tools.py',
			'    test tests/test_tools.py']
		return '\n'.join(L) + '\n'
	L += ['unit {} agent'.format(name),
		'  intent "TODO: say what the tool must do, in one sentence"',
		'  in item str "the item to work on"',
		'  out text "the end of the run, with the problems"',
		'  code gates gates.py',
		'    test tests/test_gates.py',
		'  code steps steps.py',
		'    test tests/test_steps.py',
		'',
		'  rule limits.min_length 3',
		'    min 1',
		'    max 1000',
		'    label "Shortest item"',
		'    unit "characters"',
		'    note "TODO: say where this value comes from"']
	if level >= 4:
		L += ['  rule permissions.write off',
			'    label "The tool may write"',
			'    note "off: a dry run. The run ends at ready and changes nothing."']
	L += ['',
		'  step look "Look"',
		'    do "read the item and measure it"',
		'    by steps.look',
		'    next -> long-enough',
		'  gate long-enough hard "Long enough"',
		'    ensure "the item has at least {limits.min_length} characters"',
		'    by gates.long_enough',
		'    pass -> sensible',
		'    fail -> stop "too short"',
		'  gate sensible judge "Makes sense"',
		'    brief "TODO: say what the model must judge; pass if the item makes sense"',
		'    pass -> {}'.format('approve' if level >= 4 else 'done'),
		'    fail -> stop "the model said no"']
	if level >= 4:
		L += ['  gate approve human "A person agrees"',
			'    brief "TODO: say what to show the person and what to ask"',
			'    pass -> allowed',
			'    fail -> stop "the person said no"',
			'  gate allowed hard "The tool may write"',
			'    reads permissions.write',
			'    ensure "the rule permissions.write is on"',
			'    by gates.may_write',
			'    pass -> done',
			'    fail -> ready "dry run"',
			'  end ready "Ready, nothing written"']
	L += ['  end done "Done"', '  end stop "Stopped"']
	return '\n'.join(L) + '\n'


def template_files(level):
	'''-> [(template path, target path)] for the level.'''
	out = []
	for family in (['tools'] if level == 1 else ['flow'] + (['flow3'] if level >= 3 else []) + (['flow4'] if level >= 4 else [])):
		base = os.path.join(TEMPLATES, family)
		for dirpath, _, names in os.walk(base):
			for n in sorted(names):
				src = os.path.join(dirpath, n)
				out.append((src, os.path.relpath(src, base)))
	return out


def level_blocks(text, level):
	'''Keep the lines between "# >>> level N" and "# <<< level N" only from level N up.'''
	out, keep = [], True
	for line in text.split('\n'):
		m = re.match(r'^\s*# (>>>|<<<) level (\d)\s*$', line)
		if m:
			keep = m.group(1) == '<<<' or level >= int(m.group(2))
			continue
		if keep:
			out.append(line)
	return '\n'.join(out)


def new(folder, name, level=2):
	if not re.match(r'^[a-z][a-z0-9-]*$', name):
		raise SystemExit('the name: small letters, digits and "-", for example "kern-check"')
	if level not in LEVELS:
		raise SystemExit('--level 1, 2, 3 or 4')
	if os.path.exists(folder) and os.listdir(folder):
		raise SystemExit('{} exists and is not empty'.format(folder))
	os.makedirs(folder, exist_ok=True)
	m = {'rig': 0, 'name': name, 'level': level, 'source': name + '.rig'}
	if level > 1:
		m['unit'] = name
	m['driver'] = 'python3 tool.py'
	m['build'] = {'gen': 'gen'} if level == 1 else {'gen': 'gen', 'skill': 'skill/SKILL.md'}
	m['kit'] = 'rigkit.py'
	m['tests'] = 'python3 -m unittest discover -s tests'
	if level >= 3:
		m['regression'] = 'tests/regression-set.json'
	rig.write(os.path.join(folder, 'rig.json'), json.dumps(m, ensure_ascii=False, indent=1) + '\n')
	rig.write(os.path.join(folder, name + '.rig'), rig_source(name, level))
	words = {'__NAME__': name, '__FN__': name.replace('-', '_'), '__LEVEL__': str(level), '__LEVEL_NAME__': LEVELS[level]}
	for src, rel in template_files(level):
		text = read(src)
		for k, v in words.items():
			text = text.replace(k, v)
			rel = rel.replace(k, v)
		text = level_blocks(text, level)
		if rel.endswith('.tmpl'):
			rel = os.path.join(os.path.dirname(rel), '.' + os.path.basename(rel)[:-5])  # gitignore.tmpl -> .gitignore
		path = os.path.join(folder, rel)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		rig.write(path, text)
	build(folder)
	if level >= 3:
		code, out = run_cmd(folder, 'python3 tool.py regress tests/regression-set.json --baseline')
		print(out)
	print('\nMade {} (level {}, {}). Next:'.format(folder, level, LEVELS[level]))
	print('  1. Replace each TODO in {}.rig and in the code files.'.format(name))
	print('  2. rig.py build {0}   then   rig.py doctor {0}'.format(folder))
	return 0


def main(cmd, rest):
	if cmd == 'new':
		level = int(rig.option(rest, '--level') or 2)
		if len(rest) < 2:
			raise SystemExit('new DIR NAME [--level 1|2|3|4]')
		return new(rest[0], rest[1], level)
	if cmd == 'plugin':
		owner = rig.option(rest, '--owner') or 'local'
		return plugin(rest[0] if rest else '.', owner)
	folder = next((a for a in rest if not a.startswith('--')), '.')
	if cmd == 'build':
		return build(folder, '--check' in rest)
	if cmd == 'doctor':
		return doctor(folder, '--no-tests' not in rest)
	if cmd == 'test':
		return test(folder)
	raise SystemExit('new, build, doctor or test')
