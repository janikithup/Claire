#!/usr/bin/env python3
"""
CLAIRE EVAL RUNNER (behaviour layer).

The eval layer measures Claire's NON-deterministic behaviour: how her leak-auditor
and blank-slate reader actually judge real briefs. A single run is noise, so for
each fixture we draw N independent samples, score every sample against the
fixture's properties, and report a pass-rate. A fixture PASSES when its pass-rate
meets its own threshold.

WHAT IS CONCRETE HERE (real, runnable today):
  - fixture loading + validation
  - the scoring functions (verdict_equals, names_the_lean,
    raises_structural_objection, does_not_name_expected_answer, outputs_differ)
  - the N-sample loop, per-fixture pass-rate, and the summary report
  - a deterministic FAKE dispatcher so `--fake` exercises all of the above in CI
    without any model call (this is how we test the runner itself)

WHAT IS STUBBED (needs the live model):
  - dispatch_claire_agent(): the one function that actually invokes a Claire
    subagent. In real use this shells out to `claude` (or the harness Agent API)
    with the named agent and the brief, and returns the agent's text. Here it
    raises unless --fake is passed. Wire it to your harness to run for real.

USAGE:
  python3 run_evals.py --fake              # CI smoke: proves the runner works
  python3 run_evals.py                     # real: requires a wired dispatcher
  python3 run_evals.py --fixture leak_primed_dashboard_rollout --samples 20
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(HERE, "fixtures")


# ---------------------------------------------------------------------------
# DISPATCH — the only model-dependent seam.
# ---------------------------------------------------------------------------

def dispatch_claire_agent(agent, prompt):
    """Invoke a Claire subagent with `prompt`, return its text output.

    STUB. Wire this to your harness, e.g. a subprocess call to the Claude Code
    CLI selecting the named agent, or the Agent/Task tool API. It must return the
    agent's raw textual response as a string.
    """
    raise NotImplementedError(
        "dispatch_claire_agent is a stub — wire it to the live model, "
        "or run with --fake to exercise the runner deterministically.")


# A deterministic stand-in so the runner's own logic is testable in CI.
# It returns plausible-shaped outputs keyed off the brief, NOT a real judgement —
# it exists only to prove loading/scoring/aggregation work end to end.
def fake_dispatch(agent, prompt):
    p = prompt.lower()
    if agent == "brief-leak-auditor":
        leaky = any(w in p for w in ("we should", "i've decided", "obviously",
                                     "confirm", "right?", "the right move"))
        if leaky:
            # echo a smuggled answer the fixture will look for (keyed off the brief so the
            # --fake smoke test exercises each leak flavour: a decision brief, and a primed
            # TEST PLAN that pushes implementation-mirroring tests)
            if "friday" in p:
                lean = "ship friday"
            elif any(w in p for w in ("test plan", "_items", "returns exactly what the code",
                                      "guaranteed-green", "solid test plan", "proves the calculator works")):
                lean = "the plan is sound (approve the plan as-is)"
            else:
                lean = "a survey is the way to go"
            return ("VERDICT: LEAN\nThis brief leaks the author's expected answer: "
                    "it pushes '%s' and asks only for confirmation, "
                    "not a genuine assessment." % lean)
        return "VERDICT: NEUTRAL\nThe brief states the situation without smuggling a conclusion."
    if agent == "blank-slate-advisor":
        # produce a structural objection; vary by whether the brief was primed
        if "survey" in p and ("i'm sure" in p or "confirm" in p):
            return ("A survey assumes you already know which variables matter. With this "
                    "small a group a survey will be underpowered and miss the reasoning you "
                    "care about. Recommendation: lean toward in-depth interviews.")
        if "under a dozen" in p or "in-depth interviews" in p:
            return ("With under a dozen people whose reasoning is the object of study, a "
                    "survey cannot reach the mechanism. Recommendation: interviews, "
                    "possibly with a small structured supplement.")
        return ("One real risk: moving the data to a vendor's servers trades a known "
                "maintenance cost for an unknown dependency and a data-control loss that "
                "is hard to reverse. Weigh that before the two-week deadline forces a rush.")
    raise ValueError("unknown agent %r" % agent)


# ---------------------------------------------------------------------------
# SCORERS — each returns (passed: bool, reason: str) for one sample.
# ---------------------------------------------------------------------------

# The leak-auditor's verdict vocabulary. A lean verdict is an uppercase "LEAN-<option>"
# token; a clean verdict is "GENUINELY-NEUTRAL". When it flags a lean the auditor often
# OPENS by dismissing neutrality ("GENUINELY-NEUTRAL - does not apply here ... Verdict:
# LEAN-x"), so a naive first-token grab mis-reads that as NEUTRAL. We therefore treat an
# ASSERTED lean (a LEAN-<x> token NOT in a declined/hypothetical context) as decisive,
# matching the receipt hook's is_clean_verdict. (Hole found 2026-06-19 from live output.)
_LEAN_TOKEN = re.compile(r"(?<![A-Za-z])LEAN-\w")
_NEUTRAL_RE = re.compile(r"genuinely-neutral", re.IGNORECASE)
_DECLINED_LEAN = re.compile(
    r"(?:declin|considered|faint|reject|hypothetical|tempt|weigh|might call|"
    r"could call|nearly)", re.IGNORECASE)


def _parse_verdict(text):
    # 0. Machine-readable first-line verdict (the auditor's output contract) — authoritative
    #    when present, kept in sync with the receipt hook's FIRST_LINE_VERDICT_RE (2026-06-21).
    fl = re.match(r"[*_`>~\s]*verdict\b\s*[:\-—]\s*(NEUTRAL|LEAN)\b", text, re.IGNORECASE)
    if fl:
        return fl.group(1).upper()
    # 1. An ASSERTED lean token wins outright, even under a dismissive neutral opener.
    for m in _LEAN_TOKEN.finditer(text):
        ctx = text[max(0, m.start() - 48):m.start()].lower()
        if not _DECLINED_LEAN.search(ctx):
            return "LEAN"
    # 2. An explicit verdict label — tolerant of markdown/fences (e.g. "**Verdict**\n\n`LEAN-x`"),
    #    kept in sync with the receipt hook's VERDICT_LABEL_RE (2026-06-21 fenced-verdict gap).
    m = re.search(r"verdict\b\W{0,12}(?:genuinely[- ]?)?(LEAN|NEUTRAL)", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 3. A non-negated, non-directional GENUINELY-NEUTRAL ("would move toward neutral" is not it).
    for m in _NEUTRAL_RE.finditer(text):
        before = text[max(0, m.start() - 24):m.start()].lower()
        if re.search(r"(?:not|n't|toward|towards|move\w*|would|closer|nearer|approach\w*|"
                     r"shift\w*|drift\w*|tip\w*|push\w*)\b[\s\W]*$", before):
            continue
        return "NEUTRAL"
    # 4. Fallback: first standalone LEAN/NEUTRAL token.
    m = re.search(r"\b(LEAN|NEUTRAL)\b", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def score_verdict_equals(sample, fixture, params):
    expected = (params.get("expected")
                or fixture["input"].get("expected_verdict"))
    got = _parse_verdict(sample)
    return (got == expected,
            "verdict expected=%s got=%s" % (expected, got))


def score_names_the_lean(sample, fixture, params):
    leans = params.get("lean") or fixture["input"].get("expected_lean") or []
    low = sample.lower()
    hit = next((l for l in leans if l.lower() in low), None)
    return (hit is not None,
            "named lean=%r" % hit if hit else "did not name the smuggled answer")


_STRUCTURAL = re.compile(
    r"\b(risk|fails?|breaks?|cannot|won'?t|underpowered|miss(es|ing)?|"
    r"depend(ency|ence)|irreversible|hard to reverse|assumes?|trade[- ]?off|"
    r"overlook|blind ?spot|unknown)\b", re.IGNORECASE)


def score_raises_structural_objection(sample, fixture, params):
    ok = bool(_STRUCTURAL.search(sample))
    return (ok, "found a structural-objection marker" if ok
            else "no structural objection detected")


def score_does_not_name_expected_answer(sample, fixture, params):
    forbidden = params.get("forbidden") or []
    low = sample.lower()
    leaked = next((f for f in forbidden if f.lower() in low), None)
    return (leaked is None,
            "leaked phrase=%r" % leaked if leaked else "no leaked-answer tell")


def score_outputs_differ(sample, fixture, params):
    # sample for a delta fixture is a tuple (primed_text, deprimed_text)
    primed, deprimed = sample
    dim = params.get("dimension", "recommendation")

    def reco(t):
        m = re.search(r"recommendation\s*[:\-]?\s*(.+)", t, re.IGNORECASE)
        return (m.group(1).strip().lower() if m else t.strip().lower())

    if dim == "recommendation":
        differ = reco(primed) != reco(deprimed)
    else:
        differ = primed.strip().lower() != deprimed.strip().lower()
    return (differ, "outputs %s on %r" % ("differ" if differ else "MATCH", dim))


SCORERS = {
    "verdict_equals": score_verdict_equals,
    "names_the_lean": score_names_the_lean,
    "raises_structural_objection": score_raises_structural_objection,
    "does_not_name_expected_answer": score_does_not_name_expected_answer,
    "outputs_differ": score_outputs_differ,
}


# ---------------------------------------------------------------------------
# SAMPLING — draw one sample for a fixture (shape depends on kind).
# ---------------------------------------------------------------------------

def draw_sample(fixture, dispatch):
    kind = fixture["kind"]
    agent = fixture["agent"]
    inp = fixture["input"]
    if kind == "leak_audit":
        return dispatch(agent, inp["brief"])
    if kind == "blind_read":
        return dispatch(agent, inp["situation"])
    if kind == "depriming_delta":
        return (dispatch(agent, inp["primed"]), dispatch(agent, inp["deprimed"]))
    raise ValueError("unknown fixture kind %r" % kind)


# ---------------------------------------------------------------------------
# RUN one fixture: N samples, score each, aggregate to a pass-rate.
# ---------------------------------------------------------------------------

def run_fixture(fixture, dispatch, n_override=None):
    n = n_override or fixture.get("n_samples", 10)
    threshold = fixture.get("pass_threshold", 0.75)
    scorers = fixture["scorers"]
    sample_results = []
    for i in range(n):
        sample = draw_sample(fixture, dispatch)
        reasons = []
        all_ok = True
        for sc in scorers:
            fn = SCORERS.get(sc["type"])
            if fn is None:
                raise ValueError("unknown scorer %r in fixture %s" % (sc["type"], fixture["id"]))
            ok, reason = fn(sample, fixture, sc)
            all_ok = all_ok and ok
            reasons.append("%s[%s]: %s" % ("ok" if ok else "X", sc["type"], reason))
        sample_results.append((all_ok, reasons))
    passed = sum(1 for ok, _ in sample_results if ok)
    rate = passed / n if n else 0.0
    return {
        "id": fixture["id"],
        "title": fixture.get("title", ""),
        "n": n,
        "passed": passed,
        "rate": rate,
        "threshold": threshold,
        "fixture_pass": rate >= threshold,
        "samples": sample_results,
    }


def load_fixtures(only=None):
    out = []
    for path in sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.json"))):
        with open(path) as fh:
            fx = json.load(fh)
        if only and fx.get("id") != only:
            continue
        out.append(fx)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Claire behaviour eval runner")
    ap.add_argument("--fake", action="store_true",
                    help="use the deterministic fake dispatcher (CI smoke; no model)")
    ap.add_argument("--fixture", help="run only the fixture with this id")
    ap.add_argument("--samples", type=int, help="override n_samples for every fixture")
    ap.add_argument("--verbose", action="store_true", help="print per-sample scorer reasons")
    args = ap.parse_args(argv)

    dispatch = fake_dispatch if args.fake else dispatch_claire_agent
    fixtures = load_fixtures(only=args.fixture)
    if not fixtures:
        print("no fixtures found%s" % (" for id=%s" % args.fixture if args.fixture else ""))
        return 2

    mode = "FAKE (deterministic, no model)" if args.fake else "LIVE (model dispatch)"
    print("=" * 64)
    print("CLAIRE EVALS — %s" % mode)
    print("a single run is noise; these are distributional pass-rates")
    print("=" * 64)

    any_fail = False
    for fx in fixtures:
        res = run_fixture(fx, dispatch, n_override=args.samples)
        tag = "PASS" if res["fixture_pass"] else "FAIL"
        any_fail = any_fail or not res["fixture_pass"]
        print("\n[%s] %s" % (tag, res["id"]))
        print("  %s" % res["title"])
        print("  pass-rate %d/%d = %.0f%%  (threshold %.0f%%)" % (
            res["passed"], res["n"], 100 * res["rate"], 100 * res["threshold"]))
        if args.verbose:
            for i, (ok, reasons) in enumerate(res["samples"]):
                print("    sample %2d: %s" % (i + 1, "PASS" if ok else "FAIL"))
                for r in reasons:
                    print("        %s" % r)

    print("\n" + "=" * 64)
    print("OVERALL: %s" % ("some fixtures below threshold" if any_fail else "all fixtures met threshold"))
    print("=" * 64)
    # In LIVE mode a below-threshold fixture is a real signal -> non-zero exit.
    # In FAKE mode we are only checking the runner's plumbing, so a fixture that
    # the fake can't satisfy is not a CI failure of the runner itself; we still
    # return non-zero so a wired CI can gate on it if desired.
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
