---
title: "Day 13: System Information: uname, dmesg, lsblk, /proc"
date: 2026-06-25
tags: ["til", "lfcs", "system-info", "proc"]
---

## What I Explored Today

Today I dug into the core tools every Linux engineer reaches for when they need to understand what hardware and kernel they're actually running on. `uname`, `dmesg`, `lsblk`, and the `/proc` filesystem are the first responders for system introspection. These aren't just trivia commands—they're the difference between guessing and knowing when you're debugging a kernel panic, sizing a block device, or verifying your deployment target.

## The Core Concept

Linux exposes system information through two primary mechanisms: dedicated command-line utilities and the virtual `/proc` filesystem. The commands (`uname`, `lsblk`, `dmesg`) are user-friendly wrappers that parse kernel data structures and device information. The `/proc` filesystem is the raw, real-time interface to kernel internals—it's not a real filesystem on disk, but a runtime view of kernel memory, processes, hardware, and configuration.

Why does this matter? When you're diagnosing why a service won't start, you need to know the kernel version (some syscalls change), the architecture (32-bit vs 64-bit), available block devices (is `/dev/sda` really there?), and recent kernel messages (did a driver fail?). These tools give you that data without rebooting or installing extra packages.

## Key Commands / Configuration / Code

### `uname` — Kernel and architecture identity

```bash
# Print all system information
uname -a
# Linux server01 5.15.0-91-generic #101-Ubuntu SMP Tue Nov 14 13:30:08 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux

# Kernel release only (useful for scripting)
uname -r
# 5.15.0-91-generic

# Machine hardware name (architecture)
uname -m
# x86_64

# Check if a 32-bit kernel on 64-bit hardware
uname -m && uname -i
# x86_64
# x86_64   # hardware platform (may differ on some systems)
```

**Real-world use**: Before deploying a kernel module or Docker image, check `uname -m` to confirm architecture. `uname -r` tells you which kernel headers to install for DKMS builds.

### `dmesg` — Kernel ring buffer (boot messages and driver logs)

```bash
# View all kernel messages (requires root for full output)
sudo dmesg | less

# Show only errors and warnings
sudo dmesg --level=err,warn

# Follow new messages in real-time (like tail -f)
sudo dmesg -w

# Human-readable timestamps
sudo dmesg -T

# Search for disk-related messages
sudo dmesg | grep -i 'sd[a-z]'
# [    1.234567] sd 0:0:0:0: [sda] 20971520 512-byte logical blocks: (10.7 GB/10.0 GiB)
```

**Real-world use**: When a USB drive doesn't mount, run `sudo dmesg -w` and plug it in. You'll see the kernel detect the device, load the driver, or report an error immediately.

### `lsblk` — List block devices (disks, partitions, LVM)

```bash
# Default tree view
lsblk
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
# sda      8:0    0   10G  0 disk
# ├─sda1   8:1    0    1G  0 part /boot
# └─sda2   8:2    0    9G  0 part /
# sdb      8:16   0   20G  0 disk
# └─sdb1   8:17   0   20G  0 part /data

# Show filesystem type and UUID
lsblk -f
# NAME   FSTYPE LABEL UUID                                 MOUNTPOINT
# sda
# ├─sda1 ext4          a1b2c3d4-...                       /boot
# └─sda2 ext4          e5f6g7h8-...                       /

# Show only disk size and model (no partitions)
lsblk -d -o NAME,SIZE,MODEL
# NAME SIZE MODEL
# sda   10G VBOX HARDDISK
# sdb   20G VBOX HARDDISK
```

**Real-world use**: Before resizing a partition, use `lsblk -f` to confirm the filesystem type and UUID. For scripting, `lsblk -n -o NAME` gives clean output without headers.

### `/proc` — The kernel's runtime filesystem

```bash
# CPU info (model, cores, flags)
cat /proc/cpuinfo | grep -E "model name|cpu cores|flags" | head -5

# Memory info (total, free, buffers)
cat /proc/meminfo | grep -E "^(MemTotal|MemFree|Buffers):"

# Uptime (seconds since boot)
cat /proc/uptime
# 123456.78 987654.32   # first = uptime, second = idle time

# Kernel command-line parameters (how the system booted)
cat /proc/cmdline
# BOOT_IMAGE=/vmlinuz-5.15.0-91-generic root=/dev/sda2 ro quiet splash

# Process-specific info (PID 1 = init/systemd)
cat /proc/1/comm
# systemd
```

**Real-world use**: To check if a CPU supports virtualization, `grep -o 'vmx\|svm' /proc/cpuinfo`. To see if swap is enabled, `grep SwapTotal /proc/meminfo`.

## Common Pitfalls & Gotchas

1. **`dmesg` requires root for full output** — On modern systems with `kernel.dmesg_restrict=1`, non-root users see only their own process messages. Always `sudo dmesg` when debugging hardware issues.

2. **`/proc` values are not always human-friendly** — `meminfo` reports in kilobytes, not bytes or megabytes. `uptime` is in seconds, not HH:MM:SS. Always check units before using in scripts.

3. **`lsblk` may not show LVM logical volumes without `-a`** — By default, `lsblk` hides empty RAM disks and some device-mapper entries. Use `lsblk -a` to see everything, including loop devices and LVM LVs.

## Try It Yourself

1. **Identify your boot device**: Run `lsblk -o NAME,SIZE,TYPE,MOUNTPOINT` and find which disk has `/` mounted. Then check `cat /proc/cmdline` to see the kernel's root parameter. Do they match?

2. **Detect a recent hardware event**: Plug in a USB drive, then immediately run `sudo dmesg -T | tail -20`. Note the timestamp and the driver messages. Unplug it and check again.

3. **Script a system summary**: Write a one-liner that outputs: kernel version, total RAM in GB, number of CPU cores, and uptime in days. Hint: use `uname -r`, `grep MemTotal /proc/meminfo`, `grep -c processor /proc/cpuinfo`, and `awk '{print int($1/86400) " days"}' /proc/uptime`.

## Next Up

Tomorrow we dive into **Permissions Deep Dive: SUID, SGID, Sticky Bit** — the special permission bits that can make or break your security model. We'll cover how `chmod` handles numeric and symbolic modes for these bits, real-world examples like `/usr/bin/passwd` and `/tmp`, and why `chmod 4777` is almost always a mistake.
