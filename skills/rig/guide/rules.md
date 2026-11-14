# Rules that have no exception

For every agent that builds or changes a Rig tool. Read this page before each piece of work.

## The source

1. **Change the source, then build.** Never edit a compiled file (`gen/`, `skill/SKILL.md`, a tool definition, the tool's copy of `rigkit.py`).
2. **Never put a number in code or in text.** A limit, a switch or a name is a rule in the `.rig` file. Code reads it with `R('group.name')`; text names it as `{group.name}`.
3. **Never put a decision in a front.** A decision that code can make is a function in `gates.py`. The skill and the plugin read the verdict.
4. **Every gate in code gets a test** that names its function, with the rule defaults and with one changed rule.
5. **Do not set or change a limit from one item.** Write in the `note` of the rule where the value comes from. When a test set disagrees with a value, stop and report: the person decides.

## The run

6. **Never decide a hard or soft gate yourself.** Read `pass`, `problems` and the next node from the result.
7. **Never answer a human gate.** Ask the person, wait, and pass their answer on.
8. **A refused call is final.** Do not repeat it. Read where the run is, and go on from there.
9. **Use only values from a result or from the rules.** Do not invent a name, an id or a number.
10. **Label a guess.** A gate that you decided is named in the `Guessed:` line of your answer.

## The work

11. **Work on a copy** unless the person named the real thing for this batch.
12. **A change that is hard to undo needs the person's word** for this batch: save, send, publish, delete, commit.
13. **The judgment of a look belongs to the person.** Say "the check passes". Do not say "it looks good".
14. **Report failures first, with the reason.** Say what you did not check.
15. **Stop and report** when: a regression case changes its result and the task did not expect that; a step runs into a time limit; an error has no clear cause after one look at the code; the task needs a decision that nobody gave.

## After every change

16. All of these must pass:

```bash
python3 RIG doctor DIR
```

```bash
python3 RIG test DIR
```

```bash
python3 tool.py regress tests/regression-set.json
```

Plus the type check or the build of each front that has one.

17. **Write down what you learned**, in the file where the next agent will look: a decision of the person in `notes/project-facts.md`, a failed method in `notes/failures-log.md`, a code bug in `bugs-and-fixes.md`.
18. Write notes, comments and reports in simple English: short sentences, and one meaning for one word.
