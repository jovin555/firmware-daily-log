---
title: "Day 13: Actions Matrix Builds, Caching & Artifacts"
date: 2026-10-23
tags: ["til", "github-mastery", "matrix", "caching"]
---

# Day 13: Actions Matrix Builds, Caching & Artifacts

## What I Explored Today

Today I dug into the three features that turn a toy workflow into something you'd actually ship: matrix builds for fanning a job out across OS/runtime combinations, caching to stop re-downloading the same dependencies on every run, and artifacts to move build outputs between jobs and out of the run entirely. Individually each is simple; together they're the difference between a 3-minute CI run and a 25-minute one. I spent most of the day breaking matrix `include`/`exclude` semantics and learning why my cache never hit.

## The Core Concept

A **matrix** is a cross-product. You declare axes (`os: [ubuntu-latest, macos-latest]`, `node: [18, 20]`) and GitHub expands them into `os × node` jobs that run in parallel. The value is isolation: each combination gets a fresh runner, so a failure on Windows doesn't poison the Linux leg, and you get a per-combination status in the UI. The subtlety is that the matrix is a *job-level* construct — you can't matrix individual steps, and every job that needs the same matrix has to redeclare it (or use a reusable workflow).

**Caching** exists because runners are ephemeral. Every job starts with an empty disk, so `npm ci` re-downloads the registry tarballs, `pip install` re-fetches wheels, and Go re-compiles the standard library. The cache action restores a tarball keyed by a string you choose, and saves it at job end if the key missed. The key is the whole game: it must change when your dependency manifest changes and stay stable otherwise. Hash the lockfile, not the source.

**Artifacts** are the durable output channel. Unlike cache (which is best-effort and evictable), artifacts are attached to the run, downloadable from the UI/API, and — critically — the only supported way to pass files *between jobs*. A build job produces `dist/`, an upload step stores it, and a downstream deploy job downloads it. Don't try to share a workspace across jobs; it doesn't exist.

## Key Commands / Configuration / Code

A realistic build workflow combining all three:

```yaml
name: build
on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false          # don't cancel siblings when one leg fails
      matrix:
        os: [ubuntu-latest, macos-latest]
        node: [18, 20]
        include:
          # add a variable only to matching combos
          - os: ubuntu-latest
            node: 20
            coverage: true
        exclude:
          # drop a specific combo from the cross-product
          - os: macos-latest
            node: 18
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
          cache: npm            # setup-node has built-in caching; prefer it

      # Manual cache example (when no setup action provides one):
      - uses: actions/cache@v4
        id: cache-deps
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - run: npm ci
      - run: npm test

      # Upload only from one leg to avoid artifact name collisions
      - if: matrix.coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ matrix.os }}-${{ matrix.node }}
          path: coverage/
          retention-days: 7
```

Downloading an artifact in a downstream job:

```yaml
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: coverage-ubuntu-latest-20
          path: ./coverage
```

Useful CLI checks:

```bash
# Inspect cache usage for a repo (requires gh + admin scope)
gh api repos/{owner}/{repo}/actions/caches

# List artifacts for the latest run
gh run view --json artifacts -q '.artifacts[].name'
```

## Common Pitfalls & Gotchas

- **Cache key that never changes.** If you key on `${{ github.sha }}` you get a new cache every run and zero hits. Key on `hashFiles('**/package-lock.json')` and add `restore-keys` for partial fallback. Also remember caches are scoped per branch and immutable — you can't overwrite a key, only create a new one.
- **Artifact name collisions in v4.** `upload-artifact@v4` rejects duplicate names within a run. In a matrix, every leg uploading `name: dist` will fail after the first. Include `${{ matrix.* }}` in the name, or use `merge-multiple` on download.
- **`fail-fast` default is `true`.** One failing matrix leg cancels the rest, which hides whether the failure is OS-specific. Set `fail-fast: false` when you're debugging cross-platform issues, and remember `continue-on-error` at the step level is a different knob entirely.

## Try It Yourself

1. Take an existing workflow and convert its single job into a 2×2 matrix (`os` × `node`). Add one `include` entry that sets an extra env var and one `exclude` that removes a combo. Verify the job count in the Actions UI matches your expectation.
2. Add `actions/cache@v4` keyed on a lockfile hash, run the workflow twice, and confirm the second run reports a cache hit in the step log. Then change a dependency and confirm the key changes.
3. Split a build into `build` and `deploy` jobs, passing a `dist/` folder via `upload-artifact`/`download-artifact`. Confirm the deploy job can read the file without checking out the repo.

## Next Up

Tomorrow: **Secrets, Variables, Environments & Deployment Protection Rules** — how to keep credentials out of logs, scope config per environment, and gate production deploys behind required reviewers.
