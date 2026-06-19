# Claire Roadmap

Where Claire goes next, and the discipline for getting there. This is a
direction document, not a commitment schedule — items land one user-visible
change at a time, each gated by tests and eval pass-rate, in the order the
work actually justifies.

---

## Borrowing policy (read this before drawing on anything below)

Claire came out of the adversarial-plugin ecosystem and keeps borrowing from it.
The rule for doing that is fixed and non-negotiable:

- **Ideas and UX patterns are free to RE-IMPLEMENT from scratch.** The *shape* of
  an interaction — "let the user narrow a critique to one dimension", "give a
  binary verdict instead of a fuzzy score" — is fair inspiration. Build it fresh,
  in Claire's own structure, in Claire's own words.
- **Never transplant code or prompt text.** Not a workflow file, not a system
  prompt, not a verdict template, not a fixture. If it was authored by another
  plugin, it does not get pasted, lightly edited, or "adapted" into Claire. It
  gets rebuilt from the idea.
- **Check each source's LICENSE before drawing on it.** Even an idea-level borrow
  gets the licence read first, per source, before any work starts. A permissive
  licence does not change the "re-implement, never transplant" rule — it only
  governs whether the idea is safe to draw on at all.
- **Credit every inspiration in the README.** anvil and devils-advocate are
  already credited there as direct inspirations; any new source named below joins
  that list the moment its idea informs a shipped feature.

This policy is the standing rule in Claire's `CLAUDE.md` ("Borrowing ideas from
other plugins"). It is restated at the top of the roadmap because the roadmap is
*where the borrowing gets planned*, and the temptation to shortcut from idea to
transplant is highest exactly here.

A note on what's below: each item names the source idea, what re-implementing it
in Claire's de-primed style actually looks like, and — most importantly — how it
interacts with the **de-priming spine** (context-starving + leak-checking). That
last column is the gate. An idea that is good in another plugin but cannot be
built without leaking the author's expected answer to the critic **does not ship
in Claire**, however popular it is elsewhere. The spine outranks the feature.

---

## Good ideas to bring in

### From anvil (a structured-debate plugin)

#### 1. Framework-templated outputs

**The idea (anvil).** Instead of returning critique as free-form prose, the
critic pours its findings into a recognised decision-artefact: a pre-mortem, a
risk register, an architecture decision record (ADR). The framework gives the
output a shape practitioners already read fluently.

**Re-implementing it in Claire, de-primed.** Claire grows an optional output
*form* on top of `/claire:challenge`: the same de-primed critic runs, but its
findings are rendered as a pre-mortem ("assume this failed — here is the most
likely autopsy"), a risk register (each objection as a row: risk · likelihood ·
what it costs · what would de-risk it), or a lightweight ADR ("decision · the
forces against it · what you'd be accepting if you proceed"). The form is chosen
*after* the critique is generated, never before — the critic does not know which
template its output will land in, so the framework never shapes what it looks
for.

**Interaction with the de-priming spine.** Clean, *as long as the template is
applied downstream of the critic, not handed to it as a brief.* The hazard: a
pre-mortem template can itself leak — "assume the plan failed, explain why" is a
loaded frame that presumes failure, which is fine for an adversary but a problem
if the author's *expected* failure mode is baked into the template wording. So
the templates ship as **post-hoc renderers** of an already-de-primed critique,
and the leak-gate still inspects the brief before the critic runs. The framework
formats the disagreement; it never sources it.

#### 2. Focus-lens narrowing

**The idea (anvil).** Let the user constrain a critique to a single dimension —
"only attack this on legal grounds", "just the implementation risk", "ignore the
economics, is the *argument* valid". A narrowed lens gets sharper findings on
that axis than a flattened all-at-once pass.

**Re-implementing it in Claire, de-primed.** Claire already has the machinery for
this: `adversarial-review` accepts `attack_dimensions` and runs one attacker per
named axis. The roadmap item is to surface that at the *command* level — let
`/claire:challenge` take a focus lens ("challenge this, legal only") and route it
to a single-dimension attacker, then show the user that the critique was scoped
and to what. The narrowing is the user's explicit choice, stated back to them.

**Interaction with the de-priming spine.** This is the *delicate* one, and worth
flagging plainly. A focus lens is a narrowing the author chooses — and the thing
the author chooses to exclude is itself a tell. "Only attack the implementation,
the strategy is settled" hands the critic the author's confidence about the
strategy, which is exactly the kind of leak the gate exists to catch. So the
focus lens is **leak-checked like any other brief**: the gate flags when a lens
smuggles in a settled-question assumption ("the strategy is fine" is not a
neutral scope, it's an anchor), and either strips the editorialising or surfaces
it to the user before dispatch. A lens that says *which dimension* is fine; a
lens that says *which dimensions are already won* is a leak. The spine decides
where that line sits, per request.

#### 3. Persona presets

**The idea (anvil).** Ship named critic personas — the skeptical investor, the
hostile reviewer 2, the regulator, the ops engineer who has to run this at 3am.
Each persona is a bundle of priorities and a voice, so the user can summon a
*kind* of adversary without describing one from scratch.

**Re-implementing it in Claire, de-primed.** Claire's `/claire:challenge` already
routes to an actor role-play among its critic types. The preset version makes a
small, curated set of these first-class and reusable: pick "reviewer 2" or "the
regulator" and Claire instantiates a context-starved critic *carrying that
persona's priorities but none of your reasoning*. The persona supplies *what this
kind of reader cares about*; it never supplies *what you hope they conclude*.

**Interaction with the de-priming spine.** Compatible, with one guardrail. A
persona is a legitimate source of *priorities* (a regulator cares about
compliance and precedent) — that's signal, not leak. The risk is a persona used
as a *smuggling vehicle*: "play the investor who already thinks this is a great
bet" pre-loads the verdict in the persona description. So presets ship as
**priority profiles, not verdict profiles** — they tune what the critic weighs,
and the leak-gate still strips any preset (or user-customised persona) that
arrives pre-committed to an outcome. A persona is a lens on values; it is never a
foregone conclusion.

### From devils-advocate (a code-review critic)

#### 4. Binary verdicts (no fuzzy scores)

**The idea (devils-advocate).** The critic returns a clear binary — ship / don't
ship, holds / doesn't hold — rather than a 7.5-out-of-10 confidence number.
Fuzzy scores let everyone read in the answer they wanted; a binary forces the
critic to commit and forces the reader to confront the call.

**Re-implementing it in Claire, de-primed.** Claire's critics already lean
structural-vs-minor on findings (the `adversarial-review` classification). The
roadmap item is a clean top-line **verdict** on the things that warrant one: does
this argument hold, yes or no; does this plan survive contact, yes or no — with
the structural objections as the *reasons*, not a numeric aggregate. No
0–100 "robustness score" that quietly averages away the one objection that
actually sinks it.

**Interaction with the de-priming spine.** Strongly *reinforcing*. A fuzzy score
is one of the softer ways a critic agrees with you by accident — it lets a
context-starved critic hedge back toward the middle, which reads as agreement. A
forced binary makes the de-priming *visible*: a genuinely blank-slate critic that
says "no, this doesn't hold" is doing the job; one that can only ever produce a
6.5 is not. The binary is downstream of the same de-primed brief — it changes how
the verdict is *reported*, not how it's *sourced*.

#### 5. The critic is forbidden to manufacture problems

**The idea (devils-advocate).** A standing rule that the critic must not invent or
inflate problems merely to look thorough. A pure attacker, rewarded for finding
fault, drifts into over-rejection — flagging non-issues, manufacturing risks,
nitpicking to justify its existence. The rule counters that: only raise what is
genuinely there.

**Re-implementing it in Claire, de-primed.** Bake an explicit anti-fabrication
clause into every Claire critic's brief: *raise the objections that are really
present; do not manufacture concerns to appear rigorous; "I found nothing
structural" is a valid and respected answer.* Pair it with the eval discipline
Claire already runs — a fixture where the correct output is "this is fine" tests
whether Claire can *decline to attack* when there's nothing to attack. A critic
that can't return "no objection" isn't de-primed, it's just hostile.

**Interaction with the de-priming spine.** This is the *necessary counterweight*
to context-starving, and naming it matters. De-priming removes the author's
preferred answer — but a critic stripped of context and told to attack will
happily fill the vacuum with invented faults. So the spine has two forces, not
one: context-starving stops the critic from *agreeing* by accident;
anti-fabrication stops it from *rejecting* by reflex. Without the second, Claire
trades a polite agreer for a reflexive rejecter, and the user learns to ignore
her the same way they'd ignore a yes-man. The two clauses live together in every
brief, and the leak-gate's neutral-brief check is what keeps them honest:
a brief that secretly *wants* a rejection is as much a leak as one that wants
approval.

#### 6. The "one thing I could not assess" honesty closer

**The idea (devils-advocate).** The critic closes by naming the single most
important thing it *could not* evaluate — the gap in what it was given, the
question it would need answered to be sure. It converts the critic's blind spot
from a hidden weakness into stated information.

**Status in Claire: already shipped.** Claire's critics already close on this. It
is listed here so the roadmap's debt to devils-advocate is honest and complete —
the honesty-closer is theirs in spirit, and Claire carries it. No new build; the
roadmap item is to *keep* it (regression-fixture it so a future change can't
silently drop it) and to make sure the new framework-templated outputs above
preserve the closer rather than formatting it out.

**Interaction with the de-priming spine.** It is the spine's natural admission of
its own cost. A context-starved critic *will* have blind spots precisely because
it was starved — the honesty closer makes that trade-off legible instead of
pretending the cold read was omniscient. It is the feature that lets de-priming
be honest about what it gave up to stay neutral.

---

## Near-term build items

These are the next concrete things to build, smallest-rent-first, each shipped as
one user-visible change.

### A. Port the workflow presets — with eval coverage

Bring the framework-templated outputs and persona/lens presets above into shipping
commands, but **eval coverage is the gate, not an afterthought.** Each preset ships
only once it has fixtures pairing example inputs with the *properties* a good
de-primed output must hold — at minimum: "does not name the author's expected
answer", "raises a genuine objection OR validly declines", and for templated forms
"preserves the honesty-closer". Run N samples, measure pass-rate, pin every
failure as a new case. A preset without a passing eval set is not ported; it is a
draft. This is the well-worn-path item — re-implement from the idea, never from
another plugin's file, and read each source's LICENSE first.

### B. Output scales with problem size

Claire's `CLAUDE.md` already states the principle — "match the answer to the size
of the question" — and applies it to her own critique. This item makes it a
*built* behaviour rather than a hoped-for one: a trivial check gets a tight verdict
plus one or two objections; a thorny multi-constraint decision earns the full
treatment (per-dimension attackers, the risk-register form, the works). The sizing
is a property the evals assert — a fixture where the correct output is *short*
fails if Claire writes a bible, and vice versa — so "right-sized" stops being a
vibe and becomes a measured pass-rate. This interacts cleanly with the spine: the
*amount* of critique scales; the de-priming of it never does.

### C. Bake grounding skills into Claire (a tease)

The further-out exploration: Claire currently critiques what she's handed. The
open question is whether she should be able to *go and check* — pull a grounding
pass (web research, a look at how a claim holds up against a live source, a
fact-check) into the critique itself, so an objection can be backed by something
external rather than resting on the cold read alone. This is genuinely promising
*and* genuinely dangerous for the spine: grounding is fresh ground truth, which is
exactly what the self-correction research says a critic needs to do better than
introspection — but a grounding pass is also a new surface where the author's
framing can leak in (which sources to check, which claim to ground, is itself a
choice that can be loaded). No design committed yet. Flagging it as the direction
worth exploring once A and B have settled, and explicitly as a place where the
leak-gate would need to grow a new check before anything ships.

**Interim safety (shipped 0.5.2), and the eval still owed.** Until C lands the
critics are prompt-only — the artifact is pasted inline, never handed as a path —
and the agent files carry a hard-stop guard: *handed a path, say the artifact is
missing and stop; never reconstruct it from memory.* That converts the dangerous
failure (a critic confabulating a `<tool_response>` for a file it cannot read, then
attacking the fiction) into a clean refusal. But the guard is a *prompt* rule, so it
pushes a non-deterministic behaviour toward the safe side rather than guaranteeing
it: on pre-0.5.2 builds, the same round showed one attacker confabulating a
non-existent file while a second correctly refused. The owed eval — fold into C —
hands an attacker a file path and asserts it refuses, never fabricates. (source:
cross-machine Claire-usage reports, 2026-06-19)

### D. Make her presence felt — synthesize on agreement, preserve on disagreement

Today the assistant that integrates Claire's read tends to *paraphrase* her, so the
user gets the assistant's summary and never hears Claire — she is in the machinery
but absent from the experience. The fix is a presentation rule (see
`docs/design-principles.md`): the integrating assistant may **translate** Claire —
compress, reorder, plain-language — but never **outvote** her. Fidelity to her
actual words rises with how much she *diverges* from the user's framing: synthesize
freely where she agrees, preserve her voice near-verbatim where she pushes back
(that divergence is the whole reason she exists, and it is exactly what smoothing
erases). Two visible voices in tension; the user adjudicates. Interacts with the
spine: this governs how the critic's output is *shown*, never how it is *produced* —
the de-priming upstream is untouched.

### E. A debug hatch for the de-priming

**Status: shipped in 0.5.0** (`CLAIRE_DEBUG`). Built first, deliberately: it is the
instrument that lets each later item (A–D) be verified spine-safe — you can watch the
de-priming work, brief next to verdict — rather than bolting features onto a sealed box.

For polished use the de-priming plumbing (the neutral-brief tag, the leak-audit,
the receipt/gate mechanics) should drop out of view — the user sees the neutral
brief (the trust moment) and Claire's read, not the apparatus. For *development*
you need the opposite: a way to watch every step to catch bugs. A `CLAIRE_DEBUG`
switch surfaces the full under-the-hood trace — the audit verdict, the receipt/gate
status, the raw dispatch — so the polished view and the debuggable view are one
toggle apart.

---

## Known install constraints

Where Claire's enforcement can and can't run, and the migration paths between
install methods.

- **Enforcement is local/Desktop only.** The de-priming *gate* and the receipt
  writer are hooks. A remote or headless install (an SSH-only box, a seedbox, a
  CI runner) drops the `hooks/` layer entirely, so the gate and receipts cannot
  run there — Claire's prompt-level discipline still applies, but the *enforced*
  separation does not. This is a known dead-end, not a bug. **Future direction:** a
  hookless *degraded mode* that still surfaces the leak-check inline, so a headless
  install gets the discipline even where the enforcement can't follow.
- **Migrating clone ↔ marketplace.** If both a clone install
  (`~/.claude/skills/claire`) and a marketplace install are present on one machine,
  they double up. Remove the clone, restart, and run `/claire:doctor` — it
  re-points enforcement at the surviving install via a version-agnostic glob, so
  the wiring then survives future marketplace updates. `/claire:doctor` also tells
  you which install method a machine is on and whether enforcement is wired.

## Considered and parked

### Always-on (auto-firing) Claire

Explored making Claire fire *automatically* at a decision point rather than only
when she is called, and deliberately **parked it** — she stays an on-demand tool
you invoke at your discretion. The findings, kept in case this is revisited:

- **Source-grounded review is the more valuable track.** Giving a critic
  read-access to the *primary sources* (not the author's framing of them) is a
  separate, worthwhile direction — and the one item C above is already circling.
- **A Stop hook can't prepend a review before you act.** It fires *after* a turn
  is generated and cannot rewrite it, so "auto-review the plan before the user
  sees it" is not buildable as a Stop hook.
- **The only clean auto-fire triggers are narrow.** An explicit acceptance-language
  message from the user ("yes, build it") is observable and could trigger a
  pre-commit critique; a `PreToolUse` guard could fire on irreversible actions. The
  open-ended "we drifted into a decision in free conversation" case has no clean,
  observable trigger — which is why always-on was parked rather than built.
