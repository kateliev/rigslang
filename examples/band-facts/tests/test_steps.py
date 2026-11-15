"""Tests of the steps and of whole runs, on the pages of tests/fixtures. No network, no model:
the test plays the answers of the model."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ['BAND_FACTS_OFFLINE'] = os.path.join(HERE, 'tests', 'fixtures')
import rigkit  # noqa: E402
import steps  # noqa: E402
import tool  # noqa: E402

GOOD = 'The Paper Lanterns are a rock band formed in 1998. The group has four members and is known for long songs with two guitars and a cello.'


class Steps(unittest.TestCase):
	def setUp(self):
		self.kit = tool.kit(runs=None)

	def test_find(self):
		got = steps.find({'band': 'The Paper Lanterns'}, self.kit.rules)
		self.assertEqual(got['url'], 'https://en.wikipedia.org/wiki/The_Paper_Lanterns')
		self.assertEqual(got['results'], ['The Paper Lanterns', 'Paper Lantern Lake'])
		nothing = steps.find({'band': 'Nobody At All'}, self.kit.rules)
		self.assertEqual((nothing['answered'], nothing['url']), (True, None))
		self.assertFalse(steps.find({'band': 'The Service Is Down'}, self.kit.rules)['answered'])

	def test_read(self):
		got = steps.read({'find': {'title': 'The_Paper_Lanterns', 'url': 'u'}}, self.kit.rules)
		self.assertEqual(got['albums'], [['First Light', 1999], ['Slow Tide', 2002], ['Harbour Songs', 2006], ['Demo Tape', 0]])
		self.assertIn('rock band', got['summary'])

	def test_compose(self):
		state = {'write': GOOD, 'read': {'url': 'https://x.example', 'albums': [['A', 1999], ['B', 0], ['C', 2001]]}}
		rules = rigkit.Rules(self.kit.catalogue, {'albums.max': 2})
		self.assertEqual(steps.compose(state, rules), GOOD + '\n\nAlbums:\n- A (1999)\n- B\n- and 1 more\n\nhttps://x.example')

	def test_the_model_gets_the_facts_it_needs(self):
		r = self.kit.run({'band': 'The Paper Lanterns'})
		self.assertEqual(r['waiting']['node'], 'is-band')
		self.assertEqual(r['waiting']['sees']['read.description'], 'Rock band (invented for a test)')
		r = self.kit.answer(r['run'], {'pass': True})
		self.assertEqual((r['waiting']['node'], r['waiting']['kind']), ('write', 'step'))
		self.assertIn('rock band formed in 1998', r['waiting']['sees']['read.summary'])
		self.assertIn('at most 120 words', r['waiting']['do'])

	def test_a_long_paragraph_does_not_pass(self):
		r = self.kit.run({'band': 'The Paper Lanterns'})
		r = self.kit.answer(r['run'], {'pass': True})
		r = self.kit.answer(r['run'], {'result': 'word ' * 142})
		self.assertEqual(r['waiting']['node'], 'write')            # back to the model, not on to the answer
		self.assertIn('142 words (answer.max_words 120)', r['problems'][-1])
		self.assertEqual(r['waiting']['sees']['write'], ('word ' * 142))

	def test_the_result_of_a_run(self):
		r = self.kit.run({'band': 'The Paper Lanterns'})
		r = self.kit.answer(r['run'], {'pass': True})
		r = self.kit.answer(r['run'], {'result': GOOD})
		r = self.kit.answer(r['run'], {'pass': True})
		self.assertEqual(r['outcome']['end'], 'done')
		self.assertTrue(r['result'].startswith(GOOD))
		self.assertIn('- Slow Tide (2002)', r['result'])
		self.assertEqual(r['guessed'], ['is-band', 'grounded'])

	def test_regression_set(self):
		cases = rigkit.read_json(os.path.join(HERE, 'tests', 'regression-set.json'))
		_, diffs = self.kit.regress(cases)
		self.assertEqual(diffs, [])


if __name__ == '__main__':
	unittest.main()
