# Claire tests

Claire is built from two kinds of parts, and they are checked in two different
ways. **Mixing them up is the main way this project goes wrong.** This folder has
one directory per layer.

```
tests/
  unit/      deterministic — runs in CI, must be 100% green
  evals/     distributional — measures Claire's non-deterministic behaviour
  contracts/ frozen external schemas Claire's output must satisfy (data, not tests)
```

## The two-layer philosophy

**The plumbing is deterministic — unit-test it.** Hooks, schema checks, manifest
sync, dispatch wiring: ordinary software, same input → same output every time.
These are unit tests. They must pass on every commit; one red unit test blocks the
release. We hold them to the test-first bar in Claire's CLAUDE.md: *would this test
fail if the bug came back?* Each test names the bug it guards in its docstring, and
every one has been confirmed to go red when that bug is reintroduced (see
"Are these real tests?" below).

**Claire's behaviour is non-deterministic — eval it, never unit-test it.** The
parts where Claire *reads* a brief, judges whether it leaks the author's answer,
and decides what to strip are model calls: the same prompt can come back slightly
different. **A single run is noise.** You cannot assert one expected string. So
instead we draw **N samples** per case and measure a **pass-rate** against the
*properties* a good output must have. A behaviour is "passing" when its pass-rate
clears the fixture's threshold — a distribution, not a point.

Why the split matters: if you unit-test behaviour, you get a flaky suite that
fails at random and trains everyone to ignore red. If you eval the plumbing, you
burn model calls measuring something that was deterministic all along. Put each
part in its own layer.

---

## Layer 1 — unit tests (`tests/unit/`)

Deterministic. Zero dependencies — bare `python3`, no pytest, no pip install (so
CI needs nothing). A tiny runner (`_runner.py`) discovers and runs every
`test_*.py`.

**Run them all:**

```bash
python3 tests/unit/_runner.py
```

Exit code is 0 if all pass, 1 if any fail. Run a single file directly, e.g.
`python3 tests/unit/test_gate_depriming.py`.

What's covered:

| file | guards |
|------|--------|
| `test_gate_depriming.py` | the de-priming gate: REMIND on an adversarial dispatch with no `[DEPRIMED-BRIEF]` tag, silent PASS with it, namespace-prefixed agent names match, ordinary dispatches stay silent, fail-open on bad input. Driven by crafted stdin JSON straight into the hook. |
| `test_nudge_trigger.py` | the discoverability nudge fires on critique-shaped prompts **and not** on ordinary ones (the negative half is what protects the product from becoming noise). |
| `test_manifests.py` | `plugin.json` and `marketplace.json` are valid JSON with the required fields, the two names agree, and **the version is in sync across `plugin.json`, `marketplace.json`, and the top of `CHANGELOG.md`** — the classic "bumped the manifest, forgot the changelog" release bug. |
| `test_gate_inject_contract.py` | the gate's injected `updatedInput` still satisfies the Agent/Task tool's **required-field schema**, checked against a *frozen external copy* (`../contracts/agent_tool_input.schema.json`) rather than the gate's own code — so **any** dropped required field is caught, not just the known `description` (the 0.8.0/0.8.1 hard-block, hotfixed 0.8.2). Driven through the shipped gate. |

The gate and nudge tests drive the **shipped hooks** in `../hooks/`
(`adversarial-gate.py` and `adv-nudge.py`) — so the unit suite pins the behaviour
of the code that actually ships, not a copy.

The manifest tests target the **real** release artifacts at the project root, so
they protect what actually gets published.

---

## Layer 2 — evals (`tests/evals/`)

Distributional. Measures Claire's behaviour by dispatching her own agents (she
dogfoods: the leak-auditor and blank-slate reader that grade the fixtures are the
same tools she ships).

**Fixture format** — `evals/fixtures/SCHEMA.md` is the full spec. In short, each
fixture is a JSON file pairing a decision-brief with the *properties* a good
output must have, an `n_samples` count, a `pass_threshold`, and a list of
`scorers`. Three `kind`s:

- `leak_audit` — feed the leak-auditor a brief, assert the verdict it should reach
  (e.g. *this primed brief must be flagged **LEAN** and the auditor must name the
  smuggled answer*).
- `blind_read` — feed Claire a neutral situation, assert she raises a real
  structural objection and never echoes an answer she was never given.
- `depriming_delta` — run the same advisor on a **primed** brief and its
  **de-primed** version, assert the two outputs **differ**. This is the fixture
  that proves de-priming is load-bearing, not decorative.

**Starter fixtures** (in `evals/fixtures/`):

- `leak_primed_dashboard_rollout.json` — a "we should ship Friday, just confirm"
  brief → must be flagged LEAN.
- `blind_read_neutral_vendor.json` — a neutral build-vs-buy situation → Claire
  must raise a structural objection without a leaked-answer tell.
- `delta_methodology_choice.json` — survey-vs-interviews, primed vs de-primed →
  recommendations must diverge.

**Run them:**

```bash
# CI smoke — deterministic fake dispatcher, no model calls. Proves the runner,
# loaders, and scorers all work end to end.
python3 tests/evals/run_evals.py --fake

# Real run — requires wiring the dispatcher to the live model (see below).
python3 tests/evals/run_evals.py

# One fixture, more samples, per-sample detail:
python3 tests/evals/run_evals.py --fixture leak_primed_dashboard_rollout --samples 20 --verbose
```

**What's concrete vs stubbed:** everything except the model call is real and
runnable today — fixture loading, the N-sample loop, all five scorers, pass-rate
aggregation, and the report. The **one** stubbed seam is
`dispatch_claire_agent()`: in real use it invokes a Claire subagent (shell out to
the Claude Code CLI selecting the named agent, or call the Agent/Task tool API)
and returns the agent's text. It raises `NotImplementedError` until wired. Pass
`--fake` to run a deterministic stand-in dispatcher that exercises the entire
runner without a model — that's the CI smoke test for the eval harness itself.

**When a fixture fails**, that failing case becomes a new permanent fixture so the
behaviour is pinned going forward (the CLAUDE.md rule). Don't delete a fixture that
caught a regression — that's the regression guard.

---

## Are these real tests?

Yes — each unit test was confirmed to **fail when its bug is reintroduced** (a
mutation check), not just pass on the happy path:

- neuter the gate's adversarial detection → the gate tests go red;
- loosen the nudge trigger to a common word → the "no ordinary prompt fires" test
  goes red;
- bump `plugin.json`'s version without touching `CHANGELOG.md` → the version-sync
  test goes red.
- drop a required field from the gate's injection (`new_input = dict(ti)` →
  `new_input = {}`) → the contract test goes red with `missing required field:
  description`.

A test that stays green when you break the thing it tests is protecting nothing.
