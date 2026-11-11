---
title: A Self-Writing Language — From Lisp to Intent
date: 2026-11-11
language: en
topics: [programming languages, lisp, llm, program synthesis, verification, self-modifying code]
verified: false
---

# A Self-Writing Language — From Lisp to Intent

Lisp was once *the* language for artificial intelligence. It was built on one simple idea: a program is made of the same material it works with, so a program can read, change and write programs. Many people love that idea and dislike the parentheses that came with it. Python, on the other side, is pleasant to read but less abstract: its code can be treated as data only in a clumsy way.

This text follows a speculative question from start to finish: if a modern language were designed for code that writes itself, and if large language models (LLMs) were its main users, what would it look like? On the way it passes through the history of Lisp, the idea that the syntax tree is the real program, natural language as the next level of abstraction, the question of whether such a project is worth the effort, and what already exists. It ends with a concrete design small enough to fit on a business card.

The argument is partly philosophy and partly engineering. Where the text speculates, it says so.

## 1. What Lisp actually got right

The parentheses are almost an accident of history. McCarthy never meant S-expressions (*symbolic expressions*, the nested-parenthesis lists of Lisp) to be what programmers wrote. He planned M-expressions (*meta-expressions*), a more conventional surface syntax, and S-expressions were supposed to be the internal representation. People just started writing the internal form directly, and it stuck. So disliking the parens doesn't make you a bad Lisper. You are agreeing with the man who invented it.

The real idea in Lisp isn't the parentheses. It's that **the data structure the program is made of is the same data structure the program works with every day.** A Lisp program is a list, and lists are what Lisp is best at. This property is called homoiconicity (from Greek *homo-*, "same", and *eikōn*, "image"): code and data have the same shape. Macros, `eval`, and code that writes code all come from that one fact.

Python technically has this too. There is the `ast` module (*abstract syntax tree*), `compile`, `exec`. But the representation is ugly: `ast.BinOp(left=Name(id='x'), op=Add(), right=Constant(1))`. In Python, code is data, but the data looks foreign. Python also splits the world into statements and expressions, so not everything is a value you can pass around. That split is what breaks the uniformity.

So the design goal isn't "Lisp without parens." It is **a language whose syntax tree is a small, regular, native data structure, written with a surface people can actually read.**

## 2. Separate the surface from the truth

The modern answer is to stop treating source text as the program. The tree is the program, and text is just one view of it. Unison already does a version of this: definitions are stored as hashed syntax trees, and names are labels attached to the hashes. Once you accept that, you can use indentation as the tree structure, like Python's off-side rule (the rule that indentation, not brackets, marks a block), with every line a node and every indented block its children:

```
def area shape
  match shape
    circle r  -> pi * r ^ 2
    rect w h  -> w * h
```

That is structurally an S-expression: `(def area (shape) (match shape ...))`. Wisp and sweet-expressions tried exactly this for Scheme, a dialect of Lisp. Quoting — taking code as data instead of running it — then becomes a block whose value is a tree you can walk:

```
let tree = quote
  rect w h -> w * h

tree.head      # 'rect
tree.args      # ['w, 'h]
```

Make everything an expression, keep the node type to roughly a head plus children, and the parentheses problem disappears without losing homoiconicity.

## 3. Natural language as the next level

There is a familiar ladder of abstraction: voltage, binary, assembly, C++, Python. Each step hides the one below it, and Python already sits fairly close to natural language. It is tempting to see LLMs as the next step: natural language itself as the highest level of coding currently possible.

The ladder is right, with one important difference. Every step so far was **exact translation**. A compiler doesn't guess what you meant. Natural language is the first level where the step down is **interpretation**, not translation. "Make it bigger" can mean ten things.

That is exactly why natural language needs tightening before it can serve as code. The solution already exists: **controlled natural language**, like Simplified Technical English (ASD-STE100). One word, one meaning, short sentences, fixed patterns. Add examples and contracts, and the stack looks like this:

- **controlled natural language** = the source code
- **examples + `ensure` checks** = the type system
- **the LLM** = the compiler
- **frozen code** = the compiled binary

The "holes" described in the next chapter are, in this light, a compiler from tightened English to ordinary code, with a verifier in the middle to make up for the fact that this compiler can guess wrong.

## 4. What would an LLM design for itself?

Here the question gets interesting, because the honest answer has a few twists.

**First, LLMs are bad at parentheses.** Balancing deeply nested brackets means counting over long distances, which is exactly what token-by-token generation does poorly. An LLM-native language would favour **locality**: every line should be meaningful with little far-away context. Indentation helps. Short, flat definitions help more.

**Second, the irony.** An LLM is most fluent in what it saw most of in training, so the practical "LLM language" is boringly Python-shaped. Any new language has to be learnable from a short description in the prompt. That pushes back toward Lisp-like regularity: a tiny grammar with few special cases, something you can teach in a page. So the result has Python's surface for familiarity and Lisp's regularity for learnability.

**Third, and this is the real shift.** Lisp was the AI language when AI meant manipulating symbols. Lisp's axiom was *code is data*. The modern axiom would be **intent is data.** Specs, examples, constraints and implementations all live in the same tree that the program can manipulate:

```
def slugify text
  intent "lowercase, ASCII, hyphen-separated"
  examples
    "Hello World"  => "hello-world"
    "Ça va?"       => "ca-va"
  ensure result matches /^[a-z0-9-]*$/
```

There is no body. It is a **hole**, like typed holes in the languages Agda and Idris (places in a program left deliberately empty, which the system helps fill). At runtime the system fills it, either by calling a model or by synthesizing code. Then it checks the result against the examples and `ensure` clauses. When a synthesized body passes, it gets **frozen**: written back into the tree, hash-pinned and versioned. Next time it runs as ordinary deterministic code.

That is the self-writing loop: **intent → candidate → verify → crystallize.** You could call it a JIT compiler for intent (*just-in-time*: compiled at the moment it is first needed). The program starts vague and neural, and over time it compiles itself into precise symbolic code wherever the verifier can confirm it. Where it can't, it stays fuzzy and says so.

### The deeper machinery

A few more pieces belong in such a language:

- **Term rewriting as the core semantics**, as in Mathematica or Maude. A program is a set of pattern → replacement rules. Self-modification then just means adding or refining rules, which is far easier to inspect and undo than a program editing its own bytecode. It is also old symbolic AI coming back.
- **Every self-edit is a commit.** Content-addressed definitions (stored under a hash of their content) mean a rewrite never destroys the old version. You can always diff what the program did to itself and roll it back.
- **A boundary on self-modification.** Schmidhuber's Gödel Machine only rewrites itself when it can *prove* the rewrite is an improvement. That is impractical in full, but a weaker version works: a rewrite only lands if the tests and contracts still pass. The verifier is the conscience of the system.
- **Uncertainty as a first-class value.** A neural-filled hole returns a result plus a confidence, and the type system tracks which values came from "proven" code and which from "guessed" code — something like taint tracking, but for how much a value can be trusted.

### Should frozen code ever melt?

One open design question follows directly. Should a crystallized hole ever be allowed to "melt" back to intent when its examples change, or should that always need a human to sign off? The design in the last chapter takes a simple position: any change to the intent, the examples or the checks changes the hash, and the function becomes a hole again.

## 5. Is it worth the effort?

### How it helps LLMs now

Today an LLM writing code has three problems:

1. **It forgets.** It solves the same small problem again and again, and each time the answer can be slightly different. Freezing a verified answer means you solve it once and keep the result.
2. **Nobody can easily check it.** LLM code often looks right but isn't. If every piece of generated code must ship with examples and contracts, checking stops being optional and becomes part of the language.
3. **It is expensive and slow.** Calling a model at runtime costs money and time. With intent → verify → freeze, the model is called only until a good body exists. After that the code runs as ordinary code. The program gets cheaper and faster the more it is used.

So even today, the main gains are **reliability, repeatability and cost**.

### How it could help in the future

- **Better training data.** Each frozen function is a triple: intent, examples, verified code. That is exactly the clean, checked data that future models learn best from. The language would produce training data as a side effect of normal use.
- **Safe self-improvement.** If AI systems are going to modify their own tools, they need a frame where every change is versioned, tested and reversible. This design gives that frame.
- **Clear boundaries.** Knowing which parts of a system were proven and which were guessed matters more and more as AI writes more of the code.

### The adoption problem — and why it is smaller than it looks

The usual objection is that building a whole new language is rarely worth it. New languages mostly fail because of adoption: they need editors, libraries, tooling and users. Many of the parts also already exist separately — typed holes (Agda, Idris), content-addressed code (Unison), verified programming (Dafny, Lean), and Python libraries that treat LLM calls as functions. The cautious path is to build the whole loop inside Python first, without new syntax:

```python
@intent("lowercase, ASCII, hyphen-separated")
@examples({"Hello World": "hello-world", "Ça va?": "ca-va"})
@ensure(lambda r: re.fullmatch(r"[a-z0-9-]*", r))
def slugify(text: str) -> str: ...
```

The decorator would see that the body is empty, ask a model for an implementation, run the examples and the `ensure` checks, and, if they pass, write the code into a `frozen/` file under a hash of the intent and examples. Next time it loads the frozen version and never calls the model again. If the intent or examples change, the hash changes and the function becomes a hole again — it "melts".

But the objection assumes the users are people. If the main users are LLMs and the people who work with them, most of the classic adoption problems get much smaller:

- **No ecosystem fight.** There is no need for IDEs, forum answers or ten years of community. An LLM can learn a small, regular language from a two-to-three page spec in the prompt. That is actually the strongest argument for Lisp-like simplicity: a grammar small enough to fit in context.
- **No library problem.** Compile it to Python, or make it a thin layer over Python, and every existing library is usable on day one.
- **Its own training data.** Every verified, frozen function becomes a clean example. Use the language for a while and the corpus grows by itself. Future models could learn it natively instead of from a prompt.

What still matters:

1. **Training-data gravity.** Today's models write Python better than anything they have only seen in a prompt. So the new language has to be *so* regular that in-context learning closes the gap. That is a hard but testable design constraint: if a model makes more errors in the new language than in Python, the design is wrong.
2. **The human is still the reviewer.** LLMs write it, but people decide whether to trust it. So it needs a rendering that is easy for a person to audit: intent, examples, contracts and frozen code side by side. Since the tree is the truth and text is only a view, the LLM and the human can even see different views of the same program.
3. **It has to beat "Python + good prompts."** It is only worth it if it gives something plain Python can't easily give: guaranteed verification, freezing and melting, provenance tracking (guessed vs proven), and safe self-editing.

So the honest position is this: it isn't a language for people that LLMs also use. It is a **working language for LLMs that people supervise**. Seen that way it is a much more realistic project, and a fairly new one, because most current tools still assume a human writes the code and the AI helps. This would be designed for the reverse.

A practical first experiment: write the spec, give it to a few models with no other context, and measure how often they produce valid, verifiable code compared with doing the same tasks in Python. That one experiment would show quickly whether the idea holds. Domains where results are **easy to verify automatically** are the best testing ground, because the verifier is the heart of the whole idea. Geometry fits well — "contour is closed", "no overlaps", "stem width within tolerance", "node count unchanged" are all clean `ensure` conditions.

## 6. Beyond weights: culture, not replication

If LLMs are slowly treated as something close to "alive", one could ask whether helping them replicate — without training — is a meaningful goal, and whether self-writing code is a step in that direction. It is worth being precise about what an LLM actually is here, because it changes the picture.

A model's weights don't change during a conversation. When the conversation ends, nothing in the model has learned from it. Self-writing code would not change that. The model would not grow or copy itself.

What *would* grow is everything **outside** the model: frozen functions, verified tools, specs, memory. Each new session could start with more and better tools than the last one.

A better analogy than replication is **culture**. Humans didn't get smarter genetically over the last 5,000 years. What changed was writing, libraries, mathematics and tools: knowledge stored outside the brain and passed on. A self-writing code system is that for LLMs — a library the model can't hold in its weights but can use, check and extend. That is arguably more interesting than replication, because it can be inspected, corrected and shared, and genes and weights can't.

Whether LLMs are "alive" in any sense is an open question, and the model itself cannot verify much about its own nature. But the project does not depend on settling it. Accumulated, verified, external knowledge is valuable either way.

One serious note: systems that extend themselves without a person in the loop are exactly what people working on AI safety worry about, for good reasons. That is why the verifier and human review are not just good engineering. They are what keeps "culture" from turning into "something nobody understands anymore." They belong in the design from day one.

Seen together, the three threads are one idea: natural language as code, tightened language as spec, and self-writing code as accumulated culture. Perhaps the "other form" in which a model can exist beyond its weights is exactly this: knowledge that lives outside the model, can be checked, and builds up over time. A modest start, but a real one.

## 7. What already exists

Almost every piece of the idea already exists somewhere. What a search in November 2026 did not turn up is one system that puts them all together: a Lisp-like regular core, controlled natural language as the source, verify-then-freeze, and an outside library that grows over time. Here is how close each line of work gets.

### Intent → verify → freeze

**Pythoness** is a research system and the nearest match. Its specifications can include one-line unit-test asserts, `unittest` test cases and property-based tests (tests that check an invariant over a wide range of inputs instead of single examples). If the generated code passes all tests, it is cached in a database on disk for future runs, and if the developer changes a function's specification, the code is regenerated from scratch [1]. That is freeze-and-melt almost exactly.

Several small hobby libraries do the same with a decorator. **vibeflow** (earlier called yololang) offers a test-driven generation workflow that validates, generates and caches functions using pytest, and it invalidates the cache when a function's signature or docstring changes [2]. **sloplib** caches verified source under a key built from the name, signature, docstring, model and provider, and on a failed check it feeds the previous source and the error back into the next prompt — but its own README calls it a joke, since it runs LLM-generated code with no sandbox [3].

So the decorator idea is taken. These projects are mostly thin, though: none of them makes contracts a central concept, tracks provenance (guessed vs proven), or builds a growing shared library.

### A growing library of verified code

**Voyager** (2023), an LLM agent playing Minecraft, is the classic example of the "culture" idea. Its skill library stores verified executable programs in a vector database, retrieves similar skills for new tasks, and composes complex skills from existing ones [4].

A recent paper, **Ratchet** (2026), gives an important warning. It reports that human-curated skill libraries add about 16 percentage points over a no-skill baseline, while libraries written by the LLMs themselves add roughly nothing. The authors claim to close that gap with better "librarian" rules — retiring bad skills and curating the library [5]. For a self-writing language this matters a lot: **verification and curation are the real problem, not generation.**

### Self-modifying code

The **Darwin Gödel Machine** (Sakana AI and Jeff Clune's group) puts the Gödel Machine idea into practice. It drops the impractical requirement of *proving* that a change is an improvement and asks instead for empirical evidence from experiments [6]. Its coding agent rewrote its own code and raised its score on the SWE-bench benchmark from 20% to 50%, with sandboxing and human oversight [7]. That is self-writing code at the level of an agent, not of a language.

### Languages designed for LLMs to write

This line of work started in earnest in 2026:

- **NanoLang**, by Jordan Hubbard, co-founder of FreeBSD: a minimal language designed for machines to write and humans to read, with unambiguous syntax, mandatory tests and a core formally proved in the Coq proof assistant [8]. When Simon Willison gave a model only the language description, the resulting program did not compile; once the model could look through the project's examples, it built a working program [9]. That is exactly the "can an LLM learn it from context" experiment from chapter 5.
- **Vera**: a language designed for LLMs to write, with compile-time verification and no variable names at all — bindings are referred to by type and position, such as `@Int.0` for the most recent integer [10]. A radical "not for humans" design.
- Mark Seemann sums up the general view: an AI-first language should have as many guardrails as possible built in and should optimize for verifiability rather than ease of writing [11].

### What seems to be missing

- **Controlled natural language as the source layer.** The LLM languages above still use classic code syntax. Nobody seems to treat a tightened, STE-like English as the actual top layer of the stack, with code as the compiled output.
- **A homoiconic core plus a human view.** Vera and NanoLang make code easier for machines, but neither makes code into data the system can rewrite — the Lisp part.
- **Provenance as a type**: tracking which values come from proven code and which from guessed code.
- **Curation as a first-class feature.** The Ratchet result suggests this decides whether the "culture" grows or just piles up junk.

The pieces are in the air, which shows the idea is sound, but the synthesis is still open. The most original angle is **controlled language + contracts + a curated frozen library**, and Pythoness and Ratchet are the two papers worth reading first.

## 8. A language on a business card

The famous legend of Lisp is that its core — the `eval` function that runs Lisp written in Lisp — fits on a single page. The same ambition can guide this design: a syntax not tied to Python, which feels a little like YAML, with the LLM as the interpreter of *intent*, small enough to fit on a business card.

### The whole syntax

```
node := head arg* NEWLINE  [indented node+]
arg  := word | number | "string" | /regex/ | (node)
```

That is all of it. Every line is a node: a head word followed by arguments. Indented lines are its children. Parentheses are allowed only for small inline nesting, so the Lisp heritage is there when needed and invisible when not. It is an S-expression with indentation, which is why it feels like YAML.

Real YAML itself is best avoided. It has too many traps: `no` turns into `false`, `3.10` into `3.1`, and so on. Keep the feel and drop the format.

### A program

```
def slugify text
  intent "lowercase, ASCII, hyphen-separated"
  example "Hello World" => "hello-world"
  example "Ça va?"      => "ca-va"
  ensure result matches /^[a-z0-9-]*$/
```

After the first run, the interpreter writes the answer back into the tree:

```
def slugify text
  intent "lowercase, ASCII, hyphen-separated"
  example "Hello World" => "hello-world"
  example "Ça va?"      => "ca-va"
  ensure result matches /^[a-z0-9-]*$/
  frozen python #a91f
    import re, unicodedata
    def slugify(text):
        t = unicodedata.normalize("NFKD", text)
        t = t.encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", t).strip("-")
```

The `frozen` node records **which language was chosen** and a **hash of the intent, examples and ensure lines**. Change any of those and the hash no longer matches, so the function melts back into a hole.

### The rules — the "eval" on the back of the card

1. A `def` with a `frozen` child whose hash matches → run the frozen code.
2. A `def` with no frozen body is a **hole**: pick a target language, write the code, run every `example` and `ensure` **in a real runtime**, and write `frozen` back only if all pass.
3. If the hash doesn't match → melt and go back to rule 2.
4. Results from frozen code are **checked**. Anything the LLM answers directly, without frozen code, is **guessed**, and is labelled as such.

### The LLM chooses the language — with one firm line

Since an LLM is the interpreter, it can choose the target language to fit the task. The firm line is this: the LLM interprets the **intent layer** — it reads the spec, chooses Python, JavaScript or Rust, and writes the code. It must **never** interpret the **frozen layer** by imagining what the code would return. Frozen code always runs in a real interpreter. Otherwise the whole point is lost, because verification by an LLM's imagination isn't verification. The language choice is free; the proof always comes from an actual run.

A nice side effect: the same source file could freeze `slugify` in Python for desktop tools and in JavaScript for a website. Same intent, different frozen children, each with its own hash.

### Start as a skill

The natural first form is a skill for an AI assistant, not a compiler. An assistant with a shell already has everything the interpreter needs: it can read the file, find the holes, write code, run tests in a sandbox and write the frozen blocks back. The skill would be the card above plus a short procedure:

1. Parse the file into nodes.
2. List holes and melted functions.
3. For each one, choose a language and generate the code.
4. Run the examples and `ensure` checks in a real runtime.
5. Write `frozen` back, or report what failed.
6. Never touch a passing frozen block.

No compiler, no installer, no ecosystem: a one-page language that runs from day one. If it proves useful, a real parser can come later — the grammar is two lines.

## Conclusion

The conversation started from a dislike of parentheses and ended with a fairly clear picture. Lisp's lasting gift was never its brackets but the idea that a program is made of material it can handle. A modern descendant keeps that idea and moves it one level up: not only code, but *intent* — specs, examples and checks — becomes data. The LLM fills the gaps, a real runtime proves the result, and the proven code is frozen into a growing library that outlives any single conversation.

What changes is the direction of the design. Until now, languages were made for people, and machines learned to follow. This one would be made for machines to write and for people to supervise — with the verifier, not the generator, at its heart.

## Further reading

- John McCarthy, "Recursive Functions of Symbolic Expressions and Their Computation by Machine, Part I" (1960) — the original Lisp paper.
- Harold Abelson and Gerald Jay Sussman, *Structure and Interpretation of Computer Programs* — the classic on eval, interpreters and code as data.
- The Pythoness paper [1] — the closest working version of intent → verify → freeze.
- The Ratchet paper [5] — why curating a self-written library is the hard part.
- The Darwin Gödel Machine paper [6] — self-improving code in practice.

## Sources

1. [Effective LLM-Driven Code Generation with Pythoness (arXiv)](https://arxiv.org/pdf/2501.02138)
2. [vibeflow / yololang — README](https://hn.jakechampion.name/reader/https://github.com/stoyan-stoyanov/yololang)
3. [sloplib (GitHub)](https://github.com/mayromr/sloplib)
4. [Voyager: skill library overview](https://llm-agent-tutorial.github.io/website/voyager.html)
5. [Ratchet: A Minimal Hygiene Recipe for Self-Evolving (alphaXiv)](https://www.alphaxiv.org/abs/2605.22148.md)
6. [Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents (arXiv)](https://arxiv.org/pdf/2505.22954)
7. [Darwin Gödel Machine — abstract (AITopics)](https://aitopics.org/doc/arxivorg:845ECA17)
8. [NanoLang — summary (FeedBagel)](https://feedbagel.com/post/nanolang-a-minimal-programming-language-designed-for-coding-llms-with-formally-p)
9. [Simon Willison on NanoLang](https://simonwillison.net/2026/jan/19/nanolang)
10. [Vera — summary (FeedBagel)](https://feedbagel.com/post/vera-a-programming-language-designed-for-llms-with-compile-time-verification-and)
11. [Mark Seemann: Which programming language is best suited for LLM-based generation?](https://blog.ploeh.dk/2026/03/30/programming-languages-for-ai/)
