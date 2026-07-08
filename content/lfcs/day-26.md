---
title: "Day 26: systemctl & journalctl: Services & Logs"
date: 2026-07-08
tags: ["til", "lfcs", "logging", "systemctl"]
---

## What I Explored Today

Today I dug into the two pillars of systemd service management: `systemctl` for controlling services and `journalctl` for inspecting their logs. While I've used both casually for years, I focused on the patterns that matter in production—how to debug a failed unit, how to follow logs without drowning in noise, and how to persist logs across reboots. The key insight is that these tools are designed to work together: `systemctl status` gives you the snapshot, `journalctl` gives you the timeline.

## The Core Concept

Systemd is the init system and service manager on virtually every modern Linux distribution. It treats every background process as a *unit*—a declarative configuration file that defines how to start, stop, and monitor a service. `systemctl` is the command-line interface to interact with those units. `journalctl` is the log viewer for systemd's binary journal, which collects structured log data from the kernel, services, and syslog.

Why two tools? Because service management and log inspection have different workflows. When a service fails, you need to know *immediately* if it's running, why it stopped, and what the last few log lines say. `systemctl status` gives you all three in one command. When you need to trace a bug over hours or correlate events across services, you reach for `journalctl` with its powerful filtering and time-range queries.

The real power comes from combining them: `journalctl -u <service>` scoped to a specific unit, with `--since` and `--until` for time windows, and `-f` for tailing. This is the bread and butter of incident response.

## Key Commands / Configuration / Code

### Service Lifecycle with systemctl

```bash
# Check status of a service (shows active/inactive, PID, recent logs)
systemctl status sshd

# Start, stop, restart (use restart for config reloads)
sudo systemctl restart nginx

# Enable service to start at boot, disable to prevent it
sudo systemctl enable --now postgresql  # enable + start in one step
sudo systemctl disable postgresql

# Reload config without restarting (if service supports SIGHUP)
sudo systemctl reload nginx

# List all failed units (critical for monitoring scripts)
systemctl --failed

# Show unit file and overrides
systemctl cat sshd
systemctl show sshd  # all properties, including environment
```

### Debugging a Failed Service

```bash
# Quick check: is it running? If not, why?
systemctl status myapp.service

# View the last 50 lines of the unit's journal
journalctl -u myapp.service -n 50 --no-pager

# Follow logs in real-time while restarting
journalctl -u myapp.service -f &
sudo systemctl restart myapp.service

# See all log entries for the unit since last boot
journalctl -u myapp.service -b
```

### Advanced journalctl Filtering

```bash
# Time-based queries (ISO 8601 or relative)
journalctl --since "2026-07-07 14:00" --until "2026-07-07 15:00"

# Relative time: last 30 minutes
journalctl --since "30 min ago"

# Show only kernel messages (useful for hardware issues)
journalctl -k

# Filter by priority (0=emerg, 3=err, 4=warning, 6=info)
journalctl -p err -b  # errors since last boot

# Output as JSON for scripting
journalctl -u nginx.service -o json-pretty

# Show disk usage of the journal
journalctl --disk-usage
```

### Persisting the Journal (Critical for Production)

By default, journald stores logs in memory (`/run/log/journal`), which means they're lost on reboot. To persist:

```bash
# Create the persistent directory
sudo mkdir -p /var/log/journal

# Restart journald to start writing there
sudo systemctl restart systemd-journald

# Verify: now you see entries in /var/log/journal
ls /var/log/journal/
```

You can also control log rotation in `/etc/systemd/journald.conf`:

```ini
# /etc/systemd/journald.conf
SystemMaxUse=500M
MaxFileSec=1week
RuntimeMaxUse=100M
```

## Common Pitfalls & Gotchas

1. **`systemctl reload` vs `restart` confusion**  
   `reload` sends SIGHUP, which only works if the service explicitly handles it (nginx, apache, sshd). For most services, `reload` silently does nothing—use `restart` unless you've verified the unit has `ExecReload=` defined. Check with `systemctl cat <service>`.

2. **Journal logs vanish after reboot**  
   This is the most common surprise. By default, journald writes to `/run/log/journal`, a tmpfs. If you haven't created `/var/log/journal`, your logs are ephemeral. Always persist in production, and set `SystemMaxUse` to prevent disk fills.

3. **`systemctl status` shows "active (exited)" for oneshot services**  
   This is correct behavior for services that run a single task and exit (e.g., `systemd-tmpfiles-clean`). Don't treat "exited" as a failure—check the exit code in the status output. A green "active (exited)" with `code=exited, status=0/SUCCESS` is fine.

## Try It Yourself

1. **Debug a failing service**  
   Create a simple script that exits with code 1, wrap it in a systemd service unit, start it, and use `systemctl status` + `journalctl -u` to find the error. Then fix the script and verify recovery.

2. **Persist journal logs and set limits**  
   On a test VM, create `/var/log/journal`, restart journald, then configure `SystemMaxUse=200M` in `journald.conf`. Generate some log activity and verify with `journalctl --disk-usage`.

3. **Time-range forensic analysis**  
   Use `journalctl --since "1 hour ago" --until "30 min ago" -p warning` to find all warnings in a specific window. Then pipe to `grep` to isolate a particular service. This is exactly how you'd triage a production incident.

## Next Up

Tomorrow: **Scheduling Tasks: cron, crontab, at** — we'll move from reactive log inspection to proactive automation, covering cron syntax, environment gotchas, and the `at` command for one-shot jobs.
