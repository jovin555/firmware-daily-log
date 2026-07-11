---
title: "Day 29: System Performance: top, vmstat, iostat, sar"
date: 2026-07-11
tags: ["til", "lfcs", "performance", "monitoring"]
---

## What I Explored Today

Today I dove into the four pillars of Linux performance analysis: `top`, `vmstat`, `iostat`, and `sar`. These tools form the core of any sysadmin's diagnostic workflow when a system goes sideways. I've used `top` casually for years, but I never fully appreciated how `vmstat` exposes memory pressure, how `iostat` reveals I/O bottlenecks, or how `sar` gives you historical context. The real insight today was that these tools aren't redundant—they're complementary, each slicing the performance onion from a different angle.

## The Core Concept

Performance troubleshooting is about identifying the *limiting resource*. Is it CPU? Memory? Disk I/O? Network? The wrong tool for the wrong resource leads to wild goose chases. The `top` command gives you a real-time dashboard of processes and CPU/memory consumption. `vmstat` (virtual memory statistics) focuses on memory paging, swapping, and CPU queue depth. `iostat` (I/O statistics) reports on block device throughput, latency, and utilization. `sar` (System Activity Reporter) is the historian—it collects and reports on all of these metrics over time, letting you spot trends and correlate events.

The key insight: **always start with `vmstat 1` to see if you're CPU-bound or I/O-bound, then drill down with `top` or `iostat`.** Don't stare at `top` for 20 minutes; use it to confirm what `vmstat` already told you.

## Key Commands / Configuration / Code

### 1. `top` — The Real-Time Process Viewer

```bash
# Launch top, then press these keys interactively:
# '1' — toggle per-CPU view
# 'M' — sort by memory usage
# 'P' — sort by CPU usage
# 'c' — show full command path
# 'k' — kill a process (enter PID, then signal 9 for SIGKILL)

# Batch mode for scripting (one-shot, non-interactive)
top -b -n 1 | head -20
```

The most overlooked column in `top` is `%WA` (I/O wait) — if this is high (>10%) and CPU is idle, you have an I/O bottleneck, not a CPU problem.

### 2. `vmstat` — Virtual Memory & System Stats

```bash
# Report every 1 second, 5 times
vmstat 1 5

# Output columns explained:
# r: run queue (processes waiting for CPU) — if > CPU count, you're CPU-bound
# b: processes in uninterruptible sleep (usually waiting on I/O)
# si/so: swap in/out — if non-zero, you're out of RAM
# us/sy/id/wa: user CPU, system CPU, idle, I/O wait
```

**My go-to command for initial triage:**
```bash
vmstat 1 10
```
Watch the `r` column. If it's consistently greater than the number of CPU cores, you're CPU-bound. If `wa` is high and `b` is non-zero, you're I/O-bound.

### 3. `iostat` — I/O Device Statistics

```bash
# Install if missing (RHEL/Debian)
# sudo yum install sysstat  # RHEL
# sudo apt install sysstat   # Debian

# Report every 2 seconds, 3 times, with extended stats (-x)
iostat -x 2 3

# Key columns:
# %util: percentage of time the device was busy (warning > 80%)
# await: average I/O latency in milliseconds (warning > 10ms for SSDs)
# r/s, w/s: read/write requests per second
# rkB/s, wkB/s: throughput
```

**Quick disk health check:**
```bash
iostat -x 1 5 | grep -E '(Device|sda|nvme)'
```

### 4. `sar` — Historical Performance Data

```bash
# Enable data collection (usually already running via cron)
# Check if sysstat service is active
systemctl status sysstat

# View today's CPU stats
sar -u

# View memory stats
sar -r

# View I/O stats (requires -b flag)
sar -b

# View load average
sar -q

# View from a specific date
sar -f /var/log/sysstat/sa11  # July 11

# Real-time monitoring (like vmstat but with sar's formatting)
sar -u 1 5
```

The killer feature of `sar`: you can look at what happened *yesterday* at 2:00 AM when the system was slow. No other tool on this list gives you that.

## Common Pitfalls & Gotchas

1. **Misinterpreting `top`'s `%CPU` for multi-threaded processes.** A process using 200% CPU on a 4-core machine is actually using 2 full cores. Don't panic—that's normal for well-written multi-threaded applications. Use `htop` (if available) for per-thread visibility.

2. **Ignoring `vmstat`'s `b` column.** A high `b` (processes in uninterruptible sleep) combined with low CPU usage means your disk is the bottleneck. Many engineers waste time tuning CPU when the real problem is a failing disk or a misconfigured RAID controller.

3. **`sar` data retention defaults.** By default, `sysstat` only keeps 7 days of data (controlled by `HISTORY=7` in `/etc/sysconfig/sysstat` on RHEL or `/etc/default/sysstat` on Debian). If you need longer history for capacity planning, increase this value. Also, ensure the `sysstat` cron job is enabled—it's often disabled by default on minimal installs.

## Try It Yourself

1. **The 60-second performance snapshot.** Run `vmstat 1 60` on a production system (or a test VM under load). After 60 seconds, note the average `r` column value and the `wa` percentage. If `r` > CPU count, you're CPU-bound. If `wa` > 10%, you're I/O-bound. Then run `iostat -x 1 3` and check `%util` on your root disk. Is it above 80%?

2. **Find the top I/O consumer.** Run `top` and press `x` to highlight the sort column, then `W` to write a custom config. Now press `f` and navigate to `WCHAN` (waiting channel) — add it to the display. Processes stuck in `D` state (uninterruptible sleep) with a kernel function like `blkdev_issue_flush` are waiting on disk I/O. Identify the PID and check its open files with `lsof -p <PID>`.

3. **Historical comparison with `sar`.** Run `sar -u -f /var/log/sysstat/sa$(date +%d --date="1 day ago")` to see yesterday's CPU stats. Compare the peak `%idle` value to today's. If today's idle is significantly lower, something changed. Use `sar -r` to check if memory pressure increased.

## Next Up

Tomorrow, we'll dive into GRUB2 configuration and boot recovery—what happens when your system won't boot and you need to drop into single-user mode, edit kernel parameters, or rebuild the bootloader from a rescue environment. Essential knowledge for the LFCS exam and real-world crisis management.
