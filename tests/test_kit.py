"""Tests for the runtime kit (skills/rig/kit/rigkit.py) and the project commands of rig.py
(new, build, doctor). Run: python -m unittest discover tests"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig'))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig', 'kit'))
import rig  # noqa: E402
import rig_project  # noqa: E402
import rigkit  # noqa: E402

RELEASE = os.path.join(ROOT, 'examples', 'release-tool')
BAND = os.path.join(ROOT, 'examples', 'band-facts')

FLOW = '''unit demo agent
  in n int "a number"
  rule limits.max 10
    min 1
    max 100
  rule limits.rounds 2
  step double "Double"
    do "double the number"
    by code.double
    next -> small
  gate small hard "Small"
    ensure "the number is at most {limits.max}"
    by code.small
    pass -> nice
    fail -> big "too big"
    fail -> huge "much too big"
  gate nice judge "Nice"
    brief "is {limits.max} a nice limit?"
    pass -> sure
    fail -> fix
  step fix "Fix"
    do "give a better number"
    next -> small
  gate sure human "Sure"
    brief "ask the person"
    pass -> done
    fail -> big
  end done "Done"
  end big "Big"
  end huge "Huge"
'''


def catalogue(text=FLOW):
	root = rig.parse(text)
	return rig.catalog(rig.units(root)[0])


def kit(runs=None, **code):
	k = rigkit.Kit(catalogue(), runs=runs)
	fns = {'double': lambda s, R: s['n'] * 2 if 'fix' not in s else s['fix'],
		'small': lambda s, R: (s.get('fix') or s['double']) <= R('limits.max') or {'pass': False, 'when': 'much too big' if s['double'] > 50 else 'too big', 'problems': ['{} is over limits.max'.format(s['double'])]}}
	fns.update(code)
	return k.bind('code', fns)


class Rules(unittest.TestCase):
	def test_values_and_limits(self):
		R = rigkit.Rules(catalogue())
		self.assertEqual(R('limits.max'), 10)
		R.set('limits.max', '20')
		self.assertEqual(R('limits.max'), 20)
		with self.assertRaises(ValueError):
			R.set('limits.max', 1000)
		with self.assertRaises(KeyError):
			R('limits.nothing')
		self.assertEqual(R.fill('at most {limits.max}, {not.a.rule} {word}'), 'at most 20, {not.a.rule} {word}')


class Runs(unittest.TestCase):
	def test_code_walks_until_the_model(self):
		r = kit().run({'n': 2})
		self.assertEqual(r['path'], ['double', 'small'])
		self.assertEqual(r['waiting']['kind'], 'judge')
		self.assertEqual(r['waiting']['brief'], 'is 10 a nice limit?')

	def test_a_fail_follows_the_line_that_the_gate_names(self):
		self.assertEqual(kit().run({'n': 8})['outcome']['end'], 'big')
		r = kit().run({'n': 80})
		self.assertEqual(r['outcome']['end'], 'huge')
		self.assertIn('limits.max', r['problems'][0])

	def test_a_rule_change_for_one_run(self):
		self.assertIn('waiting', kit().run({'n': 8}, rules={'limits.max': 16}))

	def test_inputs_are_checked(self):
		with self.assertRaises(rigkit.Refused):
			kit().run({'m': 1})
		with self.assertRaises(rigkit.Refused):
			kit().run({})

	def test_answers_and_refusals(self):
		k = kit()
		r = k.run({'n': 2})
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'result': 3})          # a gate needs "pass"
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'pass': True}, node='small')  # the run is not there
		r = k.answer(r['run'], {'pass': True, 'why': 'round'})
		self.assertEqual(r['guessed'], ['nice'])
		self.assertEqual(r['waiting']['kind'], 'human')
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'pass': True})         # the model cannot answer for the person
		r = k.answer(r['run'], {'pass': True}, who='person')
		self.assertEqual(r['outcome']['end'], 'done')
		self.assertEqual(r['guessed'], ['nice'])
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'pass': True})         # the run ended

	def test_the_model_does_a_step_with_no_code(self):
		k = kit()
		r = k.run({'n': 2})
		r = k.answer(r['run'], {'pass': False})
		self.assertEqual((r['waiting']['node'], r['waiting']['kind']), ('fix', 'step'))
		r = k.answer(r['run'], {'result': 3})
		self.assertEqual(r['waiting']['node'], 'nice')
		self.assertEqual(r['path'], ['double', 'small', 'nice', 'fix', 'small'])

	def test_a_loop_stops(self):
		k = rigkit.Kit(catalogue(), max_visits=3).bind('code', {'double': lambda s, R: 1, 'small': lambda s, R: True})
		r = k.run({'n': 1})
		for _ in range(10):
			if 'outcome' in r:
				break
			r = k.answer(r['run'], {'pass': False} if r['waiting']['kind'] == 'judge' else {'result': 1})
		self.assertIsNone(r['outcome']['end'])
		self.assertIn('more than 3 times', r['outcome']['label'])

	def test_an_error_is_a_result_and_the_run_can_resume(self):
		state = {'broken': True}

		def double(s, R):
			if state['broken']:
				raise ValueError('the host is not ready')
			return 2
		k = kit(double=double)
		r = k.run({'n': 1})
		self.assertIn('the host is not ready', r['error']['error'])
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'result': 2})          # code does this step
		state['broken'] = False
		self.assertEqual(k.resume(r['run'])['waiting']['node'], 'nice')

	def test_a_run_survives_a_restart(self):
		tmp = tempfile.mkdtemp()
		try:
			r = kit(runs=tmp).run({'n': 2})
			r = kit(runs=tmp).answer(r['run'], {'pass': True})   # a new Kit, as after a restart
			self.assertEqual(r['waiting']['node'], 'sure')
			self.assertEqual(r['path'], ['double', 'small', 'nice'])
		finally:
			shutil.rmtree(tmp)

	def test_a_gate_with_no_code_is_a_guess(self):
		k = rigkit.Kit(catalogue()).bind('code', {'double': lambda s, R: 2})
		r = k.run({'n': 1})
		self.assertEqual((r['waiting']['node'], r['waiting']['kind']), ('small', 'judge'))
		self.assertIn('no_code', r['waiting'])
		self.assertEqual(k.answer(r['run'], {'pass': True})['guessed'], ['small'])

	def test_command_line(self):
		lines = []
		k = kit()
		self.assertEqual(k.cli(['run', '{"n": 2}', '--set', 'limits.max=30'], lines.append), 0)
		self.assertEqual(k.cli(['answer', 'no-such-run', '{"pass": true}'], lines.append), 0)
		self.assertIn('waiting', lines[0])
		self.assertIn('refused', lines[1])
		self.assertEqual(k.cli(['run', 'not json'], lines.append), 0)
		self.assertIn('refused', lines[2])

	def test_batch_and_queues(self):
		tmp = tempfile.mkdtemp()
		try:
			k = kit(runs=os.path.join(tmp, 'runs'))
			report = os.path.join(tmp, 'reports', 'b.md')
			got = k.batch([{'n': 2}, {'n': 8}, {'n': 80}, {'wrong': 1}], report=report)
			self.assertEqual(got['ends'], {'big': 1, 'huge': 1})
			self.assertEqual(len(got['left_for_model']), 1)
			self.assertEqual(len(got['refused']), 1)
			with open(report, encoding='utf-8') as f:
				text = f.read()
			self.assertLess(text.index('## Errors and refused items'), text.index('## Items with problems'))
			q = k.queues()
			self.assertEqual([e['node'] for e in q['left_for_model']], ['nice'])
			r = k.answer(q['left_for_model'][0]['run'], {'pass': True})
			self.assertEqual([e['node'] for e in k.queues()['waits_for_person']], ['sure'])
			k.answer(r['run'], {'pass': True}, who='person')
			self.assertEqual(k.queues(), {'left_for_model': [], 'waits_for_person': [], 'errors': []})
		finally:
			shutil.rmtree(tmp)

	def test_a_batch_stops_when_the_host_is_down(self):
		def double(s, R):
			raise OSError('the host is down')
		got = kit(double=double).batch([{'n': 1}] * 5)
		self.assertEqual(got['started'], 2)
		self.assertIn('2 errors in a row', got['stopped'])

	def test_sees(self):
		text = FLOW.replace('    brief "is {limits.max} a nice limit?"', '    brief "is {limits.max} a nice limit?"\n    sees n double nothing.here')
		k = rigkit.Kit(catalogue(text)).bind('code', {'double': lambda s, R: {'value': s['n'] * 2}, 'small': lambda s, R: True})
		r = k.run({'n': 2})
		self.assertEqual(r['waiting']['sees'], {'n': 2, 'double': {'value': 4}})   # a path that is not there is left out
		r = k.answer(r['run'], {'pass': True})
		r = k.answer(r['run'], {'pass': True}, who='person')
		self.assertNotIn('result', r)                                              # a gate ended the run: no result

	def test_the_result_is_the_value_of_the_step_before_the_end(self):
		text = 'unit t agent\n  step make\n    by code.make\n    next -> done\n  end done\n'
		k = rigkit.Kit(catalogue(text)).bind('code', {'make': lambda s, R: 'made'})
		self.assertEqual(k.run({})['result'], 'made')

	def test_regress(self):
		cases = [{'name': 'a', 'inputs': {'n': 2}, 'answers': {'nice': {'pass': True}, 'sure': {'person': True, 'pass': True}}, 'expect': {'end': 'done'}},
			{'name': 'b', 'inputs': {'n': 8}, 'expect': {'end': 'done'}}]
		results, diffs = kit().regress(cases)
		self.assertEqual(results[0]['got']['end'], 'done')
		self.assertEqual(diffs, ["b: end is 'big', expected 'done'"])

	def test_step_wrapper(self):
		@rigkit.step
		def measure(x):
			if x < 0:
				raise rigkit.Refused('not below zero')
			return 10 // x
		with contextlib.redirect_stdout(io.StringIO()):
			self.assertEqual(measure(5), {'ok': True, 'step': 'measure', 'result': 2})
			self.assertEqual(measure(-1)['refused'], 'not below zero')
			self.assertIn('ZeroDivisionError', measure(0)['error'])


class Binding(unittest.TestCase):
	def test_levels_of_bound_code(self):
		path = os.path.join(RELEASE, 'release.rig')
		with open(path, encoding='utf-8') as f:
			root = rig.parse(f.read())
		u = rig.units(root)[0]
		self.assertEqual(rig.coverage(u, rig.Ctx(root, path))['tested'], 5)
		cv = rig.coverage(u)  # without the folder (as the viewer): the code cannot be read
		self.assertEqual((cv['tested'], cv['code'], cv['judge'], cv['human']), (0, 5, 1, 1))
		self.assertEqual(rig.check(root, path)[0], [])

	def test_a_missing_function_is_an_error(self):
		tmp = tempfile.mkdtemp()
		try:
			with open(os.path.join(tmp, 'g.py'), 'w') as f:
				f.write('def here(state, R):\n\treturn True\n')
			path = os.path.join(tmp, 'x.rig')
			text = 'unit x agent\n  code g g.py\n  gate a hard\n    by g.here\n    pass -> e\n  gate b hard\n    by g.gone\n    pass -> e\n    fail -> e\n  end e\n'
			err, warn = rig.check(rig.parse(text), path)
			self.assertEqual([t for _, t in err], ['"g.py" has no function "gone"'])
			self.assertTrue(any('no test names "here"' in t for _, t in warn))
		finally:
			shutil.rmtree(tmp)

	def test_human_gate(self):
		u = rig.units(rig.parse(FLOW))[0]
		text = rig.skill(u)
		self.assertIn('A person decides: ask the person. Stop and ask the person.', text)
		self.assertIn('Guessed: nice', text)
		self.assertNotIn('Guessed: nice, sure', text)
		driven = rig.skill(u, driver='python3 tool.py')
		self.assertIn('python3 tool.py approve <run> yes', driven)
		self.assertIn('### `small`', driven)


class Projects(unittest.TestCase):
	def quiet(self, fn, *args):
		buf = io.StringIO()
		with contextlib.redirect_stdout(buf):
			code = fn(*args)
		return code, buf.getvalue()

	def test_new_project_passes_its_doctor_at_every_level(self):
		tmp = tempfile.mkdtemp()
		try:
			for level in (1, 2, 3, 4):
				folder = os.path.join(tmp, 'level{}'.format(level))
				self.quiet(rig_project.new, folder, 'demo-tool', level)
				code, out = self.quiet(rig_project.doctor, folder)
				self.assertEqual(code, 0, out)
				self.assertEqual(self.quiet(rig_project.build, folder, True)[0], 0)
		finally:
			shutil.rmtree(tmp)

	def test_doctor_names_what_is_missing(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 3)
			path = os.path.join(folder, 'demo-tool.rig')
			with open(path, encoding='utf-8') as f:
				text = f.read()
			with open(path, 'w', encoding='utf-8') as f:
				f.write(text.replace('{limits.min_length} characters', '3 characters').replace('by gates.long_enough', 'by gates.not_written'))
			code, out = self.quiet(rig_project.doctor, folder, False)
			self.assertEqual(code, 1)
			self.assertIn('has no function "not_written"', out)
		finally:
			shutil.rmtree(tmp)

	@unittest.skipUnless(shutil.which('node'), 'node is not installed')
	def test_plugin_front_calls_the_driver(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 4)
			self.quiet(rig_project.plugin, folder, 'tester')
			self.assertEqual(self.quiet(rig_project.build, folder, True)[0], 0)
			with open(os.path.join(folder, 'plugin', 'src', 'gen', 'front.json'), encoding='utf-8') as f:
				front = json.load(f)
			self.assertEqual([t['name'] for t in front['tools']], ['start_run', 'answer_gate', 'run_status', 'start_batch', 'queues'])  # no tool for the human gate
			self.assertIn('you cannot answer', front['prompt'])

			def call(*args):
				r = subprocess.run(['node', '--no-warnings', 'try.ts'] + list(args), cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True)
				return json.loads(r.stdout.strip().splitlines()[-1])
			r = call('start_run', '{"item": "a longer item"}')
			self.assertEqual(r['waiting']['node'], 'sensible')
			r = call('answer_gate', json.dumps({'run': r['run'], 'pass': True}))
			self.assertEqual(r['waiting']['kind'], 'human')
			self.assertIn('refused', call('answer_gate', json.dumps({'run': r['run'], 'pass': True})))
		finally:
			shutil.rmtree(tmp)

	def test_examples_are_current_and_complete(self):
		for folder in (RELEASE, BAND):
			self.assertEqual(self.quiet(rig_project.build, folder, True)[0], 0, 'run: rig.py build ' + folder)
			code, out = self.quiet(rig_project.doctor, folder)
			self.assertEqual(code, 0, out)

	def test_serve_gives_the_levels_and_the_runs(self):
		import socket
		import time
		import urllib.request
		tmp = tempfile.mkdtemp()
		with socket.socket() as sock:
			sock.bind(('127.0.0.1', 0))
			port = sock.getsockname()[1]
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 3)
			subprocess.run([sys.executable, 'tool.py', 'run', '{"item": "a longer item"}'], cwd=folder, capture_output=True)
			srv = subprocess.Popen([sys.executable, os.path.join(ROOT, 'skills', 'rig', 'rig.py'), 'serve', 'demo-tool.rig', '--port', str(port)], cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			try:
				def get(path):
					for _ in range(50):
						try:
							with urllib.request.urlopen('http://127.0.0.1:{}{}'.format(port, path), timeout=2) as r:
								return json.loads(r.read().decode('utf-8'))
						except OSError:
							time.sleep(0.1)
					self.fail('the server did not answer')
				self.assertEqual(get('/levels')['demo-tool']['gates.long_enough'], 'tested')
				runs = get('/runs')
				self.assertEqual(runs[0]['state'], 'waits at sensible')
				self.assertEqual([t['node'] for t in get('/runs/' + runs[0]['id'])['trace']], ['look', 'long-enough'])
			finally:
				srv.terminate()
				srv.wait(timeout=5)
		finally:
			shutil.rmtree(tmp)

	def test_release_example_from_the_command_line(self):
		r = subprocess.run([sys.executable, os.path.join(RELEASE, 'tool.py'), 'rules'], capture_output=True, text=True)
		self.assertIn('"notes.min_words": 50', r.stdout)


if __name__ == '__main__':
	unittest.main()
