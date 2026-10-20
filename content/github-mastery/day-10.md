---
title: "Day 10: Automating GitHub Projects: Built-in Workflows & the GraphQL API"
date: 2026-10-20
tags: ["til", "github-mastery", "projects", "automation"]
---

## What I Explored Today

Today I dug into the two automation layers that sit on top of GitHub Projects (the new Projects experience, not the legacy Projects Classic). The first is the built-in workflow engine — the no-code automation that lives in the project's Settings → Workflows panel and handles the 80% case: moving items between columns when issues close, auto-archiving stale cards, and setting fields based on labels. The second is the GraphQL API, which is the *only* way to programmatically manipulate Projects v2 data — there is no REST endpoint for Projects v2 items, fields, or views. That asymmetry is the single most important thing to internalize before you try to script anything against a project board.

## The Core Concept

The reason Projects v2 is GraphQL-only comes down to its data model. A Projects v2 board isn't a flat list of cards — it's a graph of `ProjectV2` objects containing `ProjectV2Item` nodes, each of which holds a `fieldValues` connection pointing at typed field nodes (`ProjectV2Field`, `ProjectV2SingleSelectField`, `ProjectV2IterationField`). Items can be issues, pull requests, or draft issues, and the same issue can appear on multiple projects with different field values per project. That many-to-many, per-project-field-value structure doesn't map cleanly onto REST's resource-per-URL model, so GitHub never shipped a REST surface for it.

The practical consequence: if you want to do anything beyond what the built-in workflows offer — bulk-import from a CSV, sync a field from an external system, auto-populate a "Size" field from PR diff stats — you're writing GraphQL. The built-in workflows are genuinely useful and you should exhaust them first, but they're deliberately limited to a fixed menu of triggers and actions. The moment you need a custom trigger (say, "when a linked issue gets a `priority:high` label") or a custom action ("set the `Estimate` field to the sum of sub-issue estimates"), you're in GraphQL territory.

## Key Commands / Configuration / Code

**Built-in workflows** are configured per-project under Settings → Workflows. The ones worth enabling on day one:

- **Item closed** → set status to Done
- **Pull request merged** → set status to Done
- **Auto-archive items** → archive after N days of inactivity (configurable, default 14)
- **Auto-add to project** → filter-based, e.g. `is:issue label:bug` adds matching issues automatically

The auto-add filter uses GitHub's search syntax and is evaluated on issue/PR creation and updates. It's the closest thing to a "trigger" you get without code.

**The GraphQL API** requires a token with the `project` scope (classic PAT) or `Projects` read/write permission (fine-grained PAT). Here's the minimum viable query to list items on a project, with field values:

```graphql
# Requires: project scope. Replace OWNER and NUMBER.
query ProjectItems($owner: String!, $number: Int!, $cursor: String) {
  organization(login: $owner) {
    projectV2(number: $number) {
      items(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content {
            __typename
            ... on Issue { number title state }
            ... on PullRequest { number title state }
            ... on DraftIssue { title }
          }
          fieldValues(first: 20) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
```

Note the `organization(login:)` wrapper — for a user-owned project you'd use `user(login:)` instead. The `__typename` on `content` is essential because items can be issues, PRs, or drafts, and you must handle all three or your script will crash on the first draft card.

**Mutating a field value** is a two-step dance: you need the project's field ID and the item's ID, then call `updateProjectV2ItemFieldValue`:

```graphql
mutation SetEstimate($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: Float!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId
    itemId: $itemId
    fieldId: $fieldId
    value: { number: $value }
  }) {
    projectV2Item { id }
  }
}
```

The `value` input is a union — `{ number: }`, `{ text: }`, `{ singleSelectOptionId: }`, `{ date: }`, `{ iterationId: }`. Passing the wrong shape silently fails with a validation error, not a type error, so log the response.

**Pagination** is cursor-based and you must loop `hasNextPage` yourself; there's no auto-pagination in the GraphQL API. A 500-item board is 10 round trips at `first: 50`.

## Common Pitfalls & Gotchas

**The `project` scope is not the same as `repo`.** A classic PAT with only `repo` scope will authenticate fine but return `null` for `projectV2` with no error message. This is the #1 reason scripts "silently do nothing." Verify your token scopes with `curl -H "Authorization: token $TOKEN" https://api.github.com/` and check the `x-oauth-scopes` response header.

**Field IDs are per-project, not per-field-name.** Two projects can both have a "Status" field with completely different IDs and different option IDs. Never hardcode field IDs across projects — query `projectV2.fields(first: 50)` first and build a name→ID map at runtime.

**Draft issues have no `number`.** If your script assumes `content.number` exists, it will throw on draft cards. Always branch on `__typename` and handle `DraftIssue` separately (it only has `title` and `body`).

## Try It Yourself

1. **Enable auto-add and verify it.** On a test project, add an auto-add workflow with filter `is:issue label:automation-test`, then create an issue with that label and confirm it lands on the board within ~30 seconds. Note the latency — it's not instant.

2. **Write a read-only GraphQL script.** Using `gh api graphql -f query='...'` (the `gh` CLI handles auth for you), list all items on a project and print `content.title` plus the value of a single-select field. Handle pagination with a `while` loop on `hasNextPage`.

3. **Bulk-set a field.** Take the item IDs from task 2 and set a number field (e.g. `Estimate`) to a fixed value across all of them using `updateProjectV2ItemFieldValue`. Confirm the change in the UI, then re-run and observe that it's idempotent.

## Next Up

Tomorrow I'm starting the GitHub Actions deep dive: **GitHub Actions Fundamentals: Workflows, Jobs, Steps & Runners** — the execution model, how runners are provisioned, and why the job/step distinction matters more than it looks.
