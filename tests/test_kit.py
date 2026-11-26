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
		with self.assertRaises(rigkit.Refused):
			kit().run({'n': 'two'})
		with self.assertRaises(rigkit.Refused):
			kit().run({'n': True})

	def test_call_validates_input_types(self):
		c = catalogue('unit measure tool\n  intent "measure"\n  in text str "text"\n  in limit (maybe int) "limit"\n  code tools.py\n')
		k = rigkit.Kit({'rig': 1, 'flow': []}).tool(c, lambda text, limit=None: (len(text), limit))
		self.assertEqual(k.call('measure', {'text': 'hi'}), (2, None))
		self.assertEqual(k.call('measure', {'text': 'hi', 'limit': None}), (2, None))
		self.assertEqual(k.call('measure', {'text': 'hi', 'limit': 5}), (2, 5))
		with self.assertRaises(rigkit.Refused):
			k.call('measure', {'text': 123})
		with self.assertRaises(rigkit.Refused):
			k.call('measure', {'text': 'hi', 'limit': 'banana'})

	def test_schema_problems_maybe_and_tuple(self):
		maybe_int = rig.type_schema(rig.tokenize('(maybe int)', 1)[0])
		self.assertEqual(rigkit.schema_problems(None, maybe_int), [])
		self.assertEqual(rigkit.schema_problems(5, maybe_int), [])
		self.assertTrue(rigkit.schema_problems('banana', maybe_int))
		self.assertTrue(rigkit.schema_problems(True, maybe_int))
		pair = rig.type_schema(rig.tokenize('(tuple str int)', 1)[0])
		self.assertEqual(rigkit.schema_problems(['a', 1], pair), [])
		self.assertTrue(rigkit.schema_problems(['a'], pair))
		self.assertTrue(rigkit.schema_problems(['a', 1, 2], pair))
		self.assertTrue(rigkit.schema_problems(['a', 'b'], pair))

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

	def test_gate_state_sets_pass_and_failed(self):
		text = '''unit t agent
  code code code.py
  step draft by model
    if tone.failed
    do "rewrite"
    sees tone
    out text
  gate soft-check soft by code.soft_check
  gate tone model "Tone"
    check "good tone?"
    retry 1
    fail -> stop
  gate pick human "Pick?"
    options a | b
    by code.pick
  end done
  end stop
'''
		k = rigkit.Kit(catalogue(text)).bind('code', {
			'soft_check': lambda s, R: False,
			'pick': lambda s, R: {'pass': True, 'chosen': s['pick']['answer']},
		})
		r = k.run({})
		# draft was skipped because tone has not run yet (tone.failed is None)
		self.assertEqual(r['path'], ['soft-check'])
		self.assertEqual(r['waiting']['node'], 'tone')
		self.assertEqual(k.load(r['run'])['state']['soft-check'], {'pass': False, 'failed': True})
		# tone fails with why -> retry jumps to draft, where tone.failed is True
		r = k.answer(r['run'], {'pass': False, 'why': 'too stiff'})
		self.assertEqual(r['waiting']['node'], 'draft')
		self.assertEqual(r['waiting']['sees']['tone'], {'pass': False, 'failed': True, 'why': 'too stiff'})
		r = k.answer(r['run'], {'result': 'plain words'})
		self.assertEqual(r['waiting']['node'], 'tone')
		# tone passes without why -> stale why is gone, failed is False
		r = k.answer(r['run'], {'pass': True})
		self.assertEqual(r['waiting']['node'], 'pick')
		self.assertEqual(k.load(r['run'])['state']['tone'], {'pass': True, 'failed': False})
		# options human gate merges pass/failed with answer and facts
		r = k.approve(r['run'], ['b'])
		self.assertEqual(r['outcome']['end'], 'done')
		self.assertEqual(k.load(r['run'])['state']['pick'], {'answer': 'b', 'chosen': 'b', 'pass': True, 'failed': False})


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
			run_id = [n for n in os.listdir(tmp) if not n.startswith('.')][0]
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
		self.assertEqual(sorted(os.listdir(folder)), ['answers.json', 'flow.json', 'marks', 'rules.json', 'run.json'])
		self.assertEqual(sorted(os.listdir(os.path.join(folder, 'marks'))), ['double.json', 'nice.json', 'small.json'])
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

	def test_a_new_process_does_not_take_the_id_of_a_run(self):
		'''Two Kit instances sharing one runs folder get distinct short sequential ids (r1, r2).'''
		runs_in = lambda d: sorted(n for n in os.listdir(d) if not n.startswith('.'))
		old = kit(runs=self.tmp).run({'n': 2})
		self.assertEqual(old['run'], 'r1')
		k = kit(runs=self.tmp)  # a new process: its counter starts at 0
		again = k.rerun(old['run'], 'small')
		self.assertEqual(again['run'], 'r2')
		self.assertNotEqual(again['run'], old['run'])
		self.assertEqual(again['from'], {'run': old['run'], 'from': 'small'})
		self.assertEqual(kit(runs=self.tmp).status(old['run'])['at'], old['at'])  # the old run is as it was
		self.assertEqual(runs_in(self.tmp), ['r1', 'r2'])
		with self.assertRaises((ValueError, KeyError)):
			kit(runs=self.tmp).run({'n': 2}, rules={'limits.max': 'many'})  # refused before its id is reserved
		self.assertEqual(len(runs_in(self.tmp)), 2)

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
		self.assertEqual([n for n in os.listdir(self.tmp) if not n.startswith('.')], [r['run']])     # a replay writes no run
		got = loops(runs=self.tmp, even=lambda s, R: False).replay(r['run'])  # the code changed
		self.assertTrue(got['differences'])

	def test_short_run_ids_and_run_list_ordering(self):
		k = kit(runs=self.tmp)
		ids = [k.run({'n': 8})['run'] for _ in range(11)]
		self.assertEqual(ids, ['r{}'.format(i) for i in range(1, 12)])
		listed = rig.run_list(self.tmp)
		self.assertEqual(len(listed), 11)
		self.assertEqual([x['id'] for x in listed[:3]], ['r11', 'r10', 'r9'])  # newest first, not lexicographical

	@unittest.skipUnless(shutil.which('node'), 'node is not installed')
	def test_approval_matches_short_and_legacy_ids(self):
		code = (
			'import { approval } from "./src/bridge.ts";'
			'console.log(JSON.stringify(['
			'approval("approve r1 yes"),'
			'approval("approve r42 no wait"),'
			'approval("approve 20261125-101500-01 yes"),'
			'approval("approve yes")'
			']));'
		)
		r = subprocess.run(['node', '--no-warnings', '--input-type=module', '-e', code],
			cwd=os.path.join(RELEASE, 'plugin'), capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stderr)
		got = json.loads(r.stdout.strip())
		self.assertEqual(got, [['r1', ['yes']], ['r42', ['no', 'wait']], ['20261125-101500-01', ['yes']], ['', ['yes']]])

	def test_drop_removes_from_queues_and_refuses_ended(self):
		k = kit(runs=self.tmp)
		r = k.run({'n': 2})
		self.assertEqual([e['run'] for e in k.queues()['left_for_model']], [r['run']])
		dropped = k.drop(r['run'], 'cancelled by user')
		self.assertEqual(dropped['outcome'], {'end': 'dropped', 'label': 'cancelled by user'})
		self.assertEqual(k.queues(), {'left_for_model': [], 'waits_for_person': []})
		with self.assertRaises(rigkit.Refused):
			k.drop(r['run'])
		# CLI drop
		lines = []
		k.cli(['run', '{"n": 2}'], lines.append)
		r2 = json.loads(lines[-1])['run']
		k.cli(['drop', r2, 'not', 'needed'], lines.append)
		self.assertEqual(json.loads(lines[-1])['outcome'], {'end': 'dropped', 'label': 'not needed'})
		self.assertEqual(k.queues(), {'left_for_model': [], 'waits_for_person': []})

	def test_list_and_prune(self):
		k = kit(runs=self.tmp)
		f1 = k.run({'n': 8})['run']
		f2 = k.run({'n': 8})['run']
		w1 = k.run({'n': 2})['run']  # waiting: must never be pruned
		f3 = k.run({'n': 80})['run']
		f4 = k.run({'n': 80})['run']
		listed = k.list_runs()
		self.assertEqual([x['run'] for x in listed], [f4, f3, w1, f2, f1])
		self.assertEqual(listed[0]['state'], 'ended')
		self.assertEqual(listed[0]['end'], 'huge')
		self.assertEqual(listed[2]['state'], 'waiting')
		self.assertEqual(listed[2]['waiting']['node'], 'nice')
		self.assertEqual(len(k.list_runs(limit=2)), 2)
		pruned = k.prune(keep=2)
		self.assertEqual(sorted(pruned['removed']), sorted([f1, f2]))
		self.assertEqual(pruned['kept'], 3)  # 2 finished + 1 waiting
		remaining = sorted(n for n in os.listdir(self.tmp) if not n.startswith('.'))
		self.assertEqual(remaining, sorted([w1, f3, f4]))
		# CLI list and prune
		lines = []
		k.cli(['list', '--limit', '2'], lines.append)
		self.assertEqual([x['run'] for x in json.loads(lines[-1])['runs']], [f4, f3])
		k.cli(['prune', '--keep', '1'], lines.append)
		self.assertEqual(json.loads(lines[-1]), {'removed': [f3], 'kept': 2})
		self.assertEqual(sorted(n for n in os.listdir(self.tmp) if not n.startswith('.')), sorted([w1, f4]))

	def test_waiting_index_and_reconciliation(self):
		k = kit(runs=self.tmp)
		f1 = k.run({'n': 8})['run']
		w1 = k.run({'n': 2})['run']
		f2 = k.run({'n': 80})['run']
		idx_path = os.path.join(self.tmp, '.waiting.json')
		self.assertTrue(os.path.exists(idx_path))
		idx = rigkit.read_json(idx_path)
		self.assertEqual(list(idx.keys()), [w1])
		self.assertNotIn(f1, idx)
		self.assertNotIn(f2, idx)
		# Delete .waiting.json: queues() reconciles from disk and recreates it
		os.remove(idx_path)
		q = kit(runs=self.tmp).queues()
		self.assertEqual([e['run'] for e in q['left_for_model']], [w1])
		self.assertTrue(os.path.exists(idx_path))
		self.assertEqual(list(rigkit.read_json(idx_path).keys()), [w1])
		# Stale entry in .waiting.json is cleaned up
		rigkit.write_json(idx_path, {w1: idx[w1], 'r999': {'node': 'nice', 'kind': 'model', 'started': '2026-01-01T00:00:00'}})
		q2 = kit(runs=self.tmp).queues()
		self.assertEqual([e['run'] for e in q2['left_for_model']], [w1])
		self.assertEqual(list(rigkit.read_json(idx_path).keys()), [w1])

	def test_per_node_marks_and_legacy_fallback(self):
		k = kit(runs=self.tmp)
		r = k.run({'n': 2})
		r = k.answer(r['run'], {'pass': True})
		r = k.approve(r['run'], ['yes'])
		marks_dir = os.path.join(self.tmp, r['run'], 'marks')
		self.assertTrue(os.path.isdir(marks_dir))
		self.assertIn('small.json', os.listdir(marks_dir))
		# Rerun from per-node mark and replay the rerun
		again = k.rerun(r['run'], 'small', {'limits.max': 3})
		self.assertEqual((again['outcome']['end'], again['path']), ('big', ['small', 'big']))
		rep = k.replay(again['run'])
		self.assertEqual((rep['end'], rep['differences']), ('big', []))
		# Legacy monolithic marks.json fallback
		saved_small = rigkit.read_json(os.path.join(marks_dir, 'small.json'))
		shutil.rmtree(marks_dir)
		rigkit.write_json(os.path.join(self.tmp, r['run'], 'marks.json'), {'small': saved_small})
		again2 = kit(runs=self.tmp).rerun(r['run'], 'small', {'limits.max': 3})
		self.assertEqual((again2['outcome']['end'], again2['path']), ('big', ['small', 'big']))

	def test_answer_with_meta(self):
		k = kit(runs=self.tmp)
		r = k.run({'n': 2})
		meta = {'model': 'test', 'tokens': 42, 'seconds': 1.2}
		lines = []
		self.assertEqual(k.cli(['answer', r['run'], '{"pass": true}', '--meta', json.dumps(meta)], lines.append), 0)
		k.approve(r['run'], ['yes'])
		log = rigkit.read_json(os.path.join(self.tmp, r['run'], 'answers.json'))
		self.assertEqual(log[0]['meta'], meta)
		self.assertNotIn('meta', log[1])

	def test_work_structured_think_retry_and_refusal(self):
		# 1. Missing api_url / model refuses cleanly (ignoring env vars)
		k = loops(runs=self.tmp)
		r = k.run({'n': 2})
		saved_env = {key: os.environ.pop(key, None) for key in ('RIG_API_URL', 'RIG_MODEL', 'RIG_API_KEY')}
		try:
			with self.assertRaises(rigkit.Refused):
				k.work(r['run'], model='m')
			with self.assertRaises(rigkit.Refused):
				k.work(r['run'], api_url='http://example.invalid/v1')
			lines = []
			self.assertEqual(k.cli(['work', r['run']], lines.append), 0)
			self.assertIn('refused', json.loads(lines[-1]))
		finally:
			for key, val in saved_env.items():
				if val is not None:
					os.environ[key] = val

		# 2. Structured think=False happy path across a for loop (2 items)
		seen_calls = []
		def fake_structured(url, headers, payload, timeout_s):
			seen_calls.append((url, headers, payload, timeout_s))
			v = 2 * (len(seen_calls))
			return {'choices': [{'message': {'content': json.dumps({'result': {'v': v}})}, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 12}}
		progress = []
		out = k.work(r['run'], api_url='http://example.invalid/v1/', model='test-m', api_key='sk-123', think=False, on_progress=progress.append, request_fn=fake_structured)
		self.assertEqual(out['waiting']['node'], 'pick')
		self.assertEqual(out['work']['jobs'], 2)
		self.assertEqual(len(progress), 2)
		self.assertEqual(seen_calls[0][0], 'http://example.invalid/v1/chat/completions')
		self.assertEqual(seen_calls[0][1]['Authorization'], 'Bearer sk-123')
		self.assertEqual(seen_calls[0][2]['temperature'], 0.2)
		rf = seen_calls[0][2]['response_format']
		self.assertEqual(rf['type'], 'json_schema')
		self.assertTrue(rf['json_schema']['strict'])
		self.assertFalse(rf['json_schema']['schema']['additionalProperties'])
		log = rigkit.read_json(os.path.join(self.tmp, r['run'], 'answers.json'))
		self.assertEqual(log[0]['meta']['model'], 'test-m')
		self.assertEqual(log[0]['meta']['tokens'], 12)

		# 3. think=True extracts JSON from reasoning / fenced block and omits response_format
		r2 = k.run({'n': 1})
		think_calls = []
		def fake_think(url, headers, payload, timeout_s):
			think_calls.append(payload)
			return {'choices': [{'message': {'content': '<think>pick {not json} an even int</think>\n```json\n{"result": {"v": 4}}\n```'}, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 30}}
		out2 = k.work(r2['run'], api_url='http://example.invalid/v1', model='think-m', think=True, request_fn=fake_think)
		self.assertEqual(out2['waiting']['node'], 'pick')
		self.assertNotIn('response_format', think_calls[0])
		self.assertEqual(think_calls[0]['temperature'], 0.6)

		# 4. Token-cap and invalid-JSON retry feedback propagate into waiting.problems and answers.json meta
		r3 = k.run({'n': 1})
		retry_prompts = []
		responses = [
			{'choices': [{'message': {'content': '{"result": {"v":'}, 'finish_reason': 'length'}], 'usage': {'completion_tokens': 100}},
			{'choices': [{'message': {'content': 'not json at all'}, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 10}},
			{'choices': [{'message': {'content': '{"result": {"v": 6}}'}, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 8}},
		]
		def fake_retry(url, headers, payload, timeout_s):
			retry_prompts.append(payload['messages'][1]['content'])
			return responses.pop(0)
		out3 = k.work(r3['run'], api_url='http://example.invalid/v1', model='retry-m', max_tokens=100, request_fn=fake_retry)
		self.assertEqual(out3['waiting']['node'], 'pick')
		self.assertEqual(out3['work']['jobs'], 3)
		self.assertEqual([e['ok'] for e in out3['work']['each']], [False, False, True])
		self.assertIn('hit max_tokens (100)', retry_prompts[1])
		self.assertIn('response was not valid JSON', retry_prompts[2])
		log3 = rigkit.read_json(os.path.join(self.tmp, r3['run'], 'answers.json'))
		self.assertIn('hit max_tokens (100)', log3[0]['meta']['error'])
		self.assertEqual(log3[1]['meta']['error'], 'response was not valid JSON')
		self.assertNotIn('error', log3[2]['meta'])


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

	def test_parallel_batch_workers(self):
		tmp = tempfile.mkdtemp()
		try:
			k = kit(runs=os.path.join(tmp, 'runs'))
			got = k.batch([{'n': 2}, {'n': 8}, {'n': 80}, {'wrong': 1}, {'n': 3}], workers=3)
			self.assertEqual(got['started'], 5)
			self.assertEqual(got['ends'], {'big': 1, 'huge': 1})
			self.assertEqual(len(got['left_for_model']), 2)
			self.assertEqual(len(got['refused']), 1)
			# Input order is preserved in left_for_model
			n_order = [k.load(rid)['inputs']['n'] for rid in got['left_for_model']]
			self.assertEqual(n_order, [2, 3])
			# Waiting index has both waiting runs
			self.assertEqual(len(k.queues()['left_for_model']), 2)
			# CLI --workers flag
			lines = []
			self.assertEqual(k.cli(['batch', '[{"n": 8}, {"n": 80}]', '--workers', '2'], lines.append), 0)
			self.assertEqual(json.loads(lines[-1])['ends'], {'big': 1, 'huge': 1})
			# errors_stop stops submitting further chunks
			def boom(s, R):
				raise OSError('down')
			stopped = kit(double=boom).batch([{'n': 1}] * 6, workers=2)
			self.assertEqual(stopped['started'], 2)
			self.assertIn('errors in a row', stopped['stopped'])
		finally:
			shutil.rmtree(tmp)

	def test_serve_stdio(self):
		tmp = tempfile.mkdtemp()
		try:
			k = kit(runs=tmp)
			reqs = '\n'.join([
				json.dumps({'id': 1, 'argv': ['run', '{"n": 2}']}),
				'',
				'not valid json',
				json.dumps({'id': 2, 'argv': ['status', 'r1']}),
				json.dumps({'id': 3, 'argv': ['answer', 'r1', '{"pass": true}']}),
				json.dumps({'id': 4, 'argv': ['drop', 'r1', 'done testing']}),
				json.dumps({'id': 5, 'argv': ['serve-stdio']}),
				json.dumps({'id': 6, 'argv': ['queues']}),
			]) + '\n'
			lines = []
			code = k.serve_stdio(stdin=io.StringIO(reqs), out=lines.append)
			self.assertEqual(code, 0)
			res = [json.loads(l) for l in lines]
			self.assertEqual(len(res), 7)
			self.assertEqual((res[0]['id'], res[0]['code'], res[0]['result']['run']), (1, 0, 'r1'))
			self.assertEqual((res[1]['id'], res[1]['code'], res[1]['result']), (None, 1, {'refused': 'Bad request JSON'}))
			self.assertEqual((res[2]['id'], res[2]['result']['waiting']['node']), (2, 'nice'))
			self.assertEqual((res[3]['id'], res[3]['result']['waiting']['node']), (3, 'sure'))
			self.assertEqual((res[4]['id'], res[4]['result']['outcome']), (4, {'end': 'dropped', 'label': 'done testing'}))
			self.assertIn('refused', res[5]['result'])
			self.assertEqual((res[6]['id'], res[6]['result']), (6, {'left_for_model': [], 'waits_for_person': []}))
			# Subprocess test over real stdin/stdout pipes
			p = subprocess.run([sys.executable, os.path.join(RELEASE, 'tool.py'), 'serve-stdio'],
				input=json.dumps({'id': 'a', 'argv': ['rules']}) + '\n' + json.dumps({'id': 'b', 'argv': ['flow']}) + '\n',
				capture_output=True, text=True)
			self.assertEqual(p.returncode, 0, p.stderr)
			sub_res = [json.loads(l) for l in p.stdout.strip().splitlines()]
			self.assertEqual([x['id'] for x in sub_res], ['a', 'b'])
			self.assertIn('rules', sub_res[0]['result'])
			self.assertIn('flow', sub_res[1]['result'])
		finally:
			shutil.rmtree(tmp)

	def test_mcp_in_process_flow_and_tools(self):
		tmp = tempfile.mkdtemp()
		saved_env = {key: os.environ.pop(key, None) for key in ('RIG_API_URL', 'RIG_MODEL', 'RIG_API_KEY')}
		try:
			tool_cat = catalogue('unit word-count tool\n  intent "count words"\n  in text str "the text"\n  in limit (maybe int) "max"\n  out int "word count"\n  code tools.py\n')
			k = kit(runs=tmp).tool(tool_cat, lambda text, limit=None: len(text.split()) if limit is None else min(len(text.split()), limit))
			reqs = '\n'.join([
				json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}}),
				json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
				json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}),
				json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'}),
				json.dumps({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'start_run', 'arguments': {'n': 2}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'run_status', 'arguments': {'run': 'r1'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call', 'params': {'name': 'answer_gate', 'arguments': {'run': 'r1', 'pass': True, 'why': 'looks good'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'answer_gate', 'arguments': {'run': 'r1', 'pass': True}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call', 'params': {'name': 'queues', 'arguments': {}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call', 'params': {'name': 'drop_run', 'arguments': {'run': 'r1', 'reason': 'done testing'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 10, 'method': 'tools/call', 'params': {'name': 'queues', 'arguments': {}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 11, 'method': 'tools/call', 'params': {'name': 'word_count', 'arguments': {'text': 'one two three'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 12, 'method': 'tools/call', 'params': {'name': 'start_batch', 'arguments': {'items': [{'n': 8}, {'n': 80}], 'workers': 2}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 13, 'method': 'no/such/method'}),
				'not valid json',
			]) + '\n'
			out = io.StringIO()
			self.assertEqual(k.mcp(stdin=io.StringIO(reqs), stdout=out), 0)
			msgs = [json.loads(line) for line in out.getvalue().strip().splitlines()]
			# notifications/initialized produced no response: 14 replies for 15 lines
			self.assertEqual(len(msgs), 14)
			self.assertEqual(msgs[0]['id'], 1)
			self.assertEqual(msgs[0]['result'], {
				'protocolVersion': '2025-03-26',
				'capabilities': {'tools': {}},
				'serverInfo': {'name': 'demo', 'version': '1'},
			})
			self.assertEqual(msgs[1], {'jsonrpc': '2.0', 'id': 2, 'result': {}})
			listed = msgs[2]['result']['tools']
			names = [t['name'] for t in listed]
			self.assertEqual(names, ['start_run', 'answer_gate', 'run_status', 'start_batch', 'queues', 'drop_run', 'word_count'])
			self.assertFalse(any('approve' in n or 'human' in n for n in names))
			wc = next(t for t in listed if t['name'] == 'word_count')
			self.assertEqual(wc['inputSchema']['required'], ['text'])
			self.assertIn('limit', wc['inputSchema']['properties'])

			def payload(msg):
				self.assertFalse(msg['result']['isError'])
				return json.loads(msg['result']['content'][0]['text'])

			r_start = payload(msgs[3])
			self.assertEqual(r_start['run'], 'r1')
			self.assertNotIn('answer', r_start['waiting'])
			self.assertEqual(r_start['waiting']['next_action'], {'call': 'answer_gate', 'args': {'run': 'r1', 'pass': '<true|false>', 'why': '<one sentence>'}})
			r_status = payload(msgs[4])
			self.assertNotIn('answer', r_status['waiting'])
			self.assertEqual(r_status['waiting']['next_action']['call'], 'answer_gate')
			r_human = payload(msgs[5])
			self.assertEqual(r_human['waiting']['kind'], 'human')
			self.assertNotIn('answer', r_human['waiting'])
			self.assertEqual(r_human['waiting']['next_action'], {'call': 'NONE', 'show_verbatim': r_human['waiting']['say']})
			r_refused = payload(msgs[6])
			self.assertIn('refused', r_refused)
			self.assertIn('human gate', r_refused['refused'])
			q1 = payload(msgs[7])
			self.assertEqual([x['run'] for x in q1['waits_for_person']], ['r1'])
			r_drop = payload(msgs[8])
			self.assertEqual(r_drop['outcome'], {'end': 'dropped', 'label': 'done testing'})
			self.assertEqual(payload(msgs[9]), {'left_for_model': [], 'waits_for_person': []})
			self.assertEqual(payload(msgs[10]), {'ok': True, 'tool': 'word-count', 'result': 3})
			self.assertEqual(payload(msgs[11])['ends'], {'big': 1, 'huge': 1})
			self.assertEqual(msgs[12], {'jsonrpc': '2.0', 'id': 13, 'error': {'code': -32601, 'message': 'Method not found'}})
			self.assertEqual(msgs[13], {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}})
		finally:
			for key, val in saved_env.items():
				if val is not None:
					os.environ[key] = val
			shutil.rmtree(tmp)

	def test_mcp_model_steps_answer_step_vs_work_run(self):
		tmp = tempfile.mkdtemp()
		saved_env = {key: os.environ.pop(key, None) for key in ('RIG_API_URL', 'RIG_MODEL', 'RIG_API_KEY')}
		try:
			# Without worker config: LOOPS has no model gate and has a model step -> exposes answer_step, not answer_gate or work_run
			k = loops(runs=tmp)
			reqs = '\n'.join([
				json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}),
				json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'start_run', 'arguments': {'n': 1}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'answer_step', 'arguments': {'run': 'r1', 'result': {'v': 2}, 'node': 'draft'}}}),
			]) + '\n'
			out = io.StringIO()
			self.assertEqual(k.mcp(stdin=io.StringIO(reqs), stdout=out), 0)
			msgs = [json.loads(line) for line in out.getvalue().strip().splitlines()]
			names = [t['name'] for t in msgs[0]['result']['tools']]
			self.assertEqual(names, ['start_run', 'answer_step', 'run_status', 'start_batch', 'queues', 'drop_run'])
			r_start = json.loads(msgs[1]['result']['content'][0]['text'])
			self.assertNotIn('answer', r_start['waiting'])
			self.assertEqual(r_start['waiting']['next_action'], {'call': 'answer_step', 'args': {'run': 'r1', 'result': '<value matching schema>'}})
			r_next = json.loads(msgs[2]['result']['content'][0]['text'])
			self.assertEqual(r_next['waiting']['kind'], 'human')
			self.assertEqual(r_next['waiting']['next_action']['call'], 'NONE')

			# With worker config (api_url + model): exposes work_run instead of answer_step, and waiting.next_action points to work_run
			reqs2 = '\n'.join([
				json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}),
				json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'start_run', 'arguments': {'n': 1}}}),
			]) + '\n'
			out2 = io.StringIO()
			self.assertEqual(k.mcp(api_url='http://example.invalid/v1', model='test-m', stdin=io.StringIO(reqs2), stdout=out2), 0)
			msgs2 = [json.loads(line) for line in out2.getvalue().strip().splitlines()]
			names2 = [t['name'] for t in msgs2[0]['result']['tools']]
			self.assertEqual(names2, ['start_run', 'work_run', 'run_status', 'start_batch', 'queues', 'drop_run'])
			r_start2 = json.loads(msgs2[1]['result']['content'][0]['text'])
			self.assertEqual(r_start2['waiting']['next_action'], {'call': 'work_run', 'args': {'run': 'r2'}})
		finally:
			for key, val in saved_env.items():
				if val is not None:
					os.environ[key] = val
			shutil.rmtree(tmp)

	def test_mcp_subprocess_pipes_and_mcp_config(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'demo')
			buf = io.StringIO()
			with contextlib.redirect_stdout(buf):
				rig_project.new(folder, 'demo-tool', 4)
			# Subprocess pipe test against real tool.py mcp
			reqs = '\n'.join([
				json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}),
				json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
				json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}),
				json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'}),
				json.dumps({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'start_run', 'arguments': {'item': 'a longer item'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'answer_gate', 'arguments': {'run': 'r1', 'pass': True, 'why': 'ok'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call', 'params': {'name': 'answer_gate', 'arguments': {'run': 'r1', 'pass': True}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'queues', 'arguments': {}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call', 'params': {'name': 'drop_run', 'arguments': {'run': 'r1'}}}),
				json.dumps({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call', 'params': {'name': 'queues', 'arguments': {}}}),
			]) + '\n'
			env = dict(os.environ)
			env.pop('RIG_API_URL', None)
			env.pop('RIG_MODEL', None)
			p = subprocess.run([sys.executable, os.path.join(folder, 'tool.py'), 'mcp'],
				cwd=folder, input=reqs, capture_output=True, text=True, env=env)
			self.assertEqual(p.returncode, 0, p.stderr)
			msgs = [json.loads(l) for l in p.stdout.strip().splitlines()]
			self.assertEqual([m['id'] for m in msgs], [1, 2, 3, 4, 5, 6, 7, 8, 9])
			self.assertEqual(msgs[0]['result']['protocolVersion'], '2024-11-05')
			self.assertEqual(msgs[0]['result']['serverInfo'], {'name': 'demo-tool', 'version': '1'})
			self.assertEqual([t['name'] for t in msgs[2]['result']['tools']], ['start_run', 'answer_gate', 'run_status', 'start_batch', 'queues', 'drop_run'])
			self.assertEqual(json.loads(msgs[3]['result']['content'][0]['text'])['waiting']['next_action']['call'], 'answer_gate')
			self.assertEqual(json.loads(msgs[4]['result']['content'][0]['text'])['waiting']['next_action']['call'], 'NONE')
			self.assertIn('refused', json.loads(msgs[5]['result']['content'][0]['text']))
			self.assertEqual(len(json.loads(msgs[6]['result']['content'][0]['text'])['waits_for_person']), 1)
			self.assertEqual(json.loads(msgs[7]['result']['content'][0]['text'])['outcome']['end'], 'dropped')
			self.assertEqual(json.loads(msgs[8]['result']['content'][0]['text']), {'left_for_model': [], 'waits_for_person': []})

			# Verify release-tool over subprocess pipes: answer_step by default, work_run with --api-url & --model
			list_req = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}) + '\n'
			p_rel = subprocess.run([sys.executable, os.path.join(RELEASE, 'tool.py'), 'mcp'], input=list_req, capture_output=True, text=True, env=env)
			self.assertEqual(p_rel.returncode, 0, p_rel.stderr)
			rel_names = [t['name'] for t in json.loads(p_rel.stdout.strip())['result']['tools']]
			self.assertIn('answer_step', rel_names)
			self.assertIn('answer_gate', rel_names)
			self.assertNotIn('work_run', rel_names)
			p_rel_w = subprocess.run([sys.executable, os.path.join(RELEASE, 'tool.py'), 'mcp', '--api-url', 'http://127.0.0.1:1234/v1', '--model', 'qwen'], input=list_req, capture_output=True, text=True, env=env)
			self.assertEqual(p_rel_w.returncode, 0, p_rel_w.stderr)
			rel_w_names = [t['name'] for t in json.loads(p_rel_w.stdout.strip())['result']['tools']]
			self.assertIn('work_run', rel_w_names)
			self.assertNotIn('answer_step', rel_w_names)

			# rig.py mcp-config DIR (plain and with --api-url / --model)
			rig_py = os.path.join(ROOT, 'skills', 'rig', 'rig.py')
			c1 = subprocess.run([sys.executable, rig_py, 'mcp-config', RELEASE], capture_output=True, text=True)
			self.assertEqual(c1.returncode, 0, c1.stderr)
			cfg1 = json.loads(c1.stdout)
			srv1 = cfg1['mcpServers']['release']
			self.assertEqual(srv1['command'], 'python3')
			self.assertEqual(srv1['args'], [os.path.abspath(os.path.join(RELEASE, 'tool.py')), 'mcp'])
			self.assertEqual(srv1['cwd'], os.path.abspath(RELEASE))
			c2 = subprocess.run([sys.executable, rig_py, 'mcp-config', RELEASE, '--api-url', 'http://127.0.0.1:1234/v1', '--model', 'qwen'], capture_output=True, text=True)
			self.assertEqual(c2.returncode, 0, c2.stderr)
			srv2 = json.loads(c2.stdout)['mcpServers']['release']
			self.assertEqual(srv2['args'], [os.path.abspath(os.path.join(RELEASE, 'tool.py')), 'mcp', '--api-url', 'http://127.0.0.1:1234/v1', '--model', 'qwen'])
		finally:
			shutil.rmtree(tmp)

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
		self.assertIn('## Flow (summary)', driven)
		self.assertIn('| `nice` | model gate |', driven)
		self.assertIn('| `sure` | human gate |', driven)
		self.assertNotIn('### `small`', driven)
		self.assertNotIn('### `double`', driven)


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

	def test_build_writes_the_plugin_readme(self):
		'''The README of the plugin is compiled too: a hand copy of it went out of step.'''
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 4)
			self.quiet(rig_project.plugin, folder, 'tester')
			path = os.path.join(folder, 'plugin', 'README.md')
			with open(path, encoding='utf-8') as f:
				text = f.read()
			self.assertIn('# demo-tool: the LM Studio front', text)
			with open(os.path.join(folder, 'tests', 'regression-set.json'), encoding='utf-8') as f:
				first = json.load(f)[0]['inputs']
			self.assertIn("start_run '{}'".format(json.dumps(first)), text)  # the inputs of a real case
			self.assertNotIn('__', text)
			with open(path, 'a', encoding='utf-8') as f:
				f.write('a change by hand\n')
			self.assertEqual(self.quiet(rig_project.build, folder, True)[0], 1)  # --check sees it
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
				r = subprocess.run(['node', '--no-warnings', 'try.ts'] + list(args), cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True, timeout=15)
				self.assertEqual(r.returncode, 0, r.stderr)
				return json.loads(r.stdout.strip().splitlines()[-1])
			r = call('start_run', '{"item": "a longer item"}')
			self.assertEqual(r['waiting']['node'], 'sensible')
			self.assertNotIn('answer', r['waiting'])
			self.assertEqual(r['waiting']['next_action'], {'call': 'answer_gate', 'args': {'run': r['run'], 'pass': '<true|false>', 'why': '<one sentence>'}})
			r = call('answer_gate', json.dumps({'run': r['run'], 'pass': True}))
			self.assertEqual(r['waiting']['kind'], 'human')
			self.assertNotIn('answer', r['waiting'])
			self.assertEqual(r['waiting']['next_action'], {'call': 'NONE', 'show_verbatim': r['waiting']['say']})
			self.assertIn('refused', call('answer_gate', json.dumps({'run': r['run'], 'pass': True})))
			self.assertEqual(r['waiting']['command'], 'cd {} && python3 tool.py approve {} yes'.format(os.path.realpath(folder), r['run']))
		finally:
			shutil.rmtree(tmp)

	@unittest.skipUnless(shutil.which('node'), 'node is not installed')
	def test_plugin_bridge_warm_stdio_active_run_and_step_next_action(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 4)
			self.quiet(rig_project.plugin, folder, 'tester')
			# Test in one Node process: warm stdio across multiple calls, activeRun disambiguation
			# when two runs wait for a person, and decorate() for kind === "step".
			script = r'''
import { callTool, closeDriver, decorate, front, operatorAnswer } from "./src/bridge.ts";
try {
  const byName = Object.fromEntries(front.tools.map((t) => [t.name, t]));
  const r1 = JSON.parse(await callTool(byName.start_run, { item: "first long item" }));
  const w1 = JSON.parse(await callTool(byName.answer_gate, { run: r1.run, pass: true }));
  const r2 = JSON.parse(await callTool(byName.start_run, { item: "second long item" }));
  const w2 = JSON.parse(await callTool(byName.answer_gate, { run: r2.run, pass: true }));
  const qBefore = JSON.parse(await callTool(byName.queues, {}));
  // Two runs wait for a person; activeRun is r2, so "approve yes" without a run id picks r2.
  const approved = JSON.parse((await operatorAnswer("approve yes")) ?? "null");
  const qAfter = JSON.parse(await callTool(byName.queues, {}));
  const stepDecorated = JSON.parse(decorate(JSON.stringify({ run: "r9", waiting: { node: "sort", kind: "step", answer: "{\"result\": ...}" } }), process.cwd()));
  console.log(JSON.stringify({ r1: r1.run, r2: r2.run, w1: w1.waiting.kind, w2: w2.waiting.kind, qBefore: qBefore.waits_for_person.map((x) => x.run), approvedRun: approved.run, approvedEnd: approved.outcome?.end, qAfter: qAfter.waits_for_person.map((x) => x.run), stepDecorated }));
} finally {
  closeDriver();
}
'''
			res = subprocess.run(['node', '--no-warnings', '--input-type=module', '-e', script],
				cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True, timeout=15)
			self.assertEqual(res.returncode, 0, res.stderr)
			got = json.loads(res.stdout.strip().splitlines()[-1])
			self.assertEqual((got['w1'], got['w2']), ('human', 'human'))
			self.assertEqual(got['qBefore'], [got['r1'], got['r2']])
			self.assertEqual((got['approvedRun'], got['approvedEnd']), (got['r2'], 'ready'))
			self.assertEqual(got['qAfter'], [got['r1']])
			self.assertNotIn('answer', got['stepDecorated']['waiting'])
			self.assertEqual(got['stepDecorated']['waiting']['next_action'], {'call': 'work_run', 'args': {'run': 'r9'}})

			# Now add a third waiting run so 2 runs wait, then test a fresh process with no activeRun:
			# "approve yes" without a run id must be refused and list both runs.
			r3 = subprocess.run(['node', '--no-warnings', 'try.ts', 'start_run', '{"item": "third long item"}'],
				cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True, timeout=15)
			r3_id = json.loads(r3.stdout.strip().splitlines()[-1])['run']
			subprocess.run(['node', '--no-warnings', 'try.ts', 'answer_gate', json.dumps({'run': r3_id, 'pass': True})],
				cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True, timeout=15)
			ref = subprocess.run(['node', '--no-warnings', 'try.ts', 'say', 'approve yes'],
				cwd=os.path.join(folder, 'plugin'), capture_output=True, text=True, timeout=15)
			self.assertEqual(ref.returncode, 0, ref.stderr)
			ref_json = json.loads(ref.stdout.strip().splitlines()[-1])
			self.assertIn('refused', ref_json)
			self.assertIn('2 runs wait for a person', ref_json['refused'])
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

	def test_the_bookmarks_flow_has_at_most_23_nodes(self):
		# 19 steps and gates (pure gate sort-ok separated from step keep), 4 ends
		c = rigkit.read_json(os.path.join(BOOKMARKS, 'gen', 'bookmarks.json'))
		self.assertLessEqual(len(c['flow']), 23)

	def test_doctor_flags_model_step_without_out_and_front_has_no_finish_step(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 2)
			rig_path = os.path.join(folder, 'demo-tool.rig')
			with open(rig_path, encoding='utf-8') as f:
				txt = f.read()
			no_out = txt.replace('  end done "Done"\n', '  step draft "Draft" by model\n    do "write a draft"\n  end done "Done"\n')
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(no_out)
			code, out = self.quiet(rig_project.doctor, folder, False)
			self.assertEqual(code, 1, out)
			self.assertIn('every step of the model has an "out" type', out)
			# Plugin front emits work_run and never finish_step
			m = rig_project.manifest(folder)
			m['plugin'] = {'folder': 'plugin', 'owner': 'tester', 'timeout_s': 120}
			files = rig_project.loaded(folder, m)
			fr = rig_project.front(m, files, rig_project.main_unit(m, files))
			tool_names = [t['name'] for t in fr['tools']]
			self.assertIn('work_run', tool_names)
			self.assertNotIn('finish_step', tool_names)
			self.assertNotIn('finish_step', fr['prompt'])
			# Adding "out text" clears the doctor check
			with_out = no_out.replace('    do "write a draft"\n', '    do "write a draft"\n    out text\n')
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(with_out)
			self.quiet(rig_project.build, folder)
			code2, out2 = self.quiet(rig_project.doctor, folder, False)
			self.assertEqual(code2, 0, out2)
		finally:
			shutil.rmtree(tmp)

	def test_manifest_refuses_rig_version_0(self):
		tmp = tempfile.mkdtemp()
		try:
			with open(os.path.join(tmp, 'rig.json'), 'w', encoding='utf-8') as f:
				json.dump({'rig': 0, 'source': 'x.rig'}, f)
			with self.assertRaises(SystemExit):
				rig_project.manifest(tmp)
		finally:
			shutil.rmtree(tmp)

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

	def test_doctor_runs_tool_examples(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'sizes', 1)
			with open(os.path.join(folder, 'tools.py'), 'w', encoding='utf-8') as f:
				f.write('def sizes(text):\n\treturn (len(text.split()), len(text))\n')
			with open(os.path.join(folder, 'tests', 'test_tools.py'), 'w', encoding='utf-8') as f:
				f.write('import os, sys, unittest\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\nimport tools\nclass T(unittest.TestCase):\n\tdef test_sizes(self):\n\t\tself.assertEqual(tools.sizes("two words"), (2, 9))\n')
			rig_path = os.path.join(folder, 'sizes.rig')
			good_rig = 'unit sizes tool\n  intent "count words and chars"\n  in text str "the text"\n  out (tuple int int) "counts"\n  example "two words" => (2 9)\n  code tools.py\n    test tests/test_tools.py\n'
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(good_rig)
			self.quiet(rig_project.build, folder)
			code, out = self.quiet(rig_project.doctor, folder)
			self.assertEqual(code, 0, out)
			self.assertIn('every example of a tool unit passes', out)
			bad_rig = good_rig.replace('=> (2 9)', '=> (2 99)')
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(bad_rig)
			self.quiet(rig_project.build, folder)
			code, out = self.quiet(rig_project.doctor, folder)
			self.assertEqual(code, 1, out)
			self.assertIn('got (2, 9), expected [2, 99]', out)
		finally:
			shutil.rmtree(tmp)

	def test_level_4_permissions_check_requires_default_off_and_hard_gate(self):
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'p')
			self.quiet(rig_project.new, folder, 'demo-tool', 4)
			rig_path = os.path.join(folder, 'demo-tool.rig')
			with open(rig_path, encoding='utf-8') as f:
				orig = f.read()
			# Default "on" must fail
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(orig.replace('rule permissions.write off', 'rule permissions.write on'))
			code, out = self.quiet(rig_project.doctor, folder, False)
			self.assertEqual(code, 1, out)
			self.assertIn('permissions.write must default to off', out)
			# Not read by any hard gate must fail (even if read by a step)
			with open(os.path.join(folder, 'gates.py'), 'r', encoding='utf-8') as f:
				gates_orig = f.read()
			with open(os.path.join(folder, 'gates.py'), 'w', encoding='utf-8') as f:
				f.write(gates_orig.replace("R('permissions.write')", 'True'))
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(orig.replace('    reads permissions.write\n', '').replace('    do "read the item and measure it"', '    do "read the item and measure it"\n    reads permissions.write'))
			code, out = self.quiet(rig_project.doctor, folder, False)
			self.assertEqual(code, 1, out)
			self.assertIn('permissions.write is not read by a hard gate', out)
		finally:
			shutil.rmtree(tmp)

	def test_doctor_json_flag(self):
		tool = os.path.join(ROOT, 'skills', 'rig', 'rig.py')
		r = subprocess.run([sys.executable, tool, 'doctor', RELEASE, '--no-tests', '--json'], capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
		data = json.loads(r.stdout)
		self.assertEqual((data['name'], data['level'], data['level_name'], data['ok'], data['missing']), ('release', 4, 'production', True, 0))
		self.assertTrue(isinstance(data['checks'], list) and all({'level', 'state', 'text'} <= set(c) for c in data['checks']))
		self.assertIsInstance(data['notes'], list)
		tmp = tempfile.mkdtemp()
		try:
			folder = os.path.join(tmp, 'bad')
			self.quiet(rig_project.new, folder, 'demo-tool', 4)
			rig_path = os.path.join(folder, 'demo-tool.rig')
			with open(rig_path, encoding='utf-8') as f:
				txt = f.read()
			with open(rig_path, 'w', encoding='utf-8') as f:
				f.write(txt.replace('rule permissions.write off', 'rule permissions.write on'))
			r2 = subprocess.run([sys.executable, tool, 'doctor', folder, '--no-tests', '--json'], capture_output=True, text=True)
			self.assertEqual(r2.returncode, 1)
			d2 = json.loads(r2.stdout)
			self.assertFalse(d2['ok'])
			self.assertGreaterEqual(d2['missing'], 1)
		finally:
			shutil.rmtree(tmp)


if __name__ == '__main__':
	unittest.main()
