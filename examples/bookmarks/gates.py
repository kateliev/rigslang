"""The gates of bookmarks: every decision that code can make.

Pure Python: no files, no network. A gate reads the state of the run and the rules
(R('group.name')), and returns "pass", and for a fail the "problems".

A gate that only ends a loop (no page is left, no batch is left) returns "route": true with its
fail. That fail is a turn of the flow, not a problem, so the runner does not add it to the problems.
"""
import bm


def file_ok(state, R):
	r = state['read']
	ok = bool(r.get('ok')) and r.get('bookmarks', 0) > 0
	return {'pass': ok, 'bookmarks': r.get('bookmarks', 0), 'problems': [] if ok else [r.get('problem') or 'the file has no bookmarks']}


def page_left(state, R):
	p = state['page']
	if p.get('page') is None:
		return {'pass': False, 'route': True, 'when': 'every page is decided', 'pages': p.get('of', 0)}
	return {'pass': True, 'page': p['page'], 'of': p['of']}


def choice_ok(state, R):
	a = state['apply']
	return {'pass': bool(a.get('ok')), 'problems': list(a.get('problems') or [])}


def batch_left(state, R):
	b = state['batch']
	if b.get('batch') is None:
		return {'pass': False, 'route': True, 'when': 'every batch is sorted', 'batches': b.get('of', 0)}
	return {'pass': True, 'batch': b['batch'], 'of': b['of']}


def sort_ok(state, R):
	'''Every bookmark of the batch once, no other id, no changed URL or title, only known folders or
	new folders under a known folder, and not too many new folders.'''
	b = state['batch']
	known = [p for p in b['folders'] if p not in b['new_so_far']]
	problems, new = bm.sort_problems(state.get('sort'), b['bookmarks'], known, b['new_so_far'], R)
	return {'pass': not problems, 'new': new, 'problems': ['batch {}: {}'.format(b['batch'], p) for p in problems]}


def rounds_left(state, R):
	'''The answers of the model for this batch so far, against sort.rounds retries.'''
	tries = state.get('_visits', {}).get('sort', 0) - state['batch'].get('sort_visits', 0)
	retries = max(0, tries - 1)
	ok = retries < R('sort.rounds')
	return {'pass': ok, 'retries': retries, 'problems': [] if ok else ['batch {}: no good answer after {} retries (sort.rounds {}); it stays unsorted'.format(state['batch']['batch'], retries, R('sort.rounds'))]}


def any_new(state, R):
	n = len(state['folders'].get('new') or [])
	if not n:
		return {'pass': False, 'route': True, 'when': 'no new folder is proposed'}
	return {'pass': True, 'new': n}


def accept_ok(state, R):
	a = state['accept']
	return {'pass': bool(a.get('ok')), 'problems': list(a.get('problems') or [])}


def share_ok(state, R):
	'''A plan that removes a large share of the bookmarks points at a bug or a wrong rule.'''
	r = state['report']
	ok = r['removed_share'] <= R('safety.max_removed')
	return {'pass': ok, 'share': r['removed_share'], 'problems': [] if ok else ['the plan removes {}% of the bookmarks (safety.max_removed {}%)'.format(r['removed_share'], R('safety.max_removed'))]}


def verify(state, R):
	'''The new file has every bookmark that stays, with the same title and URL, every folder of the export
	with the same name, every new folder, and every moved bookmark in its new folder.'''
	b = state['build']
	problems = []
	if not b['same_bookmarks']:
		problems.append('the new file has {} bookmarks, {} expected; missing: {}; extra: {}'.format(b['bookmarks_found'], b['bookmarks_expected'], b['missing'], b['extra']))
	if b['folders_missing']:
		problems.append('folders missing in the new file: {}'.format(', '.join(b['folders_missing'])))
	if b['moves_astray']:
		problems.append('moved bookmarks not in their new folder: ids {}'.format(b['moves_astray']))
	return {'pass': not problems, 'problems': problems}


def may_place(state, R):
	'''The output file is new, or the person allowed to write over it.'''
	b = state['build']
	ok = not b['target_exists'] or bool(R('permissions.overwrite'))
	return {'pass': ok, 'target': b['target'], 'problems': [] if ok else ['{} exists (permissions.overwrite off): move it away, or allow it for this run'.format(b['target'])]}
