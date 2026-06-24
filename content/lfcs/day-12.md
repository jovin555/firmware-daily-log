---
title: "Day 12: Process Management: ps, kill, nice, jobs, nohup"
date: 2026-06-24
tags: ["til", "lfcs", "processes", "jobs"]
---

## What I Explored Today

Today I dove into the Linux process lifecycle — how processes are spawned, how they run, and how we control them from the shell. The commands `ps`, `kill`, `nice`, `jobs`, and `nohup` form the core toolkit for any engineer who needs to manage running workloads, whether that’s debugging a runaway daemon, adjusting CPU priority for a batch job, or keeping a script alive after logout. I focused on the practical flags and patterns that matter in daily operations, not the exhaustive man page.

## The Core Concept

Every command you run becomes a process — a running instance of a program with its own PID, memory space, and scheduling state. The kernel’s scheduler decides which process gets CPU time and for how long. As an engineer, you need to:

- **Inspect** what’s running (`ps`)
- **Signal** processes to stop, pause, or reconfigure (`kill`)
- **Adjust** scheduling priority (`nice`, `renice`)
- **Manage** background and foreground tasks (`jobs`, `fg`, `bg`)
- **Detach** processes from the terminal so they survive logout (`nohup`, `disown`)

The key insight: processes are not just “programs running.” They are objects in a hierarchy (parent/child), with ownership (UID), resource limits, and signal handlers. Understanding these five commands gives you surgical control over that ecosystem.

## Key Commands / Configuration / Code

### 1. `ps` — Process Snapshot

The most common patterns:

```bash
# Full-format listing for all processes (BSD style)
ps aux

# Forest view showing parent-child hierarchy
ps auxf

# Custom output: PID, PPID, %CPU, %MEM, command with args
ps -eo pid,ppid,%cpu,%mem,cmd --sort=-%cpu | head -20

# Show threads of a process (useful for Java/Python apps)
ps -L -p <PID>
```

`ps aux` is my go-to. The `u` flag shows the user, `a` shows all users, `x` includes daemons without a terminal. The `--sort` flag is invaluable for finding CPU hogs.

### 2. `kill` — Send Signals

`kill` doesn’t just terminate — it sends any signal. The default is `SIGTERM` (15), which asks the process to clean up. Use `SIGKILL` (9) only as a last resort.

```bash
# Graceful termination
kill 1234

# Force kill (bypasses cleanup)
kill -9 1234

# Reload configuration (e.g., nginx)
kill -HUP $(cat /var/run/nginx.pid)

# List all available signals
kill -l
```

**Pro tip:** Always try `SIGTERM` first. `SIGKILL` can leave shared memory segments or sockets in an inconsistent state.

### 3. `nice` and `renice` — Priority Adjustment

Nice values range from -20 (highest priority) to 19 (lowest). Default is 0. Only root can set negative nice values.

```bash
# Start a CPU-intensive job with low priority
nice -n 19 ./heavy_compilation.sh

# Change priority of a running process (requires permission)
renice -n 10 -p 5678

# Set priority for all threads of a process group
renice -n 5 -g 5678
```

### 4. `jobs`, `fg`, `bg` — Job Control

When you run a command in the foreground, you can suspend it with `Ctrl+Z` and then manage it:

```bash
# Start a long-running task in the background
sleep 300 &

# List background jobs
jobs

# Bring job 1 to foreground
fg %1

# Resume job 2 in background
bg %2

# Kill a specific job by job number
kill %1
```

The `%n` syntax refers to job numbers, not PIDs. This is critical when you have multiple background tasks.

### 5. `nohup` — Survive Logout

When you log out, the shell sends `SIGHUP` to all child processes. `nohup` ignores that signal and redirects output to `nohup.out`:

```bash
# Run a script immune to hangups
nohup ./long_running_script.sh &

# Specify custom output file
nohup ./script.sh > output.log 2>&1 &

# Alternative: use disown after starting a job
./script.sh &
disown
```

`disown` removes the job from the shell’s job table, so it won’t receive `SIGHUP` when you exit. It’s useful when you forgot to use `nohup`.

## Common Pitfalls & Gotchas

1. **`kill -9` is not a magic bullet.** It does not allow the process to close file descriptors, release locks, or flush buffers. Use it only when `SIGTERM` fails after a reasonable timeout (e.g., 5 seconds). For databases or critical services, `SIGTERM` is mandatory.

2. **`nohup` does not daemonize.** The process still runs in the same session group. If you need a true daemon, use `systemd` or `daemonize`. `nohup` only protects against `SIGHUP` from the terminal.

3. **Job numbers (`%1`) are local to your shell.** If you open another terminal, those job numbers don’t exist. Use `ps` and `kill <PID>` for cross-session management.

4. **`nice` values are inherited.** If you start a shell with `nice -n 10 bash`, every command run inside that shell inherits the lowered priority. This is useful for sandboxing interactive sessions.

## Try It Yourself

1. **Find and tame a CPU hog:** Run `ps aux --sort=-%cpu | head -5`. Identify the top process, then run `renice -n 15 -p <PID>` to lower its priority. Verify with `ps -o pid,ni,cmd -p <PID>`.

2. **Survive a logout:** Start `ping 8.8.8.8` with `nohup`, log out of your SSH session, log back in, and use `ps aux | grep ping` to confirm it’s still running. Then kill it gracefully.

3. **Practice job control:** Run `sleep 100`, suspend it with `Ctrl+Z`, then background it with `bg`. Start a second `sleep 200` in the foreground, suspend it, then bring the first job back to the foreground with `fg %1`. Use `jobs` to verify state changes.

## Next Up

Tomorrow, I’ll explore system information commands: `uname`, `dmesg`, `lsblk`, and the `/proc` filesystem — the raw interfaces to kernel and hardware state that every engineer should know for diagnostics and performance analysis.
