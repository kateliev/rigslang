"""Tests of the steps and of whole runs, on temporary folders. No model: the test plays its answers.
The picks come from the draw of the run itself, never from a list written here."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rigkit  # noqa: E402
import steps  # noqa: E402
import tool  # noqa: E402

FONT_NAMES_ENGINE = os.path.join(os.path.dirname(HERE), 'font-names', 'engine.py')		# the next tool of the chain
STORY = {'story': 'A sturdy serif for a museum show about the siege of Troy'}
TOPIC = {'result': {'list': 'trojan-heroes', 'why': 'the story is about the siege of Troy'}}


def picks(waiting, n=3):
	'''The first n drawn names of a run that waits at pick, as an answer of the model.'''
	drawn = waiting['sees']['sample']['names']
	return {'result': [{'name': d['name'], 'why': 'a hero of Troy'} for d in drawn[:n]]}


class Steps(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.out = os.path.join(self.tmp, 'out')
		self.kit = tool.kit(runs=None)

	def tearDown(self):
		shutil.rmtree(self.tmp)

	def rules(self, **changes):
		return rigkit.Rules(self.kit.catalogue, dict((k.replace('__', '.'), v) for k, v in changes.items()))

	def test_lists_reads_every_list_of_the_folder(self):
		folder = os.path.join(self.tmp, 'lists')
		os.mkdir(folder)
		for name, count in (('b-list', 2), ('a-list', 1)):
			with open(os.path.join(folder, name + '.json'), 'w', encoding='utf-8') as f:
				json.dump({'name': name, 'about': 'a test list', 'names': [{'name': 'N%d' % i, 'note': ''} for i in range(count)]}, f)
		with open(os.path.join(folder, 'README.txt'), 'w') as f:
			f.write('not a list')
		got = steps.lists({}, self.rules(names__lists=folder))
		self.assertEqual(got, [{'name': 'a-list', 'about': 'a test list', 'count': 1}, {'name': 'b-list', 'about': 'a test list', 'count': 2}])
		self.assertEqual(steps.lists({}, self.rules(names__lists=os.path.join(self.tmp, 'nothing'))), [])

	def test_the_lists_of_the_tool_are_valid(self):
		R = self.rules()
		for d in steps.read_lists(R):
			names = [n['name'] for n in d['names']]
			self.assertTrue(d['source'].startswith('https://en.wikipedia.org/wiki/'), d['name'])
			self.assertEqual(len(names), len(set(names)), d['name'])
			for n in names:
				fam = steps.family_of(n)
				self.assertRegex(fam, r'^[A-Za-z][A-Za-z0-9]*$', n)
				self.assertLessEqual(len(fam), R('family.max_name'), n)

	@unittest.skipUnless(os.path.exists(FONT_NAMES_ENGINE), 'the example font-names is not next to this one')
	def test_every_plant_makes_font_names_ask_the_model(self):
		'''The list plants is for the chain: with the preset mac of font-names, the placeholders of each
		plant need dropped vowels or a cut, so font-names stops at its reason block abbreviate.
		This is the check that chose the names (notes/project-facts.md).'''
		spec = importlib.util.spec_from_file_location('font_names_engine', FONT_NAMES_ENGINE)
		engine = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(engine)
		fn = rigkit.read_json(os.path.join(os.path.dirname(FONT_NAMES_ENGINE), 'gen', 'font-names.json'))
		fr = rigkit.Rules(fn, fn['presets']['mac'])
		R = self.rules()
		plants = next(d for d in steps.read_lists(R) if d['name'] == 'plants')
		self.assertGreaterEqual(len(plants['names']), 20)
		for n in plants['names']:
			fam = steps.family_of(n['name'])
			inst = [{'family': fam, 'name': s, 'italic': 'Italic' in s, 'variable': False} for s in R('family.styles')]
			rows = engine.build_rows(inst, engine.settings_of(fr, R('family.formats')[0]))
			self.assertTrue(engine.weak_words(inst, rows, fr('shorten.abbr_letters')[1] + 1), n['name'])

	def test_sample_with_a_seed_is_repeatable(self):
		state = {'lists': steps.lists({}, self.rules()), 'topic': {'list': 'Trojan-Heroes'}}
		one = steps.sample(state, self.rules(names__seed=7))
		self.assertEqual(one, steps.sample(state, self.rules(names__seed=7)))
		self.assertEqual((one['list'], one['seed'], len(one['names'])), ('trojan-heroes', 7, 8))
		self.assertEqual(len(set(n['name'] for n in one['names'])), 8)
		self.assertNotEqual(one['names'], steps.sample(state, self.rules(names__seed=8))['names'])

	def test_sample_without_a_seed_records_the_seed_it_used(self):
		state = {'lists': steps.lists({}, self.rules()), 'topic': {'list': 'winds'}}
		new = steps.sample(state, self.rules(names__sample=30))
		self.assertGreater(new['seed'], 0)
		self.assertEqual(len(new['names']), 13)		# the sample is never larger than the list
		again = steps.sample(state, self.rules(names__sample=30, names__seed=new['seed']))
		self.assertEqual(new['names'], again['names'])

	def test_a_sample_smaller_than_the_candidates_is_refused(self):
		# B2: with names.sample 2, pick cannot give three distinct drawn names, and every run is held back
		with self.assertRaisesRegex(ValueError, 'names.sample: at least 3'):
			self.kit.run(STORY, rules={'names.sample': 2})

	def test_family_of(self):
		self.assertEqual(steps.family_of('Ajax the Great'), 'AjaxTheGreat')
		self.assertEqual(steps.family_of('Laocoön'), 'Laocoon')
		self.assertEqual(steps.family_of('north-northwest wind'), 'NorthNorthwestWind')

	def test_names_lists_the_families_that_exist(self):
		os.makedirs(os.path.join(self.out, 'Hector'))
		with open(os.path.join(self.out, 'Paris'), 'w') as f:
			f.write('a file, not a family folder')
		state = {'sample': {'names': [{'name': 'Ajax the Great', 'note': 'Achaean'}]}, 'pick': [{'name': 'Ajax the Great', 'why': 'strong'}]}
		got = steps.names(state, self.rules(files__out=self.out))
		self.assertEqual(got['existing'], ['Hector'])
		self.assertEqual(got['families'], [{'number': 1, 'family': 'AjaxTheGreat', 'name': 'Ajax the Great', 'why': 'strong', 'note': 'Achaean'}])

	def test_choice(self):
		fams = [{'number': i + 1, 'family': f, 'name': n, 'why': 'w'} for i, (f, n) in enumerate([('Hector', 'Hector'), ('AjaxTheGreat', 'Ajax the Great')])]
		for words in ('2', 'ajaxthegreat', 'Ajax the Great'):
			v = steps.choice({'choose': {'answer': words}, 'names': {'families': fams}}, self.rules())
			self.assertEqual((v['pass'], v['family']), (True, 'AjaxTheGreat'), words)
		v = steps.choice({'choose': {'answer': '3'}, 'names': {'families': fams}}, self.rules())
		self.assertFalse(v['pass'])
		self.assertIn('from 1 to 2', v['problems'][0])

	def test_write_makes_the_placeholders_and_refuses_a_folder_that_exists(self):
		state = {'choose': {'family': 'Hector'}}
		got = steps.write(state, self.rules(files__out=self.out))
		want = ['Hector-Bold.otf', 'Hector-BoldItalic.otf', 'Hector-Italic.otf', 'Hector-Regular.otf']
		self.assertEqual((got['files'], got['after']), (want, want))
		self.assertEqual([os.path.getsize(os.path.join(got['folder'], n)) for n in want], [0, 0, 0, 0])
		with self.assertRaises(OSError):
			steps.write(state, self.rules(files__out=self.out))
		got = steps.write({'choose': {'family': 'Paris'}}, self.rules(files__out=self.out, family__formats=['.otf', '.ttf'], family__styles=['Regular']))
		self.assertEqual(got['after'], ['Paris-Regular.otf', 'Paris-Regular.ttf'])

	def test_a_run_waits_at_topic(self):
		r = self.kit.run(STORY)
		w = r['waiting']
		self.assertEqual((w['node'], w['kind']), ('topic', 'step'))
		self.assertEqual([d['name'] for d in w['sees']['lists']], ['plants', 'trojan-heroes', 'winds'])
		self.assertEqual(w['schema']['required'], ['list', 'why'])

	def test_pick_is_a_creative_reason_with_three_candidates(self):
		r = self.kit.run(STORY, rules={'names.seed': 7})
		r = self.kit.answer(r['run'], TOPIC)
		w = r['waiting']
		self.assertEqual((w['node'], w['kind'], w['mode'], w['candidates']), ('pick', 'reason', 'creative', 3))
		self.assertEqual((w['schema']['minItems'], w['schema']['maxItems']), (3, 3))
		self.assertEqual(w['intent']['local'], 'choose the names that fit the story best, as a type designer names a family')
		self.assertEqual([n['gate'] for n in w['intent']['never']], ['picks-ok', 'choose', 'free'])
		self.assertEqual(w['sees']['sample']['seed'], 7)
		self.assertEqual(len(w['sees']['sample']['names']), 8)
		# two candidates do not have the form of out: the reason block waits again
		r = self.kit.answer(r['run'], dict(picks(w, 2)))
		self.assertEqual(r['waiting']['node'], 'pick')
		self.assertIn('does not have the form of out', r['waiting']['problems'][0])

	def full_run(self, rules, choose='2'):
		r = self.kit.run(STORY, rules=dict(rules, **{'names.seed': 7}))
		r = self.kit.answer(r['run'], TOPIC)
		chosen = picks(r['waiting'])
		r = self.kit.answer(r['run'], chosen)
		r = self.kit.answer(r['run'], {'pass': True, 'why': 'all three are heroes of Troy'})  # fits: a model gate
		self.assertEqual(r['waiting']['kind'], 'human')
		return self.kit.approve(r['run'], [choose]), chosen['result'][int(choose) - 1]['name']

	def test_a_full_run_writes_the_placeholders(self):
		r, name = self.full_run({'files.out': self.out})
		self.assertEqual(r['outcome']['end'], 'done')
		self.assertEqual(r['guessed'], ['fits'])
		family = steps.family_of(name)
		self.assertEqual(r['result']['family'], family)
		self.assertEqual(r['result']['folder'], os.path.join(self.out, family))
		self.assertEqual(os.listdir(self.out), [family])
		self.assertEqual(sorted(os.listdir(r['result']['folder'])), ['{}-{}.otf'.format(family, s) for s in ('Bold', 'BoldItalic', 'Italic', 'Regular')])

	def test_a_folder_that_exists_holds_the_run_back(self):
		r, name = self.full_run({'files.out': self.out}, choose='1')
		family = steps.family_of(name)
		with open(os.path.join(self.out, family, 'notes.txt'), 'w') as f:
			f.write('the work of a person')
		r, _ = self.full_run({'files.out': self.out}, choose='1')
		self.assertEqual(r['outcome']['end'], 'held')
		self.assertIn('has a folder in', ' '.join(r['problems']))
		self.assertIn('notes.txt', os.listdir(os.path.join(self.out, family)))

	def test_the_model_cannot_answer_for_the_person(self):
		r = self.kit.run(STORY, rules={'names.seed': 7, 'files.out': self.out})
		r = self.kit.answer(r['run'], TOPIC)
		r = self.kit.answer(r['run'], picks(r['waiting']))
		r = self.kit.answer(r['run'], {'pass': True})
		self.assertEqual(r['waiting']['options'], ['1', '2', '3'])
		with self.assertRaises(rigkit.Refused):
			self.kit.answer(r['run'], {'answer': '1'})
		self.assertFalse(os.path.exists(self.out))

	def test_regression_set(self):
		cases = rigkit.read_json(os.path.join(HERE, 'tests', 'regression-set.json'))
		taken = os.path.join(HERE, 'tests', 'cases', 'taken')
		before = sorted(os.listdir(taken))
		try:
			_, diffs = self.kit.regress(cases)
		finally:
			tool.clean_cases()
		self.assertEqual(diffs, [])
		self.assertEqual(sorted(os.listdir(taken)), before)
		self.assertFalse(os.path.exists(os.path.join(HERE, tool.REGRESS_OUT)))


if __name__ == '__main__':
	unittest.main()
