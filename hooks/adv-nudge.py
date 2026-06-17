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

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nudge-fire.log")


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
