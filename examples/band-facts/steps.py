"""The steps of band-facts: the only code that touches the world (here: the public API of English Wikipedia).

The steps only read. Nothing is changed anywhere, so no step needs a way back.
With BAND_FACTS_OFFLINE set to a folder, "fetch" reads the pages from that folder:
the tests and the regression set run with no network (tests/fixtures).
"""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote

import parse

AGENT = 'band-facts-example/0.1'
SEARCH = 'https://en.wikipedia.org/w/api.php?format=json&formatversion=2&action=query&list=search&srsearch='
SUMMARY = 'https://en.wikipedia.org/api/rest_v1/page/summary/'
API = 'https://en.wikipedia.org/w/api.php?format=json&formatversion=2&redirects=1&action=parse'


def offline(url):
	'''The page of a URL from the fixture folder: index.json maps a part of the URL to a file.'''
	folder = os.environ['BAND_FACTS_OFFLINE']
	with open(os.path.join(folder, 'index.json'), encoding='utf-8') as f:
		index = json.load(f)
	for part, name in index.items():
		if part in url:
			with open(os.path.join(folder, name), encoding='utf-8') as f:
				return f.read()
	return ''


def fetch(url, R):
	'''The text of a page, or an empty text when the service does not answer with a page.'''
	if os.environ.get('BAND_FACTS_OFFLINE'):
		return offline(url)
	try:
		req = urllib.request.Request(url, headers={'User-Agent': AGENT})
		with urllib.request.urlopen(req, timeout=R('http.timeout')) as res:
			return res.read().decode('utf-8', 'replace')
	except (urllib.error.URLError, OSError):
		return ''  # no page: the gate after the step says so


def find(state, R):
	'''Search English Wikipedia (its public search API) and pick the title of the band.'''
	text = fetch(SEARCH + quote(state['band']) + '&srlimit={}'.format(R('search.results')), R)
	answered = text.strip().startswith('{')
	results = parse.search_titles(json.loads(text), R('search.results')) if answered else []
	title = parse.pick_title(state['band'], results)
	title = title.replace(' ', '_') if title else None
	return {'answered': answered, 'results': results, 'title': title, 'url': 'https://en.wikipedia.org/wiki/' + quote(title) if title else None}


def read(state, R):
	text = fetch(SUMMARY + quote(state['find']['title'], safe=''), R)
	page = json.loads(text) if text.strip().startswith('{') else {}
	if not page.get('extract'):
		return {'title': state['find']['title'], 'url': state['find']['url'], 'description': '', 'summary': '', 'albums': []}
	q = '&page=' + quote(page['title'], safe='')
	sections = (json.loads(fetch(API + '&prop=sections' + q, R) or '{}').get('parse') or {}).get('sections', [])
	found = next((s for s in sections if s.get('line', '').strip().lower() == 'discography'), None)
	wikitext = ''
	if found:
		wikitext = (json.loads(fetch(API + '&prop=wikitext&section={}'.format(found['index']) + q, R) or '{}').get('parse') or {}).get('wikitext', '')
	return {'title': page['title'], 'url': ((page.get('content_urls') or {}).get('desktop') or {}).get('page') or state['find']['url'],
		'description': page.get('description', ''), 'summary': page['extract'], 'albums': parse.album_list(wikitext)}


def compose(state, R):
	article = state['read']
	albums = article['albums'][:R('albums.max')]
	lines = [state['write'].strip(), '']
	if albums:
		lines += ['Albums:'] + ['- {}{}'.format(t, ' ({})'.format(y) if y else '') for t, y in albums]
		if len(article['albums']) > len(albums):
			lines.append('- and {} more'.format(len(article['albums']) - len(albums)))
	else:
		lines.append('The article lists no albums.')
	lines += ['', article['url']]
	return '\n'.join(lines)
