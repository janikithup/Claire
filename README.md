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

- **`/claire:doctor`** — Health- and conflict-check this install. Verifies
  dependencies and integrity, flags duplicate installs and agent-name clashes with
  your current workspace, and runs a live self-test confirming the de-priming
  enforcement is actually firing here (the gate blocks by default, so this tells you
  whether enforcement works end-to-end or a broken install needs the
  `CLAIRE_GATE_STRICT=0` escape hatch). Run it after installing or updating.

## How she differs

A second opinion from the same model, asked neutrally, tends to drift back
toward agreeing with you — it shares your priors and politely re-derives your
view. Claire instead pairs a blank slate with a leak-checked, de-primed brief,
so the disagreement you get is real rather than performative. The same
de-priming discipline is what makes her useful well outside code review.

## Enforcing the de-priming

The leak-check isn't a polite suggestion the assistant can talk itself out of. A
built-in gate watches every critic dispatch and stays quiet only once the
leak-auditor has *actually* cleared that exact brief — proven by a short-lived
receipt written when the audit passes, not by the assistant claiming it did the
step. If a brief never passes the auditor in two tries, the assistant is told to
stop and show you the lean it keeps finding rather than push on regardless.

By default the gate *blocks* a critic dispatch that skipped or failed the audit —
it hard-stops rather than waving the dispatch through with a warning. This is safe
to default on because the gate recognises a Claire dispatch only by exact identity
(a `claire:`-named critic, or a real receipt marker), never by guessing from
keywords, so a block can only ever land on a genuine Claire critic — never on
unrelated work. If a broken install ever locks you out (receipts not being written,
so every dispatch is denied), set `CLAIRE_GATE_STRICT=0` on that machine to soften
the gate back to advisory warnings while you fix it — `/claire:doctor` diagnoses
exactly that case.

**Running Claire during autonomous work.** By default Claire is invoke-only — nothing
fires until you ask. For long unattended / AFK runs where no one is there to invoke her,
set `CLAIRE_AUTO=1` for that run (the same per-machine opt-in style as
`CLAIRE_GATE_STRICT`). When it is on *and* your prompt kicks off an autonomous run
("scan and fix", "work the queue", "clear the backlog", `/autoloop`, …), Claire injects a
standing instruction for the run: treat her as a per-judgement-call step — on every fork
the run resolves itself, every plan it commits to, every file it writes, and anything
outbound, run a Claire pass first. The de-priming is unchanged: every brief is still
leak-checked before the critic sees it, and a brief that keeps leaning is parked for you
rather than waved through. Claire still only critiques — she never auto-approves a
decision. It stays off for interactive use, so "nothing fires until you invoke her" holds
there; arming an unattended run is itself the invocation. Recommended on AFK machines:
`CLAIRE_AUTO=1` together with `CLAIRE_GATE_STRICT=1` (after `/claire:doctor` confirms
receipts fire), so a skipped audit hard-stops the run instead of warning into a log no one
is reading. `/claire:doctor` reports whether the mode is armed.

**Building on Claire? Turn on the trace.** Set `CLAIRE_DEBUG=1` and every critic
dispatch surfaces a short under-the-hood trace — the leak-audit verdict, whether a
receipt matched, and the gate's decision — so you can watch the de-priming work and
see the brief next to the verdict. It is off by default and reaches no normal user:
it only changes what is *shown*, never how a brief is de-primed or how a critic runs.

**On the Claude Desktop app, run `setup-receipts.sh` once per machine.** Desktop
does not fire a plugin's *after-tool* hooks — and writing the receipt is an
after-tool hook — so without this step no receipt is ever written, the gate can
only ever warn (it never goes quiet), and strict mode would block everything. The
script wires the receipt writer into your `~/.claude/settings.json`, where those
hooks *do* fire; it is safe to re-run, idempotent, and undoes cleanly if you remove
Claire (a missing script becomes a no-op, never a hang). `/claire:doctor` tells you
whether this machine still needs it.

## Install

### Recommended — the plugin marketplace (plug-and-play)

On the **Claude Desktop app**, open the plugins panel, choose **Add marketplace**, and enter:

```
janikithup/claire-marketplace
```

Then enable **claire** from the panel. `/claire:challenge` and `/claire:blank` are live on the next session, and updates come from refreshing the marketplace in the panel — no terminal, no git. (On the terminal/CLI the equivalent is `/plugin marketplace add janikithup/claire-marketplace` then `/plugin install claire@claire-marketplace`.)

**Then turn on enforcement — one step, recommended.** Run `/claire:doctor` and say **yes** when it offers to enable the receipt-backed enforcement. Out of the box the gate *warns* you to audit; once enforcement is on, it goes **silent only on a brief that genuinely passed the leak-check** (and strict mode becomes available). `/claire:doctor` wires it for you — nothing to edit by hand. See *Enforcing the de-priming* above for what this buys you.

### Alternative — clone install

Drop Claire straight into your skills folder; she loads automatically on the next session, no commands needed:

```
git clone https://github.com/janikithup/Claire.git ~/.claude/skills/claire
```

On Windows, use `"%USERPROFILE%\.claude\skills\claire"` as the target. Restart Claude Code (or open a new session) and `/claire:challenge` and `/claire:blank` are live. Update later with `git -C ~/.claude/skills/claire pull`. Turn on enforcement the same way — run `/claire:doctor` (it offers to wire it), or `bash ~/.claude/skills/claire/setup-receipts.sh` directly.

## In regular Claude chat (not Claude Code)

Claire's full machinery is Claude Code only. For regular Claude chat (claude.ai and
the Claude apps), the [`chat/`](chat/) folder ships a prompt-only **custom Skill**
that carries her de-priming discipline and cold-critic persona — the practice
without the enforced separation. See [chat/README.md](chat/README.md) to add it in
claude.ai → Settings → Skills, or as a Project's custom instructions.

## Where the name comes from

Claire began as a typo. Someone fat-fingered `.claude` as `.claire` one too many
times, the misspelling stuck, and the critic who lived in that folder got a name. It
fit — an outsider's name for the outsider in the room.

Her title, **Challenge Officer**, is borrowed in spirit from a real kind of role:
the person an organisation appoints whose entire job is to push back on a plan
*before* it hardens into a decision. Not a contrarian, not a critic-for-hire — a
sanctioned challenger, there to make sure the comfortable answer has actually earned
its place. That is the posture Claire takes: she is not trying to be right, she is
trying to make sure you are not wrong for a reason no one said out loud.

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
