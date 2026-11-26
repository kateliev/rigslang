"""Tests of the steps on the synthetic fixture, in a temporary folder. No model, no network.
The person and the model are played by the test. The last test stops a run in the middle and goes on
with a new runner, as after a restart."""
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

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'bookmarks.json'))
FIXTURE = os.path.join(HERE, 'tests', 'fixtures', 'export.html')


class Steps(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.R = rigkit.Rules(CATALOGUE, {'files.work': os.path.join(self.tmp, 'work'), 'files.out': os.path.join(self.tmp, 'out'), 'sort.batch': 10})

	def tearDown(self):
		shutil.rmtree(self.tmp)

	def go(self, state, name):
		'''Run one step as the runner does: its value goes to the state, under the id of its node.'''
		node = {'page': 'show', 'dupes': 'similar', 'group': 'similar'}.get(name, name)
		state[node] = getattr(steps, name)(state, self.R)
		return state[node]

	def test_read(self):
		self.assertFalse(steps.read({'file': os.path.join(self.tmp, 'none.html')}, self.R)['ok'])
		r = steps.read({'file': os.path.join(HERE, 'tests', 'fixtures', 'live-bookmarks.json')}, self.R)
		self.assertFalse(r['ok'])
		self.assertIn('JSON', r['problem'])
		r = steps.read({'file': 'tests/fixtures/export.html'}, self.R)  # relative: in the tool folder
		self.assertTrue(r['ok'])
		self.assertEqual((r['bookmarks'], r['folders'], r['bar']), (42, 8, 3))
		self.assertTrue(os.path.exists(os.path.join(r['work'], 'collection.json')))

	def test_the_steps_in_order(self):
		s = {'file': FIXTURE}
		self.go(s, 'read')
		self.assertEqual(self.go(s, 'dupes'), {'removed': 3})
		self.assertEqual(self.go(s, 'group'), {'folded': 2, 'groups': 2, 'pages': [1], 'too_big': 0})
		s['page'] = 1  # the item of the loop "for page in similar.pages"
		p = self.go(s, 'page')
		self.assertEqual((p['page'], p['of'], len(p['groups']), p['ask']), (1, 1, 2, True))
		self.assertTrue(os.path.exists(p['file']))
		s['choose'] = {'answer': 'yes 1=7'}
		self.assertFalse(self.go(s, 'apply')['pass'])
		self.assertTrue(self.go(s, 'page')['ask'])  # nothing was saved
		s['choose'] = {'answer': 'yes 1=2'}
		self.assertEqual(self.go(s, 'apply')['removed'], 3)  # group 1 keeps URL 2; group 2 keeps the shortest
		self.assertFalse(self.go(s, 'page')['ask'])  # decided before: a restart does not ask again
		self.assertEqual(self.go(s, 'loose'), {'fit': 22, 'loose': 11, 'misfiled': 1, 'batches': [1, 2]})
		s['batch'] = 1  # the item of the loop "for batch in loose.batches"
		b = self.go(s, 'prepare')
		self.assertEqual((b['batch'], b['of'], len(b['bookmarks'])), (1, 2, 10))
		self.assertNotIn('Favorites bar', b['folders'])  # keep.bar
		paprika = [x for x in b['bookmarks'] if x['title'] == 'Smoked paprika guide'][0]
		self.assertEqual(paprika['choices'][str(paprika['now'])], 'Other favorites')  # its present folder, by number
		self.assertNotIn('folder', paprika)
		self.assertIn('Other favorites > Cooking', paprika['choices'].values())  # Cooking holds a page of its site
		self.assertLessEqual(len(paprika['choices']), self.R('sort.choices'))
		self.assertEqual(sorted(b['map']), ['Other favorites > Clubs', 'Other favorites > Cooking', 'Other favorites > Programming', 'Other favorites > Travel'])
		self.assertIn('Python', b['map']['Other favorites > Programming'])
		s['sort'] = [{'id': x['id'], 'folder': 'Other favorites > Hobbies', 'new': True} for x in b['bookmarks']]
		self.assertEqual(steps.keep(s, self.R), {'pass': True, 'batch': 1, 'moved': 10, 'new': ['Other favorites > Hobbies']})
		s['batch'] = 2
		b = self.go(s, 'prepare')
		self.assertEqual((b['batch'], b['new_so_far']), (2, ['Other favorites > Hobbies']))
		self.assertIn('Other favorites > Hobbies', b['folders'])  # batch 2 gets no saved answer: it stays unsorted
		f = self.go(s, 'folders')
		self.assertEqual([(x['n'], x['bookmarks']) for x in f['new']], [(1, 10)])
		s['new-ok'] = {'answer': 'yes 2=no'}
		self.assertFalse(self.go(s, 'accept')['pass'])
		s['new-ok'] = {'answer': 'yes'}
		self.assertEqual(self.go(s, 'accept')['made'], ['Other favorites > Hobbies'])
		self.assertEqual(steps.dead_links(s, self.R), [])
		r = self.go(s, 'report')
		self.assertEqual((r['bookmarks_before'], r['bookmarks_after'], r['moved'], r['new_folders'], r['unsorted_batches']), (42, 34, 10, 1, 1))
		with open(r['report'], encoding='utf-8') as fh:
			text = fh.read()
		self.assertIn('Nothing is written yet', text)
		self.assertFalse(os.path.exists(os.path.join(self.tmp, 'out')))  # the dry run writes no output
		b = self.go(s, 'build')
		self.assertTrue(b['same_bookmarks'])
		self.assertEqual((b['folders_missing'], b['moves_astray'], b['target_exists']), ([], [], False))
		placed = self.go(s, 'place')
		self.assertTrue(os.path.exists(placed['file']))
		with open(FIXTURE, encoding='utf-8') as fh:
			self.assertIn('Generators explained (comments)', fh.read())  # the export did not change
		s['build'] = self.go(s, 'build')
		self.assertTrue(s['build']['target_exists'])
		with self.assertRaises(PermissionError):
			steps.place(s, self.R)

	def test_a_new_folder_left_out(self):
		s = {'file': FIXTURE}
		for name in ('read', 'dupes', 'group'):
			self.go(s, name)
		s['choose'], s['page'], s['batch'] = {'answer': 'no'}, 1, 1
		self.go(s, 'page')
		self.assertTrue(self.go(s, 'apply')['rest'])
		self.go(s, 'loose')
		b = self.go(s, 'prepare')
		ids = [x['id'] for x in b['bookmarks']]
		s['sort'] = [{'id': ids[0], 'folder': 'Other favorites > A', 'new': True}, {'id': ids[1], 'folder': 'Other favorites > A > B', 'new': True}] + \
			[{'id': i, 'folder': 'Other favorites > Travel'} for i in ids[2:]]
		self.go(s, 'keep')
		self.go(s, 'folders')
		s['new-ok'] = {'answer': 'yes 1=no'}
		a = self.go(s, 'accept')
		self.assertEqual((a['made'], a['left_out']), ([], ['Other favorites > A', 'Other favorites > A > B']))  # B was in A
		plan = steps.plan_of(s, self.R)
		self.assertEqual(sorted(set(plan['moves'].values())), ['Other favorites > Travel'])

	def test_the_hook_for_dead_links(self):
		s = {'file': FIXTURE}
		for name in ('read', 'dupes', 'group'):
			self.go(s, name)
		s['choose'], s['page'] = {'answer': 'no'}, 1
		for name in ('page', 'apply', 'loose', 'folders'):
			self.go(s, name)
		s['new-ok'] = {'answer': 'no'}
		self.go(s, 'accept')
		steps.save(s['read']['work'], 'dead.json', [0, 20])  # what a later link checker writes
		self.assertEqual(steps.dead_links(s, self.R), [0, 20])
		r = self.go(s, 'report')
		self.assertEqual((r['dead'], r['new_folders']), (2, 1))
		b = self.go(s, 'build')
		self.assertEqual((b['same_bookmarks'], b['moves_astray']), (True, []))
		with self.assertRaises(NotImplementedError):
			steps.dead_links(s, rigkit.Rules(CATALOGUE, {'links.check': True}))


class Resume(unittest.TestCase):
	def test_a_run_goes_on_after_a_restart(self):
		tmp = tempfile.mkdtemp()
		try:
			changes = {'files.work': os.path.join(tmp, 'work'), 'files.out': os.path.join(tmp, 'out'), 'sort.batch': 10}
			runs = os.path.join(tmp, 'runs')
			r = tool.kit(runs).run({'file': FIXTURE}, rules=changes)
			self.assertEqual(r['waiting']['node'], 'choose')
			r = tool.kit(runs).approve(r['run'], ['yes'])
			sees = r['waiting']['sees']
			self.assertEqual(sees['prepare.batch'], 1)
			self.assertNotIn('prepare', sees)  # the model gets the choices, not the whole folder list
			first = [{'id': x['id'], 'topic': 'a test', 'pick': 1} for x in sees['prepare.bookmarks']]
			r = tool.kit(runs).answer(r['run'], {'result': first})
			self.assertEqual(r['waiting']['sees']['prepare.batch'], 2)
			# a new process: the saved batch is not asked again
			again = tool.kit(runs)
			self.assertEqual(again.status(r['run'])['waiting']['sees']['prepare.batch'], 2)
			self.assertEqual(again.queues()['left_for_model'][0]['run'], r['run'])
			r = again.answer(r['run'], {'result': [{'id': x['id'], 'topic': 'a test', 'pick': 1, 'folder': x['choices'][str(x['now'])]} for x in r['waiting']['sees']['prepare.bookmarks']]})
			self.assertEqual(r['waiting']['node'], 'approve')
			self.assertEqual(tool.kit(runs).queues()['waits_for_person'][0]['run'], r['run'])
			self.assertIn('refused', json.dumps(_refused(lambda: tool.kit(runs).answer(r['run'], {'pass': True}))))  # the model cannot answer for the person
			self.assertEqual(r['problems'], [])  # the ends of the loops are no problems
		finally:
			shutil.rmtree(tmp)


def _refused(fn):
	try:
		return fn()
	except rigkit.Refused as e:
		return {'refused': str(e)}


if __name__ == '__main__':
	unittest.main()
