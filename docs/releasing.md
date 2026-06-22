# Releasing Claire

The rules that govern a release live as a short directive in `CLAUDE.md`; this is the
*how*.

## The rules (also in CLAUDE.md)

- **One user-visible change per release.** Don't bundle.
- **Semver:** a breaking change bumps the first number, a new feature the second, a fix
  the third. (Claire is pre-1.0, so a behaviour change that alters what every install
  does — e.g. flipping a default — bumps the minor.)
- **The version bump is the last step** — only after the tests pass, the eval pass-rate
  holds, and the change is confirmed landed. Never bump first. The bump is the feature's
  last commit, not the release script's job.

## Publish to BOTH repos — run `./release.sh`

A release touches **two** repos, and forgetting the second strands every user:

1. this plugin repo — `plugin.json` version, a `vX.Y.Z` tag, a GitHub Release;
2. the separate `claire-marketplace` repo — the `version` field in its
   `.claude-plugin/marketplace.json`.

The Desktop plugins panel shows users that marketplace `version` field as "latest" and
only offers an update when it climbs. The plugin `source` is a bare repo URL that tracks
`main` HEAD for the *code* — but the version number users *see* comes only from the
marketplace manifest. Bump the plugin without bumping the marketplace and everyone is
silently stuck on the old version (exactly what happened to 0.6.1→0.7.1 — four releases
no one could install).

`./release.sh` does tag + push + GitHub Release + marketplace bump + push + a
post-publish remote check in one step. `./release.sh --check` verifies all four version
sources (plugin.json, marketplace.json, latest tag, CHANGELOG) agree. Run
`./release.sh --check` first to confirm the at-rest state, then `./release.sh` to publish
— it assumes plugin.json is **already bumped and committed**. Run the script; don't do
these steps by hand. (The cross-repo check can't live in the unit suite: the sibling
marketplace repo isn't present in CI.)
