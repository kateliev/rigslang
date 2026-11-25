"""Guards against drift between the texts and the code (docs/handout-docs-review.md, Section 7).
Run: python3 -m unittest discover -s tests

Each check is its own test, so that a fail names the problem."""
import ast
import inspect
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig'))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig', 'kit'))
import rig  # noqa: E402
import rigkit  # noqa: E402

# Records of their time: they may name old words and old files.
RECORDS = re.compile(r'^(docs/history/|docs/handout-|docs/review-|\.claude/)')
COMMANDS_GONE = ('prove', 'probe', 'stamp', 'emit', 'hash')
# A line that says that a word is gone may name it.
SAYS_GONE = re.compile(r'\b(gone|removed|version 0|refuses?|Then:)\b', re.I)


def tracked(suffix):
	out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True).stdout.split()
	return [f for f in out if f.endswith(suffix) and 'node_modules/' not in f and not RECORDS.match(f)]


def docs():
	'''The Markdown files of the review: every text, not the compiled skills of the examples.'''
	return [f for f in tracked('.md') if not re.match(r'^examples/[^/]+/skill/SKILL\.md$', f)]


def read(rel):
	with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
		return f.read()


def cli_commands():
	'''The commands of Kit.cli, read from its code: cmd == 'x' and cmd in ('x', 'y').'''
	src = inspect.getsource(rigkit.Kit.cli)
	out = set(re.findall(r"cmd == '(\w+)'", src))
	for group in re.findall(r"cmd in \(([^)]*)\)", src):
		out |= set(re.findall(r"'(\w+)'", group))
	return out


def doc_commands(path):
	'''The commands that the module docstring of a tool.py names: the word after "tool.py", and each word after a "|".'''
	doc = ast.get_docstring(ast.parse(read(path))) or ''
	out = set()
	for line in doc.splitlines():
		m = re.match(r'\s*python3? tool\.py\s+(.*)$', line)
		if not m:
			continue
		for part in m.group(1).split(' | '):
			word = part.split()[0] if part.split() else ''
			if re.match(r'^[a-z]+$', word):
				out.add(word)
	return out


class Links(unittest.TestCase):
	def test_every_relative_link_resolves(self):
		bad = []
		for f in docs():
			text = re.sub(r'```.*?```', '', read(f), flags=re.S)
			for m in re.finditer(r'\]\(([^)\s]+)\)', text):
				url = m.group(1)
				if re.match(r'^(https?:|mailto:|#)', url):
					continue
				target = os.path.normpath(os.path.join(ROOT, os.path.dirname(f), url.split('#')[0]))
				if not os.path.exists(target):
					bad.append('{} -> {}'.format(f, url))
		self.assertEqual(bad, [], 'links that point to nothing')


class RemovedWords(unittest.TestCase):
	def hits(self):
		'''-> [(file, line number, text)] where a removed word is used as a word of the language.'''
		removed = set(rig.REMOVED)
		out = []
		for f in docs():
			heading, in_rig = '', False
			for n, line in enumerate(read(f).splitlines(), 1):
				if line.startswith('#'):
					heading = line
				if line.startswith('```'):
					in_rig = line.strip() in ('```rig', '```') and not in_rig
					continue
				if 'version 0' in heading or SAYS_GONE.search(line):
					continue
				if in_rig:  # a line of Rig: its head word, a judge gate, a snippet unit
					words = line.split()
					if words and (words[0] in removed or (words[0] == 'gate' and 'judge' in words) or (words[0] == 'unit' and 'snippet' in words)):
						out.append((f, n, line.strip()))
					continue
				for span in re.findall(r'`([^`\n]+)`', line):
					words = span.split()
					if not words:
						continue
					as_line = words[0] in removed and len(words) > 1 and (words[1] == '->' or words[1].startswith('"'))
					a_kind = (words[0] == 'gate' and 'judge' in words) or span in ('judge', 'snippet') or (words[0] == 'unit' and 'snippet' in words)
					a_command = span in COMMANDS_GONE or bool(re.search(r'rig\.py (' + '|'.join(COMMANDS_GONE) + r')\b', span))
					if as_line or a_kind or a_command:
						out.append((f, n, span))
		return out

	def test_no_text_uses_a_word_of_version_0(self):
		self.assertEqual(self.hits(), [], 'a word that version 1 refuses, used as a word of the language')

	def test_no_finish_step_tool_per_step(self):
		'''The worker (work_run) took the place of the finish_<step> tools.'''
		bad = ['{}:{}'.format(f, n) for f in docs() for n, line in enumerate(read(f).splitlines(), 1)
			if re.search(r'finish_(?!step\b)\w+|finish_<', line) and not SAYS_GONE.search(line) and 'took the place' not in line and 'has taken its place' not in line]
		self.assertEqual(bad, [], 'a finish_<step> tool: the worker (work_run) took its place')


class ToolDocstrings(unittest.TestCase):
	def test_a_flow_tool_names_every_command_of_kit_cli(self):
		want = cli_commands()
		self.assertIn('run', want)
		paths = [p for p in tracked('tool.py') if p.startswith('examples/') and p.count('/') == 2] + ['skills/rig/kit/templates/flow/tool.py']
		self.assertTrue(paths)
		for p in paths:
			self.assertEqual(sorted(doc_commands(p)), sorted(want), p)

	def test_a_level_1_tool_names_only_commands_of_kit_cli(self):
		got = doc_commands('skills/rig/kit/templates/tools/tool.py')  # no flow: only "call" works
		self.assertIn('call', got)
		self.assertLessEqual(got, cli_commands())


if __name__ == '__main__':
	unittest.main()
