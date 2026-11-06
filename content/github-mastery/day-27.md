---
title: "Day 27: GitHub Copilot: Chat, Code Review & Coding Agent"
date: 2026-11-06
tags: ["til", "github-mastery", "copilot", "ai"]
---

# Day 27: GitHub Copilot: Chat, Code Review & Coding Agent

## What I Explored Today

Today I moved past Copilot as a fancy autocomplete and dug into the three surfaces that actually change how a team ships: Copilot Chat (inline and the sidebar), Copilot code review (the PR-level reviewer), and the Copilot coding agent (the asynchronous worker that opens PRs on its own). The mental model shift is this: the first is a pair programmer in your editor, the second is a reviewer that never gets tired, and the third is a teammate you delegate an issue to and check back on later. Each has different trust boundaries and different failure modes, and conflating them is where teams get burned.

## The Core Concept

The reason these three exist as separate products rather than one "AI button" is about *context scope* and *who holds the loop*. Copilot Chat operates with your open files, selection, and workspace as context — it's synchronous and you're in the driver's seat. Copilot code review runs against a diff in a pull request, with the repo as context, and comments like a reviewer — it's asynchronous but bounded to the PR. The coding agent runs against an *issue*, in a sandboxed environment, and produces a branch and PR — it's fully asynchronous and you review the result, not the process.

The engineering implication: the more autonomy you grant, the more you must constrain the input. A chat prompt can be sloppy because you'll catch it. An agent prompt must be precise because you won't see the intermediate steps. That's why the agent is driven by issues with clear acceptance criteria and why `copilot-instructions.md` matters more for the agent than for chat.

## Key Commands / Configuration / Code

**1. Repository custom instructions** — the single highest-leverage config. Copilot reads `.github/copilot-instructions.md` for chat, review, and the agent.

```markdown
<!-- .github/copilot-instructions.md -->
# Project conventions
- Language: TypeScript, strict mode. No `any`.
- Tests: Vitest. Every new function needs a test in `*.test.ts`.
- Errors: throw typed errors from `src/errors.ts`, never bare `Error`.
- Do not modify files under `migrations/` — they are append-only.
```

**2. Path-specific instructions** for finer control (applies to matching files):

```markdown
<!-- .github/instructions/api.instructions.md -->
---
applyTo: "src/api/**/*.ts"
---
- All handlers must validate input with zod before touching the DB.
- Return the shared `ApiResponse<T>` envelope, never raw objects.
```

**3. Enabling Copilot code review on a PR** — via CLI with `gh`:

```bash
# Request a Copilot review on the current PR
gh pr edit --add-reviewer "@copilot"

# Or from the API for automation
gh api repos/{owner}/{repo}/pulls/{number}/requested_reviewers \
  -f 'reviewers[]=copilot-pull-request-reviewer[bot]'
```

**4. Delegating to the coding agent** — assign an issue to Copilot. The agent needs an environment; configure it in the repo settings, but you can drive assignment from the CLI:

```bash
# Assign an issue to the Copilot coding agent (bot handle)
gh issue edit 142 --add-assignee "@copilot"

# Watch what it produces
gh pr list --author "app/copilot-swe-agent" --state open
```

**5. A well-formed agent issue** — the agent reads this literally, so be explicit:

```markdown
## Task
Add rate limiting to `POST /api/login`.

## Acceptance criteria
- Max 5 attempts per IP per 15 min, using the existing Redis client in `src/redis.ts`.
- Return HTTP 429 with `Retry-After` header when exceeded.
- Add tests in `src/api/login.test.ts` covering the limit and the reset window.

## Constraints
- Do not add new dependencies.
- Follow `.github/copilot-instructions.md`.
```

**6. Chat slash commands** worth knowing in the editor: `/explain`, `/fix`, `/tests`, `/doc`, and `@workspace` to scope context to the whole repo rather than the open file.

## Common Pitfalls & Gotchas

- **The agent ignores vibes, not instructions.** If your issue says "make login more secure," you'll get a plausible-looking PR that does something adjacent to what you wanted. Acceptance criteria are not optional — they're the contract. Vague issues produce confidently wrong diffs that cost more to review than to write yourself.
- **`copilot-instructions.md` is context, not enforcement.** Copilot will *usually* follow it, but it's a prompt, not a linter. Don't rely on it for security invariants — keep those in CI (SAST, secret scanning, branch protection). Treat instructions as steering, not guardrails.
- **Code review comments are suggestions with no authority.** Copilot's PR review doesn't block merges and can be wrong or noisy. Don't wire it as a required status check expecting it to gate quality; use it to catch the stuff humans skim (missing null checks, inconsistent error handling) and keep your required checks on real tests and linters.

## Try It Yourself

1. **Write the instructions file.** Create `.github/copilot-instructions.md` for a repo you own with 5–8 concrete conventions (language rules, test framework, forbidden patterns). Then open Copilot Chat and ask it to write a function — confirm it respects them, and tighten any rule it ignored.

2. **Run a Copilot review.** Open a small PR and request `@copilot` as a reviewer via `gh pr edit --add-reviewer "@copilot"`. Compare its comments against what a human reviewer flagged. Note which categories it caught and which it missed.

3. **Delegate one real issue.** Pick a genuinely small, well-scoped issue (add a validation check, fix a flaky test). Rewrite it with explicit acceptance criteria and constraints, assign it to `@copilot`, and review the resulting PR like you would a junior engineer's — because that's exactly the trust level to apply.

## Next up

Tomorrow: **Organization Admin: Teams, Org Rulesets, Audit Log & Insights** — how to structure teams for CODEOWNERS and access, enforce policy across every repo with org-level rulesets, and actually read the audit log and Insights dashboards when something goes sideways.
