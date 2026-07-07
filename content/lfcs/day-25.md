---
title: "Day 25: systemd: Units, Targets & Dependency Graph"
date: 2026-07-07
tags: ["til", "lfcs", "systemd", "services"]
---

## What I Explored Today

Today I dug into systemd's unit model and dependency graph — the real engine behind service orchestration on modern Linux. I've used `systemctl start/stop` for years, but I never fully understood how systemd decides *what* to start, *when*, and *why*. The answer lies in units, targets, and the directed acyclic graph (DAG) that systemd builds at boot. This isn't just academic; understanding the dependency graph is how you debug boot hangs, fix service ordering, and write robust unit files.

## The Core Concept

Systemd doesn't just run services in a linear sequence. Instead, it models every resource — a service, a mount point, a socket, a timer, a device — as a **unit**. Each unit declares its dependencies (`Requires`, `Wants`, `After`, `Before`). At boot, systemd resolves all these declarations into a dependency graph, then parallelizes startup as much as possible while respecting ordering constraints.

The key insight: **systemd starts units in parallel unless explicitly ordered**. If service A says `After=network.target` and service B says `After=network.target`, both A and B can start simultaneously once the network target is reached. This is why modern Linux boots so fast — it's not doing less work, it's doing work concurrently.

**Targets** are special units that group other units. Think of them as synchronization points or "runlevels" (though they're more flexible). `multi-user.target` is the traditional multi-user mode; `graphical.target` adds the display manager. When you switch to a target, systemd starts all units that `Wants` or `Requires` that target, and stops units that conflict.

The dependency graph is a DAG — no cycles allowed. If you create a circular dependency, systemd will refuse to load the units. This is enforced at unit load time, not at runtime, so you'll see errors in `systemctl daemon-reload` or during boot.

## Key Commands / Configuration / Code

### Viewing the dependency graph

```bash
# Show all units that depend on sshd.service (reverse dependencies)
systemctl list-dependencies sshd.service --reverse

# Show what sshd.service needs to start (forward dependencies)
systemctl list-dependencies sshd.service

# Show the entire dependency tree for multi-user.target
systemctl list-dependencies multi-user.target

# Visualize as a graph (requires graphviz)
systemd-analyze dot multi-user.target | dot -Tsvg > boot-graph.svg
```

### Understanding unit types

```bash
# List all unit types currently loaded
systemctl -t help

# List all service units
systemctl list-units --type=service

# List all target units
systemctl list-units --type=target
```

### Writing a unit with explicit dependencies

Here's a real-world example: a custom application that must start after PostgreSQL and the network are ready, but before the web server:

```ini
# /etc/systemd/system/myapp.service
[Unit]
Description=My Custom Application
# Strong dependency: if postgresql fails, myapp stops
Requires=postgresql.service
# Soft dependency: start nfs if available, but don't fail if missing
Wants=network-online.target
# Ordering: these must be fully started before myapp
After=postgresql.service network-online.target
# Ordering: myapp must start before nginx
Before=nginx.service

[Service]
Type=simple
ExecStart=/usr/local/bin/myapp --config /etc/myapp/config.yaml
Restart=on-failure
User=myapp
Group=myapp

[Install]
WantedBy=multi-user.target
```

After writing this file:

```bash
systemctl daemon-reload
systemctl enable myapp.service
systemctl start myapp.service
```

### Checking the resolved dependency graph

```bash
# See why a unit is not starting (critical for debugging)
systemctl list-dependencies myapp.service

# Check if there are any dependency cycles
systemd-analyze verify myapp.service

# Show the boot critical chain (longest path)
systemd-analyze critical-chain
```

### Targets as synchronization points

```bash
# Switch to rescue mode (single-user)
systemctl rescue

# Switch to multi-user mode (no GUI)
systemctl isolate multi-user.target

# Set default target for next boot
systemctl set-default multi-user.target
```

## Common Pitfalls & Gotchas

1. **`Requires` vs `After` confusion**: `Requires=postgresql.service` means "if postgresql fails, stop me too." `After=postgresql.service` means "start me after postgresql." They are independent! If you only use `Requires` without `After`, systemd may start your service *before* postgresql finishes starting — and then fail because the DB isn't ready. Always pair `Requires` with `After` when you need both dependency and ordering.

2. **`Wants` is not `Requires`**: `Wants` means "try to start this, but if it fails, continue anyway." This is useful for optional dependencies like logging or monitoring. But if you use `Wants` and expect the dependency to be running before your service, you still need `After` — `Wants` alone provides no ordering.

3. **Circular dependencies are silently rejected**: If you create a cycle (A requires B, B requires A), `systemctl daemon-reload` will succeed, but the units won't load. You'll see errors like "Found ordering cycle on A.service/start." Always run `systemd-analyze verify` after writing complex unit files.

4. **Targets are not runlevels**: Unlike SysV init, targets don't have a numeric order. `multi-user.target` doesn't "come before" `graphical.target`. They're independent synchronization points. Switching to `graphical.target` starts the display manager; it doesn't "upgrade" from multi-user. Use `systemctl isolate` to switch between them cleanly.

## Try It Yourself

1. **Map your boot**: Run `systemd-analyze critical-chain` and identify the longest dependency chain. Then run `systemd-analyze blame` to see which units took the most time. Is there a unit you can optimize or parallelize?

2. **Write a custom target**: Create a new target file at `/etc/systemd/system/myapp.target` that `Wants` your application service and `Requires` `network-online.target`. Use `systemctl isolate myapp.target` to switch to it. Verify with `systemctl list-dependencies myapp.target`.

3. **Break the boot**: Temporarily add a circular dependency to a test unit (e.g., make `sshd.service` `Requires=myapp.service` and `myapp.service` `Requires=sshd.service`). Run `systemd-analyze verify` on both units and observe the error. Then fix it.

## Next Up

Tomorrow we'll dive into `systemctl` and `journalctl` — the two tools you'll use every day for managing services and reading logs. We'll cover filtering journald output by unit, priority, and time range, plus how to debug a service that won't start using real journalctl queries.
