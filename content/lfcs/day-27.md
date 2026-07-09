---
title: "Day 27: Scheduling Tasks: cron, crontab, at"
date: 2026-07-09
tags: ["til", "lfcs", "cron", "scheduling"]
---

## What I Explored Today

Today I dug into Linux task scheduling—specifically `cron`, `crontab`, and `at`. These are the tools every sysadmin reaches for when they need something to happen automatically, whether it's a nightly backup at 2 AM or a one-off cleanup job in an hour. I've used `cron` before, but today I focused on the nuances: environment differences, proper logging, and when `at` is actually the better choice.

## The Core Concept

Why do we need separate scheduling tools? Because not all tasks are the same.

`cron` is for recurring jobs—things that happen daily, weekly, or at specific intervals. It's the workhorse of system automation. `at`, on the other hand, is for one-shot scheduling: "run this script exactly once at 3:15 PM next Tuesday." The distinction matters because `cron` jobs persist until removed, while `at` jobs self-destruct after execution.

The real gotcha? `cron` runs with a minimal environment. Your `$PATH`, `$HOME`, and other variables are stripped down. This is the #1 cause of "it works when I run it manually but not in cron" frustration. Understanding this is half the battle.

## Key Commands / Configuration / Code

### Crontab Entry Format

The classic five-field syntax, plus the optional sixth field for the user (in system crontabs):

```
# ┌───────── minute (0-59)
# │ ┌───────── hour (0-23)
# │ │ ┌───────── day of month (1-31)
# │ │ │ ┌───────── month (1-12)
# │ │ │ │ ┌───────── day of week (0-7, 0 and 7 = Sunday)
# │ │ │ │ │
  * * * * * command_to_run
```

### Editing Your User Crontab

```bash
# Opens your personal crontab in $EDITOR
crontab -e

# List current cron jobs
crontab -l

# Remove all cron jobs for current user
crontab -r
```

### Practical Cron Examples

```bash
# Run backup script every night at 2:30 AM
30 2 * * * /home/user/scripts/backup.sh

# Run log rotation every Sunday at 3 AM
0 3 * * 0 /usr/sbin/logrotate /etc/logrotate.conf

# Run a job every 15 minutes during business hours (9 AM - 5 PM, Mon-Fri)
*/15 9-17 * * 1-5 /usr/local/bin/healthcheck.sh

# Run on the 1st and 15th of every month at midnight
0 0 1,15 * * /home/user/scripts/monthly_report.sh
```

### Using `at` for One-Shot Jobs

```bash
# Schedule a job to run at 3:15 PM today
echo "/home/user/scripts/cleanup.sh" | at 15:15

# Schedule for 2 days from now at 10 AM
at 10:00 +2 days
at> /home/user/scripts/archive_logs.sh
at> <Ctrl+D>

# List pending at jobs
atq

# Remove job with ID 5
atrm 5
```

### The Environment Trap: Fixing It

```bash
# Always set PATH and other critical variables at the top of your cron job
# This is the most common fix for "cron doesn't work"

# In crontab -e:
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
SHELL=/bin/bash
MAILTO=admin@example.com

# Now your commands will find everything
30 2 * * * /home/user/scripts/backup.sh
```

### Logging Cron Output

```bash
# Redirect stdout and stderr to a log file with timestamps
# This is critical for debugging
30 2 * * * /home/user/scripts/backup.sh >> /var/log/backup.log 2>&1

# Better: use logger to send to syslog
30 2 * * * /home/user/scripts/backup.sh 2>&1 | logger -t backup
```

### System Crontab Locations

```bash
# System-wide crontab (requires 6th field: user)
/etc/crontab

# Drop-in directories for cron jobs
/etc/cron.d/          # Individual files, same format as /etc/crontab
/etc/cron.hourly/     # Scripts run every hour
/etc/cron.daily/      # Scripts run daily
/etc/cron.weekly/     # Scripts run weekly
/etc/cron.monthly/    # Scripts run monthly
```

## Common Pitfalls & Gotchas

**1. Percent signs (%) in cron commands**
The `%` character has special meaning in cron—it's interpreted as a newline. If you need to use `date +%Y%m%d` in a cron command, you must escape it: `date +\%Y\%m\%d`. Better yet, put complex commands in a script file.

**2. Cron doesn't load your shell profile**
When cron runs a script, it doesn't source `.bashrc`, `.bash_profile`, or `.profile`. Your script must set its own environment or you must explicitly source the profile at the top of the cron command:
```
30 2 * * * . $HOME/.bash_profile; /home/user/scripts/backup.sh
```

**3. Forgetting that `at` jobs run in a different context**
Like cron, `at` jobs run with a limited environment. But `at` actually captures the environment variables from when you submit the job. This can be surprising—if you submit an `at` job from a shell with modified variables, those variables persist. Always test `at` jobs with explicit paths.

**4. Mail flooding**
By default, cron sends the output of every job to the user's local mailbox. If a job runs every minute and produces output, you'll get 1440 emails per day. Always redirect output unless you specifically want mail:
```
* * * * * /script.sh > /dev/null 2>&1
```

## Try It Yourself

1. **Create a cron job that logs the current date and load average every 5 minutes** to `/var/log/system_health.log`. Ensure it includes proper PATH and SHELL settings. Check the log after 10 minutes to confirm it's working.

2. **Use `at` to schedule a one-time job** that creates a file named `/tmp/at_test_$(date +%s)` exactly 10 minutes from now. Verify it was created, then check `atq` to confirm the queue is empty.

3. **Debug a broken cron job**: Write a script that intentionally fails (e.g., `exit 1`). Schedule it via cron, then check `/var/log/syslog` or `/var/log/cron` to see the error. Add proper logging and fix the script to log success/failure with timestamps.

## Next Up

Tomorrow, we're diving into kernel modules: `lsmod`, `modprobe`, and `insmod`. We'll cover how to dynamically load and unload kernel modules, check what's currently loaded, and handle module dependencies—essential skills for managing hardware drivers and filesystem support without rebooting.
