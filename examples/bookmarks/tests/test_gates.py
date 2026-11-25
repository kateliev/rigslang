"""Tests of the gates, with the rule defaults of the catalogue and with changed rules. No files, no model.
Run: python3 -m unittest discover -s tests   (or: rig.py test .)
Every gate needs a test here that names it: rig.py check counts a gate as tested only then."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import bm  # noqa: E402
import gates  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'bookmarks.json'))


def rules(**changes):
	'''The rules of the catalogue; write a change as sort__rounds=1.'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


def a_batch(**more):
	b = {'batch': 2, 'of': 3, 'new_so_far': ['Top > Made'],
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

	def test_sort_ok_with_picks(self):
		batch = a_batch(bookmarks=[dict(x, choices={'1': 'Top', '2': 'Top > Cooking'}) for x in a_batch()['bookmarks']])
		picks = [{'id': 1, 'pick': 2}, {'id': 2, 'pick': 1}]
		self.assertTrue(gates.sort_ok({'prepare': batch, 'sort': picks}, rules())['pass'])
		self.assertEqual(bm.places(picks, batch['bookmarks']), {1: 'Top > Cooking', 2: 'Top'})
		mixed = [{'id': 1, 'pick': 2}, {'id': 2, 'folder': 'Top > Garden', 'new': True}]
		self.assertTrue(gates.sort_ok({'prepare': batch, 'sort': mixed}, rules())['pass'])
		self.assertEqual(bm.places(mixed, batch['bookmarks'])[2], 'Top > Garden')
		for bad in (3, 0, '2', True):
			v = gates.sort_ok({'prepare': batch, 'sort': [{'id': 1, 'pick': bad}, {'id': 2, 'pick': 1}]}, rules())
			self.assertFalse(v['pass'], bad)
			self.assertIn('is not one of its choices (1, 2); when none fits, give "folder"', v['problems'][0])
		v = gates.sort_ok({'prepare': batch, 'sort': [{'id': 1}, {'id': 2, 'pick': 1}]}, rules())
		self.assertIn('no "pick" of its choices, and no "folder"', v['problems'][0])
		zero = [{'id': 1, 'topic': 'gardens', 'pick': 1, 'folder': 'Top > Garden', 'new': True}, {'id': 2, 'topic': 'soup', 'pick': 2}]  # the folder counts
		self.assertTrue(gates.sort_ok({'prepare': batch, 'sort': zero}, rules())['pass'])
		self.assertEqual(bm.places(zero, batch['bookmarks']), {1: 'Top > Garden', 2: 'Top > Cooking'})

	def test_sort_ok(self):
		good = [{'id': 1, 'folder': 'Top > Cooking'}, {'id': 2, 'folder': 'Top'}]
		self.assertTrue(gates.sort_ok({'prepare': a_batch(), 'sort': good}, rules())['pass'])
		self.assertTrue(gates.sort_ok({'prepare': a_batch(), 'sort': [{'id': 1, 'folder': 'Top > Made'}, {'id': 2, 'folder': 'Top > Garden', 'new': True}]}, rules())['pass'])
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
			v = gates.sort_ok({'prepare': a_batch(), 'sort': answer}, rules())
			self.assertFalse(v['pass'], want)
			self.assertTrue(any(want in p for p in v['problems']), (want, v['problems']))
			self.assertTrue(v['problems'][0].startswith('batch 2: '))
		two_new = [{'id': 1, 'folder': 'Top > A', 'new': True}, {'id': 2, 'folder': 'Top > B', 'new': True}]
		self.assertTrue(gates.sort_ok({'prepare': a_batch(), 'sort': two_new}, rules())['pass'])
		v = gates.sort_ok({'prepare': a_batch(), 'sort': two_new}, rules(sort__new_per_batch=1))
		self.assertIn('sort.new_per_batch 1', v['problems'][0])
		v = gates.sort_ok({'prepare': a_batch(), 'sort': two_new}, rules(sort__new_max=2))
		self.assertIn('sort.new_max 2', v['problems'][0])  # one made earlier, two now

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
