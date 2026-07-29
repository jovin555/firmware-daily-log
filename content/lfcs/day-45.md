---
title: "Day 45: Full Mock Exam \u2014 All Domains"
date: 2026-07-29
tags: ["til", "lfcs", "mock-exam", "review", "exam-prep"]
---

## What I Explored Today

After 44 days of drilling into file permissions, process management, storage configuration, networking, and systemd, today I sat for a full mock exam covering all LFCS domains. The goal wasn't to memorize answers but to simulate the pressure of a real exam environment: 2 hours, 20 performance-based tasks, no internet, and no looking back. I used a fresh CentOS 9 VM snapshot for each run. The results were humbling — I discovered gaps in SELinux context restoration, logical volume resizing on the fly, and systemd unit dependency ordering. This post captures the exact scenarios I faced and the commands that saved me.

## The Core Concept

The LFCS exam is not a trivia test. It tests whether you can fix a broken system under time constraints. Every task is rooted in a real-world failure: a disk that won't mount, a service that won't start, a user who can't write to their home directory. The "why" behind the exam design is simple — Linux systems engineers spend more time debugging than configuring. The mock exam forces you to practice recovery workflows, not just command syntax. For example, knowing `lvresize -L +5G` is useless if you don't first check `pvdisplay` for free extents. The mock exam trains your diagnostic chain: identify the symptom, trace the root cause, apply the fix, verify.

## Key Commands / Configuration / Code

Below are the exact commands I used during the mock exam, with inline comments explaining the context.

### 1. Fix a misconfigured logical volume that won't mount

```bash
# Symptom: /dev/vg_data/lv_app fails to mount with "wrong fs type"
# Step 1: Check the actual filesystem signature
blkid /dev/vg_data/lv_app
# Output: /dev/vg_data/lv_app: UUID="..." TYPE="xfs"

# Step 2: /etc/fstab had ext4 — fix it
# Before: UUID=... /app ext4 defaults 0 0
# After:
echo "UUID=$(blkid -s UUID -o value /dev/vg_data/lv_app) /app xfs defaults 0 0" >> /etc/fstab

# Step 3: Test the mount
mount -a && mount | grep /app
```

### 2. Restore SELinux context on a web directory

```bash
# Symptom: Apache returns 403 Forbidden, audit.log shows AVC denials
# Step 1: Check current context
ls -Z /var/www/html/index.html
# Output: unconfined_u:object_r:user_home_t:s0 (wrong!)

# Step 2: Restore default context for web content
restorecon -Rv /var/www/html/

# Step 3: Verify
ls -Z /var/www/html/index.html
# Output: system_u:object_r:httpd_sys_content_t:s0 (correct)

# Step 4: Reload Apache and test
systemctl reload httpd && curl -I http://localhost
```

### 3. Create a systemd timer that runs a script every 5 minutes

```bash
# Script: /usr/local/bin/check_disk.sh
# Timer unit: /etc/systemd/system/check-disk.timer
cat > /etc/systemd/system/check-disk.timer << 'EOF'
[Unit]
Description=Run disk check every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Service unit: /etc/systemd/system/check-disk.service
cat > /etc/systemd/system/check-disk.service << 'EOF'
[Unit]
Description=Disk check service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/check_disk.sh
EOF

# Enable and start
systemctl daemon-reload
systemctl enable --now check-disk.timer
systemctl list-timers --all | grep check-disk
```

### 4. Extend a root filesystem online (XFS)

```bash
# Scenario: /dev/mapper/rl-root is at 95% usage, need +10G
# Step 1: Check volume group for free space
vgdisplay rl | grep Free
# Output: Free PE / Size 2560 / 10.00 GiB

# Step 2: Extend logical volume (no unmount needed for XFS)
lvextend -L +10G /dev/mapper/rl-root

# Step 3: Grow the filesystem (xfs_growfs, not resize2fs)
xfs_growfs /

# Step 4: Verify
df -h /
```

### 5. Diagnose a service that fails to start due to dependency

```bash
# Symptom: systemctl start myapp.service fails silently
# Step 1: Check status for dependency errors
systemctl status myapp.service
# Output: dependency failed for myapp.service

# Step 2: List all dependencies
systemctl list-dependencies myapp.service

# Step 3: Found missing mount unit — /etc/fstab had a stale NFS entry
# Fix: comment out the bad entry in /etc/fstab, then
systemctl daemon-reload
systemctl start myapp.service
```

## Common Pitfalls & Gotchas

1. **Forgetting to run `partprobe` after partitioning** — If you create a partition with `fdisk` and immediately try to use it, the kernel may not see the new partition table. Always run `partprobe /dev/sdX` or `udevadm settle` before proceeding. I lost 10 minutes on this during the mock exam.

2. **Using `resize2fs` on XFS filesystems** — XFS uses `xfs_growfs` for online expansion, not `resize2fs`. Running `resize2fs` on an XFS volume will fail silently or corrupt metadata. Always check `blkid` for the filesystem type before resizing.

3. **Misunderstanding `systemctl enable` vs `systemctl start`** — `enable` creates symlinks for automatic boot, `start` launches the service now. Many candidates enable a timer but forget to start it, then wonder why it doesn't fire. Use `systemctl enable --now` to do both.

## Try It Yourself

1. **SELinux context recovery**: Create a file in `/var/www/html/` with a wrong context (e.g., `chcon -t user_home_t /var/www/html/test.html`), then use `restorecon` to fix it. Verify with `ls -Z` and test with `curl`.

2. **Logical volume resize under pressure**: On a test VM, fill a logical volume to 90% capacity, then add a new disk, create a physical volume, extend the volume group, and grow the filesystem online — all without unmounting.

3. **Systemd timer debugging**: Write a timer that runs every minute, but intentionally misconfigure the `OnCalendar` syntax (e.g., `*:0/0`). Use `systemctl list-timers` and `journalctl -u my-timer.timer` to find the error, then fix it.

## Next Up

Tomorrow is the final review — Day 46: Full Review. I’ll consolidate every domain into a single cheat sheet, highlight the most missed commands from today’s mock exam, and share my last-minute exam strategy. If you’re taking the LFCS soon, you won’t want to miss it.
