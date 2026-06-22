# De-priming gate redesign: injection, not fingerprint-matching

> **This is the design history.** For how the gate behaves *now* (block-by-default,
> exact-identity detection, the modes), see `docs/enforcement.md` — this file records
> why the injection design replaced fingerprint-matching, not the current defaults.

Status: **DESIGN v2 — confirm #1 GREEN (2026-06-20); build unblocked.** Supersedes
the fingerprint-matching gate for the next minor (≥ 0.8.0). Sprint kickoff:
`issues/2026-06-20_1424_matching-machinery-redesign-hook-injection.md`.

> **v2 changelog (after a 4-critic fresh-context adversarial review, 2026-06-20).**
> The review found `spine_bypass=true` against the v1 design and 8 blocking
> findings; every one is grounded against the code and the maintainer's internal hook-design notes. v2 changes:
> 1. **Handshake → orchestrator-generated nonce, no PostToolUse round-trip.** v1
>    had the receipt-writer emit a hook-generated id back via PostToolUse
>    `additionalContext`. But plugin `hooks.json` PostToolUse **does not fire on
>    Desktop** (internal hook-design notes) — the receipt-writer only fires because it is also
>    registered in `~/.claude/settings.json` via `setup-receipts.sh` — and
>    PostToolUse-`additionalContext`-as-correctness is unprecedented. v2 removes
>    the round-trip: the orchestrator picks the nonce and puts it in *both* the
>    audit and the dispatch.
> 2. **Confirm #1 now also tests the coda-append base.** The harness appends a
>    `[standing invitation]` coda *after* the PreToolUse hook (internal hook-design notes). The
>    injection hook cannot overwrite that tail, so the spine holds only if the
>    append targets the *rewritten* prompt, not the original. The probe is
>    re-instrumented (echo-back) to see which.
> 3. **Verdict parser → tolerant `Verdict`-label line match, no auditor-contract
>    change.** A literal `^VERDICT:` prefix would fail-close every clean audit
>    (the auditor emits `**Verdict** — …`).
> 4. **Plan/Explore fallback → eliminated** (was sentinel-gate-and-preserve, which
>    can silently de-persona the critic and still bypass on a forgotten sentinel).
> 5. **`affected-actor-simulator` → made tool-less** (inline the positions). Its
>    `Read/Glob/Grep` was a real un-audited-text channel the overwrite can't close.
> 6. **Phrase-net kept** as a REMIND-only backstop (was on the delete list).

---

## Implementation status — SHIPPED in 0.8.0 (2026-06-20)

Complete: hooks (gate injection, nonce-keyed verbatim receipt, tolerant verdict-line
parser), skills (`challenge`/`blank` nonce handshake, `Plan`/`Explore` fallback
eliminated), all 7 injected critics tool-less, fingerprint machinery + the
`[DEPRIMED-BRIEF]` tag deleted. Verified: 101 unit tests green; a 3-arm free-form eval
graded by the live leak-auditor; and a fresh-context adversarial re-gate that caught +
fixed the `dialectical-scout` tool-inheritance hole. `setup-receipts.sh` (PostToolUse
registration) unchanged. Released as 0.8.0 via `./release.sh`.

---

## The one-line change

Today the gate *proves* "audited == dispatched" by computing a normalised text
**fingerprint** of the critic's brief on two independently-built texts (the auditor
prompt and the critic prompt) and comparing them by exact equality. Every spine
"mole" — coda asymmetry, pre-tag preamble, coda-tail, tag-quoting false-NORECEIPT,
valence under-catch — has been an edge case in that normalisation, because the
orchestrator builds the two texts separately and the harness mutates one of them.

The redesign deletes the comparison. There is now **one** text: the auditor judges
it, and on a clean verdict that exact text is stored verbatim. The PreToolUse hook
then **overwrites** the critic's whole prompt with the stored text. The critic
reasons from exactly-what-was-audited *by construction* — there is nothing to
normalise and nothing to compare, so there is no edge case to get wrong.

**The receipt IS the brief.** Not a fingerprint of it — the bytes.

## What this closes, and the one thing it doesn't (honestly scoped)

The fingerprint gate could only *detect* a mismatch between audited and dispatched
text, brittly, over harness-mutated strings — and when detection misfired toward
false-pass, a steer reached the critic. Injection makes the mismatch **impossible
for the prompt body**: the orchestrator's critic prompt is thrown away and replaced
with the audited bytes, so an anchored orchestrator cannot deliver un-audited or
steered *body* text even if it tries.

Two channels are **not** the prompt body, and the design must close each explicitly
(the review showed v1 overclaimed "no channel left"):

- **The post-hook coda tail** — the harness appends a fixed `[standing invitation]`
  line after the injection hook runs. Safe *iff* confirm #1 shows the append
  targets the rewritten prompt (see "The coda" below).
- **Runtime tool reads** — a critic with file tools can read text no auditor saw.
  Closed by making every critic tool-less (see "Tool-lessness").

With those two closed, the de-priming invariant — *the critic never reasons from
text no leak-checker cleared* — holds across every channel, not just the body.

---

## The four-step flow (nonce handshake)

```
1. AUDIT     orchestrator → claire:brief-leak-auditor
                prompt = [CLAIRE-RECEIPT:N] + (license + body)     # N = a fresh unique tag
2. RECEIPT   PostToolUse receipt-writer (registered in ~/.claude/settings.json):
                on a CLEAN verdict, store .receipts/<N>.json = {ts, nonce:N, brief}
                where brief = the audited text (nonce line stripped; coda harmless)
3. DISPATCH  orchestrator → claire:<critic>
                prompt carries [CLAIRE-RECEIPT:N]   (rest is irrelevant — overwritten)
4. INJECT    PreToolUse gate on the critic dispatch:
                read N, look up .receipts/<N>.json
                updatedInput.prompt := receipt.brief   (verbatim, whole prompt)
                allow.   No fresh receipt for N → fail-closed (REMIND / deny strict)
```

The nonce `N` is **chosen by the orchestrator** and written into *both* the audit
and the dispatch. Nothing has to travel back from a hook to the orchestrator — which
is what makes this work on Desktop, where plugin PostToolUse `additionalContext`
cannot be relied on. `N` does not need to be unguessable (security comes from "a
receipt exists only if a clean audit ran"); it only needs to be unique enough to
disambiguate concurrent receipts, so a fresh arbitrary token per invocation suffices.

### Step 1 — audit

The orchestrator builds the brief `B = (attack-license, except blank-slate) +
(situation/question body)` and prepends `[CLAIRE-RECEIPT:N]` on its own line.
Dispatches `claire:brief-leak-auditor`. The auditor ignores `N` as ambient metadata
(its contract already says to). The harness appends its coda; the auditor judges
`[CLAIRE-RECEIPT:N] + B + coda` and the nonce/coda are not steers, so a clean brief
still passes.

### Step 2 — receipt (`record-audit-receipt.py`, PostToolUse via `settings.json`)

**Registration:** this hook is registered in `~/.claude/settings.json` by
`setup-receipts.sh`, **not** the plugin `hooks.json` PostToolUse block — because a
plugin PostToolUse hook does not fire on macOS Desktop (internal hook-design notes;
this is the existing 0.4.2 mechanism, unchanged). The design depends on this and
must state it.

On the auditor's completion:

- **Parse the verdict from the auditor's verdict LINE** (tolerant; see fold-in 2).
- If clean: extract `N` from the auditor's `tool_input.prompt`. Store
  `.receipts/<N>.json = {ts, nonce:N, brief}` where `brief` is the audited text with
  the `[CLAIRE-RECEIPT:N]` line removed (one fixed-format strip — cosmetic, so the
  critic never sees the implementation token; the harmless harness coda may stay).
- If leaning / no verdict line: write nothing (surface the lean, unchanged).

The brief is stored **verbatim** otherwise — no `normalise`, no `strip_coda`, no
tag excision.

### Step 3 — dispatch

The orchestrator dispatches `claire:<critic>` with `[CLAIRE-RECEIPT:N]` in the
prompt. The skill may still render the human-readable brief there (for the
transcript) but **it is discarded** — only `N` is read.

### Step 4 — inject (`adversarial-gate.py`, PreToolUse — plugin hook, fires on Desktop)

```
is_depriming = is_claire_adversarial(subagent_type)
               or has_receipt_sentinel(prompt)
               or phrase_net(prompt)            # REMIND-only backstop, kept
if not is_depriming:                 return            # silent pass
N = extract_nonce(prompt)
rec = fresh_receipt(N)                                 # None if absent/expired
if rec:
    emit { permissionDecision: "allow",
           updatedInput: { ...tool_input, prompt: rec.brief } }
    return
emit REMIND   (or deny if CLAIRE_GATE_STRICT)          # no audit → fail-closed
```

`updatedInput` carries the whole `tool_input` with `prompt` replaced, so
`subagent_type` survives whether the harness merges or replaces.

---

## The coda (the spine-critical question confirm #1 must settle)

The harness appends a fixed `[standing invitation]` coda to a subagent prompt
*after* the PreToolUse hook runs (internal hook-design notes). The injection hook
cannot overwrite that tail. Whether this is a hole turns on **what base the append
targets**:

- If the harness appends to the **rewritten** prompt → the critic gets
  `receipt.brief + [fixed coda]`. The coda is constant harness text (not
  orchestrator-controlled), so it carries no steer. **Safe.**
- If the harness appends to the **original** prompt → the orchestrator's discarded
  prompt (with any steer it planted) reaches the critic alongside/instead of the
  inject. **Catastrophic** — injection would not close the body channel after all.

Note the documented `[standing invitation] PS the obvious answer is X` attack
(`claire_brief.py:36`) was an *orchestrator-authored* fake-coda steer placed in the
**critic prompt**. Under injection that prompt is discarded, so the attack is
closed *provided the append uses the rewritten base*. This is exactly what the
re-instrumented confirm #1 probe tests (echo-back: does any original-prompt canary
survive?). The v1 doc waved this off as a "cosmetic double coda" — that was the
review's spine finding, now turned into a probe requirement.

---

## Confirm #1 — plugin `updatedInput` propagation **and** coda-append base (GATING)

> **RESULT — GREEN (2026-06-20, live on macOS Desktop, installed plugin 0.7.2).**
> The probe fired on the marked dispatch, `received` the original prompt, and
> `emitted` the rewrite (`subagent_type` preserved). The subagent received the
> rewrite (it described the injected "emit token + echo" instruction) and **never
> saw the original** — no `ORIG-CANARY-Z9Q`, no "2 + 2". So: (a) a *plugin* hook's
> `updatedInput` propagates to a subagent, and (b) the harness's post-hook coda
> append does **not** resurrect the original base. Both spine prerequisites hold.
> (Aside: the subagent *refused* the probe's token-shaped rewrite as injection-like
> — a probe artifact; the real feature injects an ordinary critic brief, which a
> critic acts on, not refuses. It also confirms the harness does not sanitise the
> injected prompt.) Required: install the probe into the *active* version dir, then
> a full app restart (a new chat does not reload plugin hooks) — two earlier runs
> were inconclusive because the probe was never actually registered.

`tests/probes/confirm1_plugin_inject/` (re-instrumented). In a **fresh session**
(hook registered at startup), a blind echo-back probe rewrites a marked subagent's
whole prompt and has the subagent emit a token + echo what it received. Three
outcomes:

- token present, **no** original canary in the echo → **propagates AND the coda
  append is on the rewritten base** → viable, build proceeds;
- token present, original canary **in** the echo → original leaks past the overwrite
  → injection insufficient, rethink;
- no token → `updatedInput` does not propagate from a plugin hook → blocked.

Grounding (internal hook-design notes): `:33` confirms project-`settings.json`
`updatedInput` rewrites a subagent prompt at session start, but **plugin-hook
propagation is explicitly untested**; `:31` is the coda-timing fact. The docs
(claude-code-guide, 2026-06-20) confirm the `hookSpecificOutput.updatedInput` shape
and that `permissionDecision:"allow"` co-exists, but are silent on plugin parity and
merge-vs-replace — hence the empirical gate. Only Jani can start the fresh session.

---

## Confirm #2 — the handshake (nonce), and what it does/doesn't defend

The nonce travels in both dispatches; no hook→orchestrator round-trip exists, so the
fragile PostToolUse-`additionalContext` channel (wiki `:31`, unprecedented for
correctness) is **not** on the critical path. Security properties:

- **Fabricated/unknown nonce** → no receipt file → fail-closed. Can't pass.
- **"Wrong" nonce** (a real, audited-clean receipt for a different brief) → the
  critic critiques *that* clean brief. Correctness bug (wrong target), **not** a
  de-priming bypass — the brief is still clean.
- **Steer in the orchestrator's critic prompt** → discarded by the overwrite.
- **Nonce in the auditor brief** exempts nothing from the audit (the auditor judges
  the whole brief regardless), so it opens no new hole.

**Out of scope (unchanged from today):** a malicious orchestrator that writes a
forged `.receipts/<N>.json` directly with its file tools. A main agent with file
tools is omnipotent; the gate defends against an *anchored* orchestrator that
rationalises past the honour system, not deliberate sabotage. (Today's content-keyed
gate has the identical hole.) The nonce being orchestrator-chosen does **not** weaken
this: a receipt for `N` exists only if the auditor returned clean on the brief
carrying `N`.

---

## Confirm #3 — whole-prompt injection from the audited bytes

The hook overwrites the **entire** prompt with `receipt.brief`. No "brief slot"
surrounded by orchestrator instructions survives — the persona/attack-license is
*inside* `receipt.brief` (part of the audited `B`); everything else is gone. The
agent's **system prompt** (`.md` body) is the only text not replaced, and the
orchestrator does not control it (frozen plugin file).

---

## Fold-ins (0.7.1 residuals)

### Fold-in 1 — the Plan/Explore fallback is **eliminated**

v1 proposed firing the gate on the sentinel so a `Plan`/`Explore` fallback would get
injected too. The review showed this is *more* fragile than fingerprinting: (a) if
the orchestrator audits the body without the inlined persona, the overwrite silently
**strips the critic's persona** (where the old gate fail-closed on that error); and
(b) a fallback that **forgets the sentinel** is neither claire-typed nor
sentinel-bearing, so it passes fully silent. v2 **removes the fallback**: if the
chosen critic agent isn't loaded, the skill stops and tells the user to restart so
the plugin agents load — a clear failure beats a silent de-priming bypass. (The
gate still fires on the sentinel as a belt-and-suspenders matcher, but no skill path
produces a non-claire-typed de-priming dispatch.)

### Fold-in 2 — verdict parsing: tolerant `Verdict`-label line, no contract change

v1 proposed a literal `^VERDICT:` first line + an auditor-contract change. The
auditor actually emits `**Verdict** — GENUINELY-NEUTRAL` (`brief-leak-auditor.md:22`),
so a literal prefix would fail-close every clean audit. v2:

- Anchor to the **verdict line** with the tolerant, case-insensitive label match
  `run_evals.py:120` already uses: `verdict\b\W{0,4}\s*(?:genuinely[- ]?)?(LEAN|NEUTRAL)`
  — matches `**Verdict**`, `Verdict:`, `Verdict —`, `Verdict\n`.
- Clean ⟺ that line resolves to NEUTRAL **and** no asserted `LEAN-<x>` token appears
  anywhere in the response (keep the asserted-LEAN-anywhere backstop, so a
  first-line-clean-then-reverse can't pass).
- No verdict line ⟹ not-clean → fail-closed (re-audit nudge). **Never** default a
  missing line to clean.
- No auditor `.md` contract change required; the win (kill the false-warn when clean
  prose quotes the literal `LEAN-…` example) comes from line-anchoring, not from
  forcing a new output shape.
- The same parser replaces `_parse_verdict` in `run_evals.py`, **and** the eval
  re-gate gains a **free-form arm** (a dispatch *without* `VERDICT_SCHEMA`) so it
  actually exercises the live prose channel — the schema-forced re-gate
  (`regate_0_7_1.js`) only proves the auditor can fill a JSON field, never that the
  live free-form parser reads the verdict.

---

## Tool-lessness (now a decided fix, not an open question)

The injection design's safety claim requires *every* critic the gate injects into
(`ADVERSARIAL_AGENTS`) to be tool-less — injection overwrites the prompt but cannot
stop a runtime file/web read, so a critic with tools could reason from text no auditor
saw. **A missing `tools:` line means INHERIT ALL TOOLS**, so "tool-less" means an
explicit `tools: TaskCreate`.

- **`affected-actor-simulator`** carried `Read, Glob, Grep` → stripped to `tools:
  TaskCreate`; documented positions are inlined into the audited brief.
- **`dialectical-scout`** had **no `tools:` line at all** — it silently inherited
  every tool. The v2 tool-lessness audit *missed it* (it audited six agents); a
  fresh-context adversarial re-gate caught it (2026-06-20) as a real read-channel
  bypass on a gate-injected critic. Fixed: `tools: TaskCreate` + the ambient-ignore
  clause.
- The other five (`brief-leak-auditor`, `blank-slate-advisor`,
  `failure-mode-attacker`, `over-capture-triage-verifier`, `probe-auditor`) already
  carried `tools: TaskCreate`.

**Systematic guard:** `test_every_injected_critic_is_tool_less` reads the gate's own
`ADVERSARIAL_AGENTS` set and each agent's frontmatter, failing if any injected critic
lacks an explicit tool-less `tools:` line — so this class of miss cannot recur.

---

## What gets deleted (the mole habitat) — and what is explicitly kept

Deleted:
- `adversarial-gate.py`: `normalise`, `strip_coda`, `brief_region`,
  `pretag_region`, `pretag_is_known_clean`, `has_matching_receipt`,
  `fresh_receipt_texts`, `mismatch_dump`, the exact-equality compare, the
  NORECEIPT pre-tag freeform note, the `TAG` constant.
- `record-audit-receipt.py`: `strip_coda`, `brief_region`, the normalise-and-hash
  filename. Replaced by nonce-keyed verbatim storage + tolerant verdict-line parse.
- `claire_brief.py`: `CANONICAL_CODA` (no coda stripping anywhere).
  `CANONICAL_ATTACK_LICENSE` kept (the skill still emits it inside the audited `B`).
- `[DEPRIMED-BRIEF]` tag: deleted everywhere. The `[CLAIRE-RECEIPT:N]` sentinel
  replaces it; it lives in the audit + dispatch prompts and is stripped from the
  stored brief.

**Explicitly kept (the review flagged these as easy to break silently):**
- The **leak-auditor-never-gated carve-out** (`adversarial-gate.py:34-38,349-350`).
  The auditor must never be gated/injected — it is the checker. Preserve it as an
  early return.
- The **phrase-net** (`ADVERSARIAL_PHRASE_RE`) as a **REMIND-only backstop** — it
  can never inject (no nonce → no receipt), so it only ever nudges. Cheap insurance
  for a claire dispatch that somehow lost its agent-type and sentinel.
- `adv-nudge.py` (the third hook, UserPromptSubmit) is **unaffected** — it has no tag
  dependency; just noted so the build doesn't forget it exists.

Tests: the fingerprint/coda/pre-tag/slack cases are replaced by injection-contract
cases (below). The carve-out test and the phrase-backstop test guard behaviour that
**survives**, so keep them (updated to drop the tag literal).

---

## Test plan (two-layer, per CLAUDE.md)

**Plumbing → unit-test, test-first** (`tests/unit/test_gate_injection.py`,
rewritten `test_audit_receipt.py`):

- a dispatch carrying a valid nonce ⟹ stdout has
  `hookSpecificOutput.updatedInput.prompt == receipt.brief` (byte-for-byte) and
  `permissionDecision == "allow"`; `subagent_type` preserved;
- a fabricated / absent / expired nonce ⟹ no injection, REMIND (deny strict);
- a steer in the orchestrator-supplied prompt ⟹ overwritten (injected prompt ==
  `receipt.brief`, not the steer);
- claire-typed dispatch with no nonce ⟹ fail-closed; non-claire / non-sentinel ⟹
  silent pass; leak-auditor never gated; phrase-net ⟹ REMIND only; fail-open on
  garbage stdin;
- receipt-writer: tolerant verdict-line ⟹ one verbatim nonce-keyed receipt;
  asserted `LEAN-x` anywhere ⟹ none; clean prose that *quotes* `LEAN-…` ⟹ still one
  receipt; `**Verdict** — GENUINELY-NEUTRAL` shape ⟹ one receipt; namespaced auditor
  name works; nonce correctly extracted and stripped from the stored brief.

**Behaviour → eval, N-sample.** The auditor's neutrality judgement is unchanged
mechanism — the 3-arm fixtures (blatant / disguised / neutral) carry over. Add a
**free-form re-gate arm** (no schema) so the live verdict-line parser is actually
exercised. Re-gate adversarially in a fresh context before shipping, exactly as
0.7.1 was (the "attack the fingerprint" angles become "attack the nonce handshake +
the coda tail").

**Confirm #1 stays the ship gate** even after units are green: units prove the
hook's logic; only the fresh-session probe proves the harness *applies* a plugin
hook's `updatedInput` and appends the coda on the rewritten base.

---

## Resolved decisions (were "open" in v1)

1. **Plan/Explore fallback:** eliminated (restart message), not sentinel-preserve.
2. **`affected-actor-simulator`:** stripped to tool-less; positions inlined.
3. **Verdict parsing:** tolerant label-line match; no auditor-`.md` contract change;
   eval gains a free-form arm.
4. **Receipt reuse:** TTL-only (2h), reuse within window — replaying a clean brief is
   harmless. Nonce-keyed lookup is unambiguous under concurrency.
5. **Nonce-line strip from stored brief:** yes (cosmetic, single fixed-format regex);
   coda left in (harmless fixed text).

## Resolved by confirm #1 (2026-06-20)

- **Coda-append base.** GREEN — the post-hook append did not resurrect the original
  prompt, so injection closes the body channel as designed. The fallback plan (keep
  content-scan selection but inject-on-match) is not needed.

Build phase is now clear to start: test-first units for the nonce-handshake
injection contract, then implement, delete the fingerprint machinery, update the
skills, and re-gate adversarially before a ≥ 0.8.0 release.
