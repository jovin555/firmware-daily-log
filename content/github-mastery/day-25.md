---
title: "Day 25: The gh CLI & REST/GraphQL API Automation"
date: 2026-11-04
tags: ["til", "github-mastery", "gh-cli", "api"]
---

## What I Explored Today

Today I dug into the `gh` CLI as more than a convenience wrapper for `git push` — specifically its ability to hit the GitHub REST and GraphQL APIs directly via `gh api`. The realization that landed: `gh` handles authentication, pagination, and JSON formatting for you, which means you can write one-liners that would otherwise require a full script with a token in an environment variable and a `curl` invocation with `-H "Authorization: Bearer ..."`. I spent the afternoon replacing a handful of brittle bash scripts with `gh api` calls and learning where the abstraction leaks.

## The Core Concept

The GitHub CLI is a thin, authenticated client over the same REST and GraphQL endpoints you'd hit with `curl`. The value isn't that it does anything you *can't* do manually — it's that it removes three recurring sources of friction:

1. **Auth.** `gh auth login` stores a token in the system keyring (or `~/.config/gh/hosts.yml`). Every `gh api` call reuses it. No more exporting `GITHUB_TOKEN` in every shell.
2. **Pagination.** REST endpoints return 30 items by default. `gh api` with `--paginate` follows `Link` headers automatically, so you get the full set without writing a loop.
3. **Formatting.** `--jq` pipes the JSON response through `jq` inline, and `--template` lets you use Go templates. You get structured output without a second process.

The mental model: `gh api <endpoint>` is `curl` + auth + pagination + JSON tooling. For anything the higher-level `gh` subcommands (`gh pr`, `gh issue`, etc.) don't cover, `gh api` is the escape hatch. And for complex queries that would take five REST round-trips, GraphQL via `gh api graphql` gets it in one.

## Key Commands / Configuration / Code

```bash
# REST: get the authenticated user, filtered to two fields
gh api user --jq '{login: .login, id: .id}'

# REST with a path parameter — list open PRs on a repo, paginated
gh api --paginate repos/cli/cli/pulls \
  --jq '.[] | "\(.number)\t\(.title)"'

# POST with a JSON body — create an issue
gh api repos/OWNER/REPO/issues \
  -f title="Automate the thing" \
  -f body="Filed via gh api" \
  -f labels[]="automation"

# -F reads from a file or treats the value as typed (numbers, booleans)
gh api repos/OWNER/REPO/issues \
  -F title="Typed field" -F assignee=42

# GraphQL: one query, multiple resources, no pagination dance
gh api graphql -f query='
  query($owner: String!, $name: String!) {
    repository(owner: $owner, name: $name) {
      pullRequests(first: 10, states: OPEN) {
        nodes { number title author { login } }
      }
      issues(states: OPEN) { totalCount }
    }
  }' -f owner=cli -f name=cli

# Pass variables from a file for long queries
gh api graphql -F query=@query.graphql -f owner=cli -f name=cli

# Check rate limit headroom before a batch job
gh api rate_limit --jq '.resources.core | {remaining, limit}'
```

The `-f` vs `-F` distinction matters: `-f` always sends a string, `-F` infers type (so `-F draft=true` sends a boolean, `-F number=5` sends an integer). Getting this wrong is the most common cause of a 422 from the API.

## Common Pitfalls & Gotchas

**1. `--paginate` with `--jq` runs jq per page, not on the whole result.** If you `--paginate` and `--jq '.[]'`, you get the items from each page concatenated — usually what you want. But if your jq expression aggregates (e.g., `length`), you'll get one number *per page* instead of a total. Aggregate in a second pass or use GraphQL's `totalCount`.

**2. GraphQL rate limits are points-based, not request-based.** A single GraphQL query can cost hundreds of points depending on node count. REST gives you 5,000 requests/hour; GraphQL gives you 5,000 *points*/hour. A naive query fetching 100 PRs with nested comments can burn through that fast. Always request only the fields you need.

**3. `gh api` inherits the token's scopes, and missing scopes fail with a 404, not a 403.** If your token lacks `repo` scope, hitting a private repo's endpoint returns "Not Found" — which looks like a typo in your path. Check `gh auth status` to see granted scopes before debugging your URL.

## Try It Yourself

1. **Audit stale branches.** Use `gh api --paginate repos/OWNER/REPO/branches --jq '.[].name'` and pipe through a filter for branches with no commits in 90 days (combine with `git for-each-ref` locally, or query the branch's commit date via the API).
2. **Build a PR digest.** Write a GraphQL query that pulls the last 20 merged PRs with author and merge date, then format it as a Markdown table using `--template`.
3. **Rate-limit guard.** Wrap a batch of `gh api` calls in a script that checks `gh api rate_limit` first and exits early if `remaining` is below a threshold you set.

## Next Up

Tomorrow: **Codespaces & Dev Containers for Reproducible Toolchains** — how to pin your entire dev environment (including the `gh` CLI version and your API helper scripts) into a `devcontainer.json` so every collaborator gets the same setup on clone.
