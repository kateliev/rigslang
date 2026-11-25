"""The gates of bookmarks: every decision that code can make.

Pure Python: no files, no network. A gate reads the state of the run and the rules
(R('group.name')), and returns "pass", and for a fail the "problems".

The loops (the pages of choices, the batches to sort) are "for" blocks of the flow, so no gate
here ends a loop. The answers of the person are read by steps.apply and steps.accept: the code
of the human gates with options.
"""
import bm


def file_ok(state, R):
	r = state['read']
	ok = bool(r.get('ok')) and r.get('bookmarks', 0) > 0
	return {'pass': ok, 'bookmarks': r.get('bookmarks', 0), 'problems': [] if ok else [r.get('problem') or 'the file has no bookmarks']}


def sort_ok(state, R):
	'''Every bookmark of the batch once, no other id, no changed URL or title, a pick that is one of the
	choices of that bookmark, or a known folder or a new folder under a known folder, and not too many
	new folders. The known folders come from prepare["folders"], which the model does not see.'''
	b = state['prepare']
	known = [p for p in b['folders'] if p not in b['new_so_far']]
	problems, new = bm.sort_problems(state.get('sort'), b['bookmarks'], known, b['new_so_far'], R)
	return {'pass': not problems, 'new': new, 'problems': ['batch {}: {}'.format(b['batch'], p) for p in problems]}


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
