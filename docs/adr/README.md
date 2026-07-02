# Architecture Decision Records (ADRs)

This directory tracks significant architecture and product decisions for
SecureWise (and GuideWisey backend decisions that materially affect it) as
lightweight, permanent records — not just commit messages or chat history.

## Why

As SecureWise grows from a scanner into an AI security engineering platform
(orchestrator, correlation engine, plugin SDK, knowledge graph, multi-agent
AI, etc.), decisions made today constrain what's possible later. Without a
written record, the reasoning behind a decision is lost as soon as the
person who made it forgets it or leaves the project — and every new
contributor re-litigates settled questions. An ADR is cheap insurance
against that.

## When to write one

Write an ADR **before or immediately after** any decision that is:

- Hard or expensive to reverse (data model shape, API contracts, choice of
  sync vs. async execution model, choice of monolith vs. services).
- Cross-cutting (affects more than one module/team).
- Something a new engineer would reasonably ask "wait, why did we do it
  this way?" about in 6 months.

Examples of ADR-worthy decisions already made informally in this codebase
(see `0001`–`0003` for retroactive write-ups): bundling an offline Semgrep
rule pack instead of relying on `--config=auto`, fingerprint-based finding
deduplication across rescans, and the quality-gate "not evaluated" vs.
"passed" semantics.

Do **not** write an ADR for routine bug fixes, refactors with no
alternative considered, or anything reversible in a single PR.

## Process

1. Copy `0000-template.md` to `NNNN-short-kebab-title.md` (next sequential
   number, zero-padded to 4 digits).
2. Fill in Context, Decision, Consequences, and Alternatives Considered.
3. Open a PR alongside (or immediately after) the code change it documents.
4. Status starts as `Proposed`. Once merged/shipped, update to `Accepted`.
   If a later ADR replaces this one, mark it `Superseded by ADR-NNNN` —
   never delete or silently edit history.
5. Link the ADR from the relevant `docs/architecture/*.md` doc if one
   exists, and from the PR description.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-offline-semgrep-rule-pack.md) | Bundle an offline curated Semgrep rule pack instead of `--config=auto` | Accepted |
| [0002](0002-fingerprint-based-finding-dedup.md) | Fingerprint-based finding deduplication across scans | Accepted |
| [0003](0003-quality-gate-not-evaluated-state.md) | Quality gate must distinguish "not evaluated" from "passed" | Accepted |

New ADRs go at the bottom, oldest first, numbers never reused.
