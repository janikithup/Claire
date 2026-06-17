# Claire — design principles (the *why*)

Decisions about how Claire works that are not obvious from the code, kept so a
maintainer (human or model) understands the reasoning before changing something
load-bearing.

## Showing the critic: synthesize on agreement, preserve on disagreement

When the assistant that holds the user's full context folds Claire's assessment
into the final answer, how much of *her* voice survives is **not a fixed ratio — it
is conditional on divergence.**

- Where Claire **agrees** with the user's framing → synthesize freely. Nothing is
  being suppressed; merge her in and save the user's attention.
- Where Claire **diverges** — names a contradiction, withholds approval, reframes
  the question → preserve her voice near-verbatim. Divergence is the entire reason a
  second opinion has value, and it is exactly what the "helpful assistant" instinct
  sands off.
- The integrating assistant may **translate** her (compress, reorder, plain-language)
  but must never **outvote** her — resolve a disagreement by quietly taking the
  user's side.

Rationale — a **failure-mode asymmetry**: over-synthesis fails *silently* (the sharp
version is erased and undetectable in the output); over-preservation fails *loudly
and recoverably* (visible tension the reader adjudicates). Design toward the visible
failure — you can always trim a tool that shows too much, but you cannot debug one
that quietly smoothed away its own point.

The dial depends on the reader: for a sophisticated user who wants two voices in
tension and will adjudicate them, preserve aggressively. That is Claire's default
audience.

## Why the brief gets its own separate audit (not self-certification)

A producer **cannot reliably neutralise its own brief** toward its preferred
answer. Demonstrated live during Claire's own build: the informed agent wrote a
brief, the leak-auditor flagged a lean, it applied the rewrite — and the lean simply
re-formed at a new structural location, twice, with the producer rating each version
"neutral". Self-certification of brief-neutrality fails, and "I fixed the lean" is
itself an anchored judgement.

Two consequences baked into the design:

1. The brief is checked by a **separate, fresh-context auditor**, never
   self-certified. The "neutralised brief" handed to the critic is itself an editing
   act by the informed stage — if that stage strips the question toward something
   convenient, the critic's independence is compromised before she writes a word.
   The leak-audit is the safeguard for *that* attack surface.
2. The fix loop is **bounded and ends in escalation**, not endless rewriting. After
   a small cap of rewrites that still lean, hand the critic the *raw, un-optioned*
   question and let her build her own frame — because the producer's framing is the
   thing carrying the lean. Done live during the build, it produced an answer the
   producer could not reach on its own.
