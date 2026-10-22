---
title: "Day 12: Actions Triggers: push, pull_request, schedule, workflow_dispatch & Filters"
date: 2026-10-22
tags: ["til", "github-mastery", "actions", "triggers"]
---

## What I Explored Today

Today I dug into the `on:` block — the part of a workflow that everyone writes on day one and then misconfigures for the next six months. I focused on the four triggers that cover 95% of real workflows: `push`, `pull_request`, `schedule`, and `workflow_dispatch`, plus the `paths`/`branches`/`types` filters that decide whether a run actually fires. The surprising part wasn't the syntax — it was how many "why didn't my workflow run?" bugs trace back to a filter that silently excluded the event, or to the difference between `pull_request` and `pull_request_target` and which branch a `schedule` actually runs against.

## The Core Concept

A trigger is a **predicate over an event payload**. GitHub emits an event (a push, a PR opened, a cron tick, a manual click), and for every workflow in the repo it evaluates the `on:` block against that event. If it matches, a run is queued. The mental model that finally clicked for me: the filters (`branches`, `paths`, `types`) are ANDed together, and within each filter the list is ORed. So `branches: [main]` + `paths: ['src/**']` means "on main **and** touching src" — not "on main **or** touching src."

The second concept is **which ref the workflow runs against**. `push` runs on the pushed commit. `pull_request` runs on the *merge commit* of the PR head into the base — not the head itself — which is why your CI tests what would land, not what you wrote. `schedule` always runs on the default branch's latest commit, regardless of what you set in `branches`. And `workflow_dispatch` runs on whatever ref you pick in the UI (default: the default branch). Getting this wrong is the root of the classic "works locally, fails in CI" and "scheduled job ran old code" complaints.

## Key Commands / Configuration / Code

```yaml
name: CI

on:
  # push: only on main, and only when source or build files change.
  # Ignoring docs/ prevents a README typo from burning CI minutes.
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'Cargo.toml'
      - 'Cargo.lock'
      - '.github/workflows/**'

  # pull_request: run on PRs targeting main, but only for these activity types.
  # Default types are [opened, synchronize, reopened] — 'ready_for_review'
  # lets you skip draft PRs until they're actually ready.
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, ready_for_review]

  # schedule: cron in UTC, always runs against the default branch HEAD.
  # Minimum interval is 5 minutes; high-frequency crons get throttled.
  schedule:
    - cron: '0 6 * * 1-5'   # 06:00 UTC, weekdays only

  # workflow_dispatch: manual runs from the UI/API/gh CLI, with typed inputs.
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        type: choice
        options: [staging, production]
        required: true
      dry_run:
        description: 'Skip deploy'
        type: boolean
        default: true

jobs:
  build:
    # Guard: skip draft PRs even if the trigger fired.
    if: github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cargo build --release
```

Triggering a manual run from the CLI — this is the one I use constantly:

```bash
# Fire workflow_dispatch on a specific branch with inputs.
gh workflow run ci.yml \
  --ref feature/login \
  -f environment=staging \
  -f dry_run=true

# Confirm it queued, then watch it.
gh run list --workflow=ci.yml --limit 3
gh run watch
```

Reading the event payload inside a job — useful for debugging why a run fired:

```bash
# The full event JSON is available at this path in every job.
jq '.ref, .commits[0].message' "$GITHUB_EVENT_PATH"
```

## Common Pitfalls & Gotchas

**1. `paths` filters silently skip required checks.** If a workflow is a required status check on a branch protection rule but you filter it with `paths: ['src/**']`, a PR that only touches `docs/` will never produce that check — and the PR sits blocked forever. Either drop the path filter on required checks, or add a companion "always runs" job that reports the same check name.

**2. `pull_request` from forks has no secrets and a read-only token.** This is by design — a fork's PR runs untrusted code. If you need secrets (e.g., to post a comment), don't reach for `pull_request_target` casually: it runs in the context of the base repo *with* secrets and a write token, and checking out the PR head under it is a well-known RCE vector. Use `pull_request_target` only for metadata-only jobs that never execute fork code.

**3. `schedule` ignores `branches` and drifts.** Cron workflows always run on the default branch, and GitHub explicitly disables scheduled workflows after 60 days of repo inactivity. Also, cron is best-effort — a `0 * * * *` job can fire minutes late under load. Never build correctness on exact timing; make scheduled jobs idempotent and tolerant of a late start.

## Try It Yourself

1. **Prove the AND semantics.** Add a workflow with `push` filtered to `branches: [main]` and `paths: ['src/**']`. Push a commit touching only `README.md` to main — confirm no run. Then touch a file in `src/` — confirm it fires. Check the Actions tab to see the skipped event.

2. **Wire up a manual trigger with inputs.** Add a `workflow_dispatch` with a `choice` input and a `boolean`. Run it twice from the CLI with `gh workflow run` using different `-f` values, and echo the inputs in a step via `${{ inputs.environment }}` and `${{ inputs.dry_run }}`.

3. **Break a required check on purpose.** On a test branch, mark a path-filtered workflow as a required status check, then open a PR that only edits a markdown file. Watch the check never appear and the merge stay blocked — then fix it by removing the path filter.

## Next Up

Tomorrow: **Actions Matrix Builds, Caching & Artifacts** — fanning one job across OS/version combinations with `strategy.matrix`, shaving minutes off CI with `actions/cache` keyed correctly, and passing build outputs between jobs with `actions/upload-artifact` / `download-artifact`.
