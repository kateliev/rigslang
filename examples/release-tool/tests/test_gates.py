"""Tests of the gates, with the rule defaults of the catalogue. No files, no model.
Run: python3 -m unittest discover -s tests   (or: rig.py test .)"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'release.json'))


def rules(**changes):
	'''The rules of the catalogue; a change is written as notes__min_words=10.'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


def state(notes='word ' * 60, version='1.2.3', tests=None, **more):
	s = {'collect': {'notes': notes, 'version': version, 'tests': {'passed': True} if tests is None else tests}}
	s.update(more)
	return s


class Gates(unittest.TestCase):
	def test_notes_ok(self):
		self.assertTrue(gates.notes_ok(state(), rules())['pass'])
		v = gates.notes_ok(state(notes='too short'), rules())
		self.assertFalse(v['pass'])
		self.assertIn('notes.min_words', v['problems'][0])
		self.assertTrue(gates.notes_ok(state(notes='word ' * 12), rules(notes__min_words=10))['pass'])

	def test_notes_ok_reads_the_rewrite(self):
		self.assertTrue(gates.notes_ok(state(notes='short', rewrite='word ' * 60), rules())['pass'])

	def test_version_ok(self):
		self.assertTrue(gates.version_ok(state(), rules())['pass'])
		self.assertFalse(gates.version_ok(state(version='v1.2'), rules())['pass'])

	def test_tests_required(self):
		self.assertTrue(gates.tests_required(state(), rules())['pass'])
		red = state(tests={'passed': False})
		self.assertFalse(gates.tests_required(red, rules())['pass'])
		self.assertTrue(gates.tests_required(red, rules(tests__required=False))['pass'])
		self.assertFalse(gates.tests_required(state(tests={}), rules())['pass'])

	def test_tests_green(self):
		self.assertTrue(gates.tests_green(state(), rules())['pass'])
		self.assertFalse(gates.tests_green(state(tests={'passed': False}), rules(tests__required=False))['pass'])
		self.assertIn('no test result', gates.tests_green(state(tests={}), rules())['problems'][0])

	def test_may_publish(self):
		self.assertFalse(gates.may_publish(state(), rules())['pass'])
		self.assertTrue(gates.may_publish(state(), rules(permissions__publish=True))['pass'])


if __name__ == '__main__':
	unittest.main()
