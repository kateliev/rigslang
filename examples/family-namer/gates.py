"""The gates of family-namer: every decision that code can make.

Pure Python: no files, no network. A gate reads the state of the run and the rules
(R('group.name')) and returns "pass", and for a fail the "problems". A step that needs the file
system (names, write) returns what it found; the gate decides from the state.
Never write a number here: the numbers live in family-namer.rig.
"""
import re

NONE = 'none'
FAMILY = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')


def list_named(lists, answer):
	'''The name of the list that an answer names (case and outer spaces do not count), else None.'''
	key = str(answer or '').strip().lower()
	return next((d['name'] for d in lists if d['name'].lower() == key), None)


def topic_ok(state, R):
	'''The model named one of the lists, or "none".'''
	answer = (state.get('topic') or {}).get('list')
	known = list_named(state['lists'], answer) is not None or str(answer or '').strip().lower() == NONE
	names = ', '.join(d['name'] for d in state['lists'])
	return {'pass': known, 'list': answer,
		'problems': [] if known else ['{!r} is not a list of the tool; give one of: {}, or {}'.format(answer, names, NONE)]}


def has_list(state, R):
	'''The answer is a list, not "none".'''
	ok = list_named(state['lists'], state['topic']['list']) is not None
	return {'pass': ok, 'problems': [] if ok else ['the model found no list for the story: {}'.format(state['topic'].get('why', ''))]}


def picks_ok(state, R):
	'''Each pick is a drawn name, written as drawn, and no name comes twice.'''
	drawn = set(n['name'] for n in state['sample']['names'])
	problems, seen = [], set()
	for p in state.get('pick') or []:
		if p['name'] not in drawn:
			problems.append('{!r} was not drawn; choose from: {}'.format(p['name'], ', '.join(sorted(drawn))))
		if p['name'].lower() in seen:
			problems.append('{!r} comes twice'.format(p['name']))
		seen.add(p['name'].lower())
	if not state.get('pick'):
		problems.append('no picks')
	return {'pass': not problems, 'problems': problems}


def names_ok(state, R):
	'''Each family name has only ASCII letters and digits, starts with a letter, is not too long,
	and no two family names are the same (file systems compare names without case).'''
	longest = R('family.max_name')
	problems, seen = [], set()
	for f in state['names']['families']:
		fam = f['family']
		if not FAMILY.match(fam):
			problems.append('{!r} ({}): only ASCII letters and digits, and a letter first'.format(fam, f['name']))
		if len(fam) > longest:
			problems.append('{!r}: {} characters, family.max_name is {}'.format(fam, len(fam), longest))
		if fam.lower() in seen:
			problems.append('{!r} comes twice'.format(fam))
		seen.add(fam.lower())
	return {'pass': not problems, 'problems': problems}


def free(state, R):
	'''No folder of the chosen family is in files.out yet (names compared without case).'''
	family = state['choose']['family']
	taken = family.lower() in set(d.lower() for d in state['names']['existing'])
	return {'pass': not taken, 'family': family,
		'problems': ['{} has a folder in {} already'.format(family, state['names']['out'])] if taken else []}


def written(state, R):
	'''Every placeholder file is in the new folder, and nothing else.'''
	want, after = set(state['write']['files']), set(state['write']['after'])
	problems = ['{} is missing'.format(n) for n in sorted(want - after)]
	problems += ['{} should not be there'.format(n) for n in sorted(after - want)]
	return {'pass': not problems, 'files': len(after), 'problems': problems}
