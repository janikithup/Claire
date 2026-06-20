# Claire issues — scope gate

This folder is **public** (it ships in the Claire plugin repo). It is for issues
about **building, testing, or releasing the Claire plugin itself** — design notes,
bug reports, spine-gap findings, sprint kickoffs.

**Before filing here, ask what the issue is *about* — not which repo you happen to
be in.** An issue lands here only if its subject is the Claire plugin. If it is
about anything else, it does **not** belong in this public repo:

- **The maintainer's global Claude behaviour** (how Claude should act across all
  their projects), or anything that resolves into their private `~/.claude/`
  rulebook, memory, or wiki → their **private** meta queue, not here.
- **A Claire *usage* barrier hit from another project** (Claire errored/refused
  while you were working elsewhere) → the standing **private** Claire-barrier queue
  (`~/.claude/claire/issues/`), not here.

**Never paste private material into an issue in this folder:** absolute home paths
(`/Users/<you>/...`), private knowledge-base or rules paths (`~/.claude/wiki/...`,
`~/.claude/memory/...`), other (private) projects' names or internals, or personal
details. Describe the situation generically. If the private queue was unreachable
(e.g. sandbox-blocked) and you fell back to this repo, that is exactly the case to
catch — sanitise first, or hold the issue for the private queue instead of pushing
it public.

*(This gate exists because a global-rule deliberation and several private-workspace
references were once filed here by location rather than by scope, and pushed
public.)*
