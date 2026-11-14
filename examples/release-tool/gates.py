"""The gates of the release tool: every decision that code can make.

Pure Python: no files, no network. A gate reads the state of the run and the rules
(R('group.name')) and returns "pass", and for a fail the "problems" and, when the
gate has more than one fail line, "when". The numbers live in release.rig, not here.
"""
import re


def notes_of(state):
	'''The notes of the run: the last rewrite, else the notes of the folder.'''
	return state.get('rewrite') or state['collect']['notes']


def notes_ok(state, R):
	words = len(notes_of(state).split())
	ok = words >= R('notes.min_words')
	return {'pass': ok, 'words': words, 'problems': [] if ok else ['the notes have {} words (notes.min_words {})'.format(words, R('notes.min_words'))]}


def version_ok(state, R):
	version = state['collect']['version']
	ok = re.search(R('version.pattern'), version) is not None
	return {'pass': ok, 'version': version, 'problems': [] if ok else ['version {!r} does not match version.pattern {}'.format(version, R('version.pattern'))]}


def tests_green(state, R):
	tests = state['collect']['tests']
	if tests.get('passed') is True:
		return {'pass': True}
	problem = 'the last test run failed' if tests else 'no test result'
	if R('tests.required'):
		return {'pass': False, 'when': 'tests failed and tests are required', 'problems': [problem + ' (tests.required on)']}
	return {'pass': False, 'when': 'tests failed; reported', 'problems': [problem]}


def rounds_left(state, R):
	done = state.get('_visits', {}).get('rewrite', 0)
	ok = done < R('notes.rounds')
	return {'pass': ok, 'rewrites': done, 'problems': [] if ok else ['the notes were rewritten {} times (notes.rounds {})'.format(done, R('notes.rounds'))]}


def may_publish(state, R):
	ok = R('permissions.publish')
	return {'pass': ok, 'problems': [] if ok else ['permissions.publish is off: a dry run']}
