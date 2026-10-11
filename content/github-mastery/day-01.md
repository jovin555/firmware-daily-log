---
title: "Day 01: GitHub Overview: Repos, Orgs, Permissions & the Feature Map"
date: 2026-10-11
tags: ["til", "github-mastery", "github", "overview"]
---

# Day 01: GitHub Overview: Repos, Orgs, Permissions & the Feature Map

## What I Explored Today

I kicked off this series by mapping GitHub's object model end-to-end instead of treating it as "just a remote for `git push`." I spent the day tracing how a repository, an organization, a team, and a permission level compose into the access decisions GitHub actually enforces. I also walked the feature map — Issues, Projects, Actions, Packages, Codespaces, Security — and noted which of those are repo-scoped versus org-scoped, because that distinction drives almost every design decision you'll make later. The goal was to build a mental model solid enough that when I hit a 403 in CI or a fork can't see a secret, I know exactly which layer to inspect.

## The Core Concept

Git is a distributed content-addressable filesystem. GitHub is a multi-tenant authorization and automation layer bolted on top of it. These are two different systems, and conflating them is the root of most confusion.

The key insight: **GitHub permissions are not stored in the repository.** They live in GitHub's database and are evaluated at the API/transport boundary. A clone is a full copy of history; access is a policy decision made per-request. That's why you can have a local clone of a repo you've since lost access to — the objects are yours, the *future* fetches are not.

The hierarchy is: **Enterprise → Organization → Team → Repository → Branch.** Permissions flow down and can be tightened at each level. A repository can be owned by a personal account or an organization. Organizations group repos and people, and Teams are the unit of bulk permission assignment. Branch protection is the final, most granular gate.

The base permission ladder for a repo is: **Read → Triage → Write → Maintain → Admin.** These are cumulative roles, not flags. `Write` can push to unprotected branches; `Maintain` adds repo settings without destructive access; `Admin` can delete the repo and manage access. Outside collaborators get per-repo access without org membership — useful for contractors, and a common source of "why can't they see the other repo" tickets.

## Key Commands / Configuration / Code

The `gh` CLI is the fastest way to inspect the model. Everything below is real and runnable.

```bash
# Authenticate and check which scopes your token actually has.
# Missing scopes are the #1 cause of confusing 404s (GitHub returns 404, not 403,
# for resources you can't see — a deliberate information-hiding choice).
gh auth status

# Inspect a repo's visibility and default branch.
gh repo view cli/cli --json name,visibility,defaultBranchRef,isFork

# List org members and their roles.
gh api /orgs/<org>/members --paginate --jq '.[].login'
gh api /orgs/<org>/memberships/<username> --jq '.role'   # "admin" or "member"

# List teams in an org.
gh api /orgs/<org>/teams --paginate --jq '.[].slug'

# Check a user's effective permission on a specific repo.
# Returns: admin, maintain, push, triage, pull, or none.
gh api /repos/<owner>/<repo>/collaborators/<username>/permission --jq '.permission'

# See branch protection rules (requires admin or a token with repo scope).
gh api /repos/<owner>/<repo>/branches/main/protection
```

For raw Git, the remote is just a URL — GitHub's auth happens over HTTPS or SSH:

```bash
# HTTPS: credentials come from a helper (gh auth setup-git wires this up).
git remote -v
# origin  https://github.com/<owner>/<repo>.git (fetch)

# SSH: identity is your key, and access is still evaluated server-side.
ssh -T git@github.com   # prints "Hi <user>! You've successfully authenticated..."
```

A minimal org-level Actions permissions policy, expressed as the API call you'd make to lock it down:

```bash
# Restrict which actions can run org-wide (allowlist model).
gh api -X PUT /orgs/<org>/actions/permissions \
  -f enabled_repositories=all \
  -f allowed_actions=selected
```

## Common Pitfalls & Gotchas

**1. 404 vs 403 is intentional.** GitHub returns `404 Not Found` for private resources you lack access to, rather than `403 Forbidden`, to avoid leaking existence. If a CI job "can't find" a repo that clearly exists, check the token's scopes and the app's installation scope before you debug the URL.

**2. Fork secrets don't propagate.** When you fork a repo, Actions secrets, environments, and most settings do **not** come with it. Workflows that pass on the upstream repo will fail on the fork with empty `secrets.*` values. This is by design — otherwise anyone could exfiltrate your credentials by forking.

**3. Team permissions are additive, and "no access" isn't a thing.** A user's effective access is the *maximum* across all their team memberships and direct grants. You cannot subtract access with a team. To reduce someone's rights you must remove them from the granting team or downgrade the repo's base permission — there is no deny rule.

## Try It Yourself

1. **Audit your own access.** Run `gh auth status` and note the scopes. Then pick a repo you contribute to and run `gh api /repos/<owner>/<repo>/collaborators/<your-username>/permission --jq '.permission'`. Confirm it matches what you *thought* you had.

2. **Map an org.** If you have access to any org, list its teams (`gh api /orgs/<org>/teams --jq '.[].slug'`) and its repos (`gh repo list <org> --limit 100`). Identify one repo whose access is granted purely via a team rather than direct collaborators.

3. **Prove the fork-secret gotcha.** Fork a public repo that uses Actions secrets, open the Actions tab, and inspect a workflow run. Note that `secrets.*` resolves to empty. Then read the workflow YAML and identify which step would fail first.

## Next Up

Tomorrow: **Git Essentials for GitHub: Branches, Remotes, Rebase vs Merge.** We'll cover how GitHub's branch model interacts with `origin` vs `upstream`, when to rebase versus merge on a PR, and why `git push --force-with-lease` is the only force-push you should ever type.
