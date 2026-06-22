---
title: "Day 10: Regular Expressions for the LFCS Exam"
date: 2026-06-22
tags: ["til", "lfcs", "regex", "grep"]
---

## What I Explored Today

Today I dove deep into regular expressions (regex) as they apply to the LFCS exam. While regex is a cross-tool skill, the exam focuses on its use with `grep`, `sed`, `awk`, and `less`. I spent the morning running pattern matches against logs, configuration files, and system output, learning how to distinguish between basic, extended, and Perl-compatible regex flavors. The key insight: the LFCS expects you to know which tools use which regex engine by default, and how to switch between them.

## The Core Concept

Regular expressions are a pattern-matching language for text. In the LFCS context, they are not a programming language themselves but a syntax you embed in command-line tools. The "why" matters: you use regex to filter, extract, or transform text streams without writing scripts. For example, finding all failed SSH login attempts in `/var/log/auth.log` requires a pattern like `Failed password` — but that’s a literal string. Real power comes from metacharacters: `^` (start of line), `$` (end of line), `.` (any character), `*` (zero or more of previous), `+` (one or more), `[]` (character class), and `()` (grouping).

The critical distinction for the exam: **Basic Regular Expressions (BRE)** vs. **Extended Regular Expressions (ERE)**. BRE requires escaping `?`, `+`, `{`, `|`, `(`, `)` with a backslash to give them special meaning. ERE treats them as metacharacters without escaping. `grep` defaults to BRE; use `grep -E` for ERE. `sed` uses BRE by default; `sed -E` enables ERE. `awk` uses ERE natively. `less` uses basic regex unless you invoke it with `less -r` or use `&` pattern mode.

## Key Commands / Configuration / Code

### 1. `grep` — The Workhorse

```bash
# Find lines containing exactly "error" (case-insensitive)
grep -i '^error$' /var/log/syslog

# Find IP addresses (IPv4) in a file
grep -E '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' access.log

# Count failed SSH attempts (BRE version)
grep -c 'Failed password' /var/log/auth.log

# Show 2 lines of context around each match
grep -B1 -A2 'panic' kernel.log
```

### 2. `sed` — Stream Editor with Regex

```bash
# Replace all "foo" with "bar" (global, in-place)
sed -i 's/foo/bar/g' config.txt

# Delete lines matching a pattern
sed '/^#/d' /etc/ssh/sshd_config

# Print only lines 10-20 that contain "error"
sed -n '10,20{/error/p}' application.log
```

### 3. `awk` — Pattern Scanning and Processing

```bash
# Print lines where field 3 (e.g., HTTP status) is 500
awk '$3 == 500 { print $0 }' /var/log/nginx/access.log

# Use regex to match field 1 (IP) starting with 192.168
awk '/^192\.168/ { print $1, $NF }' access.log

# Count lines matching a pattern
awk '/ERROR/ { count++ } END { print count }' syslog
```

### 4. `less` — Interactive Pager with Regex

```bash
# Open a file and search with regex (type /pattern)
less /var/log/syslog
# Inside less, type: /^Jan 10.*error

# Use extended regex in less (requires -r flag)
less -r /var/log/syslog
# Then: /(error|warning)
```

### 5. Character Classes and Quantifiers

```bash
# Match lines with a 5-digit number (postal code)
grep -E '\b[0-9]{5}\b' addresses.txt

# Match email addresses (simplified)
grep -E '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' contacts.txt

# Match lines that start with a capital letter
grep '^[A-Z]' document.txt
```

## Common Pitfalls & Gotchas

1. **Forgetting to escape dots and other metacharacters in BRE**  
   `grep '192.168.1.1'` matches `192x168y1z1` because `.` matches any character. Always escape: `grep '192\.168\.1\.1'` or use `grep -F` for fixed strings.

2. **Confusing `*` (zero or more) with `+` (one or more)**  
   `grep 'ab*'` matches `a`, `ab`, `abb` — but also `a` alone. If you need at least one `b`, use `grep -E 'ab+'`. This is a frequent exam trap.

3. **Greedy vs. lazy matching in `sed`**  
   `sed 's/foo.*bar//'` removes from the first `foo` to the *last* `bar` on the line (greedy). To match the shortest span, you need `sed -E 's/foo.*?bar//'` but `sed` doesn't support lazy quantifiers natively — use `[^b]*` as a workaround: `sed 's/foo[^b]*bar//'`.

4. **Using `grep` on binary files**  
   `grep` treats binary files as text, which can corrupt your terminal. Always use `grep -a` (treat as text) or `grep -I` (ignore binary) explicitly when processing logs that might contain binary data.

## Try It Yourself

1. **Extract all IPv4 addresses from a log file**  
   Create a file `test.log` with lines like:  
   `192.168.1.1 - - [22/Jun/2026] "GET /" 200`  
   `10.0.0.255 - - [22/Jun/2026] "POST /login" 401`  
   Use `grep -E` to extract only the IP addresses. Then modify the pattern to exclude private ranges (10.x.x.x, 192.168.x.x, 172.16-31.x.x).

2. **Clean a configuration file**  
   Take `/etc/ssh/sshd_config` (or a copy). Use `sed` to:  
   - Remove all blank lines  
   - Remove all comment lines (starting with `#`)  
   - Print only lines that contain `PermitRootLogin` or `PasswordAuthentication`  
   Save the result to a new file.

3. **Count HTTP status codes from an access log**  
   Use `awk` to parse an Apache/Nginx access log. Count how many lines have status 200, 404, and 500. Then use `grep -c` to verify your counts match.

## Next Up

Tomorrow we shift from pattern matching to the shell itself: **Shell Variables, Environment & Startup Files**. We’ll explore how `$PATH` works, what `.bashrc`, `.bash_profile`, and `.profile` actually do, and how to set persistent environment variables for system-wide use. Expect hands-on with `export`, `env`, and `set`.
