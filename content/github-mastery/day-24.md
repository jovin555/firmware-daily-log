---
title: "Day 24: Discussions, Wikis & Community Health Files"
date: 2026-11-03
tags: ["til", "github-mastery", "discussions", "community"]
---

## What I Explored Today

Today I went past the code itself and looked at the collaboration surface that surrounds a repository: GitHub Discussions, the built-in Wiki, and the "community health files" that GitHub silently looks for in a `.github` directory. What surprised me is how much of this is *convention over configuration* — GitHub auto-detects files like `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and issue/PR templates by filename and location, and then surfaces them in the UI (the "Community Standards" checklist, the "New issue" chooser, the security policy link) without any settings toggles. I spent the afternoon wiring these into a repo and testing the `gh` CLI paths for Discussions, which is where the real automation friction lives.

## The Core Concept

The mental model that finally clicked: **GitHub treats a repository as a community, not just a code folder.** Issues are for *actionable* work items; Discussions are for *open-ended* conversation (Q&A, ideas, polls, show-and-tell) that shouldn't clutter the issue tracker. The Wiki is a separate git-backed repo for durable docs that don't belong in the main tree. And community health files are *declarative metadata* — you don't configure them in settings, you commit them to well-known paths and GitHub's UI reads them.

The "why" is discoverability and reducing maintainer load. A first-time contributor landing on your repo sees a green "Community Standards" checklist, a `CONTRIBUTING.md` link on the new-issue page, and a security policy — all because the files exist at the right paths. The `.github` directory is special: files placed there apply repo-wide, and a `.github` **repository** (org-level, named literally `.github`) can provide *default* community health files to every repo in the org that doesn't override them. That default-inheritance behavior is the part most engineers miss.

## Key Commands / Configuration / Code

Community health files live at these recognized paths (root, `docs/`, or `.github/`):

```text
.github/
├── CONTRIBUTING.md          # linked from new-issue/PR pages
├── CODE_OF_CONDUCT.md       # shown in Community Standards
├── SECURITY.md              # "Report a vulnerability" button
├── SUPPORT.md               # how to get help
├── FUNDING.yml              # sponsor button config
├── ISSUE_TEMPLATE/
│   ├── bug_report.yml       # YAML form (preferred over .md)
│   └── config.yml           # chooser config: blank issues, contact links
└── PULL_REQUEST_TEMPLATE.md
```

A real `ISSUE_TEMPLATE/bug_report.yml` (GitHub issue forms syntax):

```yaml
name: Bug report
description: Something is broken
labels: ["bug", "triage"]
body:
  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
      placeholder: |
        1. Run `make build`
        2. ...
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: Version
      placeholder: "v1.4.2"
```

`ISSUE_TEMPLATE/config.yml` to disable blank issues and add a Discussion link:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Ask a question
    url: https://github.com/org/repo/discussions/categories/q-a
    about: Please use Discussions for questions, not issues.
```

`SECURITY.md` — the `security` CLI reads this and the private advisory flow:

```markdown
# Security Policy
## Reporting a Vulnerability
Please do **not** open a public issue. Use
[private vulnerability reporting](https://github.com/org/repo/security/advisories/new).
```

Enabling Discussions and driving it from the CLI (Discussions has **no** first-class `gh` subcommand — you go through the GraphQL API):

```bash
# Enable Discussions on the repo (REST)
gh api -X PATCH repos/org/repo -f has_discussions=true

# List discussion categories (GraphQL — needs the repo node id)
gh api graphql -f query='
  query($owner:String!,$name:String!){
    repository(owner:$owner,name:$name){
      discussionCategories(first:20){ nodes { id name } }
    }
  }' -f owner=org -f name=repo
```

Wiki is a separate git repo you clone directly:

```bash
# Clone the wiki (note the .wiki.git suffix)
git clone https://github.com/org/repo.wiki.git
cd repo.wiki
echo "# Architecture" > Architecture.md
git add . && git commit -m "Add architecture page" && git push
```

## Common Pitfalls & Gotchas

1. **`.github` repo inheritance only fills gaps.** Org-level default community health files are used *only* when the individual repo lacks that file. If you add a `CONTRIBUTING.md` to one repo, it stops inheriting the org default — there's no merge. Also, the org `.github` repo must be **public** for the defaults to apply.

2. **Discussions can't be created via REST.** There's no `POST /repos/{owner}/{repo}/discussions`. Everything beyond enabling the feature is GraphQL (`createDiscussion`, `addDiscussionComment`). Scripts that assume REST parity with issues will fail silently or 404.

3. **Wiki is disabled by default and not in the main clone.** `has_wiki` defaults to `true` on new repos but many orgs disable it; and `git clone` of the main repo does **not** include wiki content. You must clone `repo.wiki.git` separately, and wikis can't be edited via the Contents API — only via git or the web UI.

## Try It Yourself

1. In a scratch repo, create `.github/ISSUE_TEMPLATE/bug_report.yml` and `config.yml` (with `blank_issues_enabled: false`), push, then open the "New issue" page and confirm the form renders and the blank-issue option is gone.

2. Enable Discussions with `gh api -X PATCH repos/<you>/<repo> -f has_discussions=true`, then use a GraphQL mutation to create one discussion in the General category and verify it appears in the UI.

3. Clone a repo's wiki (`git clone https://github.com/<you>/<repo>.wiki.git`), add a page, push, and confirm the "Wiki" tab updates — then check whether your repo shows the green Community Standards checklist once `CONTRIBUTING.md` and `SECURITY.md` exist.

## Next up

Tomorrow: **The `gh` CLI & REST/GraphQL API Automation** — scripting repo operations end-to-end, pagination, `--jq` filtering, and when to reach for GraphQL over REST.
