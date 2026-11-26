#!/usr/bin/env python3
"""bookmarks: one command line for every front (Agent Skill, MCP, HTTP/OpenAPI, plugin, person).

    python3 tool.py run '{"file": "~/Downloads/favorites.html"}'   start a run; code walks the flow as far as it can
    python3 tool.py answer RUN '{"result": [...]}' [--meta JSON]  the model gives the answers of a sort batch
    python3 tool.py arena RUN TOOL [JSON]      call a read-only tool in a waiting reason arena
    python3 tool.py work RUN [--api-url URL] [--model NAME] [--provider openai|ollama|anthropic]  run model/reason jobs
    python3 tool.py approve RUN yes|no [WORDS] a person answers a human gate (or the words of an answer)
    python3 tool.py restore RUN                run the rollback block to restore state
    python3 tool.py artifact RUN NAME [--path KEY]  inspect a saved brief step payload
    python3 tool.py batch ITEMS [--report PATH] [--workers N]  a run for each item of a JSON list (or of a file)
    python3 tool.py next-batch [ITEMS] [--size N] [--report PATH]  run one unattended chunk with rollback on deferral
    python3 tool.py queues                     the runs that wait: for the model, for a person, and pending queue
    python3 tool.py resume RUN | status RUN    walk on after a stop; show a run again
    python3 tool.py drop RUN [REASON] | list [--limit N] | prune [--keep N]   manage runs
    python3 tool.py rerun RUN --from ID [--set group.name=value]   a new run from a line of an old run
    python3 tool.py replay RUN                 the flow again, with the answers recorded in RUN
    python3 tool.py rules | flow               the values of the rules; the nodes of the flow
    python3 tool.py regress tests/regression-set.json [--baseline]
    python3 tool.py eval DATASET [--baseline PATH] [--save-baseline]  score a ground-truth dataset
    python3 tool.py serve-stdio                keep the runner warm over stdin/stdout JSON lines
    python3 tool.py serve-http [--port 8780]   serve Streamable HTTP MCP, OpenAPI 3.1, and approval UI
    python3 tool.py mcp [--api-url URL] [--model NAME]  run as a stdio MCP server

Each call prints one JSON line. A "refused" result is final: do not repeat the call.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402
import steps  # noqa: E402

TMP = os.path.join(HERE, 'tests', '.tmp')  # the work and out folders of the regression cases (their rules name it)


def kit(runs=os.path.join(HERE, 'runs')):
	return rigkit.Kit(os.path.join(HERE, 'gen', 'bookmarks.json'), runs=runs).bind('gates', gates).bind('steps', steps)


def clean_cases():
	'''A test set must be the same before and after a run: take the work of the regression cases out.'''
	shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
	regress = sys.argv[1:2] == ['regress']
	if regress:
		clean_cases()
	code = kit().cli(sys.argv[1:])
	if regress:
		clean_cases()
	sys.exit(code)
