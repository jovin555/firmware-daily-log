---
title: "Day 08: Merge Strategies, Merge Queue & Required Status Checks"
date: 2026-10-18
tags: ["til", "github-mastery", "merge-queue", "status-checks"]
---

## What I Explored Today

Today I dug into the mechanics of how pull requests actually land on `main` — the three merge strategies GitHub offers, how required status checks gate merges, and how the merge queue solves the "semantic conflict" problem that plagues busy repositories. I set up a merge queue on a test repo with branch protection, watched a PR get ejected for a failing check, and learned why `merge_group` events matter for CI workflows. This is the plumbing that separates a repo that scales from one that becomes a merge-conflict warzone every Friday afternoon.

## The Core Concept

GitHub gives you three merge strategies, and the choice is architectural, not cosmetic:

- **Merge commit** (`--no-ff`): preserves full branch topology. Every PR is a distinct node with two parents. Great for auditability, noisy for `git log`.
- **Squash and merge**: collapses all PR commits into one on the base branch. Clean linear history, but you lose the individual commit granularity inside the PR.
- **Rebase and merge**: replays each commit onto the base without a merge commit. Linear history *and* per-commit granularity — but rewrites SHAs, which breaks anything referencing the original commits.

The real problem these strategies don't solve: **semantic conflicts**. Two PRs can each pass CI against `main` independently, then break `main` when merged together because they touch adjacent code or share a dependency. Required status checks alone can't catch this — they validate each PR against a *stale* `main`.

The **merge queue** fixes this. When you queue a PR, GitHub builds a temporary branch (`gh-readonly-queue/main/pr-123-<sha>`) containing `main` plus the PRs ahead of it in the queue, runs your required checks against *that* combined state, and only merges if they pass. If a check fails, the PR is ejected and the queue re-evaluates. This is the difference between "passes in isolation" and "passes in reality."

## Key Commands / Configuration

**Enable merge queue via branch protection** (Settings → Branches → protection rule for `main`):

```yaml
# Required status checks must include the merge queue context.
# In the UI, check "Require merge queue" and set:
#   - Merge method: Squash (or your preference)
#   - Build concurrency: 5
#   - Minimum group size: 1
#   - Maximum group size: 5
#   - Wait time: 5 minutes
```

**Your CI workflow must handle `merge_group` events** — this is the #1 thing people forget:

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
  merge_group:        # REQUIRED — without this, queue checks never run
    types: [checks_requested]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
```

**Required checks are configured per-branch**, and the check name must match exactly what the workflow reports:

```bash
# List required status checks for a branch (requires admin token)
gh api repos/OWNER/REPO/branches/main/protection \
  --jq '.required_status_checks.contexts'

# Add a required check via API (merge with existing contexts)
gh api -X PATCH repos/OWNER/REPO/branches/main/protection/required_status_checks \
  -f strict=true \
  -f 'contexts[]=test' \
  -f 'contexts[]=lint'
```

**Enqueue a PR from the CLI** (after enabling merge queue):

```bash
# Requires the PR to be approved and all required checks green
gh pr merge 123 --squash --auto
# --auto enqueues into the merge queue rather than merging immediately
```

**Merge method defaults** live at the repo level:

```bash
# Allow only squash merges repo-wide
gh api -X PATCH repos/OWNER/REPO \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false
```

## Common Pitfalls & Gotchas

**1. Forgetting the `merge_group` trigger.** If your CI workflow only listens to `pull_request`, the merge queue will enqueue PRs and then sit forever because no checks ever report. The queue times out after the configured wait time and ejects the PR. Always add `merge_group: types: [checks_requested]` to every workflow that backs a required check.

**2. `strict` required checks vs. merge queue.** The "Require branches to be up to date before merging" (`strict: true`) setting forces every PR to rebase onto `main` before merging — which serializes merges and creates a rebase treadmill on busy repos. The merge queue *replaces* this need: it validates against the combined state without forcing developers to manually rebase. Don't enable both; you'll get redundant churn.

**3. Rebase-and-merge breaks commit references.** If you use `--rebase`, any commit SHA referenced in issues, PR comments, or external systems (Jira links, deploy tags) becomes dangling. For repos with heavy cross-referencing, squash is usually safer — one stable SHA per PR.

## Try It Yourself

1. **Enable the merge queue** on a test repo's `main` branch protection rule, set max group size to 3, and open two PRs that both modify the same file. Watch the queue build the combined branch and merge them in order — then intentionally break one and watch it get ejected.

2. **Add `merge_group` to a workflow** and verify it fires: push a PR to the queue and check the Actions tab for a run with the `merge_group` event. Confirm the check name appears in the branch protection required list.

3. **Compare histories**: create three branches with three commits each, merge one via merge commit, one via squash, one via rebase. Run `git log --graph --oneline` on each result and note the topology difference.

## Next Up

Tomorrow I'm moving from merge mechanics to project management: **GitHub Projects — Tables, Boards, Roadmaps, Custom Fields & Iterations**. We'll wire up a project that tracks issues across repos, build a roadmap view with date fields, and automate iteration assignment with a workflow.
