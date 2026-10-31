---
title: "Day 21: Dependabot: Version Updates, Security Alerts & Auto-Merge"
date: 2026-10-31
tags: ["til", "github-mastery", "dependabot", "dependencies"]
---

## What I Explored Today

Today I dug into Dependabot, GitHub's built-in dependency management bot. I'd been treating it as a "nice to have" that occasionally opened PRs I'd ignore for weeks, but it turns out there are three distinct features that are easy to conflate: **Dependabot alerts** (security vulnerabilities in your dependency graph), **Dependabot security updates** (automatic PRs to fix those alerts), and **Dependabot version updates** (scheduled PRs to keep dependencies current regardless of vulnerabilities). I spent the day wiring all three up on a Node project, then configured auto-merge with branch protection so the safe updates land without me babysitting them. The distinction between the three matters more than I expected — most teams enable one and assume they've covered the others.

## The Core Concept

The "why" here is that dependency rot is silent. A `package-lock.json` from eighteen months ago is a liability: transitive dependencies you never chose are accumulating CVEs, and the longer you wait, the more painful the upgrade becomes because the version delta grows. Dependabot attacks this from two angles.

**Security alerts** are reactive — GitHub scans your dependency graph against the GitHub Advisory Database and the CVE feed, then flags vulnerable packages. **Security updates** are the automated response: Dependabot opens a PR bumping the vulnerable package to the minimum patched version. These are triggered by advisories, not a schedule.

**Version updates** are proactive — you declare a schedule and Dependabot opens PRs to move dependencies forward even when nothing is broken. This is what keeps you from ever being in the "we're 40 versions behind" hole. The two systems share a config file but run on different triggers, and that's the mental model that finally made it click for me.

The real payoff comes from combining version updates with **auto-merge gated on CI**. Patch and minor bumps that pass your test suite merge themselves; majors wait for a human. That's the sweet spot: you get continuous maintenance without reviewing a hundred trivial PRs.

## Key Commands / Configuration / Code

The whole thing lives in `.github/dependabot.yml`:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "npm"        # npm, pip, cargo, gomod, github-actions, etc.
    directory: "/"                   # location of package.json / lockfile
    schedule:
      interval: "weekly"             # daily | weekly | monthly
      day: "monday"
      time: "06:00"
      timezone: "America/New_York"
    open-pull-requests-limit: 5      # cap concurrent PRs (default 5)
    groups:                          # batch related bumps into one PR
      minor-and-patch:
        patterns: ["*"]
        update-types: ["minor", "patch"]
    ignore:
      - dependency-name: "aws-sdk"   # pin majors we upgrade manually
        update-types: ["version-update:semver-major"]

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

Note the `groups` block — this collapses a dozen minor bumps into a single PR, which is the difference between a usable inbox and a wall of noise.

Security alerts and security updates are toggled per-repo, not in the YAML. Via the API:

```bash
# Enable vulnerability alerts (security alerts)
gh api -X PUT repos/OWNER/REPO/vulnerability-alerts

# Enable automated security fixes (security update PRs)
gh api -X PUT repos/OWNER/REPO/automated-security-fixes

# Inspect open alerts
gh api repos/OWNER/REPO/dependabot/alerts \
  --jq '.[] | select(.state=="open") | {pkg: .dependency.package.name, sev: .security_advisory.severity}'
```

For auto-merge, you need branch protection requiring status checks, then either enable it per-PR or automate it. The `gh` CLI path:

```bash
# Enable auto-merge on a PR (requires "Allow auto-merge" in repo settings)
gh pr merge 42 --auto --squash
```

The scalable approach is a workflow that auto-merges Dependabot PRs only when they're patch/minor:

```yaml
# .github/workflows/dependabot-automerge.yml
name: Dependabot auto-merge
on: pull_request

permissions:
  contents: write
  pull-requests: write

jobs:
  automerge:
    if: github.actor == 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - uses: dependabot/fetch-metadata@v2
        id: meta
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
      - name: Enable auto-merge for patch/minor
        if: |
          steps.meta.outputs.update-type == 'version-update:semver-patch' ||
          steps.meta.outputs.update-type == 'version-update:semver-minor'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Common Pitfalls & Gotchas

**Confusing alerts with version updates.** Enabling version updates does *not* enable security alerts, and vice versa. Security alerts require the dependency graph (on by default for public repos, must be enabled for private). If your alerts page is empty, check the dependency graph is actually populated — a missing lockfile means no graph, no alerts.

**Auto-merge without required checks is a footgun.** `gh pr merge --auto` only waits for checks that branch protection *requires*. If you haven't marked your CI job as a required status check, auto-merge will merge immediately on approval — including a broken build. Set required checks first, always.

**`open-pull-requests-limit` silently starves updates.** The default cap of 5 means once you have 5 open Dependabot PRs, new ones simply don't get created. Teams that ignore PRs wonder why updates "stopped." Either keep the queue drained or raise the limit deliberately.

## Try It Yourself

1. Add a `.github/dependabot.yml` to a repo with a `groups` block for minor/patch and a weekly schedule. Push it, then check **Insights → Dependency graph → Dependabot** to confirm it registered.
2. Enable security alerts and automated security fixes via the two `gh api` commands above, then list open alerts with the `--jq` filter to see severities.
3. Set up the auto-merge workflow with branch protection requiring your CI check, and verify a patch-level Dependabot PR merges itself while a major bump waits.

## Next Up

Tomorrow: **Code Scanning with CodeQL, Secret Scanning & Push Protection** — moving from dependency risk to your own code, catching leaked credentials before they hit the remote, and wiring CodeQL into CI.
