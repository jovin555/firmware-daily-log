---
title: "Day 11: Shell Variables, Environment & Startup Files"
date: 2026-06-23
tags: ["til", "lfcs", "shell", "environment"]
---

## What I Explored Today

Today I dug into how the shell manages variables and environment, and how startup files like `.bashrc`, `.bash_profile`, and `/etc/profile` shape every interactive session. This is the plumbing behind `$PATH`, `$HOME`, and every alias or function you've ever set. Understanding this isn't just about passing the LFCS—it's about debugging why a script works in your terminal but fails in cron, or why `ssh` inherits different settings than a local login.

## The Core Concept

Shell variables fall into two categories: **local** (shell-only) and **environment** (inherited by child processes). The distinction is critical. When you run a script, it spawns a child shell. That child sees environment variables automatically, but it does *not* see local variables unless you explicitly `export` them.

Startup files are the shell's initialization scripts. They run in a specific order depending on whether the shell is **login** (e.g., `ssh`, console login) or **non-login interactive** (e.g., opening a terminal in a GUI). The key takeaway: environment variables you want in every context (like `EDITOR` or `PATH` extensions) should go in a file that runs for both login and non-login shells. The classic pattern is to put them in `~/.profile` (login) and source `~/.bashrc` from it (non-login interactive).

## Key Commands / Configuration / Code

### Viewing and Setting Variables

```bash
# List all environment variables (child processes inherit these)
env

# List all shell variables (local + environment)
set

# Export a local variable to the environment
MY_VAR="hello"
export MY_VAR

# One-liner: set and export in one step
export MY_VAR="hello"

# Unset a variable (remove it entirely)
unset MY_VAR

# Make a variable read-only (prevents accidental overwrite)
readonly MY_VAR="immutable"
```

### Startup File Execution Order (Bash)

| Shell Type | Files Executed (in order) |
|------------|---------------------------|
| Login interactive | `/etc/profile`, then first found of `~/.bash_profile`, `~/.bash_login`, `~/.profile` |
| Non-login interactive | `~/.bashrc` (bash reads it directly) |
| Non-interactive (script) | `$BASH_ENV` if set, otherwise nothing |

**Practical pattern** — put everything in `~/.bashrc`, then source it from `~/.profile`:

```bash
# ~/.profile — runs for login shells
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi
```

```bash
# ~/.bashrc — runs for all interactive bash shells
# System-wide settings
export EDITOR=vim
export VISUAL=vim
export PAGER=less

# Extend PATH safely (avoid duplicates)
case ":$PATH:" in
    *:"$HOME/bin":*) ;;
    *) export PATH="$HOME/bin:$PATH" ;;
esac

# Aliases
alias ll='ls -alF'
alias grep='grep --color=auto'

# Prompt customization
PS1='\u@\h:\w\$ '
```

### Environment Variables Every Engineer Should Know

```bash
# $HOME — user's home directory
echo "$HOME"          # /home/username

# $PATH — colon-separated list of directories to search for executables
echo "$PATH"          # /usr/local/bin:/usr/bin:/bin:...

# $SHELL — path to current shell
echo "$SHELL"         # /bin/bash

# $USER — current username
echo "$USER"          # username

# $PWD — current working directory (updated by cd)
echo "$PWD"           # /home/username/projects

# $OLDPWD — previous working directory (cd - uses this)
echo "$OLDPWD"        # /home/username

# $? — exit status of last command
false; echo $?        # 1
true; echo $?         # 0

# $$ — PID of current shell
echo $$               # 12345

# $RANDOM — random integer 0-32767 (bash-specific)
echo $RANDOM          # 28473
```

### Modifying PATH Safely

```bash
# Prepend a directory (takes priority)
export PATH="/opt/custom/bin:$PATH"

# Append a directory (lower priority)
export PATH="$PATH:/opt/custom/bin"

# Remove a directory from PATH (advanced)
PATH=$(echo "$PATH" | tr ':' '\n' | grep -v '/unwanted/path' | tr '\n' ':' | sed 's/:$//')
```

## Common Pitfalls & Gotchas

1. **Missing `export` in scripts** — A variable set inside a script is local to that script's shell. If you call another script or program, it won't see it. Always `export` variables that child processes need. This is the #1 cause of "works in terminal, fails in script" bugs.

2. **Startup file confusion** — Many engineers put `PATH` modifications in `~/.bashrc` but then wonder why `ssh host command` doesn't see them. `ssh host command` runs a non-interactive, non-login shell, which does *not* source `~/.bashrc`. Use `~/.ssh/environment` or set `PermitUserEnvironment yes` in `/etc/ssh/sshd_config` (not recommended for security), or explicitly source your config in the command.

3. **Quoting and whitespace** — `export MY_VAR = value` (with spaces around `=`) is a syntax error. `export MY_VAR="value with spaces"` is correct. Always quote values containing spaces or special characters. Forgetting this breaks paths with spaces.

4. **`env` vs `printenv` vs `set`** — `env` and `printenv` show only exported environment variables. `set` shows everything (including functions, local variables). If you're debugging why a variable isn't inherited, use `env` in the child process.

## Try It Yourself

1. **Trace your startup files**: Add `echo "Loading: $0"` at the top of `~/.bashrc` and `~/.profile`. Open a new terminal, then `ssh localhost`. Observe which files run and in what order. Then remove the debug lines.

2. **Export vs local experiment**: Create a script `test.sh` with `echo "VAR is: $VAR"`. In your shell, set `VAR="local"` (no export), then run `./test.sh`. Now do `export VAR="exported"` and run it again. See the difference? Now unset VAR and try `VAR="inline" ./test.sh` — that's a one-shot environment variable.

3. **Safe PATH surgery**: Add a directory to your PATH in `~/.bashrc` using the safe duplicate-check pattern shown above. Then verify with `echo $PATH` and `which your-command`. Remove it when done.

## Next Up

Tomorrow we tackle **Process Management**: `ps`, `kill`, `nice`, `jobs`, and `nohup`. You'll learn how to inspect running processes, send signals, adjust priority, background jobs, and keep processes alive after logout. Essential for any production system.
