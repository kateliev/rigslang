"""Tests of bm.py: the file form, the normal form of a URL, duplicates, similar groups, the answers, the
new file. Pure functions: no files but the synthetic fixture, no model."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import bm  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'bookmarks.json'))
FIXTURE = os.path.join(HERE, 'tests', 'fixtures', 'export.html')


def rules(**changes):
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


def fixture():
	with open(FIXTURE, encoding='utf-8') as f:
		return f.read()


def by_url(c, url):
	return [b for b in c['bookmarks'] if b['url'] == url]


class Parse(unittest.TestCase):
	def test_folders_bookmarks_and_attributes(self):
		c = bm.parse(fixture())
		self.assertEqual(len(c['bookmarks']), 42)
		self.assertEqual(len(c['folders']), 8)
		self.assertTrue(c['folders'][0]['bar'])
		self.assertEqual(bm.path_of(c, c['folders'][3]['id']), 'Other favorites > Cooking > Baking')
		cafe = by_url(c, 'https://quiet-cafe.example/')[0]
		self.assertEqual(cafe['title'], 'Quiet caf&eacute; &amp; bakery')  # kept as written
		self.assertEqual(bm.plain_title(cafe), 'Quiet café & bakery')
		self.assertIn('ICON="data:image/png;base64,iVBORw0KGgo="', cafe['attrs'])
		self.assertEqual(cafe['dd'], 'A place to read on Sundays')
		self.assertEqual(by_url(c, 'https://mail.example.net/')[0]['add_date'], 1300000001)

	def test_not_a_bookmarks_file(self):
		with self.assertRaises(ValueError) as e:
			bm.parse('{"roots": {}}')
		self.assertIn('live Bookmarks file', str(e.exception))
		with self.assertRaises(ValueError):
			bm.parse('<html><body>hello</body></html>')

	def test_the_same_file_again_with_an_empty_plan(self):
		c = bm.parse(fixture())
		self.assertEqual(bm.render(c, {'removed': [], 'moves': {}, 'new_folders': []}, rules()), fixture())


class Key(unittest.TestCase):
	def test_the_normal_form(self):
		R = rules()
		same = ['https://www.a.example/x/', 'http://a.example/x', 'https://a.example/x#top', 'https://A.example/x?utm_source=n&utm_medium=m',
			'https://a.example/x?fbclid=123', 'https://a.example:443/x']
		self.assertEqual(set(bm.key(u, R) for u in same), {'a.example/x'})
		self.assertNotEqual(bm.key('https://a.example/X', R), bm.key('https://a.example/x', R))  # a path keeps its case
		self.assertEqual(bm.key('https://a.example/x?b=2&a=1', R), 'a.example/x?a=1&b=2')
		self.assertEqual(bm.key('https://a.example/#/route/one', R), 'a.example#/route/one')  # a one-page site keeps its routes
		self.assertNotEqual(bm.key('https://a.example/#/one', R), bm.key('https://a.example/#/two', R))
		self.assertEqual(bm.key('javascript:alert(1)', R), 'javascript:alert(1)')
		self.assertNotEqual(bm.key('https://a.example/x?ref=1', R), 'a.example/x')  # only the listed parameters go
		self.assertEqual(bm.key('https://a.example/x?ref=1', rules(dupes__tracking=['ref'])), 'a.example/x')


class Duplicates(unittest.TestCase):
	def test_deeper_folder_then_oldest(self):
		c = bm.parse(fixture())
		d = bm.duplicates(c, rules())
		kept = dict((x['removed'], x['kept']) for x in d)
		tomato_loose = by_url(c, 'http://www.soup-pot.example/recipes/tomato?utm_source=news&utm_medium=mail')[0]['id']
		tomato_cooking = by_url(c, 'https://soup-pot.example/recipes/tomato')[0]['id']
		self.assertEqual(kept[tomato_loose], tomato_cooking)
		self.assertEqual(len(d), 3)

	def test_the_bar_copy_stays(self):
		c = bm.parse(fixture())
		removed = set(x['removed'] for x in bm.duplicates(c, rules()))
		self.assertFalse(removed & set(b['id'] for b in by_url(c, 'https://soup-pot.example/recipes/lentil')))
		removed = set(x['removed'] for x in bm.duplicates(c, rules(keep__bar=False)))
		self.assertIn(by_url(c, 'https://soup-pot.example/recipes/lentil')[0]['id'], removed)  # the bar copy is the less deep one

	def test_oldest_when_the_depth_is_the_same(self):
		text = fixture().replace('<DT><A HREF="https://fieldnotes.example/owls" ADD_DATE="1400000009">',
			'<DT><A HREF="https://fieldnotes.example/birds/" ADD_DATE="1200000000">Old birds</A>\n<DT><A HREF="https://fieldnotes.example/owls" ADD_DATE="1400000009">')
		c = bm.parse(text)
		d = [x for x in bm.duplicates(c, rules()) if x['key'] == 'fieldnotes.example/birds'][0]
		self.assertEqual(bm.plain_title(c['bookmarks'][d['kept']]), 'Old birds')


class Similar(unittest.TestCase):
	def setUp(self):
		self.c = bm.parse(fixture())
		self.removed = set(x['removed'] for x in bm.duplicates(self.c, rules()))

	def test_groups_and_variants(self):
		s = bm.similar(self.c, self.removed, rules())
		self.assertEqual([g['host'] for g in s['groups']], ['chess-club.example', 'choir.example'])
		chess = s['groups'][0]
		self.assertEqual([self.c['bookmarks'][i]['url'] for i in chess['ids']],
			['https://chess-club.example', 'https://chess-club.example/events', 'https://chess-club.example/members/account'])
		self.assertEqual(chess['default'], chess['ids'][0])
		self.assertEqual(sorted(f['why'] for f in s['folded']), ['/default.aspx', '/index.html'])

	def test_sites_that_are_never_grouped(self):
		s = bm.similar(self.c, self.removed, rules())
		hosts = [g['host'] for g in s['groups']]
		self.assertNotIn('github.com', hosts)  # similar.skip_hosts
		self.assertNotIn('docs.langref.example', hosts)  # similar.skip_pattern
		self.assertNotIn('railplan.example', hosts)  # two routes of a one-page site are not variants
		s = bm.similar(self.c, self.removed, rules(similar__skip_hosts=[], similar__skip_pattern='^$'))
		self.assertIn('github.com', [g['host'] for g in s['groups']])
		self.assertIn('docs.langref.example', [g['host'] for g in s['groups']])

	def test_too_big(self):
		s = bm.similar(self.c, self.removed, rules(similar__max_group=2))
		self.assertEqual([g['host'] for g in s['groups']], ['choir.example'])
		self.assertEqual(s['too_big'], [{'host': 'chess-club.example', 'size': 3}])

	def test_pages(self):
		groups = [{'n': i} for i in range(1, 6)]
		self.assertEqual(bm.pages(groups, 2), [[1, 2], [3, 4], [5]])


class Choices(unittest.TestCase):
	groups = [{'n': 3, 'ids': [7, 8, 9], 'default': 7}, {'n': 4, 'ids': [1, 2], 'default': 1}]

	def test_answers(self):
		self.assertEqual(bm.choices('', self.groups, True), ({3: 'short', 4: 'short'}, False, []))
		self.assertEqual(bm.choices('3=all, 4=2', self.groups, True), ({3: 'all', 4: 2}, False, []))
		self.assertEqual(bm.choices('rest', self.groups, True), ({3: 'short', 4: 'short'}, True, []))
		self.assertEqual(bm.choices('', self.groups, False), ({3: 'all', 4: 'all'}, True, []))
		for word in ('5=all', '3=4', 'keep'):
			self.assertTrue(bm.choices(word, self.groups, True)[2], word)

	def test_removed_by_choice(self):
		g = self.groups[0]
		self.assertEqual(bm.removed_by_choice(g, 'all'), [])
		self.assertEqual(bm.removed_by_choice(g, 'short'), [8, 9])
		self.assertEqual(bm.removed_by_choice(g, 2), [7, 9])


class Fits(unittest.TestCase):
	def test_loose_misfiled_and_fit(self):
		c = bm.parse(fixture())
		removed = set(x['removed'] for x in bm.duplicates(c, rules()))
		f = bm.fits(c, removed, rules())
		urls = dict((k, set(c['bookmarks'][i]['url'] for i in v)) for k, v in f.items())
		self.assertIn('https://bread-oven.example/sourdough', urls['loose'])
		self.assertEqual(urls['misfiled'], {'https://soup-pot.example/recipes/fish'})  # Cooking has three of that site
		self.assertIn('https://spice-rack.example/cumin', urls['fit'])  # alone in its folder, but no other folder has its site
		self.assertIn('https://mail.example.net/', urls['fit'])  # on the bar
		self.assertIn('https://trailmaps.example/dolomites', urls['fit'])  # shares its site with a sibling
		more = bm.parse(fixture().replace('<DT><A HREF="https://jam-jar.example/plum"', '<DT><A HREF="https://spice-rack.example/mace" ADD_DATE="1">Mace</A>\n<DT><A HREF="https://jam-jar.example/plum"'))
		f2 = bm.fits(more, set(), rules())
		self.assertNotIn(by_url(more, 'https://spice-rack.example/cumin')[0]['id'], f2['misfiled'])  # two loose ones of its site do not count
		f = bm.fits(c, removed, rules(sort__host_elsewhere=4))
		self.assertEqual(f['misfiled'], [])
		f = bm.fits(c, removed, rules(sort__loose_depth=0))
		self.assertEqual(f['loose'], [])


class Render(unittest.TestCase):
	def test_remove_move_and_new_folders(self):
		c = bm.parse(fixture())
		owls = by_url(c, 'https://fieldnotes.example/owls')[0]['id']
		fish = by_url(c, 'https://soup-pot.example/recipes/fish')[0]['id']
		gone = by_url(c, 'https://choir.example/schedule')[0]['id']
		plan = {'removed': [gone], 'moves': {str(owls): 'Other favorites > Nature > Birds', str(fish): 'Other favorites > Cooking'},
			'new_folders': ['Other favorites > Nature', 'Other favorites > Nature > Birds']}
		again = bm.parse(bm.render(c, plan, rules(), now=1700000000))
		self.assertEqual(len(again['bookmarks']), len(c['bookmarks']) - 1)
		self.assertFalse(by_url(again, 'https://choir.example/schedule'))
		self.assertEqual(bm.path_of(again, by_url(again, 'https://fieldnotes.example/owls')[0]['folder']), 'Other favorites > Nature > Birds')
		self.assertEqual(bm.path_of(again, by_url(again, 'https://soup-pot.example/recipes/fish')[0]['folder']), 'Other favorites > Cooking')
		before = set(bm.path_of(c, f['id']) for f in c['folders'])
		after = set(bm.path_of(again, f['id']) for f in again['folders'])
		self.assertEqual(after - before, {'Other favorites > Nature', 'Other favorites > Nature > Birds'})
		self.assertFalse(before - after)
		cafe = by_url(again, 'https://quiet-cafe.example/')[0]
		self.assertEqual((cafe['title'], cafe['dd']), ('Quiet caf&eacute; &amp; bakery', 'A place to read on Sundays'))

	def test_a_name_with_html_characters(self):
		c = bm.parse(fixture())
		owls = by_url(c, 'https://fieldnotes.example/owls')[0]['id']
		again = bm.parse(bm.render(c, {'removed': [], 'moves': {str(owls): 'Rock & <Roll>'}, 'new_folders': ['Rock & <Roll>']}, rules()))
		self.assertEqual(bm.path_of(again, by_url(again, 'https://fieldnotes.example/owls')[0]['folder']), 'Rock & <Roll>')


if __name__ == '__main__':
	unittest.main()
