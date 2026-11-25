"""Tests for the runtime kit (skills/rig/kit/rigkit.py) and the project commands of rig.py
(new, build, doctor, test). Run: python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig'))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig', 'kit'))
import rig  # noqa: E402
import rig_project  # noqa: E402
import rigkit  # noqa: E402

RELEASE = os.path.join(ROOT, 'examples', 'release-tool')
BAND = os.path.join(ROOT, 'examples', 'band-facts')
BOOKMARKS = os.path.join(ROOT, 'examples', 'bookmarks')

FLOW = '''unit demo agent
  in n int "a number"
  code code code.py
  rule limits.max 10 "Largest number"
    range 1 100
  step double "Double" by code.double
    do "double the number"
  gate small hard "Small"
    check "the number is at most {limits.max}"
    by code.small
    fail -> big "too big"
    fail -> huge "much too big"
  gate nice model "Nice"
    check "is {limits.max} a nice limit?"
    fail -> big
  gate sure human "Sure?"
    check "ask the person"
    fail -> big
  end done "Done"
  end big "Big"
  end huge "Huge"
'''

LOOPS = '''unit loops agent
  in n int "a number"
  code code code.py
  rule loop.rounds 1 "Retries"
    range 0 5
  step make by code.make
  for x in make.items
    tolerate 50%
    fail -> held "too many left"
    step draft by model
      do "give a number"
      out (record v int)
      timeout 1h
    gate even hard
      check "the number is even"
      by code.even
      retry loop.rounds
      fail -> continue "odd"
  if make.big
    gate big human "Big?"
      timeout 1h
      fail -> no "timeout"
  else
    step small by code.small
  until make.done
    retry 2
    fail -> held
    step tick by code.tick
  gate pick human "Which?"
    options a | b c
    by code.pick
  end done "Done"
  end held "Held"
  end no "No"
  finally
    step summary by code.summary
'''


def catalogue(text=FLOW):
	return rig.catalog(rig.units(rig.parse(text))[0])


def kit(runs=None, **code):
	k = rigkit.Kit(catalogue(), runs=runs)
	fns = {'double': lambda s, R: s['n'] * 2,
		'small': lambda s, R: s['double'] <= R('limits.max') or {'pass': False, 'when': 'much too big' if s['double'] > 50 else 'too big', 'problems': ['{} is over limits.max'.format(s['double'])]}}
	fns.update(code)
	return k.bind('code', fns)


def make(s, R):
	return {'items': list(range(s['n'])), 'big': s['n'] > 5, 'done': False}


def tick(s, R):
	s['make']['done'] = (s.get('tick') or 0) >= 1
	return (s.get('tick') or 0) + 1


def pick(s, R):
	return s['pick']['answer'] in ('a', 'b c') or {'pass': False, 'problems': ['say a, or b c']}


def loops(runs=None, text=LOOPS, **code):
	k = rigkit.Kit(catalogue(text), runs=runs)
	fns = {'make': make, 'even': lambda s, R: s['draft']['v'] % 2 == 0, 'small': lambda s, R: 'small',
		'tick': tick, 'pick': pick, 'summary': lambda s, R: 'summary'}
	fns.update(code)
	return k.bind('code', fns)


def ago(run_file, seconds):
	'''Move the start of the wait of a run back in time, as if the time had passed.'''
	run = rigkit.read_json(run_file)
	run['since'] = (__import__('datetime').datetime.now() - __import__('datetime').timedelta(seconds=seconds)).isoformat(timespec='seconds')
	rigkit.write_json(run_file, run)


class Rules(unittest.TestCase):
	def test_values_and_range(self):
		R = rigkit.Rules(catalogue())
		self.assertEqual(R('limits.max'), 10)
		R.set('limits.max', '20')
		self.assertEqual(R('limits.max'), 20)
		with self.assertRaises(ValueError):
			R.set('limits.max', 1000)
		with self.assertRaises(KeyError):
			R('limits.nothing')
		self.assertEqual(R.fill('at most {limits.max}, {not.a.rule} {word}'), 'at most 20, {not.a.rule} {word}')

	def test_a_catalogue_of_version_0_is_refused(self):
		with self.assertRaises(ValueError):
			rigkit.Kit({'rig': 0, 'flow': []})


class Runs(unittest.TestCase):
	def test_code_walks_until_the_model(self):
		r = kit().run({'n': 2})
		self.assertEqual(r['path'], ['double', 'small'])
		self.assertEqual(r['waiting']['kind'], 'model')
		self.assertEqual(r['waiting']['check'], 'is 10 a nice limit?')

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
		self.assertEqual(r['waiting']['say'], 'To answer, write one of these messages: approve {0} yes, approve {0} no.'.format(r['run']))
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'pass': True})         # the model cannot answer for the person
		r = k.approve(r['run'], ['yes'])
		self.assertEqual(r['outcome']['end'], 'done')
		self.assertEqual(r['guessed'], ['nice'])
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'pass': True})         # the run ended

	def test_a_gate_with_no_code_is_a_guess(self):
		k = rigkit.Kit(catalogue()).bind('code', {'double': lambda s, R: 2})
		r = k.run({'n': 1})
		self.assertEqual((r['waiting']['node'], r['waiting']['kind']), ('small', 'model'))
		self.assertIn('no_code', r['waiting'])
		self.assertEqual(k.answer(r['run'], {'pass': True})['guessed'], ['small'])

	def test_an_error_ends_the_run_and_finally_runs(self):
		def broken(s, R):
			raise ValueError('the host is not ready')
		r = loops(make=broken).run({'n': 2})
		self.assertEqual(r['outcome']['end'], 'error')
		self.assertIn('the host is not ready', r['error']['error'])
		self.assertEqual(r['path'], ['make', 'summary'])  # finally ran after the error

	def test_a_code_step_that_runs_too_long(self):
		text = 'unit t agent\n  code code code.py\n  step slow by code.slow\n    timeout 1s\n  end done\n'
		k = rigkit.Kit(catalogue(text)).bind('code', {'slow': lambda s, R: time.sleep(3)})
		r = k.run({})
		self.assertEqual(r['outcome']['end'], 'error')
		self.assertIn('Timeout', r['error']['error'])

	def test_the_result_is_the_value_of_the_step_before_the_end(self):
		text = 'unit t agent\n  code code code.py\n  step make by code.make\n  end done\n'
		k = rigkit.Kit(catalogue(text)).bind('code', {'make': lambda s, R: 'made'})
		self.assertEqual(k.run({})['result'], 'made')

	def test_sees(self):
		text = FLOW.replace('    check "is {limits.max} a nice limit?"', '    check "is {limits.max} a nice limit?"\n    sees n double nothing.here')
		k = rigkit.Kit(catalogue(text)).bind('code', {'double': lambda s, R: {'value': s['n'] * 2}, 'small': lambda s, R: True})
		r = k.run({'n': 2})
		self.assertEqual(r['waiting']['sees'], {'n': 2, 'double': {'value': 4}})   # a path that is not there is left out
		r = k.answer(r['run'], {'pass': True})
		r = k.approve(r['run'], ['yes'])
		self.assertNotIn('result', r)                                              # a gate came last: no result


class Blocks(unittest.TestCase):
	def test_for_with_retry_and_continue(self):
		k = loops()
		r = k.run({'n': 3})
		self.assertEqual((r['waiting']['node'], r['waiting']['item']), ('draft', {'for:x': 0}))
		self.assertEqual(r['waiting']['schema']['required'], ['v'])
		r = k.answer(r['run'], {'result': {'v': 1}})           # odd: retry goes back to draft
		self.assertEqual((r['waiting']['node'], r['waiting']['problems']), ('draft', ['even: odd']))
		r = k.answer(r['run'], {'result': {'v': 3}})           # odd again: no retry left, the item is left
		self.assertEqual(r['waiting']['item'], {'for:x': 1})
		self.assertEqual(r['left'], [{'block': 'for:x', 'item': 0, 'gate': 'even', 'why': 'odd'}])
		r = k.answer(r['run'], {'result': {'v': 2}})
		r = k.answer(r['run'], {'result': {'v': 4}})
		self.assertEqual(r['waiting']['node'], 'pick')          # 1 of 3 left: within tolerate 50%
		self.assertIn('small', r['path'])                       # n <= 5: the else body
		self.assertEqual(r['path'].count('tick'), 2)            # until: the body, then once more

	def test_tolerate(self):
		k = loops(even=lambda s, R: False)
		r = k.run({'n': 2})
		for _ in range(4):
			r = k.answer(r['run'], {'result': {'v': 1}})
		self.assertEqual(r['outcome']['end'], 'held')           # 2 of 2 left: more than 50%
		self.assertIn('2 of 2 items were left', r['problems'][-1])
		self.assertEqual(r['path'][-1], 'summary')

	def test_the_answer_must_have_the_form_of_out(self):
		k = loops()
		r = k.run({'n': 1})
		r = k.answer(r['run'], {'result': {'v': 'two'}})
		self.assertEqual(r['waiting']['node'], 'draft')
		self.assertIn('result.v: a whole number', r['waiting']['problems'][0])

	def test_options_ask_again_and_the_default(self):
		k = loops()
		r = k.run({'n': 1})
		r = k.answer(r['run'], {'result': {'v': 2}})
		self.assertEqual((r['waiting']['options'], r['waiting']['default']), (['a', 'b c'], 'a'))
		self.assertEqual(r['waiting']['say'], 'To answer, write one of these messages: approve {0} a, approve {0} b c. The first one is the default.'.format(r['run']))
		with self.assertRaises(rigkit.Refused):
			k.answer(r['run'], {'answer': 'a'})                  # only a person
		r = k.approve(r['run'], ['zz'])
		self.assertEqual(r['waiting']['problems'], ['pick: the answer "zz" is not understood: say a, or b c'])
		r = k.approve(r['run'], ['b', 'c'])
		self.assertEqual(r['outcome']['end'], 'done')
		r2 = k.answer(k.run({'n': 1})['run'], {'result': {'v': 2}})
		self.assertEqual(k.approve(r2['run'], [])['outcome']['end'], 'done')  # only accept: the default "a"

	def test_if(self):
		k = loops(make=lambda s, R: {'items': [], 'big': True, 'done': True})
		r = k.run({'n': 6})
		self.assertEqual(r['waiting']['node'], 'big')
		r = k.approve(r['run'], ['no'])
		self.assertEqual(r['outcome']['end'], 'no')

	def test_until_gives_up(self):
		k = loops(make=lambda s, R: {'items': [], 'big': False, 'done': False}, tick=lambda s, R: 1)
		r = k.run({'n': 0})
		self.assertEqual(r['outcome']['end'], 'held')
		self.assertEqual(r['path'].count('tick'), 3)          # the body, then retry 2

	def test_an_if_on_one_node(self):
		text = 'unit t agent\n  code code code.py\n  step a by code.a\n  step b by code.b\n    if a.go\n  end done\n'
		k = rigkit.Kit(catalogue(text)).bind('code', {'a': lambda s, R: {'go': False}, 'b': lambda s, R: 'b'})
		self.assertEqual(k.run({})['path'], ['a', 'done'])

	def test_timeouts(self):
		tmp = tempfile.mkdtemp()
		try:
			k = loops(runs=tmp, make=lambda s, R: {'items': [1], 'big': True, 'done': True})
			r = k.run({'n': 1})
			ago(os.path.join(tmp, r['run'], 'run.json'), 7200)    # the model step waited two hours
			with self.assertRaises(rigkit.Refused):
				k.answer(r['run'], {'result': {'v': 2}})            # too late
			r = k.status(r['run'])
			self.assertEqual(r['waiting']['node'], 'draft')       # no result: the gate after it failed, and its retry asks again
			self.assertIn('gave no result in time', r['waiting']['problems'][-1])
			ago(os.path.join(tmp, r['run'], 'run.json'), 7200)    # no result again: no retry is left, the item is left
			r = k.status(r['run'])
			self.assertIn('gave no result in time', r['left'][0]['why'])
			self.assertEqual(r['outcome']['end'], 'held')         # 1 of 1 item left: more than tolerate 50%
			k = loops(runs=tmp, make=lambda s, R: {'items': [], 'big': True, 'done': True})
			r = k.run({'n': 1})
			self.assertEqual(r['waiting']['node'], 'big')
			ago(os.path.join(tmp, r['run'], 'run.json'), 7200)    # the person did not answer in time
			r = k.status(r['run'])
			self.assertEqual(r['outcome']['end'], 'no')
			self.assertIn('no answer in 1h', r['problems'][0])
		finally:
			shutil.rmtree(tmp)

	def test_progress_is_saved_after_each_item(self):
		tmp = tempfile.mkdtemp()
		try:
			seen = []

			def even(s, R):
				seen.append(s['x'])
				if s['x'] == 2 and len(seen) < 4:
					raise KeyboardInterrupt  # the process stops in the middle of item 2
				return True
			text = LOOPS.replace('    step draft by model\n      do "give a number"\n      out (record v int)\n      timeout 1h\n', '')
			text = text.replace('      retry loop.rounds\n', '')
			with self.assertRaises(KeyboardInterrupt):
				loops(runs=tmp, text=text, even=even).run({'n': 4})
			run_id = os.listdir(tmp)[0]
			r = loops(runs=tmp, text=text, even=even).resume(run_id)   # a new process
			self.assertEqual(seen, [0, 1, 2, 2, 3])                     # items 0 and 1 are not done again
			self.assertEqual(r['waiting']['node'], 'pick')
		finally:
			shutil.rmtree(tmp)


class Pinned(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.tmp)

	def test_a_run_keeps_its_flow_and_rules(self):
		r = kit(runs=self.tmp).run({'n': 2}, rules={'limits.max': 20})
		folder = os.path.join(self.tmp, r['run'])
		self.assertEqual(sorted(os.listdir(folder)), ['answers.json', 'flow.json', 'marks.json', 'rules.json', 'run.json'])
		self.assertEqual(rigkit.read_json(os.path.join(folder, 'rules.json'))['limits.max'], 20)
		changed = catalogue(FLOW.replace('  gate sure human "Sure?"\n    check "ask the person"\n    fail -> big\n', ''))
		k = rigkit.Kit(changed, runs=self.tmp).bind('code', {'double': lambda s, R: s['n'] * 2, 'small': lambda s, R: True})
		r = k.status(r['run'])
		self.assertIn('The flow changed', r['note'])
		r = k.answer(r['run'], {'pass': True})
		self.assertEqual(r['waiting']['node'], 'sure')        # the pinned flow still has the gate

	def test_answers_are_recorded(self):
		k = kit(runs=self.tmp)
		r = k.run({'n': 2})
		r = k.answer(r['run'], {'pass': True, 'why': 'round'})
		k.approve(r['run'], ['yes'])
		log = rigkit.read_json(os.path.join(self.tmp, r['run'], 'answers.json'))
		self.assertEqual([(a['node'], a['who'], a['answer']) for a in log], [('nice', 'model', {'pass': True, 'why': 'round'}), ('sure', 'person', {'pass': True})])

	def test_rerun_from_a_node(self):
		k = kit(runs=self.tmp)
		r = k.run({'n': 2})
		r = k.answer(r['run'], {'pass': True})
		r = k.approve(r['run'], ['no'])
		self.assertEqual(r['outcome']['end'], 'big')
		again = k.rerun(r['run'], 'small', {'limits.max': 3})
		self.assertEqual(again['from'], {'run': r['run'], 'from': 'small'})
		self.assertEqual((again['outcome']['end'], again['path']), ('big', ['small', 'big']))  # double is not done again; 4 > 3
		with self.assertRaises(rigkit.Refused):
			k.rerun(r['run'], 'nowhere')

	def test_replay(self):
		k = loops(runs=self.tmp)
		r = k.run({'n': 2})
		r = k.answer(r['run'], {'result': {'v': 1}})
		r = k.answer(r['run'], {'result': {'v': 2}})
		r = k.answer(r['run'], {'result': {'v': 4}})
		r = k.approve(r['run'], ['zz'])
		r = k.approve(r['run'], ['a'])
		self.assertEqual(r['outcome']['end'], 'done')
		got = loops(runs=self.tmp).replay(r['run'])
		self.assertEqual((got['end'], got['answers'], got['differences']), ('done', 5, []))
		self.assertEqual(os.listdir(self.tmp), [r['run']])     # a replay writes no run
		got = loops(runs=self.tmp, even=lambda s, R: False).replay(r['run'])  # the code changed
		self.assertTrue(got['differences'])


class CommandLine(unittest.TestCase):
	def test_command_line(self):
		tmp = tempfile.mkdtemp()
		try:
			lines = []
			k = kit(runs=tmp)
			self.assertEqual(k.cli(['run', '{"n": 2}', '--set', 'limits.max=30'], lines.append), 0)
			run = json.loads(lines[0])['run']
			self.assertEqual(k.cli(['answer', 'no-such-run', '{"pass": true}'], lines.append), 0)
			self.assertIn('refused', lines[1])
			self.assertEqual(k.cli(['answer', run, '{"pass": true}', '--node', 'small'], lines.append), 0)
			self.assertIn('waits at \\"nice\\"', lines[2])
			k.cli(['answer', run, '{"pass": true}'], lines.append)
			k.cli(['approve', run, 'no', 'not', 'now'], lines.append)
			self.assertEqual(json.loads(lines[-1])['outcome']['end'], 'big')
			k.cli(['rerun', run, '--from', 'nice', '--set', 'limits.max=40'], lines.append)
			self.assertEqual(json.loads(lines[-1])['waiting']['node'], 'nice')
			self.assertEqual(k.cli(['replay', run], lines.append), 0)
			self.assertEqual(json.loads(lines[-1])['differences'], [])
			self.assertEqual(k.cli(['run', 'not json'], lines.append), 0)
			self.assertIn('refused', lines[-1])
		finally:
			shutil.rmtree(tmp)

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
			k.approve(r['run'], ['yes'])
			self.assertEqual(k.queues(), {'left_for_model': [], 'waits_for_person': []})
		finally:
			shutil.rmtree(tmp)

	def test_a_batch_stops_when_the_host_is_down(self):
		def double(s, R):
			raise OSError('the host is down')
		got = kit(double=double).batch([{'n': 1}] * 5)
		self.assertEqual(got['started'], 2)
		self.assertIn('2 errors in a row', got['stopped'])

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
		self.assertEqual(rig.coverage(u, rig.Ctx(root, path))['tested'], 6)
		cv = rig.coverage(u)  # without the folder: the code cannot be read
		self.assertEqual((cv['tested'], cv['code'], cv['model'], cv['human']), (0, 6, 1, 1))
		self.assertEqual(rig.check(root, path)[0], [])

	def test_a_missing_function_is_an_error(self):
		tmp = tempfile.mkdtemp()
		try:
			with open(os.path.join(tmp, 'g.py'), 'w') as f:
				f.write('def here(state, R):\n\treturn True\n')
			path = os.path.join(tmp, 'x.rig')
			text = 'unit x agent\n  code g g.py\n  gate a hard by g.here\n    fail -> e\n  gate b hard by g.gone\n    fail -> e\n  end e\n'
			err, warn = rig.check(rig.parse(text), path)
			self.assertEqual([t for _, t in err], ['"g.py" has no function "gone"'])
			self.assertTrue(any('no test names "here"' in t for _, t in warn))
		finally:
			shutil.rmtree(tmp)

	def test_human_gate_in_the_skill(self):
		u = rig.units(rig.parse(FLOW))[0]
		text = rig.skill(u)
		self.assertIn('A person decides. Stop and ask the person.', text)
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
				with open(os.path.join(folder, 'rig.json'), encoding='utf-8') as f:
					self.assertEqual(json.load(f)['rig'], 1)
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

	def test_replay_a_recorded_run(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 4)

			def tool(*args):
				r = subprocess.run([sys.executable, 'tool.py'] + list(args), cwd=folder, capture_output=True, text=True)
				return json.loads(r.stdout.strip().splitlines()[-1])
			r = tool('run', '{"item": "a longer item"}')
			r = tool('answer', r['run'], '{"pass": true}')
			r = tool('approve', r['run'], 'yes')
			self.assertEqual(r['outcome']['end'], 'ready')
			code, out = self.quiet(rig_project.test, folder, r['run'])
			self.assertEqual(code, 0, out)
			self.assertEqual(json.loads(out)['differences'], [])
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
			self.assertIn('the operator decides, not you', front['prompt'])

			def call(*args):
				r = subprocess.run(['node', '--no-warnings', 'try.ts'] + list(args), cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True)
				return json.loads(r.stdout.strip().splitlines()[-1])
			r = call('start_run', '{"item": "a longer item"}')
			self.assertEqual(r['waiting']['node'], 'sensible')
			r = call('answer_gate', json.dumps({'run': r['run'], 'pass': True}))
			self.assertEqual(r['waiting']['kind'], 'human')
			self.assertIn('refused', call('answer_gate', json.dumps({'run': r['run'], 'pass': True})))
			self.assertEqual(r['waiting']['command'], 'cd {} && python3 tool.py approve {} yes'.format(os.path.realpath(folder), r['run']))
		finally:
			shutil.rmtree(tmp)

	def test_a_step_with_out_gets_its_own_tool(self):
		with open(os.path.join(BOOKMARKS, 'plugin', 'src', 'gen', 'front.json'), encoding='utf-8') as f:
			front = json.load(f)
		self.assertEqual([t['name'] for t in front['tools']], ['start_run', 'work_run', 'run_status', 'start_batch', 'queues'])  # no gate for the model
		self.assertEqual(front['tools'][1]['kind'], 'work')  # the step with "out" is a job for the worker, not for the chat
		self.assertEqual(front['work'], {'max_calls': 50, 'max_tokens': 4000, 'think': False})  # rig.json of bookmarks sets think; the rest are the defaults
		with open(os.path.join(RELEASE, 'plugin', 'src', 'gen', 'front.json'), encoding='utf-8') as f:
			self.assertEqual(json.load(f)['work'], {'max_calls': 50, 'max_tokens': 4000, 'think': False})  # the defaults
		self.assertIn('do not do the job yourself. Call work_run', front['prompt'])
		node = [n for n in rigkit.read_json(os.path.join(BOOKMARKS, 'gen', 'bookmarks.json'))['flow'] if n['id'] == 'sort'][0]
		item = node['schema']['items']  # the worker binds the answer of the model to this schema
		self.assertEqual(item['required'], ['id', 'topic', 'pick'])  # a (maybe T) field is not required: "folder", "new"
		self.assertEqual(list(item['properties']), ['id', 'topic', 'pick', 'folder', 'new'])  # in the order of the source: the topic before the pick
		self.assertNotIn('answer_gate', front['prompt'])
		self.assertIn('do not call any tool, also no finish tool', front['prompt'])   # a first run: the model took finish_sort for a human gate
		self.assertIn('"say" word for word', front['prompt'])

	def test_examples_are_current_and_complete(self):
		for folder in (RELEASE, BAND, BOOKMARKS):
			self.assertEqual(self.quiet(rig_project.build, folder, True)[0], 0, 'run: rig.py build ' + folder)
			code, out = self.quiet(rig_project.doctor, folder)
			self.assertEqual(code, 0, out)

	def test_the_bookmarks_flow_has_at_most_22_nodes(self):
		c = rigkit.read_json(os.path.join(BOOKMARKS, 'gen', 'bookmarks.json'))
		self.assertLessEqual(len(c['flow']), 22)

	def test_serve_gives_the_bundle_and_the_runs(self):
		import socket
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
				self.assertEqual(get('/bundle')['units'][0]['levels']['long-enough'], 'tested')
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
