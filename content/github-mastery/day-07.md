---
title: "Day 07: Pull Requests: Reviews, Drafts, Suggested Changes & PR Templates"
date: 2026-10-17
tags: ["til", "github-mastery", "pull-requests", "code-review"]
---

# Day 07: Pull Requests: Reviews, Drafts, Suggested Changes & PR Templates

## What I Explored Today

Today I went past the "open a PR and hope someone looks at it" phase and dug into the mechanics that make pull requests actually useful as a review tool. Specifically: draft PRs as a signal that work isn't ready for review, the review workflow (approve/request changes/comment) and how it maps to branch protection, suggested changes that reviewers can propose inline and authors can commit with one click, and PR templates that enforce a consistent description format. I also spent time on the `gh` CLI equivalents, because doing this from the terminal is faster than clicking through the web UI once you know the flags.

## The Core Concept

A pull request is not just a diff — it's a **conversation with state**. GitHub models that state explicitly: a PR can be a draft or ready-for-review, a review can be `APPROVED`, `CHANGES_REQUESTED`, or `COMMENTED`, and each review is tied to a specific commit SHA. That last detail matters: if you push new commits after a review, the approval doesn't automatically apply to the new code unless branch protection is configured to dismiss stale reviews.

The "why" behind drafts and suggested changes is about **reducing review noise and round-trips**. A draft PR says "I want CI to run and I want early feedback, but don't block your day reviewing this yet." A suggested change embeds the exact diff a reviewer wants, so the author doesn't have to interpret a prose comment and re-implement it — they click "Commit suggestion" and the change lands as a commit (or a batch of them) authored by the reviewer. PR templates exist because a PR description is the only durable context future readers (including you in six months) will have for *why* a change exists; without a template, that context is whatever the author felt like typing at 11pm.

## Key Commands / Configuration / Code

### Draft PRs from the CLI

```bash
# Create a PR as a draft — CI runs, but reviewers know it's WIP
gh pr create --draft --title "WIP: refactor auth middleware" --body "Early feedback welcome"

# Flip an existing draft to ready-for-review (this notifies reviewers)
gh pr ready 123

# Check whether a PR is a draft
gh pr view 123 --json isDraft --jq '.isDraft'
```

### Reviewing and requesting changes

```bash
# Approve
gh pr review 123 --approve --body "LGTM, tested locally"

# Request changes (blocks merge if branch protection requires approval)
gh pr review 123 --request-changes --body "See inline comment on token refresh"

# Comment-only review (does not count toward approval)
gh pr review 123 --comment --body "Nit: naming"
```

### Suggested changes (web UI + CLI)

In the web UI, a reviewer selects lines in the diff and clicks the **±** (suggest change) button, producing a fenced block:

````markdown
```suggestion
const token = await refreshToken(credentials);
```
````

The author can then apply it with **Commit suggestion** (single) or **Add suggestion to batch** → **Commit suggestions** (multiple at once). From the CLI, you can list and apply review comments that contain suggestions:

```bash
# List review comments on a PR (includes suggestion bodies)
gh api repos/{owner}/{repo}/pulls/123/comments \
  --jq '.[] | {id, path, body}'
```

### PR template

Create `.github/pull_request_template.md` (or `.github/PULL_REQUEST_TEMPLATE.md` — both work). GitHub auto-populates the PR body with it:

```markdown
## Summary
<!-- What changed and why. Link the issue: Closes #123 -->

## Test plan
- [ ] Unit tests added/updated
- [ ] Manually verified on staging

## Risk
<!-- Rollback plan if this breaks prod -->
```

You can also have multiple templates in `.github/PULL_REQUEST_TEMPLATE/` and select one via `?template=bugfix.md` in the compare URL, or with `gh pr create --template bugfix.md`.

### Dismissing stale approvals (branch protection)

In repo **Settings → Branches → Branch protection rules**, enable **Dismiss stale pull request approvals when new commits are pushed**. This is the config that makes reviews actually mean something after a force-push or follow-up commit.

## Common Pitfalls & Gotchas

1. **Approvals don't survive new commits by default.** If "Dismiss stale approvals" is off, a reviewer can approve commit A, you push commit B, and the PR merges with an approval that never saw B. Turn it on for any branch where review is load-bearing.

2. **Suggested changes can't span deleted lines or cross file boundaries.** The suggestion block must replace contiguous existing lines in a single file. If a reviewer wants to delete a line and add two others, the suggestion has to be anchored to the line being replaced — otherwise the "Commit suggestion" button won't appear.

3. **Draft PRs still trigger CI and still count against your Actions minutes.** A draft is a *review* signal, not a CI gate. If you're iterating on a flaky test, you're burning minutes; consider `paths-ignore` or a separate workflow trigger for drafts if cost matters.

## Try It Yourself

1. **Draft → ready flow:** Open a draft PR with `gh pr create --draft`, push a follow-up commit, then run `gh pr ready <num>`. Confirm in the web UI that the "Ready for review" event appears in the timeline and that reviewers were notified.

2. **Suggested change round-trip:** On a PR you own, have a second account (or a collaborator) leave a suggestion on a single line. Apply it via **Commit suggestion**, then check `git log` — the commit should be authored by the reviewer, not you.

3. **Template enforcement:** Add `.github/pull_request_template.md` with a "Test plan" checklist, open a new PR, and verify the body is pre-filled. Then try `gh pr create --template` with a second template in `.github/PULL_REQUEST_TEMPLATE/`.

## Next Up

Tomorrow: **Merge Strategies, Merge Queue & Required Status Checks** — squash vs. merge commit vs. rebase, why merge queues exist (and when they're overkill), and how to wire required checks so a green PR can't merge onto a red `main`.
