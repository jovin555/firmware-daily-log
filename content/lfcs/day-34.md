---
title: "Day 34: Mounting: mount, umount & /etc/fstab"
date: 2026-07-16
tags: ["til", "lfcs", "mount", "fstab"]
---

## What I Explored Today

Today I dug into the Linux mount system — the bridge between raw block devices and the filesystem tree. While `mount` and `umount` are commands I use daily, I realized I had gaps in understanding the kernel's mount model, the role of `/etc/fstab`, and how systemd integrates with traditional mount units. I spent time tracing through the kernel's VFS layer, testing bind mounts, and hardening my fstab entries for production systems. The goal was to move beyond "it works" to "I know exactly what the kernel is doing."

## The Core Concept

Mounting is the act of attaching a filesystem (ext4, XFS, tmpfs, etc.) to a specific directory in the global VFS tree. The kernel's Virtual File System (VFS) abstraction allows multiple filesystem drivers to coexist — each block device or pseudo-filesystem registers with VFS and the mount syscall tells VFS which driver to use and where to attach it.

The critical insight: **the mount point directory becomes the root of that filesystem's tree**. Any files previously in that directory become hidden until the filesystem is unmounted. This is why you never mount on a non-empty directory without understanding the consequences.

`/etc/fstab` is not a configuration file that the kernel reads directly — it's a lookup table used by `mount -a` (and systemd) at boot. Each entry defines a mapping from a source (device, UUID, label, or remote path) to a target directory, with filesystem type, mount options, dump frequency, and fsck pass order. Systemd translates these into `.mount` units, but the kernel still receives the same mount syscall.

## Key Commands / Configuration / Code

### Basic mount and umount

```bash
# Mount a device by device node
mount /dev/sdb1 /mnt/data

# Mount by UUID (preferred for scripts — survives device reordering)
mount UUID="a1b2c3d4-..." /mnt/data

# Mount with explicit filesystem type and options
mount -t ext4 -o noatime,nodiratime,errors=remount-ro /dev/sdb1 /mnt/data

# Bind mount — make a directory tree accessible at another point
mount --bind /var/log /mnt/backup/logs

# Remount with different options (no need to unmount first)
mount -o remount,ro /mnt/data

# Unmount — fails if filesystem is busy
umount /mnt/data

# Force unmount (use sparingly — can corrupt data)
umount -f /mnt/data

# Lazy unmount — detach immediately, clean up when no longer busy
umount -l /mnt/data
```

### /etc/fstab entry anatomy

```
# <file system>  <mount point>  <type>  <options>  <dump>  <pass>
UUID=a1b2c3d4    /mnt/data      ext4    defaults,noatime  0       2
/dev/sdc1        /var/log       xfs     defaults          0       2
tmpfs            /tmp           tmpfs   defaults,size=2G  0       0
```

- **dump** (field 5): 0 = don't backup, 1 = backup (rarely used today)
- **pass** (field 6): 0 = don't fsck, 1 = fsck first (root), 2 = fsck after root

### Checking mounted filesystems

```bash
# List all mounted filesystems
mount

# Show only specific filesystem type
mount -t ext4

# Kernel's view of mount table
cat /proc/mounts

# Human-readable with filesystem usage
df -hT

# Find what's using a mount point (before unmount fails)
lsof /mnt/data
fuser -v /mnt/data
```

### Systemd mount unit equivalent

```ini
# /etc/systemd/system/mnt-data.mount
[Unit]
Description=Data partition

[Mount]
What=/dev/disk/by-uuid/a1b2c3d4-...
Where=/mnt/data
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
```

## Common Pitfalls & Gotchas

1. **Mounting on a non-empty directory hides existing files.** Always check `ls -la /mountpoint` before mounting. If you accidentally mount over important data, unmount immediately — the files are still there, just hidden. Never write to the mount point while the filesystem is mounted.

2. **UUID vs device node in fstab.** Using `/dev/sdb1` in fstab is fragile — device names change across reboots (kernel assigns based on detection order). Always use `blkid` to get the UUID or PARTUUID. For swap, use the swap UUID. For LVM, use `/dev/mapper/vgname-lvname`.

3. **The `nofail` option in fstab.** If a filesystem in fstab fails to mount at boot (e.g., external USB not connected), the boot process will drop into emergency mode. Add `nofail` to the options field for non-critical mounts: `defaults,nofail,x-systemd.device-timeout=10`. This tells systemd to continue booting even if the mount fails.

4. **Unmount fails with "target is busy".** This means a process has an open file descriptor on that filesystem. Use `lsof` or `fuser` to find the culprit. Common offenders: shell sessions with `cd` into the mount point, database processes, or log writers. The lazy unmount (`umount -l`) is a workaround but can cause data loss if processes continue writing.

## Try It Yourself

1. **Create a test filesystem and mount it manually.** Use `dd` to create a 1GB file, format it with `mkfs.ext4`, then mount it via loopback (`mount -o loop`). Verify with `df -hT` and `mount`. Unmount and clean up.

2. **Add a permanent mount to /etc/fstab.** Use `blkid` to get the UUID of a spare partition or USB drive. Add an entry with `noatime` and `nofail` options. Run `mount -a` to test without rebooting. Verify with `findmnt --verify`.

3. **Debug a busy mount point.** Mount a filesystem, `cd` into it in another terminal, then try to unmount. Use `lsof` and `fuser` to identify the blocking process. Practice using `umount -l` and understand when it's safe versus dangerous.

## Next Up

Tomorrow: **LVM: PVs, VGs, LVs & Snapshots** — we'll move from raw partitions to logical volume management, covering physical volume creation, volume group management, logical volume resizing, and how to take instant snapshots for backups without downtime.
