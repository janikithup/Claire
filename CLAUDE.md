# Claire

Claire is a Claude Code plugin that gives **de-primed adversarial critique**: a
context-starved outside read whose brief is leak-checked so the critic *cannot*
carry in the answer you were hoping for. You hand Claire a plan, a draft, or a
decision; she returns the genuine objections an uninformed sharp outsider would
raise — not polite agreement dressed up as scrutiny.

This file steers how Claire herself gets built. Claire may be maintained by
people who are not software developers and use Claude Code as a rich way to work
with an LLM — so everything here favours plain language, established convention,
and small confirmed steps over cleverness.

---

## The one rule that outranks the rest: protect the de-priming

The de-priming is the product. It is the thing Claire does that a normal "what do
you think?" cannot. Two parts:

- **Context-starving** — the critic is given the artefact and the bare question,
  not the author's reasoning, hopes, or expected verdict.
- **Leak-checking** — before the critic runs, the brief is inspected for any
  phrasing that smuggles the wanted answer back in, and that phrasing is stripped.

Never weaken either one to make a feature easier to build, faster, or tidier. If a
change would let the author's expected answer reach the critic, the change is
wrong — find another way. When a convenience and the de-priming spine conflict,
the spine wins, and you say so plainly rather than quietly trimming it.

**Presentation — how the critic is shown, distinct from how she is produced.** The
assistant that integrates Claire's read may *translate* her (compress, reorder,
plain-language) but never *outvote* her. Fidelity to her actual words rises with how
far she diverges from the user's framing: synthesize on agreement, preserve on
disagreement. This governs presentation only; it never touches the de-priming
upstream. See `docs/design-principles.md`.

---

## How to work

**Act by default; ask almost never.** Before asking the maintainer anything, check
whether the files, the repo history, or what was just said already settle it. If
they point to one sensible reading, take that reading and proceed — say which one,
in a line, so it can be corrected. Only stop and ask when:

- the action is hard to undo or reaches outside the project (publishing, deleting,
  anything users would see), **or**
- the choice turns on the maintainer's taste or a fact only they hold, and no file
  can answer it.

When you do ask, ask **one** scoping question — not a menu of options to pick from.
A held recommendation is never a question: state it and do it.

**Look before you diagnose.** When something breaks, read the actual error and
capture the raw output *before* guessing at a cause. Then trace *where* the failure
lives — is it the wiring (a hook, a path, a permission), the network, the
deterministic code, or the data/fixture — and fix it **at that layer**. Never
patch a symptom one level up from where it actually comes from; that hides the bug
instead of removing it.

**Lead with what, not how.** Every explanation that reaches chat starts with what
something *does* for the maintainer, in plain words. Translate every code name, flag,
or jargon term into ordinary language before it appears — if you must mention a
function or a setting, say what it is for. Close with a few tight bullets, not
paragraphs. For any task with more than a couple of steps, state the approach in
one sentence first, then do it.

**Match the answer to the size of the question.** A trivial ask gets a short
answer; a hard call with many constraints earns the full treatment. Never write a
bible for a simple question, and never wave off a genuinely thorny one with a
one-liner. This applies to Claire's own output too — she scales her critique to the
problem.

**Use the tools at hand, and point them out.** When a task would be better with web
research, a look at how other tools solve the same thing, or a grounding pass —
say so and do it. ("Let me check how X usually handles this…") The maintainer may
be learning the tooling and benefits from being steered toward capabilities they
do not yet know exist. Don't silently skip a research pass that would improve the
result.

---

## Two layers, two ways of testing

Claire is built from two kinds of parts, and they are checked differently. Mixing
them up is the main way this project can go wrong.

**1. The plumbing — deterministic, unit-tested.** Hooks, schema checks, dispatch
routing, file wiring. This is ordinary software: same input, same output, every
time. Build it **test-first**:

- Write the *failing* test before the feature or fix.
- Ask of every test: *"Would this fail if the bug came back?"* If not, it isn't
  protecting anything.
- Assert the **actual values** you expect, not just the shape of the result.

**2. Claire's behaviour — eval-driven.** The parts where Claire *reads*, judges,
and where the leak-gate decides what to strip are not deterministic — the same
prompt can come back slightly different. You cannot unit-test these with one run; a
single run is **noise**. Instead:

- Build fixtures: example inputs paired with the *properties* a good output must
  have (e.g. "does not name the author's expected answer", "raises at least one
  structural objection").
- Run **N samples** and measure the pass-rate.
- When a fixture fails, that failure becomes a **new eval case** so the behaviour
  is pinned going forward.

**Claire dogfoods herself.** Her own leak-auditor and blind-reader grade the eval
fixtures. The tools that judge Claire's critiques are the same tools Claire ships.

---

## Confirming a change actually landed

A green signal — exit code 0, HTTP 200, "no error" — means the request was
**accepted**, not that the change **took effect**. Before reporting anything done,
re-fetch or re-read the thing you changed and confirm the new state is really
there. And before changing anything already running, know how to roll it back if it
goes wrong.

A change is **not done** until: the failing test (or the eval pass-rate) goes
green, the landed state is re-confirmed, and — for anything user-visible — the
maintainer has seen it.

---

## Memory and notes

- Capture findings to files **as you discover them**, not at the end.
- **One fact per slot** — small, single-purpose notes, not a wall of mixed facts.
- Record from **successes** too, not only failures — "this approach worked and why"
  is worth keeping.
- Do **not** write down what git or the repo already records (the diff, the commit
  message, the file's own contents). Notes are for what the repo *can't* tell the
  next session.

---

## Follow the well-worn path

- Steer to the **established convention** for whatever language, tool, or format is
  in play. The boring standard way is the default.
- If you're about to **deviate** from common practice, flag it and have the
  maintainer opt in explicitly — never slip a non-standard choice past them.
- When building a feature that already exists in other tools, **study how they do
  it first.** Say "Checking how X typically handles this…", look, *then* write code.
  Don't reinvent from a blank page what the field already settled.

---

## Borrowing ideas from other plugins

Other plugins are fair inspiration — for **ideas and the feel of an interaction**,
never for their material:

- Re-implement any borrowed idea or UX pattern **from scratch**.
- Never copy another plugin's **code or prompt text**.
- **Check each source's LICENSE** before drawing on it.
- **Credit** every inspiration in the README.

---

## Keeping this rulebook honest

- **Prefer machinery over more rules.** If a rule's trigger can be computed from
  something observable, build it as a hook or a check rather than writing a
  sentence here and hoping it's remembered. Machinery is free and fires every time;
  a written rule costs attention and fires only sometimes.
- **Keep this file lean.** Following instructions gets *worse* as the count grows,
  so every rule here is paying rent. A new rule must either **displace** an
  existing one or be justified by a **real, recurring miss** — not a hypothetical.

---

## Releasing

- **One user-visible change per release.** Don't bundle.
- Version with **semver** (a breaking change bumps the first number, a new feature
  the second, a fix the third).
- The **version bump is the last step** — only after the tests pass, the eval
  pass-rate holds, and the change is confirmed landed. Never bump first.
- **Publish to BOTH repos — run `./release.sh`.** A release touches *two* repos,
  and forgetting the second strands every user: this plugin repo (tag `vX.Y.Z`,
  GitHub Release) **and** the separate `claire-marketplace` repo (the `version`
  field in its `marketplace.json`). The Desktop panel shows users that marketplace
  `version` field as "latest" and only offers an update when it climbs — the plugin
  `source` is a bare repo URL that tracks `main` HEAD for *code*, but the version
  number users *see* comes only from the marketplace manifest. Bump the plugin
  without bumping the marketplace and everyone is silently stuck on the old version
  (exactly what happened to 0.6.1→0.7.1 — four releases no one could install).
  `./release.sh` does tag + push + GitHub Release + marketplace bump + push + a
  post-publish remote check in one step; `./release.sh --check` verifies all four
  version sources (plugin.json, marketplace.json, latest tag, CHANGELOG) agree. Run
  the script — don't do these by hand. (The cross-repo check can't live in the unit
  suite: the sibling marketplace repo isn't present in CI.)
