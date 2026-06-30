---
title: "Day 18: Essential Commands Review & Mock Lab"
date: 2026-06-30
tags: ["til", "lfcs", "review", "mock-exam"]
---

## What I Explored Today

After seventeen days of building up individual command knowledge, today I ran a full mock lab that forced me to chain together everything from the Essential Commands domain: file operations, text processing, process management, permissions, and shell expansion. The exercise revealed that knowing commands in isolation is not the same as being able to solve a real problem under time pressure. I deliberately worked without internet access, using only `man` pages and `--help` flags, which is exactly the LFCS exam environment.

## The Core Concept

The Essential Commands domain is not about memorizing flags—it's about developing a mental model of how the Linux filesystem, process tree, and shell interact. Every command you run is a child process of your shell. Every file path is resolved through the kernel's VFS layer. Every permission check is evaluated against your effective UID/GID and the file's inode metadata.

The real skill is **command composition**: piping `find` output into `xargs`, which feeds `chmod` or `rm`, while using `grep` to filter results and `tee` to log everything. The LFCS exam expects you to do this fluidly, not by rote, but by understanding the data flow between stdin/stdout/stderr.

## Key Commands / Configuration / Code

I built a mock lab scenario: "Audit all world-writable files in `/var`, change their permissions to `750` if owned by a system user (UID < 1000), and log every change to `/root/audit.log`."

Here's the solution I worked through:

```bash
# Step 1: Find all world-writable files in /var (excluding /var/spool)
find /var -type f -perm -o=w ! -path "/var/spool/*" 2>/dev/null > /tmp/world_writable.txt

# Step 2: Check ownership and filter for system users (UID < 1000)
# Using stat to extract UID, then awk to filter
while IFS= read -r file; do
    uid=$(stat -c "%u" "$file" 2>/dev/null)
    if [ "$uid" -lt 1000 ] 2>/dev/null; then
        # Step 3: Change permissions to 750
        chmod 750 "$file" && echo "$(date +%F_%T) CHANGED $file to 750" >> /root/audit.log
    fi
done < /tmp/world_writable.txt

# Alternative one-liner using xargs (more efficient for large sets)
find /var -type f -perm -o=w ! -path "/var/spool/*" -exec stat -c "%u %n" {} \; \
  | awk '$1 < 1000 {print $2}' \
  | xargs -I {} sh -c 'chmod 750 "{}" && echo "$(date +%F_%T) CHANGED {} to 750" >> /root/audit.log'
```

**Process management mock task**: "Find the top 3 memory-consuming processes owned by `www-data`, then send them SIGTERM with a 5-second grace period before SIGKILL."

```bash
# List processes sorted by RSS, filter for www-data, take top 3
ps -eo user,pid,%mem,rss,comm --sort=-rss | awk '/^www-data/ {print $2}' | head -3 > /tmp/pids.txt

# Graceful shutdown loop
for pid in $(cat /tmp/pids.txt); do
    kill -TERM "$pid" 2>/dev/null
    sleep 5
    kill -KILL "$pid" 2>/dev/null && echo "Killed PID $pid" >> /root/kill.log
done
```

**Text processing mock task**: "Extract all IPv4 addresses from `/var/log/syslog`, count unique occurrences, and display top 10."

```bash
grep -oE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' /var/log/syslog \
  | sort \
  | uniq -c \
  | sort -rn \
  | head -10
```

**Permission deep-dive**: I also verified SUID/SGID files, which are common exam traps:

```bash
# Find all SUID binaries owned by root
find / -type f -perm -4000 -user root -exec ls -la {} \; 2>/dev/null
```

## Common Pitfalls & Gotchas

1. **`find` with `-exec` vs `xargs`**: When using `-exec chmod 750 {} \;`, each file spawns a new `chmod` process. For hundreds of files, this is slow. Use `-exec chmod 750 {} +` (batch mode) or pipe to `xargs`. But `xargs` has its own gotcha: filenames with spaces break it unless you use `-print0` with `xargs -0`.

2. **`stat` format strings**: `stat -c "%u %n"` outputs UID and filename separated by a space. If a filename contains a space, `awk` will misparse. Safer: use `stat --printf="%u\t%n\n"` with tab delimiter, then set `awk -F'\t'`.

3. **Redirection order matters**: `command 2>&1 > file` redirects stderr to the original stdout (terminal), then stdout to file. The correct order for both to file is `command > file 2>&1`. This is a classic exam trap.

## Try It Yourself

1. **Audit your own system**: Find all files in `/etc` that are not owned by root and have world-readable permissions. Change them to `640` and log the changes. Use `find` with `-not -user root` and `-perm -o=r`.

2. **Process tree exercise**: Write a one-liner that finds all processes whose parent PID is 1 (orphaned but running), prints their PID, command, and memory usage, then kills any using more than 100MB RSS.

3. **Text processing challenge**: Extract all email addresses from `/var/log/mail.log` (or a sample log file), deduplicate them, and count how many are from `@example.com` vs other domains. Use `grep -oE`, `sort`, `uniq`, and `awk`.

## Next Up

Tomorrow we dive into **User Accounts**: `useradd`, `usermod`, `userdel`, and the shadow password suite. We'll cover creating users with specific UIDs, home directories, and expiry dates, plus the difference between locking and deleting accounts. Bring your `/etc/passwd` knowledge—we're about to modify it safely.
