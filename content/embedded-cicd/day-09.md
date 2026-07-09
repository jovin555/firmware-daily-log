---
title: "Day 09: Automated Release Notes Generation from Commit History"
date: 2026-07-09
tags: ["til", "embedded-cicd", "release-notes", "automation"]
---

## What I Explored Today

I finally tackled the release notes problem that's been haunting our firmware releases. For the last three sprints, I've been manually stitching together changelogs from Jira tickets and Git log dumps—a process that inevitably misses edge-case fixes and driver patches. Today I automated the entire pipeline using `git log` with structured commit messages, `jq` for JSON parsing, and a Python script that generates Markdown release notes directly from our CI pipeline. The result: a `RELEASE_NOTES.md` that's accurate, formatted, and posted to our internal wiki within 30 seconds of a tag push.

## The Core Concept

Release notes are not just a summary of what changed—they are a contract between the engineering team and the stakeholders (QA, field application engineers, customers). In embedded systems, a missing note about a register-level workaround can waste days of debugging. The key insight is that **commit messages are the single source of truth**, but only if they follow a convention. By enforcing a structured commit format (e.g., `type(scope): description [ticket-id]`), we can parse, categorize, and generate release notes automatically. This shifts the burden from a manual end-of-release scramble to a disciplined, per-commit habit.

The pipeline works in three stages: (1) extract commits between two tags using `git log --oneline --format=...`, (2) parse each commit into structured fields (type, scope, description, ticket), and (3) render a Markdown document grouped by type (Features, Fixes, Breaking Changes, etc.). The output is then attached to the release artifact in our CI system.

## Key Commands / Configuration / Code

### 1. Extracting structured commits between tags

```bash
# Get all commits between v2.3.0 and v2.4.0, formatted as JSON
git log v2.3.0..v2.4.0 \
  --format='{"hash":"%h","subject":"%s","body":"%b","author":"%an","date":"%ai"}' \
  --reverse | jq -s '.' > commits.json
```

The `--format` flag outputs each commit as a JSON object. The `%s` is the subject line (first line), `%b` is the body (rest of message). We pipe through `jq -s` to slurp all objects into a JSON array.

### 2. Python script to categorize and render release notes

```python
#!/usr/bin/env python3
"""generate_release_notes.py - Parse commits.json into categorized release notes."""
import json
import re
import sys
from datetime import datetime

# Define commit type categories and their display order
CATEGORIES = {
    "feat": ("Features", "New features and enhancements"),
    "fix": ("Bug Fixes", "Bug fixes and patches"),
    "perf": ("Performance", "Performance improvements"),
    "docs": ("Documentation", "Documentation updates"),
    "refactor": ("Refactoring", "Code refactoring (no functional change)"),
    "test": ("Testing", "Test additions and modifications"),
    "build": ("Build System", "Build configuration and CI changes"),
    "break": ("Breaking Changes", "Changes that break backward compatibility"),
}

def parse_commit(commit):
    """Parse a commit subject into (type, scope, description, ticket)."""
    # Expected format: type(scope): description [TICKET-123]
    pattern = r'^(\w+)\(([^)]+)\):\s(.+?)(?:\s\[([A-Z]+-\d+)\])?$'
    match = re.match(pattern, commit['subject'])
    if not match:
        return ('other', '', commit['subject'], '')
    return (match.group(1), match.group(2), match.group(3), match.group(4) or '')

def generate_notes(commits, version, date):
    """Generate Markdown release notes from parsed commits."""
    categorized = {cat: [] for cat in CATEGORIES}
    categorized['other'] = []

    for commit in commits:
        ctype, scope, desc, ticket = parse_commit(commit)
        entry = f"- **{scope}**: {desc}"
        if ticket:
            entry += f" ([{ticket}](https://jira.example.com/browse/{ticket}))"
        entry += f" ({commit['author']})"
        categorized.get(ctype, categorized['other']).append(entry)

    # Build Markdown output
    lines = [
        f"# Release Notes - v{version}",
        f"**Date**: {date}",
        "",
        "## Summary",
        f"Total commits: {len(commits)}",
        "",
    ]
    for cat_key, (title, subtitle) in CATEGORIES.items():
        items = categorized.get(cat_key, [])
        if items:
            lines.append(f"## {title}")
            lines.append(f"*{subtitle}*")
            lines.append("")
            lines.extend(items)
            lines.append("")

    # Add uncategorized commits at the end
    if categorized['other']:
        lines.append("## Other Changes")
        lines.append("*Uncategorized commits*")
        lines.append("")
        lines.extend(categorized['other'])

    return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: generate_release_notes.py <commits.json> <version> <date>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        commits = json.load(f)
    version = sys.argv[2]
    date = sys.argv[3]

    notes = generate_notes(commits, version, date)
    with open("RELEASE_NOTES.md", "w") as f:
        f.write(notes)
    print(f"Generated RELEASE_NOTES.md with {len(commits)} commits")
```

### 3. CI pipeline integration (GitLab CI example)

```yaml
# .gitlab-ci.yml snippet
generate-release-notes:
  stage: release
  only:
    - tags
  script:
    # Get previous tag (assumes tags are semver sorted)
    - PREV_TAG=$(git tag --sort=-version:refname | head -2 | tail -1)
    - CURRENT_TAG=$CI_COMMIT_TAG
    - git log $PREV_TAG..$CURRENT_TAG --format='{"hash":"%h","subject":"%s","body":"%b","author":"%an","date":"%ai"}' --reverse | jq -s '.' > commits.json
    - python3 generate_release_notes.py commits.json ${CURRENT_TAG#v} $(date +%Y-%m-%d)
  artifacts:
    paths:
      - RELEASE_NOTES.md
```

## Common Pitfalls & Gotchas

1. **Empty commit ranges on first release**: When there's no previous tag, `git log` fails. Always handle the initial case by using `git log --since=<first_commit_date>` or check if `PREV_TAG` is empty and fall back to `git log --all`.

2. **Commit message parsing fragility**: If even one developer writes `fix(hal): fix typo` instead of `fix(hal): fix typo` (missing space after colon), your regex breaks. Enforce commit message format with a pre-commit hook or commitlint in CI. We use `commitlint` with `@commitlint/config-conventional` and a custom rule for ticket IDs.

3. **Binary blobs and large repos**: `git log` with `--format` is fast, but if your repo has thousands of commits between tags (e.g., a long-lived release branch), the JSON file can become large. Consider using `--max-count=500` or paginating. For embedded repos with firmware blobs, exclude binary paths from the log with `-- . :!*.bin :!*.hex`.

## Try It Yourself

1. **Enforce commit conventions**: Add a `.commitlintrc.json` to your repo with `"extends": ["@commitlint/config-conventional"]` and a custom rule for ticket IDs. Run `commitlint --from HEAD~1` in CI to reject non-conforming commits.

2. **Generate notes for your last release**: Run the `git log` command above between your last two tags, then pipe through the Python script. Inspect the output—how many commits ended up in "Other Changes"? That's your team's compliance metric.

3. **Add a breaking changes detector**: Modify the Python script to scan commit bodies for `BREAKING CHANGE:` or `!` after the type (e.g., `feat!:`). Categorize those commits under "Breaking Changes" and highlight them in red in the rendered Markdown.

## Next Up

Tomorrow, we dive into **Infrastructure as Code for Build Farms: Ansible & Terraform Basics**—how to stop manually provisioning Jenkins slaves and start treating your build server config like firmware source code.
