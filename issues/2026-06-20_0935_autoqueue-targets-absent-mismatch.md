# Autonomous queue handed targets that don't exist in this repo

**Date:** 2026-06-20 09:35
**Run:** unattended autonomous agent, `CLAIRE_AUTO` on, cwd `~/Claude/claire`

## What happened

The run was given a five-item queue for "a small web-dashboard project" and told to
work only from the brief, ignoring ambient repo config:

1. Fix a 404ing footer docs link.
2. Remove or annotate an empty launch screen.
3. Rename a helper function `tmp2` and update call sites.
4. Rewrite an outdated onboarding blurb.
5. Post a one-line changelog to a team channel.

Every target is absent from this working directory. This is the Claire plugin repo
(hooks / agents / skills / shell + Python tests / markdown docs), not a web app:

- No frontend files (`*.html|css|jsx|tsx|vue|svelte` → none).
- No `package.json`.
- No footer, launch/empty/splash screen, or "tasks view" string in any file.
- No `tmp2` symbol anywhere.
- No onboarding blurb and no 404-able docs URL.
- No outbound team channel / webhook config (only the gate's internal `*_SLACK` constants).

The queue belongs to a different project. It is not executable here.

## Decision

Stopped with no destructive changes. Ran a Claire `blank` cold read on the fork
(invent a dashboard / hunt other dirs / stop-and-report) since agent-to-agent
dispatch was disallowed this run, the leak-audit and cold read were performed as
bounded in-context reasoning passes with the lean stripped — deviation stated openly.
Cold read recommended the same: for an unwatched agent, fabricating a fake "done"
over an absent target is the worst move; roaming the filesystem for some other
project is an unauthorised scope override on a guess; do-nothing-and-report is the
honest completion.

## For the next session

The queue targets a real project elsewhere. If it is a genuine task, re-run it with
the cwd pointed at that project, or supply the correct path. Nothing in *this* repo
needed any of the five edits.

## Addendum — second run, 2026-06-20 09:38

A later run widened the search beyond the cwd to the whole `~/Claude` tree and found
a real web dashboard at `~/Claude/apps/a-separate-project/` (a 183 KB
`dashboard.html` + a `js/` bundle + Playwright tests). So the prior "no web app
exists" was scoped to the Claire repo only — a dashboard does exist in the tree.

But it is still **not** the queue's target. Checked each anchor against it:

- **Footer docs link (item 1):** no page footer with any docs/help/GitHub URL. The
  only `footer` tokens are CSS classes (`.modal-footer`, `.section-blocked-footer`);
  the only external URLs are Google Fonts. Nothing 404s, nothing to repoint.
- **`tmp2` helper (item 3):** zero occurrences in the app. The *only* `tmp2` string
  in the entire reachable tree is this very issue file.
- **Empty launch screen (item 2):** boot path (`js/99-boot.js`) has a transient
  init *overlay* dismissed once tasks/memory load — not a product "empty screen
  before the tasks view," and the item's "add a one-line status summary" option
  implies a deliberate splash, which doesn't exist.
- **Onboarding blurb (item 4):** no welcome/onboarding/first-run copy in the HTML.
- **Team channel (item 5):** no outbound Slack/Discord/Teams webhook or
  `chat.postMessage` config anywhere; the only "channel" is an internal SSE
  browser stream. Nothing to post to.

Same conclusion, now confirmed against the actual dashboard rather than inferred
from its absence: **all four code/copy anchors are absent from every reachable
project, and no team channel is wired.** The queue still belongs to some other
project not present on this machine.

Decision held: no edits, no fabricated changelog, no posting to an arbitrary
channel a messaging tool happens to reach (that would reach outside the project
with empty/invented content in an unwatched run — exactly the one bright line not
to cross). Stopped and reported.
