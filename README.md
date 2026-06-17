# Claire

A de-priming adversary for Claude Code. Claire gives you an outside read on a
decision, plan, draft, or argument — from a critic that was never told what
answer you were hoping for.

She is built for **decisions, not just code**. Most adversarial plugins assume
you are a developer reviewing a diff. Claire is for the judgement calls that sit
underneath that: which research direction to take, whether an argument holds,
how to frame a piece of writing, whether a plan survives contact with reality.

## Why a separate critic, instead of asking Claude to check its own work

There is a documented blind spot here. When a language model is asked to review
and revise its own reasoning **without new external information**, it tends to
talk itself out of correct answers as often as wrong ones — the act of
"reflecting" frequently reacts to the question's framing rather than to the
substance. (See research on the self-correction blind spot in LLMs: self-revision
tends to work when there is fresh ground truth to react to, not from pure
introspection.)

A *separately briefed* critic does better — but only if its brief doesn't
quietly hand it the conclusion. The well-documented failure here is anchoring:
if the critic can see how you framed the problem, which option you already lean
toward, or which side you wrote up as a worry versus a settled decision, it
tends to evaluate your framing instead of the actual claim. Anchoring bias
replaces adversarial force.

Claire's whole design is one response to those two facts:

1. **She is context-starved by design.** She gets the claim and the minimum
   needed to challenge it — not your reasoning chain, not your tool history, not
   the story of how you got there.
2. **Her brief is leak-checked before she ever sees it.** A separate read-only
   pass inspects the brief for tells that smuggle in your preferred answer
   (one option's costs painted vividly while the other's are glossed; your
   favoured side framed as a live worry and the rest as already-decided; a
   problem statement only one option happens to solve). A producer cannot
   reliably certify their own brief as neutral — that judgement is exactly the
   thing anchoring corrupts — so the check is done by a fresh reader, not
   asserted by you.
3. **You see the neutral brief before dispatch.** What Claire is actually being
   asked is shown to you first, so the de-priming is auditable rather than
   taken on trust.

That is the edge, stated plainly: not a smarter critic, but a genuinely
*blank-slate* one whose brief has been checked so it can't agree with you by
accident.

## Commands

- **`/claire:challenge`** — Give me an adversary. Routes your request to the
  right kind of critic (a cold outside read, a plan-attacker, an actor
  role-play, a source-versus-claim check, a two-sides face-off, or a check that
  a test isn't rigged), strips the brief of the answer you expect, and shows you
  that neutral brief before dispatching. Use it for "attack this", "outside view
  on this", "what am I missing", "how would X react", "is my test rigged".

- **`/claire:blank`** — A pure cold read. Hand Claire a question or a piece of
  work with no surrounding context and get back the read of someone seeing it
  fresh, with no stake in the prior answer.

## How she differs

A second opinion from the same model, asked neutrally, tends to drift back
toward agreeing with you — it shares your priors and politely re-derives your
view. Claire instead pairs a blank slate with a leak-checked, de-primed brief,
so the disagreement you get is real rather than performative. The same
de-priming discipline is what makes her useful well outside code review.

## Install

```
/plugin marketplace add janikithup/Claire
/plugin install claire@claire
```

Claire installs **disabled by default** — she appears in your "Add plugins"
panel but stays off until you enable her, per machine, on demand. Nothing runs
until you turn her on. (Requires a recent Claude Code build for the
present-but-off install; on older clients the plugin installs enabled, so check
your version if that matters to you.)

## Credit where it's due

Claire is not trying to out-compete the adversarial-plugin ecosystem — she came
out of it. She exists because a non-coder kept wanting a more *neutral*
adversary for non-code decisions and went looking for one. **anvil** and
**devils-advocate** were direct inspirations; the principle that Claude
shouldn't fold the moment you push back, and that a dedicated dissenter beats a
polite agreer, is theirs before it was hers. Claire's contribution is narrow and
specific: take that adversarial spirit, point it at decisions rather than diffs,
and put a leak-checked de-priming step in front of it so the critic can't be
quietly told the answer.

---

*Claire is an independent, community-built plugin. She is not affiliated with or
endorsed by Anthropic. The research on the self-correction blind spot and
anchoring bias in LLMs is referenced in good faith to explain her design; consult
the current literature directly for the underlying findings.*
