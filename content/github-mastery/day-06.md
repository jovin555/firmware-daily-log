---
title: "Day 06: Issue Templates & YAML Issue Forms with config.yml"
date: 2026-10-16
tags: ["til", "github-mastery", "issue-templates", "issue-forms"]
---

## What I Explored Today

Today I dug into GitHub's issue template system, which has quietly evolved from a single Markdown file into a full YAML-based form engine. I set up both legacy Markdown templates and the newer issue forms, wired them together with a `config.yml` that controls the template chooser, and tested how each behaves when a user clicks "New Issue." The difference between a free-text template and a structured form is dramatic — one nudges, the other enforces. For any repo that receives bug reports from people who aren't core maintainers, the YAML form is the difference between "it doesn't work" and a reproducible report with version, OS, and logs attached.

## The Core Concept

The problem issue templates solve is signal-to-noise. An untemplated issue tracker fills up with vague reports that require three rounds of back-and-forth before anyone can act. Templates reduce that friction by pre-filling structure, but Markdown templates are just suggestions — a user can delete every heading and type "broken pls fix."

YAML issue forms change the contract. Instead of rendering editable Markdown, GitHub renders actual form controls: text inputs, dropdowns, checkboxes, and textareas. Required fields can't be skipped. Dropdowns constrain input to known values. This means the data arriving in your issue is *parseable* — you can build automation on top of it, because a "Browser" field will always contain one of the options you defined, not "chrome i think."

The `config.yml` file is the third piece. It lives in the same directory and controls the chooser page: whether blank issues are allowed, and where the "Open a blank issue" link points. Without it, GitHub shows a default chooser. With it, you can force users through a template or redirect them to Discussions for questions.

The mental model: **Markdown templates are documentation. YAML forms are an API.** Choose based on whether you need to trust the shape of the incoming data.

## Key Commands / Configuration / Code

All template files live in `.github/ISSUE_TEMPLATE/`. The directory name is case-sensitive and must be exactly that.

**Legacy Markdown template** — `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug report
about: Something is broken
title: "[BUG] "
labels: ["bug", "triage"]
assignees: []
---

**Describe the bug**
A clear description.

**To reproduce**
1. Step one
2. Step two

**Expected behavior**
What you expected.
```

The frontmatter keys are `name`, `about`, `title`, `labels`, `assignees`. Note `about` — not `description`, which is the YAML form key. Mixing them up silently drops the field.

**YAML issue form** — `.github/ISSUE_TEMPLATE/bug_report.yml`:

```yaml
name: Bug Report
description: File a reproducible bug
title: "[Bug]: "
labels: ["bug", "needs-triage"]
body:
  - type: markdown
    attributes:
      value: "Thanks for taking the time to file this."
  - type: input
    id: version
    attributes:
      label: Version
      description: Output of `myapp --version`
      placeholder: "1.4.2"
    validations:
      required: true
  - type: dropdown
    id: os
    attributes:
      label: Operating System
      options:
        - Linux
        - macOS
        - Windows
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: Relevant logs
      render: shell   # syntax-highlights the pasted block
    validations:
      required: false
  - type: checkboxes
    id: checks
    attributes:
      label: Pre-submission checks
      options:
        - label: I searched existing issues
          required: true
```

Every `id` must be unique and is what appears as the field key in the issue body. Valid `type` values are `markdown`, `input`, `textarea`, `dropdown`, `checkboxes`. The `render` key on a textarea accepts any Linguist language identifier.

**Chooser config** — `.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Ask a question
    url: https://github.com/org/repo/discussions
    about: Please use Discussions for usage questions.
  - name: Security vulnerability
    url: https://github.com/org/repo/security/advisories/new
    about: Report security issues privately.
```

Setting `blank_issues_enabled: false` forces every issue through a template. The `contact_links` array adds buttons to the chooser that redirect elsewhere — useful for deflecting support questions away from the tracker.

To validate a form locally before pushing, use the GitHub CLI's schema check or just push to a branch and view the chooser at `https://github.com/OWNER/REPO/issues/new/choose`. Invalid YAML fails silently in the UI — the template simply won't appear.

## Common Pitfalls & Gotchas

**1. YAML forms and Markdown templates can't share a filename.** If you have both `bug_report.md` and `bug_report.yml`, GitHub shows both in the chooser. Delete the old one when migrating, or you'll confuse contributors with two nearly identical entries.

**2. `labels` must already exist.** If you reference a label in the frontmatter that doesn't exist in the repo, GitHub silently ignores it. Create labels first, or the auto-labeling you're counting on never happens.

**3. Top-level `validations` is wrong.** The `required: true` key belongs *inside* each body element's `validations` block, not at the top level of the form. A misplaced key produces no error — the field just isn't required. Also note that `markdown` elements cannot have validations at all.

## Try It Yourself

1. **Build a minimal YAML form.** Create `.github/ISSUE_TEMPLATE/feature_request.yml` with one required `input` for a title-like summary and one `textarea` for the use case. Push to a branch and open `issues/new/choose` to confirm it renders.

2. **Lock down the chooser.** Add a `config.yml` with `blank_issues_enabled: false` and one `contact_links` entry pointing to your repo's Discussions. Verify the "Open a blank issue" link disappears.

3. **Inspect the payload.** Submit a test issue through your form, then run `gh issue view <number> --json body` and look at how the field IDs become Markdown headings. This is the shape your automation will parse.

## Next Up

Tomorrow I'm moving from issues to pull requests: review workflows, draft PRs, suggested changes, and how PR templates differ from issue templates in ways that actually matter. Day 07: **Pull Requests: Reviews, Drafts, Suggested Changes & PR Templates**.
