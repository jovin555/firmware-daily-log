---
title: "Day 06: awk: Field Parsing, Conditions & Log Analysis"
date: 2026-06-18
tags: ["til", "lfcs", "awk", "text-processing"]
---

## What I Explored Today

Today I dove deep into `awk` — not the toy version that prints columns, but the full pattern-scanning and processing language that lives on every Linux system. I focused on field parsing with `FS` and `NF`, conditional logic for filtering records, and real-world log analysis patterns that sysadmins use daily. If `grep` finds lines and `sed` transforms them, `awk` is what you reach for when you need to *understand* structured text.

## The Core Concept

Most engineers learn `awk` as `awk '{print $1}'` and stop there. That's like knowing one chord on a guitar. The real power is that `awk` is an implicit loop over every line (record) in a file, where you can:

- Split each line into fields (default: whitespace)
- Apply patterns (before, during, after processing)
- Use built-in variables (`NR`, `NF`, `FS`, `OFS`)
- Write C-like conditionals and loops
- Aggregate data across records

The mental model: `awk` treats text as a database table. Each line is a row, each field is a column. Your script is a query.

## Key Commands / Configuration / Code

### Basic Field Parsing

```bash
# Print first and third field from /etc/passwd
awk -F: '{print $1, $3}' /etc/passwd

# Custom output field separator
awk -F: 'BEGIN{OFS=" | "} {print $1, $3}' /etc/passwd

# Print lines with more than 6 fields
awk -F: 'NF > 6' /etc/passwd
```

### Pattern Matching and Conditions

```bash
# Print lines where field 3 (UID) is greater than 1000
awk -F: '$3 > 1000 {print $1, $3}' /etc/passwd

# Match regex on a specific field
awk -F: '$1 ~ /^a.*/ {print $0}' /etc/passwd

# Multiple conditions (AND)
awk -F: '$3 >= 1000 && $1 != "nobody"' /etc/passwd

# BEGIN and END blocks for headers/summaries
awk -F: '
BEGIN {print "=== Users with UID > 1000 ==="}
$3 > 1000 {count++; print $1}
END {print "Total: " count}
' /etc/passwd
```

### Real Log Analysis Patterns

```bash
# Count HTTP status codes from Apache/Nginx access log
# Format: 192.168.1.1 - - [18/Jun/2026:10:15:30] "GET /index.html" 200 1234
awk '{print $9}' /var/log/nginx/access.log | sort | uniq -c | sort -rn

# Same with awk only (no pipeline)
awk '{count[$9]++} END {for (code in count) print code, count[code]}' /var/log/nginx/access.log

# Filter 5xx errors with timestamps
awk '$9 ~ /^5[0-9][0-9]$/ {print $4, $9, $7}' /var/log/nginx/access.log

# Average response size for successful requests
awk '$9 == 200 {total += $10; count++} END {print "Avg size:", total/count}' /var/log/nginx/access.log

# Find top 10 IPs by request count
awk '{ips[$1]++} END {for (ip in ips) print ips[ip], ip}' /var/log/nginx/access.log | sort -rn | head -10
```

### Advanced: Multi-line Records

```bash
# Parse /etc/hosts with comments and blank lines
awk '!/^#/ && NF > 0 {print $2, $1}' /etc/hosts

# Custom record separator (RS) for paragraph-style data
awk 'BEGIN{RS=""; FS="\n"} {print "Record", NR, "has", NF, "lines"}' /etc/hosts
```

## Common Pitfalls & Gotchas

1. **Field numbering starts at 1, not 0.** `$0` is the entire line, `$1` is first field. Newcomers often try `$0` as first field and get confused.

2. **`NR` vs `FNR` when processing multiple files.** `NR` counts total records across all files; `FNR` resets per file. If you're processing `/etc/passwd` and `/etc/group` together, use `FNR == 1` to detect file boundaries.

3. **String comparison vs numeric comparison.** `awk` is dynamically typed. `$3 > 1000` works numerically, but `$1 > "m"` does string comparison. If your field looks like a number but has leading zeros (e.g., `00123`), `awk` treats it as a string unless you force it: `$3 + 0 > 1000`.

4. **`for (key in array)` order is not guaranteed.** If you need sorted output, pipe to `sort` or use `PROCINFO["sorted_in"]` in GNU awk (`gawk`).

5. **Missing fields don't error, they're empty strings.** `awk -F: '{print $100}'` prints nothing — no error, no warning. Always validate with `NF` before accessing high field numbers.

## Try It Yourself

1. **Parse `/var/log/auth.log`** (or `/var/log/secure` on RHEL) and extract all failed SSH login attempts. Print the timestamp, source IP, and username. Count unique IPs.

2. **Analyze a CSV file** (e.g., `ps aux --no-headers | awk '{print $1, $3, $4}' > processes.csv`). Use `awk` to find processes consuming more than 50% CPU or 10% memory. Output a formatted report with column headers.

3. **Build a mini log monitor:** Given an Apache access log, write an `awk` one-liner that prints a live summary every 60 seconds showing: total requests, unique IPs, and count of 4xx/5xx errors. (Hint: use `watch` with your `awk` script.)

## Next Up

Tomorrow I'll tackle the text processing pipeline trifecta: `sort`, `uniq`, `cut`, and `wc`. We'll chain them together with pipes and `awk` to build production-grade log analysis pipelines that turn raw data into actionable insights — no Python required.
