#!/usr/bin/env python3
"""
claire discoverability nudge.

UserPromptSubmit hook. When a prompt reads like a request for a critique or an
outside view, surface a ONE-LINE marker that the toolkit exists — so a fresh
session that has no memory of it doesn't forget to reach for it. The trigger is
deliberately TIGHT (multi-word, specific): a loose nudge becomes ambient noise
and gets tuned out, which fails silently. FAIL-OPEN: any error => stay silent.
"""
import sys, os, json, datetime

# Tight markers that genuinely signal wanting a critique / outside read.
# Specific by design — these almost never appear in routine requests.
TRIGGERS = (
    "what am i missing", "am i missing anything", "am i overlooking", "poke holes",
    "poke a hole", "devil's advocate", "play devil", "outside view", "outside opinion",
    "outside read", "second opinion", "steel-man", "steelman", "stress test",
    "stress-test", "attack this", "attack the plan", "attack my", "what could go wrong",
    "is this a good idea", "talk me out of", "argue the other side", "argue against",
    "red team", "red-team", "challenge this", "critique this", "blind spot",
    "what's wrong with this", "whats wrong with this", "convince me i'm wrong",
    "change my mind", "am i wrong about",
)

# CLAIRE_AUTO autonomous-mode arming. Tight, multi-word kickoff phrases that signal
# the start of an autonomous / AFK run (mirrors the autoloop skill's trigger lexicon).
# Same "tight by design" rule as TRIGGERS: a loose match would bleed the standing
# instruction into ordinary work even with the flag left on.
AUTO_TRIGGERS = (
    "scan and fix", "work the list", "work the queue", "work the backlog",
    "clear the backlog", "clear the queue", "clear the list", "handle the queue",
    "knock these out", "knock them out", "go through the list", "go through the queue",
    "work through the list", "work through the queue", "/autoloop",
    "run unattended", "while i'm away", "while i am away", "run on autopilot",
)

# The standing instruction injected once at the start of an armed autonomous run.
# It automates the validated manual practice ("use Claire on every judgement call
# before I go AFK") and re-states the de-priming spine so frequency never erodes it.
AUTO_MSG = (
    "[claire:auto] Autonomous critique mode is ON for this run (CLAIRE_AUTO). Treat "
    "Claire as a standing step, not an optional one: on each genuine judgement call — "
    "a fork you resolve without the user, a plan or approach you commit to, a content "
    "or file change you write, or anything outbound — run a Claire pass before you move "
    "on (/claire:challenge for a plan or claim, /claire:blank for a cold read on a fork). "
    "The de-priming holds every time: the brief is leak-checked before the critic sees it, "
    "and firing often is never a reason to skip the audit or accept a lean. If a brief still "
    "leans after the bounded fix-loop (re-audit with the auditor's neutral rewrite, cap two "
    "cycles), do not proceed — park the run on that judgement call for the user, with the "
    "lean named. Claire critiques; she never approves — her read informs your call, it "
    "does not bless it. Mechanical steps with no judgement call fire nothing."
)

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nudge-fire.log")


def _flag(name):
    """A CLAIRE_* env flag is ON unless empty/0/false (matches the gate's idiom)."""
    return os.environ.get(name, "").strip() not in ("", "0", "false", "False")


def log(line):
    try:
        with open(LOG, "a") as fh:
            fh.write("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), line))
    except Exception:
        pass


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    prompt = data.get("prompt") or data.get("user_prompt") or ""
    pl = prompt.lower()

    # CLAIRE_AUTO — autonomous-mode arming. When the flag is on AND the prompt reads
    # like the start of an autonomous/AFK run, inject the standing instruction and
    # stop. Gated by BOTH the flag and the lexicon so a flag left on cannot bleed
    # Claire into interactive work. Supersedes the discoverability nudge for this turn.
    if _flag("CLAIRE_AUTO"):
        ahit = next((t for t in AUTO_TRIGGERS if t in pl), None)
        if ahit:
            log("AUTO armed matched=%r" % ahit)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": AUTO_MSG}}))
            return

    hit = next((t for t in TRIGGERS if t in pl), None)
    if not hit:
        return  # silent — not an adversarial-shaped request
    log("NUDGE matched=%r" % hit)
    msg = (
        "[claire] This reads like a request for a critique or outside view. "
        "`/claire:challenge` routes it to the right critic and leak-checks your brief first; "
        "`/claire:blank` gives a cold outside read from Claire. Ignore if that's not what you want."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-open
