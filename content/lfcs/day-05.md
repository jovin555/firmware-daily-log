---
title: "Day 05: sed: Stream Editing & In-Place Config Modification"
date: 2026-06-17
tags: ["til", "lfcs", "sed", "text-processing"]
---

## What I Explored Today

Today I dug into `sed` — the stream editor that every sysadmin reaches for when they need to automate config file changes across dozens of servers. I've used `sed` for quick find-and-replace before, but I never fully appreciated its power for non-interactive editing, in-place modification with backups, and multi-line pattern matching. By the end of this session, I was rewriting nginx config blocks and bulk-updating firewall rules without opening a single editor.

## The Core Concept

`sed` is a non-interactive text editor that processes input line by line. Unlike `vim` or `nano`, it doesn't need a terminal session — you pipe data in, apply transformations, and get transformed data out. This makes it ideal for scripting, automation, and configuration management.

The fundamental `sed` workflow is: **read a line → apply commands → print (or not) the result → repeat**. By default, every line is printed to stdout. Commands like `d` (delete) suppress printing, and `p` (print) explicitly prints the pattern space. The `-n` flag suppresses automatic printing, giving you full control.

The real power comes from addressing: you can target specific lines by number, regex pattern, or range. Combine that with the substitution command `s/old/new/flags`, and you have a surgical tool for text transformation.

## Key Commands / Configuration / Code

### Basic Substitution

```bash
# Replace first occurrence of "foo" with "bar" on each line
sed 's/foo/bar/' file.txt

# Replace all occurrences (global flag)
sed 's/foo/bar/g' file.txt

# Replace only on lines 3-5
sed '3,5s/foo/bar/g' file.txt

# Case-insensitive replace (GNU sed)
sed 's/foo/bar/I' file.txt
```

### In-Place Editing (The Killer Feature)

```bash
# Edit file in-place (no backup)
sed -i 's/Listen 80/Listen 8080/' /etc/httpd/conf/httpd.conf

# Edit in-place with backup (.bak extension)
sed -i.bak 's/old-server/new-server/' /etc/nginx/nginx.conf

# Edit in-place with custom backup suffix
sed -i'.20260617' 's/192.168.1.0/10.0.0.0/' /etc/network/interfaces
```

### Line Deletion and Printing

```bash
# Delete lines matching a pattern
sed '/^#/d' /etc/ssh/sshd_config          # Remove comments
sed '/^$/d' /etc/fstab                     # Remove empty lines

# Print only matching lines (like grep)
sed -n '/error/p' /var/log/syslog

# Print line numbers with matches
sed -n '/FAILED/=' /var/log/auth.log
```

### Range Operations

```bash
# Replace within a block (between two patterns)
sed '/<VirtualHost/,/<\/VirtualHost>/s/80/443/g' apache.conf

# Delete a block of config
sed '/^server {/,/^}/d' nginx.conf

# Extract a section
sed -n '/^\[database\]/,/^\[/p' config.ini | head -n -2
```

### Advanced: Multiple Commands and Scripts

```bash
# Multiple commands with -e
sed -e 's/foo/bar/' -e '/^#/d' file.txt

# Multiple commands in a script file
sed -f my_commands.sed file.txt

# Using addresses with negation
sed '/^#/!s/foo/bar/' file.txt  # Replace on non-comment lines
```

### Real-World Config Modification

```bash
# Disable root SSH login safely (with backup)
sed -i.bak '/^PermitRootLogin/s/yes/no/' /etc/ssh/sshd_config

# Update DNS servers in resolv.conf
sed -i 's/nameserver.*/nameserver 8.8.8.8/' /etc/resolv.conf

# Add a line after a match
sed '/^\[mysqld\]/a max_connections = 500' /etc/mysql/my.cnf

# Insert a line before a match
sed '/^listen 80/i listen 443 ssl;' /etc/nginx/sites-available/default
```

## Common Pitfalls & Gotchas

1. **In-place on symlinks breaks the link** — `sed -i` creates a new file, so if you edit a symlinked config file, the symlink becomes a regular file. Always use `sed -i --follow-symlinks` on GNU systems, or edit the target directly.

2. **Delimiter collision** — When your pattern contains `/`, use an alternate delimiter like `|` or `#`: `sed 's|/var/www|/srv/http|g'`. This avoids the "leaning toothpick syndrome" of escaping every slash.

3. **The `-i` flag behavior differs** — On macOS/BSD, `-i` requires an argument (even if empty): `sed -i '' 's/foo/bar/' file`. On Linux, `-i` alone works. Always test with `-i.bak` first to avoid destroying files.

4. **Greedy matching** — `sed` uses basic regex by default, so `*` is greedy. Use `sed -E` for extended regex (ERE) to get `+`, `?`, and non-greedy matching. Without `-E`, `*` matches zero or more of the preceding character.

## Try It Yourself

1. **Bulk-update an Apache virtual host** — Take a config file with multiple `<VirtualHost *:80>` blocks. Use `sed` to change all of them to port 443, add an `SSLEngine on` line after each opening tag, and create a backup with the date suffix.

2. **Clean a log file** — Given a syslog file, use `sed` to: remove all lines containing "DEBUG", extract only lines between "START" and "END" markers, and replace all IP addresses (pattern `[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+`) with "REDACTED".

3. **Config file transformation** — Take an nginx config and use `sed` to: comment out all `server_name` directives (prepend `#`), change all `root` paths from `/var/www` to `/data/www`, and delete any `location /static/` blocks entirely. Do it in a single `sed` command with multiple `-e` expressions.

## Next Up

Tomorrow I'm tackling **awk: Field Parsing, Conditions & Log Analysis**. If `sed` is the scalpel for line-by-line editing, `awk` is the chainsaw for columnar data — I'll be parsing access logs, computing averages, and building conditional reports that would take pages of bash to replicate.
