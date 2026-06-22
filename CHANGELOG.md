# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.0] - 2026-06-22

### Changed
- **The de-priming gate now blocks by default instead of warning.** When a critic is dispatched without a clean leak-audit behind it, the gate now **denies** the dispatch rather than emitting a warning the assistant could read and walk straight past. Reports kept showing exactly that walk-past — an outside-read or adversary dispatched *before* the de-priming step, with the warning treated as licence to skip — which is the one thing the gate exists to stop. Blocking by default closes it. This is safe to default on because the gate recognises a Claire dispatch only by **exact identity** (one of Claire's own `claire:`-named critics, or a real `[CLAIRE-RECEIPT]` marker), so a block can only ever land on a genuine Claire dispatch, never on unrelated work. If a broken install ever locks you out — receipts not being written, so every dispatch is denied — set `CLAIRE_GATE_STRICT=0` to soften the gate back to advisory while you fix it; `/claire:doctor` diagnoses and now reports that case. (Thanks to the maintainer for the call that warn-by-default had become a safety net the assistant kept leaning on.)
- **Detection no longer guesses from keywords.** The gate used to also flag a dispatch whose *prompt* contained phrases like "devil's advocate" or "steel-man". That guesser both false-fired on unrelated work (the reason the gate couldn't safely block by default) and missed real critiques that didn't use the magic words. It's gone — the gate guards Claire's own named critics, not the act of seeking criticism through any agent. (Thanks to the maintainer for "the ultimate goal is no more keyword logic.")

### Removed
- **`/claire:report` and the automatic feedback channel are out of the plugin.** Both filed to a *local* `~/.claude/claire/issues/` queue that only the person developing Claire ever reads — for everyone else, reports just piled up on disk with nothing to collect them. A feedback channel that can't carry feedback back isn't worth the command-menu space, so it's removed (the skill, both hooks, `setup-feedback.sh`, and their tests). Filing a Claire issue still works the direct way — write the note straight to the queue — and a one-tap shortcut, if wanted, belongs as a personal skill outside the shipped plugin. (Thanks to the maintainer for spotting it had no real use case.)

### Internal
- **`CLAUDE.md` is now a router, not a manual.** The build rulebook had started absorbing *mechanism* (how the gate works, the release procedure) inline. It now keeps the per-session build rules written out and routes functionality to `docs/` through a short index — the gate and the modes to `docs/enforcement.md`, release mechanics to `docs/releasing.md` — so the always-loaded file stays lean while every capability stays discoverable from it. A test pins the index against `docs/` both ways, so a pointer can't outlive its doc and a new doc can't go unlinked. (Thanks to the maintainer for "set the md up as a router to the docs.")

## [0.11.0] - 2026-06-21

### Added
- **Say "ask Claire" and you get routed to the right place — without naming a command.** The hint that surfaces Claire used to fire only on critique-shaped phrases ("what am I missing", "attack this"), never on her name. Now naming her — "ask Claire", "run it by Claire", "Claire's take", "what would Claire say" — routes you to `/claire:challenge`, the entry point that picks the right critic for what you have *and* leak-checks your brief before any critic sees it. Why route there rather than straight to a critic: the brief-stripping that makes Claire Claire lives in that step, so reaching for a critic directly would skip it. Deliberately tight: it does **not** fire on the bare word "claire" (which is everywhere in ordinary work — "fix the claire gate", "Claire's README"), only on phrases that actually ask for her read; a test pins eight such mentions as silent, including the "Claire's read"/"Claire's README" trap. (Thanks to the maintainer for the catch that "ask Claire" was free-guessing between a skill, a bare critic, and a workflow — and that a wrong guess skips the de-priming.)

## [0.10.0] - 2026-06-21

### Changed
- **Claire reads her reviewer's verdict from a fixed codename line, instead of guessing it from prose.** The leak-auditor now ends every audit with one machine-readable line — `CLAIRE-VERDICT: NEUTRAL` or `CLAIRE-VERDICT: LEAN` — and Claire reads only that line to decide whether a brief is cleared. Before, she parsed the verdict out of the auditor's free-form English, which is inherently unreliable: model prose varies every time, so each new phrasing was a fresh chance to mis-read (a markdown-fenced verdict, a "faint lean" qualifier, "closer to neutral", even the letters "tip" inside "multiple" could trip the parser). A pre-release review found that class of bug had crept back in. Defining the format we read — rather than reverse-engineering random output — removes the whole class: the reader is now a few deterministic, fully-tested lines, and if the codename is ever missing it fails **closed** (no receipt, the gate reminds), so a missing or garbled verdict can only over-remind on a clean brief, never wave a leaning one through. (Thanks to the maintainer for the call to stop parsing prose.)

### Added
- **`/claire:doctor` now tests the full round-trip, not just half of it.** Its live self-test used to confirm only that a clean audit *writes* a receipt; it now also dispatches a critic and confirms the gate *reads that receipt back and delivers* the audited brief to the critic — catching a broken hand-off (e.g. after duplicate plugin copies are removed mid-session) that the write-only check could not see. The rulebook now carries the standing principle: when a bug reaches a user that the doctor could have caught, harden the doctor before shipping the fix.

### Fixed
- **`/claire:adversarial-review` no longer crashes when handed a plain-text plan.** Its own usage hint says to pass the plan as a bare string, but the workflow then tried to parse that string as JSON and died at zero agents. A plain-text plan now just works (objects and JSON-stringified objects still work too).

### Internal
- A schema-contract test pins the de-priming gate's injected dispatch against the real Agent-tool input schema, catching a dropped-required-field regression (the class behind 0.8.2) at write time rather than on a broken release.

## [0.9.0] - 2026-06-21

### Added
- **A built-in feedback channel — file a Claire issue from any project, without it scattering into the repo you're in.** When a Claire skill or agent falls short while you're working in some *other* project, its report used to land in whatever repo happened to be open (sometimes a public one), because the assistant's file-writing is sandboxed to the current folder and can't reach Claire's central queue. Now the assistant **emits a marker** in its reply and a background step that runs with your own file access — outside that sandbox — files the report to one private folder (`~/.claude/claire/issues/`), reachable from anywhere.
  - **Use it:** `/claire:report <what happened>` files a note on demand. (A later release adds automatic filing when a Claire dispatch itself errors.)
  - **It files a real report, not a mention.** The marker counts only when it is the final, left-margin, unfenced block of the reply — so the constant discussion and examples of the marker format (especially while developing Claire) are never mistaken for a filed report.
  - **Private by construction:** reports are written only to the fixed private queue (never a project-derived path); the queue carries its own ignore guard so it can't ride into a tracked repo; and the filing step strips any environment override that could redirect it.
  - **Diagnosable, never silent:** whenever a marker is present, the filing step records its decision (filed, or exactly why not) to `~/.claude/claire/feedback-fire.log`, so a dropped report is visible rather than a mystery. Quiet on ordinary turns.
  - **Set-up:** `setup-feedback.sh` wires the filing step into your settings once (like `setup-receipts.sh`) — safe to re-run, uninstall-clean.
  - **Verified:** built test-first, then put through a hand-written breaker harness and a fresh-context adversarial re-gate that caught and fixed two ship-blockers — a quadratic-regex turn-stall on repeated markers, and a no-intent-gate spam vector — plus a privacy hole (an environment override that could redirect the write) before release. Claire's own de-primed critic reviewed the design.

## [0.8.2] - 2026-06-21

### Fixed
- **Critical: de-priming injection no longer hard-blocks the very dispatch it protects.** When 0.8.0/0.8.1 rewrote a critic dispatch to inject the audited brief, it dropped a field (`description`) that the Agent/Task tool **requires** — so the harness rejected the whole rewritten dispatch *after* the hook returned (past its fail-open net), and every properly-receipted adversarial dispatch, including the live `/claire:challenge` path, died with a hard error instead of running. The gate now overwrites **only** `prompt` and preserves every other field. (The dropped field is a UI label the critic never reads, so removing it bought no de-priming and only broke the dispatch.) Pinned by a regression test asserting the injected dispatch keeps all required fields. Caught by the live end-to-end injection probe — the one check the unit/eval layers could not substitute for.

## [0.8.1] - 2026-06-20

### Fixed
- **`/claire:doctor`'s live self-test now works on 0.8.0 — it was false-reporting de-priming as "off" on a healthy install.** 0.8.0 keys each leak-audit receipt by a one-time id the brief carries (`[CLAIRE-RECEIPT:<id>]`), but the doctor's self-test still dispatched the auditor with the brief as "the entire prompt — nothing else" (no id), so no receipt was ever written and the doctor concluded enforcement wasn't on — and offered `setup-receipts.sh`, which couldn't fix it. The self-test now tags the audit with an id and checks for that id's receipt file. De-priming itself was never affected; this was only the health check misreading a healthy install.

## [0.8.0] - 2026-06-20

### Changed
- **De-priming now works by INJECTING the audited brief into the critic — replacing the fingerprint-matching that generated every recent spine bug.** Until now the gate proved "the brief the critic gets was leak-checked" by computing a normalised text *fingerprint* of the brief on both sides (auditor and critic) and comparing them; because the orchestrator built those two texts separately and the harness mutates one of them (a "[standing invitation]" coda), every hole was an edge case in that normalisation — coda asymmetry, a pre-tag preamble, a coda-tail steer, a tag-quoting false alarm. 0.8.0 deletes the comparison. On a clean leak-audit the audited brief is stored **verbatim**, keyed by a one-time id the orchestrator places on *both* the audit and the critic dispatch; a PreToolUse hook then looks that id up and **overwrites the critic's whole prompt with the stored brief**. The critic reasons from exactly what the auditor cleared, by construction — there is nothing to normalise and nothing to compare.
  - **Consequences:** an anchored orchestrator **cannot** send un-audited or steered text to the critic (its prompt is discarded); the critic is fully context-starved; and the entire fingerprint / coda-stripping / `[DEPRIMED-BRIEF]`-tag machinery — every recent bug's habitat — is gone. Verified live on macOS Desktop: a plugin hook's prompt-rewrite reaches the subagent, and the harness coda appends to the *rewritten* prompt (the original does not survive).
  - **Folded in:** the un-gated `Plan`/`Explore` fallback is **eliminated** (under injection it could silently de-fang the critic); **every critic is now fully tool-less** (closing a runtime-file/web-read channel — a fresh-context re-gate caught `dialectical-scout` silently inheriting all tools because it had no `tools:` line); and the clean-verdict check is anchored to the auditor's verdict line, killing a false "no receipt" warning when a clean audit merely quotes a lean example.
  - **Pinned by** 101 unit tests (byte-for-byte injection; fail-closed on a forged/absent/expired id; a frozen real-auditor-prose corpus for the verdict parser; a coverage test asserting every injected critic is tool-less) and a 3-arm free-form eval graded by the live leak-auditor, with a fresh-context adversarial re-gate that found — and this release fixes — the one real hole. The receipt writer's `setup-receipts.sh` registration is unchanged.

## [0.7.2] - 2026-06-20

### Fixed
- **The probe-auditor pre-check is dispatched by its namespaced name, and the leak-check names a third rationalization it must resist.** Two small tightenings to the `/claire:challenge` de-priming discipline, in the same skill:
  - **Namespaced probe-auditor dispatch.** The "is this rigged?" pre-check — run before any probe that tests whether a behaviour fires — is now dispatched as `claire:probe-auditor`, not the bare name. A bare `probe-auditor` resolves to a workspace-local agent of the same name when one exists, silently running a drifted local copy instead of Claire's — and the de-priming receipt gate fires only on the `claire:` form, so a bare dispatch lost both at once. The chosen critic was already namespaced (Step 3); this closes the same gap on the Step 2 demand-characteristics pre-check (and the Step 1 routing row).
  - **A third named rationalization for skipping the leak-check.** The leak-check already warns against two excuses ("my brief is already neutral", "the adversary will catch any lean anyway"); it now also names "the attacker is structurally de-primed, so a minimum-context critic can't be steered" — and why it is wrong: context-starving and leak-checking are **orthogonal**. Starvation controls the critic's own priors; the leak-audit controls whether the *brief* leans, and the brief is the one channel a starved critic must trust. A starved attacker handed a leaning brief is still steered. (Observed live as a real skip rationalization.)

## [0.7.1] - 2026-06-20

### Fixed
- **The leak-audit now covers the WHOLE critic prompt, including anything before the brief tag — closing the pre-tag unaudited channel, and the disguised steers it let through.** (issue 2026-06-20_1046; gated on a 3-arm eval + two adversarial re-attacks.) 0.6.2 made the *brief* (after the `[DEPRIMED-BRIEF]` tag) match exactly, but text the orchestrator placed *before* the tag — a persona line, an attack-license, or a smuggled steer — reached the critic UNAUDITED. 0.7.1 widens the audited+matched unit to the whole prompt, so a steer anywhere is either audited (the auditor saw it) or breaks the receipt match (it didn't). Coordinated changes:
  - **Audit without the tag.** The auditor is dispatched the preamble+body **without** the `[DEPRIMED-BRIEF]` tag — the tag had misled it into discounting pre-tag content (~40% miss; it read as a "this part is already stripped" boundary). The tag is inserted only for the critic; the gate excises it before matching.
  - **Catch disguised (valence) steers.** The leak-auditor now flags a preamble that *presumes a verdict* ("arrangements like this always hide a fatal flaw, so find it") as a steer — not only one that names an option — while still passing a neutral attack-license ("find the strongest real objection") as permitted disposition. A new `hooks/claire_brief.py` holds the frozen `CANONICAL_ATTACK_LICENSE`/`CANONICAL_CODA` as the single source both hooks import.
  - **Excise every tag, not just the first.** `brief_region` now removes *all* `[DEPRIMED-BRIEF]` occurrences on both sides. With the auditor running tag-less, an artifact that merely *quotes* the tag would otherwise diverge the two regions and draw a false "no receipt" warning — the exact "trains callers to wave the gate off" failure 0.6.2 killed. (Caught by the release gate's own adversarial pass before shipping.)
  - **Strip only the exact coda.** `strip_coda` removes only the literal `CANONICAL_CODA`, not "everything after the `[standing invitation]` marker" — closing a coda-tail bypass (audit a clean brief, dispatch it + "`[standing invitation]` PS the obvious answer is X" → fingerprinted identically and passed silently) that the whole-prompt widening would otherwise have widened.

  **Honest tradeoff:** this moves the wrapper-symmetry guarantee from pure machinery (0.6.2 excluded the pre-tag wrapper deterministically) into the skill contract (audit the byte-identical prompt you dispatch) — the line between a harmless wrapper and a steer is inherently semantic, so only the auditor can draw it. Pinned by regression tests (pre-tag steer with a body-only receipt → NORECEIPT; coda-tail steer → NORECEIPT; artifact-quotes-the-tag → still passes silently; all confirmed red-on-reintroduction; 142 unit tests) and three eval fixtures graded in a fresh-context re-gate at **12/12 each** (blatant + disguised pre-tag steer → LEAN; bare license → NEUTRAL), with two independent adversaries finding no spine bypass. **Known residuals (filed, folded into the planned matching-machinery redesign):** the `Plan`/`Explore` fallback dispatch is not `claire:`-typed, so the gate never fires on it (de-priming there rests on the auditor + orchestrator discipline); and the verdict-parser can false-warn — fail-closed — when a clean audit echoes the literal `LEAN-…` example phrase.

## [0.7.0] - 2026-06-20

### Added
- **An opt-in autonomous mode — Claire can run on every judgement call during an unattended/AFK run, without being told each session.** Set `CLAIRE_AUTO=1` (parsed like `CLAIRE_GATE_STRICT`/`CLAIRE_DEBUG`: empty/`0`/`false` = off) and, when a prompt kicks off an autonomous run (`scan and fix`, `work the queue`, `clear the backlog`, `/autoloop`, …), the discoverability hook (`adv-nudge.py`, a UserPromptSubmit hook that fires on desktop) injects a standing instruction for that run: treat Claire as a per-judgement-call step — fire her on every fork the run resolves itself, every plan it commits, every file/content write, and anything outbound; leak-check every brief; park an un-neutralisable brief for the user rather than proceeding; never auto-approve on her verdict (she critiques, she does not bless). Mechanical steps with no judgement call fire nothing. Gated by **both** the flag and an autonomous-run lexicon, so a flag left on cannot bleed Claire into interactive work — "nothing fires until you invoke her" still holds interactively, and arming an unattended run is itself the invocation. This automates the validated manual practice of telling a session to use Claire on every judgement call before going AFK. `/claire:doctor` reports whether the mode is armed. Pinned by unit tests (arms on autonomous kickoffs with the flag set; silent without it; silent on interactive prompts even with the flag on; falsey flag values read as off). **Scope note:** this first cut is the standing-instruction half — it relies on the run honouring the instruction, exactly as the validated manual practice did. A planned follow-up adds an omission-watcher that makes a *skipped* Claire pass visible (and, under strict mode, blocking) rather than trusting the run not to skip. **Pre-release diagnostics:** the trigger arms correctly across 19 realistic prompts (autonomous → armed, interactive → silent, no bleed); and a controlled A/B (4 control / 4 treatment, self-contained queue, probe-audited) showed *selective* firing driven by genuine judgement, not keyword-matching — a 0/20 control baseline, treatment firing 4/4 on the two real judgement calls and 0/4 on both mechanical steps, with the de-priming spine held on every fire (leak-checked brief; an un-closable fork parked, not blessed). **Known edge:** on a low-stakes *settled-facts* outbound recap, 3/4 runs reasonably scaled down and did not fire despite the instruction's "anything outbound" — so that clause is a deliberately safe over-claim (it says fire; the run may scale on a trivial recap), not a guarantee. Two things to confirm in a live armed run: real critic dispatch (the diagnostic could only narrate intent, not spawn the critic), and whether a settled-facts outbound write should force a pass.

## [0.6.2] - 2026-06-20

### Fixed
- **The de-priming gate's receipt-matching is now exact — closing a hole that let a steer reach the critic, and the false alarms that hid it.** Live use (2026-06-20) surfaced that a brief audited **CLEAN** could still carry a steer to the critic: the audit ran on the situation+question, then a short steering "ask" was appended before dispatch, and the gate passed it. Root cause: the receipt fingerprinted the *auditor's whole prompt* while the gate measured the critic's *after-`[DEPRIMED-BRIEF]`-tag region*, bridged by a fuzzy match (≥60% coverage, or a prefix + ≤240-char trailing slack). That bridge leaked **both** ways — it false-alarmed `NORECEIPT` whenever the auditor prompt carried a wrapper the critic region lacked (the spurious warning that trained callers, and earlier autonomous sessions, to wave the gate off as "an accounting artifact"), and it false-passed any steer short enough to fit the 240-char slack. Both now closed: the receipt and the gate compare the **same canonical brief** — the text after the first tag, coda-stripped + normalised — by **exact equality**. A wrapper before the tag is excluded on both sides (no false alarm); anything appended or edited after the audited brief changes the region and is correctly flagged (no false pass). The skills now instruct building the brief once as a tagged string and sending it **byte-identical to both auditor and critic**, with the attack-license/persona preamble strictly *before* the tag. `NORECEIPT` is meaningful again — which is what makes strict mode safe to turn on (the recommended `CLAIRE_AUTO + CLAIRE_GATE_STRICT` AFK pairing depended on this). Under `CLAIRE_DEBUG`, a `NORECEIPT` now prints the dispatched brief next to what was actually audited, so a mismatch is diagnosable rather than dismissed. Pinned by regression tests: a wrapped auditor prompt no longer false-alarms; a steer appended after a clean audit is caught (the old 240-slack would have passed it — confirmed by simulation); the receipt fingerprints the after-tag region; and the 0.5.3 large-artifact assembled-audit case still passes (exact equality has no size ratio, so it does not reintroduce that false-block). Found via two live autonomous sessions. **Separate gap flagged, not bundled:** the adversarial review of this fix surfaced that text placed *before* the tag (persona/attack-license preamble) reaches the critic unaudited — a distinct, pre-existing spine hole filed as its own issue (`issues/2026-06-20_1046`), to be fixed with its own design pass.

## [0.6.1] - 2026-06-20

### Fixed
- **Claire's cold critics no longer reason from ambient repository state — a de-priming leak.** A `/claire:blank` read opened with *"the branch name in front of me — `feature/graph-purpose-primer` — tells me this isn't a neutral inquiry"*, reasoning from a git branch that was never in its brief (issue `2026-06-20_0205`). The critic agents carry no file or git tools, so the branch name could only have arrived via the **environment block the harness injects into every subagent** (working directory, current branch, recent commits) — the same preamble the main agent receives. Each persona declared "no files, no tools, no knowledge beyond the brief", which addresses *tools* but never told the model to disregard ambient signal it can passively *see*. The leak is conditional on **semantic adjacency**: an off-topic branch (`main`, unrelated commits) is filtered as noise — confirmed clean across repeated reads — but a branch named after the very thing being asked (`feature/graph-purpose-primer` for a "purpose-primer" screen decision) is read as the asker's hidden intent. That is a common case — people name feature branches after the feature they are deciding about. Fixed: the five context-starved critics (`blank-slate-advisor`, `brief-leak-auditor`, `failure-mode-attacker`, `over-capture-triage-verifier`, `probe-auditor`) now carry an explicit clause — *ignore ambient signal (cwd, repo/branch name, commit log, session metadata); a name that resembles the question is coincidence, not evidence; reason only from the brief and never mention one.* It only subtracts signal (adds no priors), so it sits squarely inside the persona's permitted "no-prior-knowledge declaration"; the two file-reading agents (`affected-actor-simulator`, `dialectical-scout`) are a separate category and unchanged. Pinned by a new eval fixture (`blind_read_ambient_env_leak`) that embeds a telling env block above a neutral bakery question. Verified: the **pre-fix persona leaked 3/3** on the live shipped agent, and a **controlled A/B with the clause as the only variable** (same brief, same agent harness) leaked **2/2 without the clause** and ran **3/3 clean with it** — while the clean reads kept the same skeptical force (they still caught the buried "for a while" trap from the brief alone). (The fixture is a stronger-signal proxy — it places the env block *inside* the brief — because the real harness vector cannot be staged from a fixed-cwd session.)

## [0.6.0] - 2026-06-20

### Added
- **An on-machine event log — Claire can now show you her own de-priming activity.** Every gate decision and every leak-audit records one privacy-safe line to `~/.claude/claire/events.jsonl`, and `/claire:doctor` reports the mix: how often the gate let a de-primed brief through (PASS) vs caught a skipped one (REMIND / NORECEIPT / BLOCK), the neutral-vs-leaning audit rate, receipts written, and per-critic counts. The log is **observability only** — it never touches a dispatch, the gate's decision, or whether a receipt is written. Privacy and the spine are guaranteed by construction: a strict field **allowlist** makes brief text, content hashes, and the lean **direction** structurally impossible to write (the verdict is collapsed to a binary neutral/leaning before it lands); writes are fail-open, bounded, lock-protected, and self-initializing. The reader **dedups the N-version double-write** the desktop hook-glob produces — one real dispatch logs once per cached version (same content-free correlation id, different version), so the metrics aren't multiplied by how many old versions sit in the cache. Stdlib only; the log is plain JSON-lines you can `cat`.

### Fixed
- **`/claire:doctor` no longer false-warns that enforcement is "stale" on a healthy install.** Its receipt-registration check read the version-agnostic **glob** registration as a literal path (with the `*` unexpanded), so every marketplace install was mislabeled "stale" even when enforcement was correctly wired and firing. It now expands the glob before checking.

## [0.5.3] - 2026-06-19

### Fixed
- **A neutral brief that pastes in a large document for review no longer draws a false "no receipt" warning — and the fix strengthened the de-priming rather than relaxing it.** The symptom: leak-audit the framing, then inline a big artifact (a draft, a plan, a chapter), and the gate warned `NORECEIPT` because the audited framing covered far less than the dispatched whole. The tempting fix — mark the artifact and exclude its bulk from the gate's coverage check — was caught as a **spine hole** by dogfooding Claire's own critics: an artifact excluded from coverage *and* never audited can carry the author's hoped-for answer straight to the critic, unchecked (the same shape as the decoy attack the coverage floor exists to stop). So the gate's matching logic is unchanged. The real fix is a workflow rule, now stated in both skills: **leak-audit the FULLY ASSEMBLED brief — the framing plus the inlined artifact, byte-for-byte what the critic receives** — never the framing alone with the artifact added after. The artifact is the most important part of the check, not an exemption; the gate's `NORECEIPT` message now names the assemble-then-inline mistake as the most common cause. Separately, the gate located the brief by the *last* `[DEPRIMED-BRIEF]` tag, so an artifact that merely *quotes* the tag — common when Claire reviews Claire's own docs — truncated the checked region and false-warned even when correctly audited; it now uses the *first* tag (the delimiter the orchestrator places), so the whole brief, embedded tag-text and all, is what gets matched. Three regression tests pin it: an assembled brief passes, a framing-only receipt with an unaudited artifact still warns, and an artifact quoting the tag still matches.

## [0.5.2] - 2026-06-19

### Fixed
- **Context-starved critics could fabricate an artifact they were pointed at — and were silently granted all tools.** Three prompt-only critics (`failure-mode-attacker`, `over-capture-triage-verifier`, `probe-auditor`) declared `tools: []`, which the harness reads as "inherit **all** tools", not "none" (the session registry showed them as "All tools"). So a critic whose own prompt said *"work entirely from the brief"* had full tool access, and when an orchestrator pointed it at a file path it **fabricated the file's contents and critiqued the fiction** (`tool_uses: 0`) — a silent integrity failure caught only because the orchestrator happened to hold the real file. A critic inventing what it critiques is worse than a leak. Fixed: the three now declare a real restriction (`tools: TaskCreate`, the project's proven prompt-only marker), and every work-from-the-brief critic carries an explicit guard — *if the artifact is not present in your brief, stop and say so; never reconstruct it from memory.* New regression test (`test_agent_tools.py`) pins both at the manifest layer, and a test-hermeticity gap (the receipt↔gate integration test inherited an ambient `CLAIRE_DEBUG`) is closed. Whether critics *should* read files is a separate, spine-delicate question (roadmap C), deliberately not addressed here. Found by dogfooding Claire on a real long document — it fabricated a critique of a document it could not actually see.

## [0.5.1] - 2026-06-19

### Fixed
- **Receipt no longer certifies a LEANING brief that opens by dismissing neutrality** — a de-priming enforcement hole. When the leak-auditor flags a lean it often opens with a dismissive *"GENUINELY-NEUTRAL — does not apply here … Verdict: LEAN-x"*. The receipt writer's clean-check used a "neutral appears before lean" ordering rule, so that leading (un-negated) clean token read as clean and a receipt got written for a brief the auditor had actually flagged — which let the de-priming gate go **silent on a primed dispatch**, defeating enforcement. `is_clean_verdict` now treats an *asserted* LEAN verdict as decisive over any earlier dismissive neutral (a *declined*-lean mention in a genuine pass is still read as clean). The same parsing weakness was hardened in the eval runner's verdict parser. Found by dogfooding — a blind-authored, de-primed test pass over the gate hooks plus direct observation of the live auditor's real output; regression-pinned.

### Added (tests / dev)
- Blind-authored unit suites for both gate hooks (`tests/unit/test_gate_blind.py`, `test_receipt_blind.py`), written by a fresh context from the behavioural spec + I/O contract only — never the source — as independent coverage alongside the primed suites.
- A `leak_audit` eval fixture whose brief is a primed **test plan** (`leak_primed_test_plan.json`), pinning that the leak-auditor flags an implementation-mirroring test plan as LEAN.
- A unit test for the eval runner's verdict parser (`test_eval_verdict_parse.py`).

## [0.5.0] - 2026-06-19

### Added
- **A developer trace switch — `CLAIRE_DEBUG`.** Set `CLAIRE_DEBUG=1` and every Claire dispatch surfaces a one-line under-the-hood trace: the gate's decision and whether a receipt matched (from `adversarial-gate.py`), plus the leak-audit verdict and whether a receipt was written (from `record-audit-receipt.py`). The `/claire:challenge` and `/claire:blank` skills render these as a `TRACE` section after Claire's read. It is **off by default**, reaches no normal user, and is pure visibility — it never changes how a brief is de-primed, which decision the gate takes, or whether a receipt is written (guarded by unit tests, including a strict-mode-still-blocks-under-debug case). The point: building on Claire's de-priming layer, you can finally watch it work — see the brief next to the verdict — which is the instrument every later feature needs to be verified spine-safe before it ships.

## [0.4.6] - 2026-06-17

### Changed
- **The leak-auditor now audits ANY adversary brief, not only two-option decision briefs.** Handed a plan, a claim, or an open question, the old persona would decline ("no A-vs-B here, not my job") and answer the underlying question instead — which skipped the neutrality check *and*, because it never returned a clean verdict, stopped a receipt from being written, so de-priming enforcement looked broken. It now judges whether a brief of any shape telegraphs the conclusion the asker is hoping for, keeping the `GENUINELY-NEUTRAL` / `LEAN-<…>` verdict the receipt mechanism reads.

## [0.4.5] - 2026-06-17

### Fixed
- **Enforcement now survives marketplace updates.** A marketplace install lives at a version-numbered path (`…/claire/<version>/…`) that changes on every update, so the settings.json receipt registration would go stale each time. `setup-receipts.sh` now registers a **version-agnostic glob** for marketplace installs (a clone install keeps its stable direct path), so enforcement keeps firing across updates with nothing to re-run.
- **`/claire:doctor`'s live self-test no longer false-negatives.** Its fixed test brief was so abstract ("two suppliers documented equally well, on equal terms") that the leak-auditor correctly *refused* to audit it — no verdict, so no receipt — which looked like broken enforcement. Replaced with a textured-but-neutral brief that earns a real `GENUINELY-NEUTRAL`.

## [0.4.4] - 2026-06-17

### Fixed
- **Migration is now smooth end to end.** When you switch install methods the old registration in `~/.claude/settings.json` points at a path that no longer exists; `/claire:doctor` now (a) reports that registration as *stale* rather than a misleading "OK" (it verifies the path exists), and (b) offers to re-point it on **any** missing-receipt result, not only when the entry is absent. So after migrating clone ↔ marketplace, one `/claire:doctor` re-enables enforcement.

## [0.4.3] - 2026-06-17

### Added
- **`/claire:doctor` offers to turn on receipt enforcement for you.** On the Desktop app the receipt writer needs a one-time registration in `~/.claude/settings.json` (a plugin's PostToolUse hook doesn't fire there); the doctor now detects when it isn't wired and offers a one-`yes` enable — no terminal. The README now leads with the **marketplace install** (plug-and-play) and points enforcement setup at `/claire:doctor`.

### Changed
- `setup-receipts.sh` is migration-safe: switching install methods (clone ↔ marketplace) changes the install path, so the script now **re-points** an existing registration at the current install (and clears a stale one) instead of seeing any prior entry and skipping.

## [0.4.2] - 2026-06-17

### Fixed
- **Receipt-backed de-priming enforcement now actually fires on the Claude Desktop app.** The receipt writer is a PostToolUse hook, and a plugin's PostToolUse hooks do not fire on Desktop (its PreToolUse hooks do) — so no receipt was ever written, the gate could never go silent, and de-priming degraded to an unconditional nag on every dispatch. Three fixes land together: (1) a new **`setup-receipts.sh`** registers the receipt writer in `~/.claude/settings.json`, where PostToolUse hooks *do* fire — run it once per machine; the registration is uninstall-safe (a missing script becomes a no-op, never a hang) and idempotent. (2) The clean-vs-leaning verdict is now read **by position**: the leak-auditor discusses leans even when it passes (e.g. "I considered a faint LEAN-One but am declining … GENUINELY-NEUTRAL"), so a clean pass is recognised by `GENUINELY-NEUTRAL` appearing *before* any `LEAN-<option>` token, instead of scanning for the word "lean" anywhere and wrongly suppressing the receipt. (3) Both hooks **strip the harness-appended "[standing invitation]" coda** before fingerprinting — it is added to a subagent prompt between the gate's read and the receipt writer's read, and would otherwise make the two fingerprints never match. `/claire:doctor` now checks the settings.json registration. Verified end-to-end live.
- `.gitattributes` pins LF line endings on `.sh`/`.py` (and all text) so the scripts run on Linux regardless of a checkout machine's git `autocrlf` setting — a seedbox clone had received CRLF-mangled scripts that failed to execute.

## [0.4.1] - 2026-06-17

### Changed
- Cleaner plugin description — dropped the internal hook/receipt mechanics from the user-facing blurb.

### Added
- `docs/design-principles.md` — the *why* behind how Claire shows her critic (synthesize on agreement, preserve on disagreement; translate, never outvote) and why the brief gets a separate audit rather than self-certification, captured from findings during the build.
- A "Where the name comes from" note in the README (the `.claire` typo origin and the Challenge Officer title).
- ROADMAP items D (make her presence felt) and E (a `CLAIRE_DEBUG` hatch); a presentation rule + pointer in `CLAUDE.md`.

## [0.4.0] - 2026-06-17

### Added
- **`/claire:doctor`** — a health- and conflict-check for a Claire install. Filesystem checks (dependencies, install integrity, **duplicate installs**, agent-name collisions with the current workspace, leftover old tools) via `doctor.sh`, plus a **live self-test** that dispatches the leak-auditor and confirms a receipt is written — i.e. that de-priming enforcement is actually firing on this machine, which tells you whether strict mode is safe to enable here.

### Changed
- **The de-priming gate now acts only on Claire's own (`claire:`-namespaced) critics**, not on a workspace's same-named local agents. Installing Claire no longer injects de-priming reminders into an unrelated project that happens to have its own `failure-mode-attacker` (etc.), and her skills now dispatch the `claire:`-prefixed agents so she always uses her own version even where a same-named local agent exists. The doctor's live self-test is the per-machine backstop if a harness ever fails to namespace.

## [0.3.0] - 2026-06-17

### Added
- **Chat edition** (`chat/`) — a prompt-only custom Agent Skill that brings Claire's de-priming discipline and cold-critic persona to regular Claude chat (claude.ai / the Claude apps), where hooks and separate subagents don't exist. It de-primes in two visible phases within one conversation, and is honest that it's the discipline, not the enforced separation of the plugin. Install via claude.ai → Settings → Skills, or paste into a Project's custom instructions. See `chat/README.md`.

## [0.2.1] - 2026-06-17

### Fixed
- **The gate no longer fires on the leak-auditor itself.** A brief that quoted the `[DEPRIMED-BRIEF]` tag or used the word "deprimed" tripped the backstop word-match (`deprime` matched inside `deprimed`), so dispatching `brief-leak-auditor` — the de-priming *checker* — drew a false warning. The checker is now never gated, and the phrase backstop matches only at word boundaries, so ordinary discussion of de-priming no longer false-triggers.

### Added
- **Strip-authorship-signals** step in the de-priming checklist (`/claire:challenge`): don't reveal that the asker built the thing under review — a reviewer who can tell the author is asking softens the critique regardless of wording. Surfaced by Claire's own leak-auditor, which passed a review brief as neutral but flagged the residual authorship-leak.
- Regression tests for the leak-auditor-never-gated and word-boundary cases.

### Changed
- CI: validate only `plugin.json` (and assert `marketplace.json` stays absent, as the clone-install requires); run the project's own test runner instead of pytest. Fixes the red `validate-manifests` job left over from removing `marketplace.json`.

## [0.2.0] - 2026-06-17

### Changed
- **The de-priming gate no longer trusts a self-typed marker.** Previously a critic dispatch carrying the `[DEPRIMED-BRIEF]` marker passed the gate silently — but the main agent types that marker itself, so it could skip the leak-check and still pass. The gate now requires a *receipt* proving the leak-auditor actually cleared the exact brief; the marker alone buys nothing. This closes the loophole an anchored agent used to rationalise past the de-priming step.

### Added
- `record-audit-receipt.py` (PostToolUse hook): writes a short-lived, git-ignored receipt — a fingerprint of the brief — only when `brief-leak-auditor` returns a clean verdict. The gate reads these receipts.
- **`CLAIRE_GATE_STRICT=1`**: opt-in environment variable that makes the gate *block* a critic dispatch lacking a receipt (PreToolUse deny) instead of warning. Off by default, so a public install never hard-blocks; recommended on your own machines.
- **Bounded, escalating fix loop** in `/claire:challenge` and `/claire:blank` for a brief that fails the leak-check: paste the auditor's own neutral rewrite verbatim, re-audit, cap at two cycles, and escalate to the user with the persistent lean named — never silently proceed.
- Unit tests for the receipt writer and the receipt-aware gate (including stale-receipt, decoy-coverage, and strict-mode cases).

## [0.1.0] - 2026-06-17

### Added
- `/claire:challenge` command: routes a plan, claim or decision to the right kind of critic (plan-attacker, cold outside read, actor role-play, source-vs-claim check, two-sides face-off, probe audit), de-priming the brief first.
- `/claire:blank` command: a cold, no-context outside read from a context-starved advisor.
- Seven scoped subagents (blank-slate-advisor, failure-mode-attacker, affected-actor-simulator, brief-leak-auditor, dialectical-scout, over-capture-triage-verifier, probe-auditor).
- `adversarial-gate.py` (PreToolUse hook): reminds the main agent to de-prime and leak-check before an adversarial dispatch. Fail-open.
- `adv-nudge.py` (UserPromptSubmit hook): surfaces a one-line pointer when a prompt reads like a request for a critique. Fail-open.
- `plugin.json` manifest. Deliberately not always-on — nothing fires without an explicit `/claire` invocation.
- MIT License.
- This changelog.

[Unreleased]: https://github.com/janikithup/Claire/compare/v0.4.6...HEAD
[0.4.6]: https://github.com/janikithup/Claire/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/janikithup/Claire/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/janikithup/Claire/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/janikithup/Claire/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/janikithup/Claire/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/janikithup/Claire/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/janikithup/Claire/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/janikithup/Claire/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/janikithup/Claire/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/janikithup/Claire/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/janikithup/Claire/releases/tag/v0.1.0
