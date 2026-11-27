"""The two examples together: family-namer makes the placeholder files of a family, and font-names
shortens their names. Played answers, no model: the test checks that the files of one tool are the
input of the other, and that a long plant name makes font-names ask its reason block.

Each example has its own modules "steps" and "gates", so each tool runs in a process of its own.
Run: python3 -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY_NAMER = os.path.join(ROOT, 'examples', 'family-namer')
FONT_NAMES = os.path.join(ROOT, 'examples', 'font-names')

# family-namer: a tree story, the list plants, a fixed draw, the first of three picks.
NAMER = r'''
import json, sys
import tool
out = sys.argv[1]
k = tool.kit(runs=None)
r = k.run({"story": "A calm book face named after a tree"}, rules={"names.seed": 7, "files.out": out})
r = k.answer(r["run"], {"result": {"list": "plants", "why": "the story asks for a tree"}})
r = k.answer(r["run"], {"result": [
    {"name": "Metasequoia glyptostroboides", "why": "the dawn redwood, a calm and old tree"},
    {"name": "Sequoiadendron giganteum", "why": "the giant sequoia"},
    {"name": "Chamaecyparis nootkatensis", "why": "a quiet cypress"}]})
r = k.answer(r["run"], {"pass": True, "why": "all three are trees"})
r = k.answer(r["run"], {"answer": "1"}, who="person")
print(json.dumps(r))
'''

# font-names: HFS, on the folder that family-namer wrote; it must ask the model, then wait for the person.
RENAMER = r'''
import json, sys
import tool
k = tool.kit(runs=None)
r = k.run({"folder": sys.argv[1]}, preset="mac")
seen = {"at": r["at"], "weak": r["waiting"]["sees"]["plan.weak_words"], "help": sorted(r["waiting"]["tool_help"])}
a = k.arena_call(r["run"], "steps.try_names", {"table": {"Metasequoia": "Meta", "Glyptostroboides": "Glyp"}})
seen["fair"] = a["result"]["fair"]
r = k.answer(r["run"], {"result": [{"Metasequoia": "Meta", "Glyptostroboides": "Glyp"}, {"Metasequoia": "Mtsq", "Glyptostroboides": "Gly"}]})
r = k.answer(r["run"], {"pass": True, "why": "the family and the styles can be read"})
seen["waits"] = r["waiting"]["node"]
seen["table"] = r["waiting"]["sees"]["final.table"]
r = k.answer(r["run"], {"pass": True}, who="person")
seen["end"] = r["outcome"]["end"]
seen["arena"] = [x["tool"] for x in r["arena"]]
seen["guessed"] = r["guessed"]
print(json.dumps(seen))
'''


def drive(folder, script, *args):
	p = subprocess.run([sys.executable, '-c', script] + list(args), cwd=folder, capture_output=True, text=True, timeout=120)
	if p.returncode != 0:
		raise AssertionError(p.stderr)
	return json.loads(p.stdout.strip().splitlines()[-1])


class Chain(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.tmp, True)

	def test_family_namer_output_is_font_names_input(self):
		named = drive(FAMILY_NAMER, NAMER, os.path.join(self.tmp, 'out'))
		self.assertEqual(named['outcome']['end'], 'done')
		folder = os.path.join(self.tmp, 'out', 'MetasequoiaGlyptostroboides')
		self.assertEqual(sorted(os.listdir(folder)), ['MetasequoiaGlyptostroboides-Bold.otf', 'MetasequoiaGlyptostroboides-BoldItalic.otf',
			'MetasequoiaGlyptostroboides-Italic.otf', 'MetasequoiaGlyptostroboides-Regular.otf'])

		seen = drive(FONT_NAMES, RENAMER, folder)
		self.assertEqual(seen['at'], 'abbreviate')  # the table of code is not enough: the reason block is asked
		self.assertEqual(seen['weak'], ['Metasequoia', 'Glyptostroboides'])
		self.assertEqual(seen['help'], ['steps.table', 'steps.try_names'])
		self.assertTrue(seen['fair'])
		self.assertEqual(seen['waits'], 'approve')  # a person decides
		self.assertEqual(sorted(t['new'] for t in seen['table']), ['MetaGlyp-Bd.otf', 'MetaGlyp-BdIt.otf', 'MetaGlyp-It.otf', 'MetaGlyp-Rg.otf'])
		self.assertEqual(seen['end'], 'ready')  # permissions.rename is off: nothing is renamed
		self.assertEqual(seen['arena'], ['steps.try_names'])
		self.assertEqual(seen['guessed'], ['readable'])
		self.assertEqual(len(os.listdir(folder)), 4)


if __name__ == '__main__':
	unittest.main()
