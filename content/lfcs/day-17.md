---
title: "Day 17: Command Sequencing: &&, ||, ; and subshells"
date: 2026-06-29
tags: ["til", "lfcs", "shell", "scripting"]
---

## What I Explored Today

Today I dug into command sequencing operators (`&&`, `||`, `;`) and subshells — the glue that turns a series of commands into a coherent pipeline of logic. While pipes (`|`) connect stdout to stdin, these operators control *when* and *under what conditions* commands run. I also explored how subshells create isolated execution environments, which is critical for managing state changes in scripts without leaking side effects.

## The Core Concept

Shell scripting isn't just about running commands — it's about orchestrating them. Every command exits with a status code (0 for success, non-zero for failure). The sequencing operators are conditional gates:

- `&&` (AND): Run next command **only if** previous succeeded (exit code 0)
- `||` (OR): Run next command **only if** previous failed (exit code non-zero)
- `;` (semicolon): Run next command **unconditionally**, regardless of exit status

Think of them as short-circuit logic operators for your terminal. They let you write "if this works, then do that" without an explicit `if` statement — perfect for one-liners and script guards.

Subshells (`( command )`) fork a child shell process. Any variable assignments, directory changes, or environment modifications inside the subshell are invisible to the parent shell. This is invaluable when you need to temporarily change state without polluting the calling environment.

## Key Commands / Configuration / Code

**Basic sequencing:**
```bash
# Run commands unconditionally (semicolons)
cd /tmp; ls -la; echo "Done"   # All three run, even if cd fails

# Conditional AND chain — stop on first failure
make clean && make && sudo make install
# If 'make clean' fails, 'make' never runs. If 'make' fails, install never runs.

# Conditional OR — fallback on failure
ping -c1 server.example.com || echo "Server unreachable, using fallback"
# If ping succeeds (exit 0), the echo is skipped. If ping fails, echo runs.
```

**Combining operators:**
```bash
# Create directory only if it doesn't exist, then enter it
mkdir -p /tmp/build && cd /tmp/build || { echo "Failed to create/enter build dir"; exit 1; }
# Note: { } groups commands without a subshell — but the semicolon inside is required
```

**Subshells for isolation:**
```bash
# Change directory temporarily without affecting parent shell
(cd /var/log && grep "error" *.log)   # Parent shell stays in original directory

# Variable isolation
x=10
( x=20; echo "Inside subshell: $x" )  # Prints 20
echo "Outside: $x"                     # Prints 10 — parent unaffected

# Subshell with exit — useful for early bailout in scripts
( cd /nonexistent || exit 1; echo "This never runs" )
echo "Script continues here"           # Runs because subshell exit doesn't kill parent
```

**Practical pattern — atomic operations:**
```bash
# Backup config, modify, verify — all or nothing
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak && \
  sed -i 's/worker_processes 1/worker_processes auto/' /etc/nginx/nginx.conf && \
  nginx -t && \
  systemctl reload nginx || \
  { echo "FAILED: restoring backup"; cp /etc/nginx/nginx.conf.bak /etc/nginx/nginx.conf; }
```

**Subshells with piped output:**
```bash
# Generate a list of files, then count them — all in a subshell
count=$(find /tmp -name "*.tmp" -type f 2>/dev/null | wc -l)
# The entire pipeline runs in a subshell, capturing stdout to variable
```

## Common Pitfalls & Gotchas

1. **`&&` vs `;` precedence confusion** — When mixing operators, `&&` and `||` have equal precedence and are left-associative. `cmd1 && cmd2 || cmd3` does NOT mean "if cmd1 succeeds do cmd2, else cmd3". It means: if cmd1 succeeds, run cmd2; regardless, if the *entire left side* fails (cmd1 fails, or cmd2 fails), run cmd3. This often surprises people. Use explicit grouping: `cmd1 && { cmd2; true; } || cmd3`

2. **Subshells and `exit`** — Calling `exit` inside a subshell only exits the subshell, not the parent script. This is a common source of bugs: `( cd /critical && some_command ) || exit 1` — the `exit 1` runs in the *parent* only if the subshell fails, but the subshell itself never exits the script.

3. **Trailing backslash in `&&` chains** — A backslash-newline continuation must have *no trailing whitespace* after the backslash. A single space will break the chain. Always use `&& \` with nothing after the backslash.

## Try It Yourself

1. **Build a safe deployment chain**: Write a one-liner that: builds a project (`make`), runs tests (`make test`), and only deploys (`./deploy.sh`) if both succeed. If any step fails, print an error message using `||`.

2. **Subshell directory isolation**: Create a script that uses a subshell to `cd` into `/tmp`, create a file, then verify the parent shell's working directory is unchanged. Use `pwd` before and after to prove it.

3. **Atomic config edit**: Write a command sequence that backs up `/etc/hosts`, appends a line to it, then verifies the syntax (use `ping -c1 localhost` as a sanity check). If anything fails, restore the backup. Use `&&`, `||`, and `{ }` grouping.

## Next Up

Tomorrow is **Essential Commands Review & Mock Lab** — I'll consolidate everything from Days 1–17 into a hands-on practice session with realistic scenarios. Expect file operations, process management, text processing, and sequencing all combined into a single challenge. Bring your terminal and your patience.
