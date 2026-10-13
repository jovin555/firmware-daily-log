---
title: "Day 03: Repository Setup: README, LICENSE, .gitignore & CODEOWNERS"
date: 2026-10-13
tags: ["til", "github-mastery", "repository", "codeowners"]
---

## What I Explored Today

Today I focused on the four files that turn an empty `git init` into a repository someone else can actually use: `README.md`, `LICENSE`, `.gitignore`, and `CODEOWNERS`. These are the first things a new contributor sees, the legal terms they agree to, the noise they never have to look at, and the routing rules that decide who reviews what. Individually each is trivial. Together they define whether your repo feels like a professional project or a weekend scratchpad. I spent the day setting them up properly on a fresh repo and reading the GitHub docs on how each one is actually interpreted.

## The Core Concept

The reason these four files matter is that they encode decisions you'd otherwise have to make repeatedly. A README answers "what is this and how do I run it" so you don't answer it in Slack every week. A LICENSE answers "can I use this at work" so legal doesn't have to. A `.gitignore` answers "should this file be tracked" so you don't accidentally commit `.env` or `node_modules`. And `CODEOWNERS` answers "who needs to approve this PR" so GitHub can enforce it automatically instead of relying on tribal knowledge.

The key insight is that all four are *conventions*, not features of Git itself. Git doesn't care about a README. GitHub reads `CODEOWNERS` from specific locations and only honors it when branch protection is configured. `.gitignore` is honored by Git, but only for files not already tracked. Understanding which tool actually consumes each file — Git vs. GitHub vs. a human — is what separates a config that works from one that silently does nothing.

## Key Commands / Configuration / Code

### README.md — start with the four questions

```markdown
# project-name

One-sentence description of what this does and who it's for.

## Quick start

```bash
git clone https://github.com/you/project-name.git
cd project-name
make install   # or npm install, pip install -e ., etc.
make test
```

## Requirements

- Go 1.22+ / Node 20+ / Python 3.11+
- Docker (optional, for integration tests)

## License

MIT — see [LICENSE](LICENSE).
```

The four questions a README must answer: what is it, how do I install it, how do I run it, how do I contribute. Everything else is optional.

### LICENSE — pick one, don't write your own

```bash
# GitHub's license picker is the fastest path:
# Repo → Add file → Create new file → type "LICENSE" → "Choose a license template"

# Or via the CLI, using the GitHub API:
gh api -X GET /licenses/mit --jq '.body' > LICENSE
```

For most projects, MIT, Apache-2.0, or GPL-3.0 covers 95% of cases. Apache-2.0 adds an explicit patent grant; GPL-3.0 is copyleft. If you have no LICENSE file, the default is "all rights reserved" — nobody can legally use your code, even if it's public.

### .gitignore — ignore early, ignore specifically

```gitignore
# .gitignore
# Dependencies
node_modules/
vendor/

# Build output
dist/
build/
*.o
*.so

# Secrets — never commit these
.env
.env.local
*.pem
credentials.json

# Editor / OS noise
.vscode/
.idea/
.DS_Store

# Keep a placeholder so the directory exists in the repo
!logs/.gitkeep
```

The `!` prefix negates a previous rule. Order matters: later rules win. If a file is already tracked, adding it to `.gitignore` does nothing — you must `git rm --cached <file>` first.

### CODEOWNERS — route reviews automatically

GitHub reads `CODEOWNERS` from one of three locations, in priority order:

1. `.github/CODEOWNERS`
2. `CODEOWNERS` (repo root)
3. `docs/CODEOWNERS`

```
# .github/CODEOWNERS
# Syntax: <pattern> <@user-or-@org/team>...

# Default owners for everything not matched below
*                       @your-org/core-team

# Infra changes need the platform team
/infra/                 @your-org/platform
*.tf                    @your-org/platform

# Docs can be reviewed by anyone on the docs team
/docs/                  @your-org/docs
*.md                    @your-org/docs

# CI config is sensitive — require a specific person
/.github/workflows/     @alice
```

Rules are evaluated bottom-up: the *last* matching pattern wins, not the most specific. This trips up almost everyone coming from a glob-background where specificity usually wins.

## Common Pitfalls & Gotchas

**1. `.gitignore` doesn't untrack files.** If you committed `node_modules/` before adding it to `.gitignore`, Git keeps tracking it. You need `git rm -r --cached node_modules/` and then commit. The files stay on disk; only the index entry is removed.

**2. CODEOWNERS does nothing without branch protection.** GitHub will *suggest* reviewers based on CODEOWNERS, but it won't *require* their approval unless you enable "Require review from Code Owners" in the branch protection rule. This is the single most common reason teams think CODEOWNERS is broken. We'll cover the protection side tomorrow.

**3. Team names must be the slug, not the display name.** If your team is called "Core Engineering" in the UI, the slug is probably `core-engineering`. Use `@your-org/core-engineering`. If the team is secret or the slug is wrong, the entry is silently ignored — no error, no warning.

**4. A missing LICENSE means "all rights reserved."** Public on GitHub ≠ open source. Without a license file, nobody can legally fork, modify, or redistribute your code, even for internal use at their company. If you want it to be usable, license it explicitly.

## Try It Yourself

1. **Bootstrap a repo with all four files.** Create a new repo, add a README with the four-question structure, pick a license via `gh api /licenses/mit --jq '.body' > LICENSE`, and write a `.gitignore` for your primary language. Commit each in a separate commit so the history tells the story.

2. **Test the CODEOWNERS parser.** Add a `.github/CODEOWNERS` with a `*` rule pointing at your username, then open a PR touching a file in a subdirectory you also listed. Confirm GitHub auto-requests you as a reviewer. Then try a deliberately wrong team slug and confirm it silently fails — that's the behavior you need to recognize in production.

3. **Recover from a bad commit.** In a scratch repo, commit a `secrets.env` file, then add it to `.gitignore` and observe that Git still tracks it. Fix it with `git rm --cached secrets.env` and verify with `git status` that the file is now untracked but still on disk.

## Next up

Tomorrow: **Branch Protection & Rulesets: Guarding main.** We'll take the CODEOWNERS file from today and actually make it enforceable — required reviews, status checks, linear history, and the newer Rulesets API that's gradually replacing the classic branch protection UI.
