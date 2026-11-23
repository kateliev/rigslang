#!/usr/bin/env python3
"""Make a larger synthetic bookmarks export, to try a long sort with a real model.
All names are made up. The file is not a test fixture: write it outside the repository.

    python3 tests/make_big.py OUT.html [LOOSE]      LOOSE: loose bookmarks (default 300)

Same output for the same LOOSE: the choices come from a fixed seed."""
import html
import random
import sys

TOPICS = {
	'Cooking': ['soup-pot', 'bread-oven', 'spice-rack', 'jam-jar', 'noodle-bar'],
	'Travel': ['trailmaps', 'hutbook', 'railplan', 'ferry-times', 'old-towns'],
	'Programming': ['codeyard', 'buildlog', 'shellnotes', 'regex-lab', 'api-zoo'],
	'Programming > Python': ['pylearn', 'snake-tips', 'wheelhouse', 'typed-py', 'async-notes'],
	'Music': ['chord-book', 'drumloop', 'score-shelf', 'tuner-tools', 'vinyl-bin'],
	'Gardening': ['seed-bank', 'compost-hub', 'tomato-patch', 'pruning-guide', 'bee-garden'],
	'Photography': ['lens-notes', 'darkroom', 'light-meter', 'photo-walks', 'film-lab'],
	'Reading': ['book-nook', 'poem-a-day', 'short-stories', 'library-card', 'essay-shelf'],
}
NEW = {'Astronomy': ['star-charts', 'moon-phases', 'telescope-tips'], 'Knitting': ['knitwork', 'yarn-shop', 'stitch-guide']}
WORDS = ['guide', 'basics', 'tips', 'notes', 'list', 'tour', 'starter', 'deep dive', 'checklist', 'ideas', 'questions', 'review']


def main(out, loose=300):
	rnd = random.Random(7)
	n = [1300000000]

	def a(host, path, title):
		n[0] += 1000
		return '<DT><A HREF="https://{}.example/{}" ADD_DATE="{}">{}</A>'.format(host, path, n[0], html.escape(title, quote=False))

	def entry(topic, hosts):
		host = rnd.choice(hosts)
		word = rnd.choice(WORDS)
		leaf = topic.split(' > ')[-1].lower()
		slug = '{}-{}-{}'.format(leaf, word.replace(' ', '-'), rnd.randint(1, 9999))
		return a(host, slug, '{} {} {}'.format(leaf.capitalize(), word, rnd.randint(1, 99)))
	L = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>', '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">', '<TITLE>Bookmarks</TITLE>',
		'<H1>Bookmarks</H1>', '<DL><p>', '<DT><H3 PERSONAL_TOOLBAR_FOLDER="true">Favorites bar</H3>', '<DL><p>', a('mail', '', 'Mail'), '</DL><p>',
		'<DT><H3>Other favorites</H3>', '<DL><p>']
	pool = [(t, h) for t, h in TOPICS.items()] * 9 + list(NEW.items())
	for _ in range(loose):
		L.append(entry(*rnd.choice(pool)))
	open_parts = []
	for topic, hosts in TOPICS.items():
		parts = topic.split(' > ')
		while open_parts and open_parts != parts[:len(open_parts)]:
			L.append('</DL><p>')
			open_parts.pop()
		L += ['<DT><H3>{}</H3>'.format(parts[-1]), '<DL><p>']
		open_parts.append(parts[-1])
		for _ in range(10):
			L.append(entry(topic, hosts))
	L += ['</DL><p>'] * len(open_parts) + ['</DL><p>', '</DL><p>']
	with open(out, 'w', encoding='utf-8') as f:
		f.write('\n'.join(L) + '\n')


if __name__ == '__main__':
	main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 300)
