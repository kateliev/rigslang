"""The gates of band-facts: every decision that code can make.

Pure Python: no files, no network. A gate reads the state of the run and the rules
(R('group.name')), and returns "pass", and for a fail the "problems".
"""
import parse


def article_found(state, R):
	found = state['find']
	ok = bool(found.get('url'))
	if not found.get('answered', True):
		return {'pass': False, 'when': 'the search did not answer', 'problems': ['the search service did not answer: offline, blocked, or slower than http.timeout {}'.format(R('http.timeout'))]}
	return {'pass': ok, 'results': len(found.get('results', [])), 'problems': [] if ok else ['the search found no article (search.results {})'.format(R('search.results'))]}


def summary_ok(state, R):
	ok = bool((state['read'].get('summary') or '').strip())
	return {'pass': ok, 'problems': [] if ok else ['no article with a summary; tried: {}'.format(', '.join(state['read'].get('tried') or [str(state['find'].get('title'))]))]}


def title_matches(state, R):
	'''The search gives a result for any words. An article with another name is not the article of the band.'''
	title = state['read'].get('title') or ''
	ok = parse.same_name(state['band'], title)
	return {'pass': ok, 'title': title, 'problems': [] if ok else ['the article is {!r}, not {!r}'.format(title, state['band'])]}


def albums_found(state, R):
	n = len(state['read'].get('albums') or [])
	return {'pass': n > 0, 'albums': n, 'problems': [] if n else ['the Discography section lists no albums']}


def short_enough(state, R):
	text = state.get('write')
	words = len(text.split()) if isinstance(text, str) else 0
	if words == 0:
		return {'pass': False, 'words': 0, 'problems': ['the paragraph is empty or is not a text']}
	ok = words <= R('answer.max_words')
	return {'pass': ok, 'words': words, 'problems': [] if ok else ['the paragraph has {} words (answer.max_words {})'.format(words, R('answer.max_words'))]}


def rounds_left(state, R):
	rewrites = max(0, state.get('_visits', {}).get('write', 0) - 1)
	ok = rewrites < R('answer.rounds')
	return {'pass': ok, 'rewrites': rewrites, 'problems': [] if ok else ['the paragraph was rewritten {} times (answer.rounds {})'.format(rewrites, R('answer.rounds'))]}
