---
title: "Day 05: Issues Deep Dive: Labels, Milestones, Sub-Issues & Issue Types"
date: 2026-10-15
tags: ["til", "github-mastery", "issues", "labels"]
---

## What I Explored Today

Today I went past the "open an issue, close an issue" workflow and dug into the metadata layer that turns a flat list of issues into something you can actually manage at scale. I spent the morning wiring up labels via the CLI, grouping work into milestones, breaking a large feature into sub-issues, and experimenting with the newer issue types feature that lets you classify issues as Bug, Task, or Feature. The surprising part wasn't any single feature — it was how much of this is scriptable. Once I realized `gh issue` and the REST API expose almost everything the web UI does, I stopped clicking and started writing one-liners.

## The Core Concept

An issue is not just a title and a body. It's a node in a graph with typed edges: labels (many-to-many tags), a milestone (one-to-many grouping), a parent (sub-issue hierarchy), and a type (a single classification). The reason this matters is that **triage is a query problem, not a reading problem**. If you can't express "all open bugs in the v2.0 milestone that aren't blocked by an open sub-issue" as a filter, you're going to spend your standup scrolling instead of shipping.

GitHub gives you two query surfaces for this: the search syntax (`is:issue label:bug milestone:v2.0`) and the GraphQL API for anything the search bar can't express. Labels are cheap and unstructured — use them liberally. Milestones are temporal — they map to a release or a sprint. Sub-issues are structural — they encode "this work is composed of that work." Issue types are categorical — they replace the old convention of prefixing titles with `[Bug]`. Getting these four axes right means your project board, your saved filters, and your automation all compose cleanly.

## Key Commands / Configuration / Code

**Creating and applying labels from the CLI:**

```bash
# Create a label with a hex color (no leading #) and a description
gh label create "priority:high" --color "B60205" --description "Blocks the release"

# Apply multiple labels to an issue in one call
gh issue edit 42 --add-label "priority:high,bug" --remove-label "triage"

# List every label in the repo as JSON, then filter with jq
gh label list --json name,color --limit 100 | jq '.[] | select(.color=="B60205")'
```

**Milestones** are not exposed as a first-class `gh` subcommand, so use the REST API:

```bash
# Create a milestone (due_on must be RFC 3339)
gh api repos/:owner/:repo/milestones \
  -f title="v2.0" \
  -f description="Q4 release" \
  -f due_on="2026-12-31T00:00:00Z"

# Assign issue 42 to that milestone by number
gh issue edit 42 --milestone "v2.0"
```

**Sub-issues** use the GraphQL API. You need the parent's node ID and the child's node ID:

```bash
# Get node IDs (note: `id` is the global node ID, `number` is the repo-local one)
gh issue view 42 --json id,number
gh issue view 43 --json id,number

# Link 43 as a sub-issue of 42
gh api graphql -f query='
  mutation($parent: ID!, $child: ID!) {
    addSubIssue(input: {issueId: $parent, subIssueId: $child}) {
      issue { number }
    }
  }' -f parent="I_kwDO..." -f child="I_kwDO..."
```

**Issue types** are configured at the organization level (Settings → Issue types) and then applied per issue:

```bash
# Set the type on an existing issue (types are org-scoped, so this needs the org)
gh issue edit 42 --type Bug
```

**The search query that ties it all together:**

```
is:issue is:open label:"priority:high" milestone:v2.0 -label:blocked
```

## Common Pitfalls & Gotchas

**1. `gh issue edit --milestone` takes the title, not the number.** This trips everyone up. `--milestone "v2.0"` works; `--milestone 3` will fail or silently match nothing. If you script this, fetch the milestone title first with `gh api repos/:owner/:repo/milestones --jq '.[].title'`.

**2. Sub-issues are GraphQL-only right now.** There is no `gh issue sub-issue add` command, and the REST API doesn't expose the relationship. You must use the `addSubIssue` mutation with global node IDs — not issue numbers. Copying the number from the URL will produce a confusing "Could not resolve to a node" error.

**3. Labels are case-insensitive but whitespace-sensitive.** `bug` and `Bug` are the same label, but `priority: high` (with a space) is a different label from `priority:high`. Pick a convention — I use `namespace:value` with no spaces — and enforce it in a repo template or a CI check, because renaming a label across 400 issues later is miserable.

**4. Issue types require an org.** If you're working in a personal repo, `--type` will error out. Types are an organization-level feature; personal accounts fall back to labels for classification.

## Try It Yourself

1. **Build a triage query.** In any repo you own, create three labels (`priority:high`, `priority:low`, `triage`), apply them to a few issues, then write a search query that returns only high-priority issues that still need triage. Save it as a bookmark.

2. **Script a milestone assignment.** Use `gh api` to list all open issues with the label `bug`, then loop over them and assign each to a milestone called `backlog` using `gh issue edit`. Bonus: make it idempotent so re-running doesn't error.

3. **Link a sub-issue.** Pick a parent issue and a child issue, fetch both node IDs with `gh issue view --json id`, and link them with the `addSubIssue` GraphQL mutation. Verify the hierarchy renders in the web UI.

## Next Up

Tomorrow I'm tackling **Issue Templates & YAML Issue Forms with `config.yml`** — how to stop your team from filing issues that say "it's broken" with no reproduction steps. We'll cover the difference between Markdown templates and the newer YAML forms, how `config.yml` controls the "New issue" chooser, and how to require structured fields before submission.
