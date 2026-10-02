# 0001. Record architecture decisions

**Status:** Accepted, 2026-10-02

## Context
The prototype made a dozen non-obvious choices (coordinate handling, threading, which speech
model) that lived only in the author's head. Moving from side project to real development means
someone else, or you in six months, has to be able to change them safely.

## Decision
Keep Architecture Decision Records in `docs/adr/`, numbered, one decision each, in the format
*Context, Decision, Consequences, Alternatives considered*. Accepted records are immutable; a
change of mind is a new record that supersedes the old one.

## Consequences
- A few minutes of writing per significant change.
- Reviews can point at the ADR instead of re-arguing a settled question.
- The `Alternatives` section is the most valuable part: it stops good ideas being retried for
  the same bad reasons, and shows when circumstances have changed enough to revisit.
