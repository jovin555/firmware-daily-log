---
title: "Day 15: Shell Scripting Basics: Loops, Conditions, Functions"
date: 2026-06-27
tags: ["til", "lfcs", "scripting", "bash"]
---

## What I Explored Today

I dove into the three pillars of shell scripting that separate a one-liner from a real tool: loops, conditionals, and functions. While I've used `for` loops in ad-hoc pipelines before, today I focused on writing robust, reusable scripts that handle errors gracefully and compose logic cleanly. The key insight? Shell scripting is not just about running commands—it's about controlling the flow of execution and data through your system.

## The Core Concept

Shell scripts are glue. They orchestrate system commands, file operations, and user input into automated workflows. But without control structures, you're just typing commands in a file. Loops let you iterate over files, lines, or arguments. Conditions let you branch based on exit codes, file existence, or string comparisons. Functions let you package logic once and reuse it across scripts or even your interactive shell.

The real power comes from combining these: a function that validates input, a loop that processes a list of hosts, and a conditional that decides whether to retry or abort. This is how system administrators build monitoring scripts, deployment pipelines, and maintenance routines that run unattended.

## Key Commands / Configuration / Code

### 1. Conditionals: `if`, `elif`, `else`, `test`

```bash
#!/bin/bash
# Check if a file exists and is readable
file="/etc/passwd"

if [[ -r "$file" ]]; then
    echo "File $file exists and is readable."
elif [[ -e "$file" ]]; then
    echo "File exists but is not readable."
else
    echo "File does not exist."
fi
```

**Key operators:**
- `-f` : regular file
- `-d` : directory
- `-z` : string is empty
- `-n` : string is non-empty
- `$?` : exit code of last command (0 = success)

### 2. Loops: `for`, `while`, `until`

```bash
#!/bin/bash
# Loop over files in a directory
for file in /var/log/*.log; do
    if [[ -f "$file" ]]; then
        echo "Processing: $file"
        # Simulate some work
        wc -l "$file"
    fi
done

# While loop with a counter
counter=0
while [[ $counter -lt 5 ]]; do
    echo "Attempt $((counter + 1))"
    ((counter++))
done

# Until loop — runs until condition is true
until ping -c1 -W1 8.8.8.8 &>/dev/null; do
    echo "Waiting for network..."
    sleep 2
done
echo "Network is up."
```

### 3. Functions: Definition, Scope, Return

```bash
#!/bin/bash
# Function to check disk usage and alert if above threshold
check_disk() {
    local mount_point="$1"
    local threshold="${2:-80}"  # default 80%
    local usage

    usage=$(df "$mount_point" | awk 'NR==2 {print $5}' | tr -d '%')

    if [[ $usage -gt $threshold ]]; then
        echo "WARNING: $mount_point is at ${usage}% (threshold: ${threshold}%)"
        return 1
    else
        echo "OK: $mount_point at ${usage}%"
        return 0
    fi
}

# Call the function
check_disk "/" 85
if [[ $? -ne 0 ]]; then
    echo "Root partition needs attention."
fi
```

**Important:** `return` in a function sets the exit code (0–255). Use `local` for variables to avoid polluting the global scope.

### 4. Practical Example: Log Rotation Helper

```bash
#!/bin/bash
# Archive logs older than 7 days, compress them, and clean up

rotate_logs() {
    local log_dir="$1"
    local days="${2:-7}"

    if [[ ! -d "$log_dir" ]]; then
        echo "Error: $log_dir is not a directory." >&2
        return 2
    fi

    find "$log_dir" -name "*.log" -mtime +$days -print0 | while IFS= read -r -d '' logfile; do
        echo "Archiving: $logfile"
        gzip "$logfile"
    done
}

rotate_logs "/var/log/myapp" 14
```

## Common Pitfalls & Gotchas

1. **Forgetting to quote variables** — `[[ -f $file ]]` breaks if `$file` contains spaces. Always use `[[ -f "$file" ]]`. Double brackets `[[ ]]` are safer than single `[ ]` because they handle empty strings and spaces correctly.

2. **Using `return` vs `exit` in functions** — `return` exits the function, `exit` exits the entire script. If you accidentally use `exit` inside a function called from a loop, you kill the whole script.

3. **Off-by-one in `while read` loops** — When reading files line by line, always use `while IFS= read -r line; do ... done < file`. The `-r` prevents backslash interpretation, and `IFS=` preserves leading/trailing whitespace.

4. **`for` loops over command output** — `for file in $(ls *.log)` breaks on filenames with spaces. Use `for file in *.log` (globbing) or `find ... -print0 | while read -r -d ''` for safety.

## Try It Yourself

1. **Write a backup rotation script** — Create a script that takes a directory path as an argument, finds all `.tar.gz` files older than 30 days, and moves them to an `archive/` subdirectory. Use a function for the move logic and a loop to iterate.

2. **Build a service health checker** — Write a script that reads a list of service names from a file (one per line), checks each with `systemctl is-active`, and prints a summary table of running vs failed services. Use conditionals to color-code output (green for active, red for failed).

3. **Implement a retry wrapper** — Create a function `retry` that takes a command as an argument, runs it up to 3 times with a 5-second delay between attempts, and exits with the final exit code if all attempts fail. Use a `while` loop and a counter.

## Next Up

Tomorrow: **Disk Usage: df, du & Finding Space Hogs** — We'll move from scripting control flow to practical disk analysis. I'll cover interpreting `df -h`, using `du` to find the biggest directories, and building a script that alerts when partitions cross 90% usage. Bring your full disks and a sense of urgency.
