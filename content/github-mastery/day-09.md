---
title: "Day 09: GitHub Projects: Tables, Boards, Roadmaps, Custom Fields & Iterations"
date: 2026-10-19
tags: ["til", "github-mastery", "projects", "roadmap"]
---

## What I Explored Today

Today I dug into GitHub Projects (the "new" Projects, not the deprecated classic Projects), specifically the four view types — Table, Board, Roadmap, and the underlying data model that powers them. The key insight that reframed everything for me: a Project is not a container of issues, it's a *queryable dataset* of project items, where each item can be an issue, a PR, or a draft issue, and each item carries custom fields. Views are just saved queries with a layout. Once you internalize that, the whole feature set stops feeling like a Jira clone and starts feeling like a lightweight database with a UI. I spent the afternoon building a small sprint board, wiring up iteration fields, and poking at the GraphQL API to understand what's happening under the hood.

## The Core Concept

The mental model that matters: **items + fields + views**. An *item* is a reference to an issue, PR, or draft. A *field* is a typed attribute attached to items — built-in fields (`Status`, `Assignees`, `Labels`, `Milestone`, `Repository`, `Title`) plus custom fields you define (`Text`, `Number`, `Date`, `Single select`, `Iteration`). A *view* is a saved filter + sort + grouping + layout combination.

Why this matters: the same item can appear in a Table sorted by priority, a Board grouped by Status, and a Roadmap plotted by a date field — without duplication. The Board view's columns are literally the options of a `Single select` field (usually `Status`). The Roadmap view is a Gantt-ish chart that requires *two* date fields (start and target). Iterations are a special field type that auto-generates fixed-length cycles (default 2 weeks) and lets you filter `iteration:@current` in views and workflows.

The other thing worth internalizing: Projects live at the **user** or **organization** level, not the repo level. A single project can pull items from many repos. That's the whole point — cross-repo planning.

## Key Commands / Configuration / Code

Projects are mostly UI-driven, but the CLI and GraphQL are where the real leverage is.

```bash
# List projects for the current repo's owner (org or user)
gh project list --owner my-org

# List projects owned by you
gh project list --owner @me

# Create a project (returns project number, not ID — you'll need both)
gh project create --owner my-org --title "Platform Sprint Board"

# Link a project to a repo so it shows in the repo's Projects tab
gh project link 5 --owner my-org --repo my-org/api

# Add an issue to a project (by URL or number + repo)
gh project item-add 5 --owner my-org --url https://github.com/my-org/api/issues/42

# List items with their field values (JSON for scripting)
gh project item-list 5 --owner my-org --format json --limit 100
```

Custom fields and iterations are created in the UI (Settings → Fields), but you can read and write them via GraphQL. The `projectV2` node is the entry point:

```graphql
# Fetch a project, its fields, and the first 20 items with field values
query($owner: String!, $number: Int!) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      title
      fields(first: 50) {
        nodes {
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField { options { id name } }
          ... on ProjectV2IterationField {
            configuration {
              iterations { id title startDate duration }
            }
          }
        }
      }
      items(first: 20) {
        nodes {
          id
          content {
            ... on Issue { number title url }
            ... on PullRequest { number title url }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldIterationValue { title field { ... on ProjectV2FieldCommon { name } } }
            }
          }
        }
      }
    }
  }
}
```

A few field-type gotchas worth knowing before you design a schema:

```text
Status        → Single select (the Board's grouping field by default)
Priority      → Single select (P0/P1/P2/P3 — keep options stable, renaming breaks filters)
Estimate      → Number
Start date    → Date   (required for Roadmap)
Target date   → Date   (required for Roadmap)
Sprint        → Iteration (auto-generates cycles; filter with iteration:@current)
```

Filter syntax in views is its own mini-language and is worth memorizing:

```text
status:"In progress" assignee:@me -label:blocked
iteration:@current milestone:"v2.0"
no:assignee is:open repo:my-org/api
```

## Common Pitfalls & Gotchas

**1. Project *number* vs. project *ID*.** The CLI takes `--owner` + a numeric project number (the `#5` you see in the URL). The GraphQL API takes a global node ID (`PVT_kwDO...`). Mixing them up is the #1 source of "not found" errors when scripting. Get the node ID with `gh project view 5 --owner my-org --format json --jq .id`.

**2. Renaming a single-select option silently breaks saved filters and workflows.** If your Board groups by `Status` and you rename `In progress` → `Doing`, any view filter or workflow that references `status:"In progress"` stops matching. Options have stable IDs internally, but the *filter syntax* uses names. Treat option names as an API contract.

**3. Iterations are per-field, not per-project.** Two iteration fields on the same project (e.g., `Sprint` and `Release cycle`) each maintain their own independent schedule. Changing the iteration length on one doesn't touch the other. Also: `iteration:@current` only resolves correctly if the field's schedule actually covers today — a misconfigured start date makes the filter silently return nothing.

**4. Draft issues are not real issues.** Items added as drafts live only in the project until you convert them. They don't appear in repo issue lists, don't trigger workflows, and can't be referenced by `#number`. Fine for backlog grooming, dangerous if you assume they're tracked.

## Try It Yourself

1. **Build a three-view project.** Create an org-level project, add `Status` (Todo / In progress / Done), `Priority` (P0–P3), and `Sprint` (Iteration, 2 weeks). Add five issues from two different repos. Then create a Table view filtered to `assignee:@me`, a Board grouped by `Status`, and a Roadmap using `Start date` and `Target date`. Confirm the same items appear in all three.

2. **Script an item dump.** Use `gh project item-list <number> --owner <org> --format json` and pipe through `jq` to print `title`, `status`, and `sprint` for every item. Then do the same via the GraphQL query above and diff the two outputs — you'll see exactly which fields the CLI flattens.

3. **Break a filter on purpose.** Rename a `Status` option in the UI, then reload a view that filtered on the old name. Note what happens (items vanish or filter shows zero results). Restore the name and confirm the view recovers. This is the fastest way to internalize pitfall #2.

## Next Up

Tomorrow: **Automating GitHub Projects: Built-in Workflows & the GraphQL API.** We'll wire up the built-in auto-add and auto-archive workflows, then go beyond them — using `actions/github-script` and the `updateProjectV2ItemFieldValue` mutation to move items between columns on PR merge, and to auto-populate the `Sprint` field from the current iteration. Bring your project node ID; you'll need it.
