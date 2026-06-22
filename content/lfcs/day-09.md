---
title: "Day 09: I/O Redirection, Pipes, tee & xargs"
date: 2026-06-22
tags: ["til", "lfcs", "redirection", "pipes"]
---

## What I Explored Today

Today I dove deep into the Linux I/O plumbing system — file descriptors, redirection operators, pipes, and the often-overlooked `tee` and `xargs` commands. While I've used `>` and `|` casually for years, understanding the underlying mechanics (stdin=0, stdout=1, stderr=2) and how these tools compose into pipelines is essential for the LFCS exam and real-world system administration. I focused on practical patterns: logging both stdout and stderr, feeding command output as arguments to other commands, and avoiding common pitfalls that silently corrupt data.

## The Core Concept

Every process in Linux starts with three open file descriptors: stdin (0), stdout (1), and stderr (2). Redirection operators manipulate where these streams point — to files, devices, or other processes. Pipes (`|`) connect one process's stdout to another's stdin, creating a data flow chain. The key insight: pipes are unidirectional and buffered, meaning the producer and consumer run concurrently, not sequentially. This concurrency is why `tail -f | grep` works in real-time.

`tee` acts as a T-junction: it writes stdin to both stdout and one or more files. This is invaluable when you need to log output while still piping it forward. `xargs` solves a different problem: it converts stdin into arguments for another command, handling batching and argument-length limits automatically. Without `xargs`, you'd hit "Argument list too long" errors when passing thousands of filenames to `rm` or `cp`.

## Key Commands / Configuration / Code

### Basic Redirection

```bash
# Redirect stdout to file (overwrite)
ls -la > output.txt

# Redirect stdout to file (append)
echo "new entry" >> log.txt

# Redirect stderr to file
grep "error" /var/log/syslog 2> errors.log

# Redirect both stdout and stderr to same file
command > all.log 2>&1
# Modern bash/zsh alternative (preferred for clarity)
command &> all.log

# Discard stderr (send to /dev/null)
noisy_command 2>/dev/null

# Redirect stderr to stdout (for piping)
command 2>&1 | grep "error"
```

### Pipes

```bash
# Classic pipeline: list processes, filter, count
ps aux | grep nginx | wc -l

# Find large files and sort by size
find /var -type f -size +100M 2>/dev/null | xargs ls -lhS | head -20

# Chain with tee to inspect intermediate output
cat /var/log/auth.log | grep "Failed password" | tee failed_attempts.txt | wc -l
```

### tee in Practice

```bash
# Log installation output while watching progress
sudo apt-get update 2>&1 | tee update.log

# Append to log file while still displaying
long_running_task | tee -a task_output.log

# Write to multiple files simultaneously
echo "config=production" | tee config1.conf config2.conf config3.conf
```

### xargs — The Argument Builder

```bash
# Basic: delete files found by find (handles spaces correctly)
find /tmp -name "*.tmp" -print0 | xargs -0 rm -f

# Dry-run with -p (prompt before each command)
find . -name "*.bak" -print0 | xargs -0 -p rm

# Batch processing: process 100 files at a time
find photos/ -name "*.jpg" -print0 | xargs -0 -L 100 convert -resize 800x600

# Use -I for placeholder substitution
cat hosts.txt | xargs -I {} ssh {} 'uptime'

# Parallel execution with -P (max 4 concurrent processes)
seq 1 10 | xargs -P 4 -I {} sh -c 'echo "Processing {}"; sleep 1'
```

### Real-World Pipeline Example

```bash
# Find top 10 largest log files, compress them, log the action
find /var/log -name "*.log" -type f -size +1M -print0 \
  | xargs -0 ls -lhS \
  | awk '{print $5, $NF}' \
  | sort -rh \
  | head -10 \
  | tee large_logs.txt \
  | awk '{print $2}' \
  | xargs -I {} gzip {}
```

## Common Pitfalls & Gotchas

1. **Piping with `sudo` doesn't escalate the pipe components.** `sudo cat /etc/shadow | grep root` runs `cat` as root but `grep` as your user. If `grep` needs elevated access (unlikely here), it fails. Use `sudo sh -c 'cat /etc/shadow | grep root'` or `cat /etc/shadow | sudo grep root` instead.

2. **`xargs` without `-0` breaks on filenames with spaces.** If a file is named `my file.txt`, `find ... | xargs rm` will try to remove `my` and `file.txt` separately. Always use `-print0` with `find` and `-0` with `xargs` when dealing with arbitrary filenames.

3. **`tee` overwrites by default.** If you use `tee log.txt` and the file exists, it's truncated. Use `tee -a log.txt` to append. This is a common cause of lost log data during debugging sessions.

4. **Redirection order matters.** `command 2>&1 > file` redirects stderr to the current stdout (terminal), then redirects stdout to file. Stderr still goes to terminal. Correct order: `command > file 2>&1` or use `&>`.

## Try It Yourself

1. **Build a monitoring pipeline:** Write a one-liner that lists all running processes, filters for those using more than 100MB RSS, sorts by memory usage descending, and logs the top 10 to a file while also displaying them on screen. Use `ps`, `awk`, `sort`, `head`, and `tee`.

2. **Safe bulk rename with xargs:** Create 10 test files with spaces in their names (`touch "file 1.txt" "file 2.txt" ...`). Then use `find` with `-print0` and `xargs -0` to rename them all to lowercase (hint: `tr '[:upper:]' '[:lower:]'` inside a shell command).

3. **Log both stdout and stderr separately:** Run a command that produces both output and errors (e.g., `find /root -type f 2>&1`), then use `tee` to write stdout to `output.log` and stderr to `error.log` simultaneously. Verify both files contain the correct streams.

## Next Up

Tomorrow we tackle **Regular Expressions for the LFCS Exam** — the grep/awk/sed trifecta that separates script kiddies from engineers. We'll cover POSIX vs extended regex, greedy vs lazy matching, and practical patterns for log parsing and configuration validation.
