---
title: "Day 11: GitHub Actions Fundamentals: Workflows, Jobs, Steps & Runners"
date: 2026-10-21
tags: ["til", "github-mastery", "actions", "ci"]
---

## What I Explored Today

Today I sat down with GitHub Actions and forced myself to understand the execution model instead of copy-pasting YAML from Stack Overflow. The vocabulary — workflows, jobs, steps, runners — sounds simple until you need to reason about *where* code runs, *what* shares a filesystem, and *when* things happen in parallel versus sequence. I built a small multi-job pipeline, watched it fail in instructive ways, and came away with a mental model I can now defend. This post is that model.

## The Core Concept

The single most useful thing to internalize: **a workflow is a DAG of jobs, and each job runs on its own fresh runner.**

That one sentence explains almost every confusing behavior you'll hit. A workflow is a YAML file in `.github/workflows/`. It contains one or more **jobs**. Each job is dispatched to a **runner** — a fresh, ephemeral VM (or container) that GitHub provisions for that job alone. Jobs run **in parallel by default** and do *not* share a filesystem, environment variables, or installed software. If job B needs an artifact from job A, you must explicitly pass it (via `actions/upload-artifact`/`download-artifact`, or by making B depend on A with `needs:` and re-doing the work).

Within a job, **steps** run **sequentially** on the *same* runner. That's why `npm ci` in step 1 is visible to `npm test` in step 2 — same machine, same working directory, same shell environment (mostly). Steps share the workspace but each step is a separate process, so `cd` in one step doesn't leak into the next.

The "why" behind this design is reproducibility and isolation. A fresh runner per job means no state bleeds between builds, no "works on the previous run's leftover cache" bugs, and jobs can be scheduled onto any available machine. The cost is that cross-job coordination is explicit and slightly annoying — which is the correct tradeoff for CI.

Runners come in two flavors: **GitHub-hosted** (`ubuntu-latest`, `windows-latest`, `macos-latest`, plus specific versions like `ubuntu-22.04`) and **self-hosted** (your own machines, registered to the repo/org). For 95% of projects, hosted is fine.

## Key Commands / Configuration / Code

A minimal but realistic workflow that exercises every concept:

```yaml
# .github/workflows/ci.yml
name: CI

# Triggers — covered in depth tomorrow, but you need one
on:
  push:
    branches: [main]

jobs:
  # Job 1: lint. Runs on its own runner.
  lint:
    runs-on: ubuntu-latest        # runner label
    steps:
      - uses: actions/checkout@v4 # step 1: clone repo into $GITHUB_WORKSPACE
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci               # step 3: install deps
      - run: npm run lint         # step 4: same runner, deps still present

  # Job 2: test. Runs in PARALLEL with lint by default.
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node: [18, 20, 22]        # spawns 3 separate jobs
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
      - run: npm ci
      - run: npm test

  # Job 3: build. Waits for BOTH lint and test.
  build:
    needs: [lint, test]           # explicit dependency edge in the DAG
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

Key facts to burn in:

- `runs-on` selects the runner. `ubuntu-latest` is currently Ubuntu 24.04; pin `ubuntu-22.04` if you need stability.
- `needs:` creates the dependency edge. Without it, `build` would start immediately alongside `lint` and `test`.
- `strategy.matrix` fans one job definition into N jobs — each gets its own runner. `${{ matrix.node }}` interpolates.
- `uses:` pulls a reusable action (a repo, optionally pinned to a tag/SHA). `run:` executes a shell command.
- Contexts like `${{ github.sha }}`, `${{ github.ref }}`, `${{ runner.os }}` are available in most fields.
- Every step is a separate process. Use `working-directory:` per step rather than `cd` if you need a subdirectory.

Useful local checks before pushing:

```bash
# Validate YAML syntax quickly
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"

# See what Actions thinks of your file (requires gh CLI + auth)
gh workflow list
gh run list --workflow=ci.yml
gh run view <run-id> --log
```

## Common Pitfalls & Gotchas

**1. Assuming jobs share state.** They don't. If `test` needs the build output from `build`, either add `needs: build` *and* download the artifact, or merge them into one job. Environment variables set in one job are invisible to another. This bites everyone once.

**2. `cd` doesn't persist across steps.** Each `run:` is a fresh shell. `- run: cd subdir` followed by `- run: npm test` runs the test in the *repo root*, not `subdir`. Use `working-directory: subdir` on the step, or chain with `&&` in a single step.

**3. Unpinned action versions are a supply-chain risk.** `uses: actions/checkout@v4` is a moving tag — fine for most, but for security-sensitive repos pin to a full commit SHA (`actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11`). Also: `actions/upload-artifact@v3` is deprecated; use `@v4`, and note v4 artifacts are immutable and can't be overwritten with the same name.

## Try It Yourself

1. **Build a two-job pipeline** where `test` runs `needs: build` and consumes an artifact produced by `build`. Verify in the Actions UI that `test` doesn't start until `build` finishes — watch the graph view.
2. **Break the isolation on purpose.** In job A, `export FOO=bar` and try to read `$FOO` in job B. Confirm it's empty, then fix it properly by passing the value through `outputs:` and `needs.<job>.outputs`.
3. **Add a matrix** with `os: [ubuntu-latest, macos-latest]` and `node: [20, 22]`. Count the jobs GitHub spawns (should be 4) and confirm each runs on a distinct runner via `${{ runner.os }}` echoed in a step.

## Next Up

Tomorrow: **Actions Triggers: push, pull_request, schedule, workflow_dispatch & Filters.** We'll cover how `on:` actually decides whether your workflow runs — branch/path filters, `pull_request` vs `pull_request_target` (and why the latter is a security footgun), cron syntax quirks, and manual dispatch inputs. The trigger is where most "why didn't my workflow run?" mysteries live.
