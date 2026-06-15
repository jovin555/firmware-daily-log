---
title: "Day 03: Finding Files: find, locate, which, whereis"
date: 2026-06-15
tags: ["til", "lfcs", "find", "search"]
---

## What I Explored Today

Today I dug into the four essential tools Linux provides for locating files and binaries: `find`, `locate`, `which`, and `whereis`. While they all answer "where is this file?", each serves a fundamentally different purpose and performance profile. I spent the morning running benchmarks, testing edge cases, and understanding when to reach for each tool in production debugging scenarios.

## The Core Concept

The Linux filesystem is a tree, and finding a file is a tree traversal problem. The four tools solve this with different trade-offs:

- **`find`** performs a live, recursive walk of the filesystem. It's accurate but I/O-bound — every directory must be read from disk. This is your scalpel for complex queries.
- **`locate`** queries a pre-built database (typically updated daily via cron). It's instant but can be stale. Use it when you need speed and approximate results.
- **`which`** searches `$PATH` only. It answers "which binary would the shell execute?" — nothing more.
- **`whereis`** searches standard binary, source, and man page directories. It's a specialized tool for developer/administrator documentation lookups.

The key insight: `find` is for *arbitrary files by attribute*, `locate` is for *fast name-based search*, `which` is for *executable resolution*, and `whereis` is for *package component discovery*.

## Key Commands / Configuration / Code

### `find` — The Swiss Army Knife

```bash
# Find all .conf files modified in the last 7 days
find /etc -name "*.conf" -mtime -7

# Find files larger than 100MB owned by www-data
find /var -type f -size +100M -user www-data

# Find and execute: chmod 644 on all .php files
find /var/www -type f -name "*.php" -exec chmod 644 {} \;

# Find empty directories and delete them (GNU find)
find /tmp -type d -empty -delete

# Find files with specific permissions (setuid)
find /usr -type f -perm -4000 -ls
```

**Critical flags:**
- `-type f` (file), `d` (directory), `l` (symlink)
- `-name` (case-sensitive), `-iname` (case-insensitive)
- `-mtime` (modification time in days), `-mmin` (in minutes)
- `-size` supports `+` (greater than), `-` (less than), `c` (bytes), `k`, `M`, `G`
- `-exec` vs `-execdir`: always prefer `-execdir` for safety — it runs the command from the file's directory, avoiding PATH injection

### `locate` — The Speed Demon

```bash
# Basic usage
locate nginx.conf

# Case-insensitive search
locate -i "systemd*service"

# Count matches without listing
locate -c "*.log"

# Update the database manually (requires root)
sudo updatedb
```

The database lives at `/var/lib/mlocate/mlocate.db` by default. Check `updatedb.conf` for excluded paths (typically `/proc`, `/sys`, `/tmp`).

### `which` — PATH Resolution

```bash
# Find the exact binary the shell will use
which python3
# /usr/bin/python3

# Show all matches in PATH (not just first)
which -a python3
```

### `whereis` — Binary + Source + Man Pages

```bash
# Find all components of a command
whereis ls
# ls: /usr/bin/ls /usr/share/man/man1/ls.1.gz

# Only search for binaries
whereis -b ls

# Only search for man pages
whereis -m ls
```

## Common Pitfalls & Gotchas

1. **`find` with `-exec` without `+` or `\;`** — Using `-exec command {} \;` spawns a new process for *every* file. For bulk operations, use `-exec command {} +` which batches arguments like `xargs`. Better yet, pipe to `xargs` with `-0` for null-delimited safety:
   ```bash
   find . -type f -name "*.tmp" -print0 | xargs -0 rm -f
   ```

2. **`locate` returns stale or missing results** — If you just created a file, `locate` won't see it until the next `updatedb` run. Conversely, deleted files may still appear. Always verify with `ls` or `find` before acting on `locate` output.

3. **`which` lies about scripts** — `which` only checks `$PATH` for executables. If a script is invoked via `./script.sh` or an absolute path, `which` won't find it. Also, `which` doesn't resolve shell aliases or functions — use `type` for that:
   ```bash
   type ll
   # ll is aliased to `ls -alF'
   ```

## Try It Yourself

1. **Find all world-writable files in `/etc`** — Use `find` with `-perm -o+w` to identify security risks. Pipe to `-ls` for a detailed listing.

2. **Build a locate database for a custom directory** — Create a small test directory with files, then run `updatedb -l 0 -o custom.db -U /path/to/test`. Query it with `locate -d custom.db "*.txt"`.

3. **Trace a command's origin** — Pick a command like `ssh` or `git`. Use `which -a`, `whereis`, and `type` to find all copies. Then use `find / -name "ssh" -type f 2>/dev/null` to see if any exist outside standard PATH.

## Next Up

Tomorrow we dive into **grep Deep Dive: BRE, ERE & Practical Patterns** — we'll move beyond `grep -r` and master basic vs extended regular expressions, lookaheads, backreferences, and real-world log parsing patterns that separate script kiddies from engineers.
