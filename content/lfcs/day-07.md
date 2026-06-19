---
title: "Day 07: sort, uniq, cut, wc & Text Pipeline Patterns"
date: 2026-06-19
tags: ["til", "lfcs", "pipelines", "text-processing"]
---

## What I Explored Today

Today I dove into the core text-processing commands that form the backbone of every Linux engineer's daily workflow: `sort`, `uniq`, `cut`, and `wc`. More importantly, I learned how to chain them together into pipelines that transform raw log output, configuration dumps, or CSV exports into actionable data. These aren't just commands—they're the verbs of a composable text-processing language that every sysadmin and embedded engineer must speak fluently.

## The Core Concept

The Unix philosophy teaches us that each tool should do one thing well. `sort` orders lines, `uniq` deduplicates adjacent duplicates, `cut` extracts columns, and `wc` counts things. Alone, they're useful. Together, they're transformative.

The real power emerges when you realize that text is the universal interface. Whether you're parsing `/proc/meminfo`, analyzing Apache access logs, or cleaning up a list of IP addresses from a firewall dump, these four commands—combined with pipes—let you answer questions like "Which user made the most requests?" or "What are the top 10 error codes?" without writing a single line of Python or Perl.

The key insight: **pipeline order matters**. You almost always `sort` before `uniq` (because `uniq` only removes *adjacent* duplicates). You `cut` early to reduce data volume. You `wc -l` at the end to count results. This pattern is so common it deserves a name: the filter-sort-aggregate pipeline.

## Key Commands / Configuration / Code

### `sort` — Ordering lines
```bash
# Basic alphabetical sort
sort users.txt

# Reverse sort
sort -r users.txt

# Numeric sort (critical for IPs, sizes, timestamps)
sort -n numbers.txt

# Sort by column (field) — here column 2, tab-separated
sort -t$'\t' -k2 -n data.tsv

# Human-readable sizes (e.g., 2K, 3M, 1G)
sort -h file_sizes.txt

# Unique sort (combines sort + uniq in one pass)
sort -u duplicates.txt
```

### `uniq` — Removing duplicates (only adjacent!)
```bash
# Count occurrences of each line
sort input.txt | uniq -c

# Show only lines that appear exactly once
sort input.txt | uniq -u

# Show only lines that appear more than once
sort input.txt | uniq -d

# Case-insensitive uniq
sort -f input.txt | uniq -i
```

### `cut` — Slicing columns
```bash
# Extract first and third fields from CSV
cut -d',' -f1,3 data.csv

# Extract characters 5-12 from each line
cut -c5-12 /etc/passwd

# Extract from field 2 to end
cut -d':' -f2- /etc/group

# Common pattern: extract usernames from /etc/passwd
cut -d':' -f1 /etc/passwd | sort
```

### `wc` — Counting words, lines, characters
```bash
# Count lines only (most common use)
wc -l access.log

# Count words
wc -w report.txt

# Count bytes (useful for binary files)
wc -c firmware.bin

# Count characters (respects multi-byte UTF-8)
wc -m utf8_file.txt
```

### Real Pipeline Pattern: Top 10 IPs from Apache log
```bash
# Extract IP column (first field, space-separated), sort, count, sort by count descending, take top 10
cut -d' ' -f1 /var/log/apache2/access.log \
  | sort \
  | uniq -c \
  | sort -rn \
  | head -10
```

### Real Pipeline Pattern: Largest files by extension
```bash
# Find all .log files, get sizes, sort human-readable, show top 5
find /var/log -name '*.log' -exec ls -lh {} \; \
  | awk '{print $5, $NF}' \
  | sort -h \
  | tail -5
```

## Common Pitfalls & Gotchas

1. **`uniq` without `sort` is almost always wrong.** If your input has duplicates separated by other lines, `uniq` won't see them. I've seen engineers waste hours debugging why `uniq -c` returned counts of 1 for everything. Always `sort` first, or use `sort -u` if you don't need counts.

2. **`cut` with default delimiter is tab, not space.** Many log files use spaces. If you do `cut -f2` on a space-separated file, you'll get the entire line. Always specify `-d' '` for space-delimited data. For variable whitespace, use `awk '{print $2}'` instead.

3. **`wc -l` counts newline characters, not lines.** A file without a trailing newline will undercount by one. This matters when processing streaming data or files created by `printf` without `\n`. Always ensure your input ends with a newline, or use `grep -c .` as a more robust line counter.

## Try It Yourself

1. **Find the most common error code in a log:** Extract the HTTP status code from an Apache access log (field 9, space-delimited), sort, count, and display the top 3. Hint: `cut -d' ' -f9 access.log | sort | uniq -c | sort -rn | head -3`.

2. **Identify duplicate usernames across systems:** Given two files `users_a.txt` and `users_b.txt` (one username per line), find usernames that appear in both files. Use `sort` and `uniq -d`. Then find usernames unique to file A.

3. **Count total lines of C code in a project:** Recursively find all `.c` and `.h` files, count lines in each, then sum the total using `awk '{total+=$1} END {print total}'`. Combine `find`, `wc -l`, and `awk` in a pipeline.

## Next Up

Tomorrow we tackle **Archiving with tar: Creation, Extraction & Compression**. We'll cover `tar` flags for creating and extracting archives, the difference between `-z`, `-j`, and `-J` compression, and how to inspect tarball contents without extracting. Plus, the gotcha that trips up everyone: relative vs. absolute paths in archives.
