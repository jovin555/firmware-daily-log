---
title: "Day 02: Git Essentials for GitHub: Branches, Remotes, Rebase vs Merge"
date: 2026-10-12
tags: ["til", "github-mastery", "git", "branching"]
---

## What I Explored Today

Yesterday I got a working mental model of what GitHub actually is: a remote host for Git repositories plus a collaboration layer on top. Today I went one level deeper into the Git primitives that GitHub is built on — branches, remotes, and the merge-vs-rebase decision. These three topics are where most intermediate engineers have gaps, because you can use Git productively for years without ever understanding what `origin/main` really points to or why your rebased branch suddenly shows conflicts on every commit. I spent the day reading the Git internals docs, testing commands in a scratch repo, and re-reading the Pro Git chapter on rebasing. Here's what stuck.

## The Core Concept

A branch in Git is not a folder of files. It's a **movable pointer to a commit**. That's it. When you run `git commit`, Git creates a new commit object, then updates the current branch pointer to point at it. `HEAD` is a separate pointer that says "which branch am I on." This is why branching in Git is instant and cheap — you're just writing 41 bytes to a file.

A **remote** is a named URL plus a set of remote-tracking branches. `origin` is not special; it's just the default name Git gives to the remote you cloned from. `origin/main` is a local, read-only snapshot of where `main` was on that remote the last time you fetched. It does **not** update automatically when someone else pushes. This is the single biggest source of confusion for engineers coming from centralized VCS.

**Merge vs rebase** is a question about history shape. Merge preserves the true topology: two branches diverge, then a merge commit ties them back together. Rebase rewrites history: it replays your commits on top of a new base, producing a linear sequence with new commit hashes. Merge is honest; rebase is tidy. The rule I've adopted: rebase your *local, unpushed* work to keep it clean, merge (or squash-merge) when integrating into a shared branch.

## Key Commands / Configuration / Code

```bash
# --- Branches are just pointers ---
git branch feature/login          # create a branch at current HEAD
git switch feature/login          # move HEAD to it (modern syntax)
git switch -c feature/login       # create + switch in one step
git branch -vv                    # show branches with upstream tracking info

# --- Remotes ---
git remote -v                     # list remotes and their URLs
git remote add upstream git@github.com:org/repo.git
git fetch origin                  # update origin/* refs, do NOT touch working tree
git fetch --prune                 # also delete stale remote-tracking branches
git push -u origin feature/login  # push and set upstream in one shot

# --- Inspecting divergence ---
git log --oneline --graph --all --decorate
git rev-list --left-right --count main...origin/main
#   ^ prints "ahead  b" — how many commits each side has that the other lacks

# --- Rebase: replay local commits onto a new base ---
git switch feature/login
git fetch origin
git rebase origin/main            # replay feature commits on top of latest main
# If conflicts: fix files, then
git add <file>
git rebase --continue
# Or bail out entirely:
git rebase --abort

# --- Interactive rebase: clean up before pushing ---
git rebase -i origin/main
# In the editor: pick / reword / squash / fixup / drop

# --- Merge: preserve topology ---
git switch main
git merge --no-ff feature/login   # force a merge commit even if fast-forward possible

# --- The safety net ---
git reflog                        # every HEAD movement, even "lost" commits
```

A useful config I set once and forget:

```bash
git config --global pull.rebase true       # pull = fetch + rebase, not merge
git config --global fetch.prune true       # auto-prune on every fetch
git config --global rebase.autoStash true  # stash dirty tree during rebase
```

## Common Pitfalls & Gotchas

**1. Rebasing a shared branch.** If you rebase `main` after pushing it, every collaborator's history diverges from yours. Their next `git pull` will either fail or create a duplicate-history mess. The rule: never rebase anything that other people have pulled. Rebase is a local-history tool.

**2. Confusing `origin/main` with `main`.** `origin/main` is a cache of the last fetch. If a teammate pushed an hour ago and you haven't fetched, your `origin/main` is stale. `git status` will happily tell you "up to date with origin/main" while you're actually behind. Run `git fetch` before you trust any comparison.

**3. Force-pushing without `--force-with-lease`.** After a rebase you'll need to force-push. Plain `git push --force` will clobber whatever is on the remote, including commits a teammate pushed while you weren't looking. `git push --force-with-lease` refuses to overwrite if the remote ref has moved since your last fetch. Always use the lease variant.

## Try It Yourself

1. **Watch a branch move.** In a scratch repo, run `cat .git/refs/heads/main` before and after a commit. Then run `git reflog` and identify the previous commit hash. This makes the "branch = pointer" model concrete.

2. **Rebase a feature branch.** Create `feature/x`, make two commits, then commit something new on `main`. Switch back to `feature/x` and run `git rebase main`. Inspect the result with `git log --oneline --graph --all`. Note the new commit hashes.

3. **Recover from a bad rebase.** Deliberately run `git reset --hard HEAD~2` to "lose" two commits, then use `git reflog` to find them and `git reset --hard <hash>` to restore. This is the skill that saves you at 2 a.m.

## Next Up

Tomorrow: **Repository Setup: README, LICENSE, .gitignore & CODEOWNERS.** We'll cover what belongs in each file, why the LICENSE choice matters more than people think, how `.gitignore` interacts with already-tracked files (spoiler: it doesn't), and how CODEOWNERS turns a flat repo into a reviewable one.
