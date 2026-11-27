"""Tests of the gates, with the rule defaults of the catalogue. No files, no model.
Run: python3 -m unittest discover -s tests   (or: rig.py test .)
Every gate needs a test here that names it: rig.py check counts a gate as tested only then.
The code of the human gate (steps.choice) is tested in test_steps.py."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'family-namer.json'))
LISTS = [{'name': 'heroes', 'about': 'heroes', 'count': 3}, {'name': 'winds', 'about': 'winds', 'count': 2}]
DRAWN = {'names': [{'name': 'Ajax the Great', 'note': ''}, {'name': 'Hector', 'note': ''}, {'name': 'Paris', 'note': ''}]}


def rules(**changes):
	'''The rules of the catalogue; write a change as family__max_name=10.'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


def families(*names):
	return {'families': [{'family': n, 'name': n} for n in names], 'existing': [], 'out': 'out'}


class Gates(unittest.TestCase):
	def test_list_named(self):
		self.assertEqual(gates.list_named(LISTS, ' Winds '), 'winds')
		self.assertIsNone(gates.list_named(LISTS, 'stars'))
		self.assertIsNone(gates.list_named(LISTS, None))

	def test_topic_ok(self):
		self.assertTrue(gates.topic_ok({'lists': LISTS, 'topic': {'list': 'heroes', 'why': ''}}, rules())['pass'])
		self.assertTrue(gates.topic_ok({'lists': LISTS, 'topic': {'list': 'None', 'why': ''}}, rules())['pass'])
		v = gates.topic_ok({'lists': LISTS, 'topic': {'list': 'stars', 'why': ''}}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('heroes, winds, or none', v['problems'][0])
		self.assertFalse(gates.topic_ok({'lists': LISTS}, rules())['pass'])

	def test_has_list(self):
		self.assertTrue(gates.has_list({'lists': LISTS, 'topic': {'list': 'winds', 'why': ''}}, rules())['pass'])
		v = gates.has_list({'lists': LISTS, 'topic': {'list': 'none', 'why': 'a story about trees'}}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('a story about trees', v['problems'][0])

	def test_picks_ok(self):
		good = [{'name': 'Hector', 'why': ''}, {'name': 'Paris', 'why': ''}, {'name': 'Ajax the Great', 'why': ''}]
		self.assertTrue(gates.picks_ok({'sample': DRAWN, 'pick': good}, rules())['pass'])
		v = gates.picks_ok({'sample': DRAWN, 'pick': [{'name': 'Achilles', 'why': ''}, {'name': 'Hector', 'why': ''}, {'name': 'hector', 'why': ''}]}, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(len(v['problems']), 3)		# Achilles was not drawn; "hector" is not as drawn, and comes twice
		self.assertIn('was not drawn', v['problems'][0])
		self.assertIn('comes twice', v['problems'][2])
		self.assertEqual(gates.picks_ok({'sample': DRAWN, 'pick': None}, rules())['problems'], ['no picks'])

	def test_names_ok(self):
		self.assertTrue(gates.names_ok({'names': families('Hector', 'AjaxTheGreat', 'Paris2')}, rules())['pass'])
		v = gates.names_ok({'names': families('Hector', '2Paris', 'Ajax-Great', 'hector')}, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(len(v['problems']), 3)
		self.assertIn('comes twice', v['problems'][2])
		v = gates.names_ok({'names': families('AjaxTheGreat')}, rules(family__max_name=8))
		self.assertIn('family.max_name is 8', v['problems'][0])

	def test_free(self):
		state = {'choose': {'family': 'Hector'}, 'names': dict(families('Hector'), existing=['Paris'])}
		self.assertTrue(gates.free(state, rules())['pass'])
		state['names']['existing'] = ['HECTOR']
		v = gates.free(state, rules())
		self.assertFalse(v['pass'])
		self.assertIn('has a folder in out', v['problems'][0])

	def test_written(self):
		files = ['Hector-Bold.otf', 'Hector-Regular.otf']
		self.assertTrue(gates.written({'write': {'files': files, 'after': files}}, rules())['pass'])
		v = gates.written({'write': {'files': files, 'after': ['Hector-Bold.otf', 'notes.txt']}}, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(v['problems'], ['Hector-Regular.otf is missing', 'notes.txt should not be there'])


if __name__ == '__main__':
	unittest.main()
