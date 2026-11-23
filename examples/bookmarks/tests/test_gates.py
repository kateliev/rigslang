"""Tests of the gates, with the rule defaults of the catalogue and with changed rules. No files, no model.
Run: python3 -m unittest discover -s tests   (or: rig.py test .)
Every gate needs a test here that names it: rig.py check counts a gate as tested only then."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'bookmarks.json'))


def rules(**changes):
	'''The rules of the catalogue; write a change as sort__rounds=1.'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


def a_batch(**more):
	b = {'batch': 2, 'of': 3, 'sort_visits': 4, 'new_so_far': ['Top > Made'],
		'folders': ['Top', 'Top > Cooking', 'Top > Made'],
		'bookmarks': [{'id': 1, 'title': 'One', 'url': 'https://a.example/', 'folder': 'Top'},
			{'id': 2, 'title': 'Two', 'url': 'https://b.example/', 'folder': 'Top'}]}
	b.update(more)
	return b


class Gates(unittest.TestCase):
	def test_file_ok(self):
		self.assertTrue(gates.file_ok({'read': {'ok': True, 'bookmarks': 3}}, rules())['pass'])
		v = gates.file_ok({'read': {'ok': False, 'problem': 'this is a JSON file'}}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('JSON', v['problems'][0])
		self.assertFalse(gates.file_ok({'read': {'ok': True, 'bookmarks': 0}}, rules())['pass'])

	def test_page_left(self):
		self.assertTrue(gates.page_left({'page': {'page': 1, 'of': 2}}, rules())['pass'])
		v = gates.page_left({'page': {'page': None, 'of': 2}}, rules())
		self.assertFalse(v['pass'])
		self.assertTrue(v['route'])  # the end of a loop is not a problem

	def test_choice_ok(self):
		self.assertTrue(gates.choice_ok({'apply': {'ok': True, 'problems': []}}, rules())['pass'])
		v = gates.choice_ok({'apply': {'ok': False, 'problems': ['"x" is not understood']}}, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(v['problems'], ['"x" is not understood'])

	def test_batch_left(self):
		self.assertTrue(gates.batch_left({'batch': {'batch': 1, 'of': 1}}, rules())['pass'])
		v = gates.batch_left({'batch': {'batch': None, 'of': 1}}, rules())
		self.assertFalse(v['pass'])
		self.assertTrue(v['route'])

	def test_sort_ok(self):
		good = [{'id': 1, 'folder': 'Top > Cooking'}, {'id': 2, 'folder': 'Top'}]
		self.assertTrue(gates.sort_ok({'batch': a_batch(), 'sort': good}, rules())['pass'])
		self.assertTrue(gates.sort_ok({'batch': a_batch(), 'sort': [{'id': 1, 'folder': 'Top > Made'}, {'id': 2, 'folder': 'Top > Garden', 'new': True}]}, rules())['pass'])
		cases = {
			'missing ids: 2': [{'id': 1, 'folder': 'Top'}],
			'is in the result 2 times': [{'id': 1, 'folder': 'Top'}, {'id': 1, 'folder': 'Top'}, {'id': 2, 'folder': 'Top'}],
			'is not in this batch': good + [{'id': 7, 'folder': 'Top'}],
			'the title was changed': [{'id': 1, 'folder': 'Top', 'title': 'Another'}, {'id': 2, 'folder': 'Top'}],
			'add "new": true': [{'id': 1, 'folder': 'Top > Garden'}, {'id': 2, 'folder': 'Top'}],
			'is not under a folder of the list': [{'id': 1, 'folder': 'Nowhere > Garden', 'new': True}, {'id': 2, 'folder': 'Top'}],
			'not a list': {'id': 1},
		}
		for want, answer in cases.items():
			v = gates.sort_ok({'batch': a_batch(), 'sort': answer}, rules())
			self.assertFalse(v['pass'], want)
			self.assertTrue(any(want in p for p in v['problems']), (want, v['problems']))
			self.assertTrue(v['problems'][0].startswith('batch 2: '))
		two_new = [{'id': 1, 'folder': 'Top > A', 'new': True}, {'id': 2, 'folder': 'Top > B', 'new': True}]
		self.assertTrue(gates.sort_ok({'batch': a_batch(), 'sort': two_new}, rules())['pass'])
		v = gates.sort_ok({'batch': a_batch(), 'sort': two_new}, rules(sort__new_per_batch=1))
		self.assertIn('sort.new_per_batch 1', v['problems'][0])
		v = gates.sort_ok({'batch': a_batch(), 'sort': two_new}, rules(sort__new_max=2))
		self.assertIn('sort.new_max 2', v['problems'][0])  # one made earlier, two now

	def test_rounds_left(self):
		def state(visits):
			return {'batch': a_batch(), '_visits': {'sort': visits}}
		self.assertTrue(gates.rounds_left(state(5), rules())['pass'])  # the first answer of this batch
		self.assertTrue(gates.rounds_left(state(6), rules())['pass'])
		v = gates.rounds_left(state(7), rules())
		self.assertFalse(v['pass'])
		self.assertIn('sort.rounds 2', v['problems'][0])
		self.assertFalse(gates.rounds_left(state(5), rules(sort__rounds=0))['pass'])

	def test_any_new(self):
		self.assertTrue(gates.any_new({'folders': {'new': [{'n': 1}]}}, rules())['pass'])
		v = gates.any_new({'folders': {'new': []}}, rules())
		self.assertFalse(v['pass'])
		self.assertTrue(v['route'])

	def test_accept_ok(self):
		self.assertTrue(gates.accept_ok({'accept': {'ok': True}}, rules())['pass'])
		self.assertFalse(gates.accept_ok({'accept': {'ok': False, 'problems': ['x']}}, rules())['pass'])

	def test_share_ok(self):
		self.assertTrue(gates.share_ok({'report': {'removed_share': 14.3}}, rules())['pass'])
		v = gates.share_ok({'report': {'removed_share': 40.0}}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('safety.max_removed 30', v['problems'][0])
		self.assertFalse(gates.share_ok({'report': {'removed_share': 14.3}}, rules(safety__max_removed=10))['pass'])

	def test_verify(self):
		good = {'same_bookmarks': True, 'bookmarks_found': 5, 'bookmarks_expected': 5, 'missing': [], 'extra': [], 'folders_missing': [], 'moves_astray': []}
		self.assertTrue(gates.verify({'build': good}, rules())['pass'])
		for k, v in (('same_bookmarks', False), ('folders_missing', ['Top > Cooking']), ('moves_astray', ['3'])):
			bad = dict(good, **{k: v})
			self.assertFalse(gates.verify({'build': bad}, rules())['pass'], k)

	def test_may_place(self):
		free = {'build': {'target': '/x/out.html', 'target_exists': False}}
		taken = {'build': {'target': '/x/out.html', 'target_exists': True}}
		self.assertTrue(gates.may_place(free, rules())['pass'])
		v = gates.may_place(taken, rules())
		self.assertFalse(v['pass'])
		self.assertIn('permissions.overwrite off', v['problems'][0])
		self.assertTrue(gates.may_place(taken, rules(permissions__overwrite=True))['pass'])


if __name__ == '__main__':
	unittest.main()
