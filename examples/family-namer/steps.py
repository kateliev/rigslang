"""The steps of family-namer: the only code that touches the world (here: the name lists and the
output folder).

A step reads the state of the run and the rules, does its work and returns a value; the value goes
to state[<step id>]. The randomness is here too: the draw of names uses a seed (names.seed), and a
run records the seed that it used, so that "--set names.seed=N" gives the same draw again.
The human gate "choose" also has its code here (choice): it reads the words of the person.
"""
import json
import os
import random
import re
import unicodedata

import gates

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_MAX = 2 ** 31 - 1		# a new seed is a positive 31-bit number: short to write, easy to repeat


def path_of(R, rule):
	'''A folder rule, relative to the tool folder (an absolute path stays as it is).'''
	return os.path.join(HERE, R(rule))


def read_lists(R):
	'''Every list in names.lists, in the order of the file names.'''
	folder = path_of(R, 'names.lists')
	out = []
	for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
		if name.endswith('.json'):
			with open(os.path.join(folder, name), encoding='utf-8') as f:
				out.append(json.load(f))
	return out


def lists(state, R):
	'''The lists as the model sees them: name, what the list holds, how many names.'''
	return [{'name': d['name'], 'about': d['about'], 'count': len(d['names'])} for d in read_lists(R)]


def sample(state, R):
	'''Draw names.sample names at random from the chosen list, without repeats.'''
	name = gates.list_named(state['lists'], state['topic']['list'])
	chosen = next(d for d in read_lists(R) if d['name'] == name)
	seed = R('names.seed') or random.SystemRandom().randint(1, SEED_MAX)
	drawn = random.Random(seed).sample(chosen['names'], min(R('names.sample'), len(chosen['names'])))
	return {'list': name, 'seed': seed, 'source': chosen.get('source'), 'names': drawn}


def family_of(name):
	'''A drawn name -> a family name: accents folded, Latin letters and digits only, each word with a
	capital letter, no spaces. "Ajax the Great" -> "AjaxTheGreat".'''
	text = unicodedata.normalize('NFKD', name)
	text = ''.join(c for c in text if ord(c) < 128 and not unicodedata.combining(c))
	return ''.join(w[:1].upper() + w[1:] for w in re.split(r'[^A-Za-z0-9]+', text) if w)


def names(state, R):
	'''The family name of each pick, and the families that are in files.out already.'''
	notes = dict((n['name'], n.get('note', '')) for n in state['sample']['names'])
	out = path_of(R, 'files.out')
	existing = sorted(d for d in os.listdir(out) if os.path.isdir(os.path.join(out, d))) if os.path.isdir(out) else []
	families = [{'number': i + 1, 'family': family_of(p['name']), 'name': p['name'], 'why': p['why'], 'note': notes.get(p['name'], '')}
		for i, p in enumerate(state['pick'])]
	return {'families': families, 'existing': existing, 'out': R('files.out')}


def choice(state, R):
	'''The code of the human gate "choose": the person answers with a number (1, 2, 3), a family
	name or a drawn name. -> the chosen family, or a fail: "not understood", and the gate asks again.'''
	text = str(state['choose']['answer']).strip()
	families = state['names']['families']
	for f in families:
		if text == str(f['number']) or text.lower() in (f['family'].lower(), f['name'].lower()):
			return {'pass': True, 'family': f['family'], 'name': f['name'], 'why': f['why']}
	return {'pass': False, 'problems': ['answer with a number from 1 to {}, or one of the names'.format(len(families))]}


def placeholders(family, R):
	'''The file names of the placeholders: Family-Style.otf, for each style and each format.'''
	return sorted('{}-{}{}'.format(family, style, fmt) for style in R('family.styles') for fmt in R('family.formats'))


def write(state, R):
	'''Make the folder of the chosen family in files.out, with one empty file for each placeholder.
	os.mkdir refuses a folder that exists, also when it came after the gate "free".'''
	family = state['choose']['family']
	out = path_of(R, 'files.out')
	os.makedirs(out, exist_ok=True)
	folder = os.path.join(out, family)
	os.mkdir(folder)
	files = placeholders(family, R)
	for name in files:
		with open(os.path.join(folder, name), 'xb'):
			pass
	return {'folder': folder, 'files': files, 'after': sorted(os.listdir(folder))}


def report(state, R):
	'''The result of the run: the chosen name, its reason, the seed of the draw, and the folder.
	The folder is the input of font-names.'''
	c = state['choose']
	return {'family': c['family'], 'name': c['name'], 'why': c['why'], 'list': state['sample']['list'],
		'seed': state['sample']['seed'], 'folder': state['write']['folder'], 'files': state['write']['files']}
