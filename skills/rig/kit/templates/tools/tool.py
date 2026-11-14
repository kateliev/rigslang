#!/usr/bin/env python3
"""__NAME__: one command line for every front (the Claude skill, a plugin, a person).

    python3 tool.py call __NAME__ '{"text": "some words"}'

Each call prints one JSON line: {"ok", "tool", "result"}, or {"refused"}, or {"ok": false, "error"}.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rigkit  # noqa: E402
import tools  # noqa: E402


def kit():
	k = rigkit.Kit({})
	k.tool(os.path.join(HERE, 'gen', '__NAME__.json'), tools.__FN__)
	return k


if __name__ == '__main__':
	sys.exit(kit().cli(sys.argv[1:]))
