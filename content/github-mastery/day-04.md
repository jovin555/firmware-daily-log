---
title: "Day 04: Branch Protection & Rulesets: Guarding main"
date: 2026-10-14
tags: ["til", "github-mastery", "branch-protection", "rulesets"]
---

## What I Explored Today

Today I dug into the two mechanisms GitHub gives you for locking down branches: classic **branch protection rules** and the newer **repository rulesets**. Branch protection has been around forever and lives under `Settings → Branches`. Rulesets arrived in 2023 and live under `Settings → Rules → Rulesets`, and they're the direction GitHub is pushing everyone. The key difference: rulesets are layered, can target multiple branches or tags with pattern matching, can be evaluated in "evaluate" mode before enforcement, and can be applied at the organization level so you don't have to configure the same rule on 200 repos. I spent the afternoon converting a repo's classic protection into a ruleset and scripting it with `gh api`.

## The Core Concept

The *why* here is simple: `main` is the branch that ships. Every accidental force-push, every half-finished PR merged at 11pm, every "I'll just fix it directly on main" is a production incident waiting to happen. Branch protection is a server-side gate — it doesn't matter what a developer's local Git config says, the GitHub API refuses the push.

The important mental model shift with rulesets is that they're **additive and evaluated as a set**. Classic protection was one rule per branch pattern, and if you had overlapping patterns you got confusing behavior. Rulesets stack: if two rulesets both apply to `main`, the *most restrictive* combination wins. A ruleset can also be in **Evaluate** mode, which logs what *would* have been blocked without actually blocking it — invaluable when you're rolling out a new rule to a busy repo and don't want to freeze everyone.

Rulesets also have a **bypass list** — users, teams, or apps that can skip the rules. This is how you let your release automation push a version bump to `main` while humans still need a PR. Classic protection had a similar concept but it was coarser.

## Key Commands / Configuration

The fastest way to see what's protecting a branch today:

```bash
# Classic branch protection (may 404 if only rulesets are used)
gh api repos/OWNER/REPO/branches/main/protection

# Rulesets — list all, then inspect one by ID
gh api repos/OWNER/REPO/rulesets
gh api repos/OWNER/REPO/rulesets/123456
```

Creating a ruleset that requires a PR, one approval, and passing status checks:

```bash
gh api --method POST repos/OWNER/REPO/rulesets \
  --input - <<'JSON'
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": true,
        "required_review_thread_resolution": true
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "ci/test" },
          { "context": "ci/lint" }
        ]
      }
    }
  ]
}
JSON
```

Notes on the payload: `actor_id: 5` is the built-in "Repository admin" role; `actor_type` can be `RepositoryRole`, `Team`, `Integration`, or `OrganizationAdmin`. `strict_required_status_checks_policy: true` means the branch must be up to date with `main` before merging — this is the setting that causes the "Update branch" button to appear. `non_fast_forward` blocks force-pushes; `deletion` blocks branch deletion.

To flip a ruleset into dry-run mode while you tune it:

```bash
gh api --method PUT repos/OWNER/REPO/rulesets/123456 \
  -f enforcement='evaluate'
```

## Common Pitfalls & Gotchas

**1. Required status checks must have run at least once.** If you add `ci/test` as a required check but no workflow has ever produced a check run with that exact name, PRs will hang forever waiting for a check that never appears. Push a commit that triggers the workflow *first*, then add the requirement. Also: the check name is the **job name**, not the workflow name — `ci/test` above means a job literally named `test` inside a workflow named `ci`.

**2. `require_last_push_approval` surprises people.** When enabled, if the last person to push to the PR is also the person who approved it, the approval is invalidated. This is great for security and infuriating when you're solo on a repo. If you're a one-person team, either leave it off or add yourself to the bypass list.

**3. Rulesets and classic protection coexist — and conflict.** If you have both, GitHub evaluates both and the union of restrictions applies. During migration, delete the classic rule *after* verifying the ruleset behaves. And remember: rulesets apply to the *ref*, not the branch object, so a ruleset targeting `refs/heads/release/*` will catch branches you create tomorrow.

## Try It Yourself

1. **Audit your busiest repo.** Run `gh api repos/OWNER/REPO/rulesets` and `gh api repos/OWNER/REPO/branches/main/protection`. Write down which rules are enforced by which mechanism. You'll likely find gaps — most teams have classic protection with no `required_status_checks`.

2. **Create a ruleset in evaluate mode.** Use the JSON above but set `"enforcement": "evaluate"` and target `refs/heads/main`. Push a trivial commit directly to `main` and check `Settings → Rules → Rulesets → [your ruleset] → Insights` to see it flagged. Then flip to `active` and confirm the push is rejected.

3. **Add a bypass for your release bot.** If you use GitHub Actions to bump versions, add the Actions integration to `bypass_actors` with `bypass_mode: "pull_request"` so it can merge but not force-push. Verify by triggering the workflow and watching it succeed where a human push would fail.

## Next Up

Tomorrow: **Issues Deep Dive: Labels, Milestones, Sub-Issues & Issue Types.** We'll cover how to model work hierarchically with sub-issues, why issue types are replacing the "prefix the title with `[Bug]`" anti-pattern, and how to wire labels and milestones into a queryable project board.
