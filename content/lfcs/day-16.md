---
title: "Day 16: Disk Usage: df, du & Finding Space Hogs"
date: 2026-06-28
tags: ["til", "lfcs", "disk", "storage"]
---

## What I Explored Today

Today I dug into the two essential disk analysis commands every sysadmin reaches for when something fills up: `df` (disk free) and `du` (disk usage). I also covered practical patterns for hunting down space hogs, interpreting output correctly, and avoiding the common mistakes that waste time or cause data loss.

## The Core Concept

Disk space management isn't just about knowing *how much* is free—it's about understanding *where* space is going and *why*. The filesystem abstraction hides the physical layout, but every byte consumed belongs to a file, a directory, or metadata. `df` gives you a high-level view of mounted filesystems, while `du` walks the directory tree to tally usage. Together they form the diagnostic loop: `df` flags a problem, `du` pinpoints the culprit.

Why this matters: A full root filesystem can crash services, prevent logins, or corrupt databases. In production, you rarely have time to guess. You need commands that work fast, handle large trees, and respect filesystem boundaries. Today's tools do exactly that.

## Key Commands / Configuration / Code

### `df` — Disk Free Overview

```bash
# Human-readable sizes, show filesystem type, exclude pseudo-filesystems
df -hT -x tmpfs -x devtmpfs

# Output:
# Filesystem     Type      Size  Used Avail Use% Mounted on
# /dev/sda1      ext4      100G   75G   25G  75% /
# /dev/sdb1      ext4      500G  200G  300G  40% /data
```

Key flags:
- `-h` — human-readable (K, M, G)
- `-T` — show filesystem type (ext4, xfs, btrfs)
- `-x` — exclude filesystem types (filters noise)
- `-i` — inode usage (filesystem can be full on inodes even with free blocks)

**Real-world pattern:** Always use `-hT` and exclude tmpfs. Without `-T`, you can't distinguish a real disk from a RAM-backed filesystem.

### `du` — Disk Usage by Directory

```bash
# Top-level usage, human-readable, one line per directory
du -h --max-depth=1 /var 2>/dev/null | sort -rh | head -10

# Output:
# 45G     /var/log
# 12G     /var/lib
# 3.2G    /var/cache
# 1.1G    /var/tmp
```

Key flags:
- `-h` — human-readable
- `--max-depth=N` — limit recursion depth (critical for speed)
- `-s` — summary only (equivalent to `--max-depth=0`)
- `-c` — grand total
- `-x` — stay on one filesystem (don't cross mount points)

**The killer combo for finding space hogs:**

```bash
# Find largest directories in /, one filesystem only, sorted
du -hx --max-depth=1 / 2>/dev/null | sort -rh | head -5

# Find largest files anywhere (slow but thorough)
find / -xdev -type f -size +100M -exec ls -lh {} \; 2>/dev/null | sort -k5 -rh | head -10
```

The `-x` flag in both commands prevents crossing into mounted filesystems (like `/proc`, `/sys`, or NFS mounts), which would either hang or produce misleading results.

### Practical Space Hog Hunt

```bash
# Step 1: Identify the full filesystem
df -hT | grep -E '9[0-9]%|100%'

# Step 2: Drill into the mounted directory
cd /var
du -hx --max-depth=1 . 2>/dev/null | sort -rh

# Step 3: If logs are the culprit, check rotated vs active
du -sh /var/log/*.log /var/log/*.gz 2>/dev/null | sort -rh | head -5
```

## Common Pitfalls & Gotchas

### 1. `du` crosses filesystem boundaries by default
Running `du /` without `-x` will descend into `/proc`, `/sys`, `/dev`, and any mounted drives. This can take minutes, produce nonsensical numbers, or hang on network mounts. **Always use `-x` when scanning from root.**

### 2. `df` shows *used* space, not *allocated* space
A 100 GB filesystem may show 75 GB used and 25 GB available, but if you delete a 10 GB file that's still held open by a process, `df` won't free the space until the process closes the file. Check with `lsof | grep '(deleted)'` to find these hidden hogs.

### 3. Hard links and shared blocks inflate `du` totals
`du` counts each hard link separately by default. The `--apparent-size` flag gives the logical size (what `ls -l` shows), while the default gives disk usage. For directories with many hard links (like Git object stores), the difference can be dramatic.

### 4. Inode exhaustion is invisible with `-h`
A filesystem can have 50% free blocks but 0% free inodes. Always check `df -i` when you get "No space left on device" errors despite `df -h` showing free space. This commonly happens on mail servers or systems with millions of tiny files.

## Try It Yourself

1. **Find your biggest log directory** — Run `du -hx --max-depth=1 /var/log 2>/dev/null | sort -rh` and identify which subdirectory (or file) is largest. Check if rotated logs (`*.gz`) are consuming more space than active logs.

2. **Detect hidden deleted files** — On a system with a nearly full filesystem, run `sudo lsof +L1` (or `lsof | grep '(deleted)'`) to find files that are deleted but still held open. Note the PID and size.

3. **Compare block usage vs apparent size** — Run `du -sh /some/dir` and `du -sh --apparent-size /some/dir` on a directory with many small files (like `/etc` or a Git repo). Calculate the overhead percentage.

## Next Up

Tomorrow I'll cover **Command Sequencing: &&, ||, ; and subshells** — how to chain commands intelligently, handle failures, and run groups of commands in isolated environments. Essential for writing robust scripts and one-liners that don't silently break.
