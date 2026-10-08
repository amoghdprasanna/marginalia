# 0022. Release process: SemVer, a changelog, and tag-triggered builds

**Status:** Accepted, 2026-10-08

## Context
There was a version number (0.1.0) and nothing else: no changelog, no tags, no builds. The
update check (ADR 0021) needs published releases to compare against, and users need to know
what changed.

## Decision
- **SemVer**, single source of truth `marginalia.__version__` (pyproject reads it dynamically).
- **`CHANGELOG.md`** in Keep a Changelog form. Each PR adds its user-visible lines under
  `[Unreleased]`, so release notes are written when the change is fresh, not reconstructed.
- **`scripts/release.py X.Y.Z`** bumps the version and moves Unreleased under the new heading
  with today's date and compare links. It never commits, tags or pushes; it prints the commands.
  `--notes` prints a section, `--check vX.Y.Z` verifies tag, version and changelog agree.
- **Pushing a `vX.Y.Z` tag** runs `release.yml`: check, tests, wheel + sdist, macOS `.dmg`
  (signed and notarised when the secrets exist), Windows `.zip`, then a GitHub release whose
  notes are that changelog section. A manual run of the workflow is a dry run.

## Consequences
- Releasing is four commands, and CI refuses a tag that disagrees with the code.
- The changelog is a review item: a PR with a user-visible change and no changelog line is
  incomplete.

## Alternatives considered
- **Version from git tags** (setuptools-scm). No file to bump, but the version of a source
  checkout depends on git metadata, and the app reads `__version__` at runtime.
- **Generated changelogs from commit messages** (release-please, git-cliff). Conventional commits
  already exist here, but commit subjects are for developers ("refactor: pure core..."), and
  release notes are for users. Writing them by hand is cheap at this size.
