---
title: "Day 33: Filesystems: mkfs, fsck & Filesystem Types"
date: 2026-07-15
tags: ["til", "lfcs", "filesystems", "mkfs"]
---

## What I Explored Today

Today I dove into the filesystem layer that sits between raw block devices and the data we actually care about. I worked through creating filesystems with `mkfs`, checking and repairing them with `fsck`, and understanding why choosing the right filesystem type matters in production. This isn't just about running a command—it's about understanding the on-disk structures that make data retrieval reliable, even when power fails or a disk develops bad sectors.

## The Core Concept

A block device (like `/dev/sda1`) is just a linear array of sectors. Without a filesystem, it's a blank slate—no directories, no filenames, no permissions. The filesystem imposes a logical structure: it defines how blocks are grouped into inodes (metadata about files), how directories map names to inodes, and how free space is tracked.

The `mkfs` command (short for "make filesystem") writes this structure. It initializes the superblock (the filesystem's "master table"), allocates the inode table, and marks the rest as free. The `fsck` command ("filesystem check") reads these structures back, verifying consistency—checking that every inode is accounted for, every block is either allocated or free, and directory entries point to valid inodes.

Why does this matter? Without a valid filesystem, the kernel can't interpret the raw bytes on disk. A corrupted superblock means the entire filesystem is unreadable. A lost inode means a file vanishes. Understanding `mkfs` and `fsck` is how you prevent and recover from these failures.

## Key Commands / Configuration / Code

### Creating a Filesystem

The most common invocation is `mkfs.ext4` (or `mkfs -t ext4`). Always specify the filesystem type explicitly—never rely on auto-detection.

```bash
# Create an ext4 filesystem on /dev/sdb1 with 0.1% reserved blocks for root
sudo mkfs.ext4 -m 0.1 /dev/sdb1

# Create an XFS filesystem with a 4k block size (good for large files)
sudo mkfs.xfs -b size=4096 /dev/sdc1

# Create a Btrfs filesystem with a label (useful for mounting by label)
sudo mkfs.btrfs -L mydata /dev/sdd1

# List all available mkfs variants on your system
ls /sbin/mkfs.*
```

Key options for `mkfs.ext4`:
- `-m` : percentage of blocks reserved for root (default 5%, often too high for data drives)
- `-b` : block size (1024, 2048, 4096 bytes)
- `-i` : bytes per inode (controls max number of files)
- `-L` : volume label

### Checking and Repairing a Filesystem

Never run `fsck` on a mounted filesystem unless it's read-only. For root filesystems, you need to boot into recovery mode or use a live USB.

```bash
# Unmount first, then check
sudo umount /dev/sdb1
sudo fsck.ext4 -f /dev/sdb1

# Force check even if filesystem appears clean
sudo fsck -f /dev/sdc1

# Automatically repair without asking (use with caution)
sudo fsck -y /dev/sdb1

# Check but do not repair (read-only mode)
sudo fsck -n /dev/sdb1
```

The `-f` flag forces a full check even if the filesystem's "clean" bit is set. This is essential when you suspect corruption but the system hasn't flagged it.

### Filesystem Types in Practice

| Type | Max File Size | Max Volume Size | Journaling | Best For |
|------|---------------|-----------------|------------|----------|
| ext4 | 16 TB | 1 EB | Yes (default) | General-purpose Linux |
| XFS | 8 EB | 8 EB | Yes (metadata only) | Large files, high concurrency |
| Btrfs | 16 EB | 16 EB | Yes (copy-on-write) | Snapshots, checksums, RAID |
| ZFS | 16 EB | 256 ZB | Yes (copy-on-write) | Enterprise storage, data integrity |

## Common Pitfalls & Gotchas

### 1. Running `mkfs` on the Wrong Device

This is the fastest way to destroy data. `mkfs` does not ask for confirmation by default. Always double-check the device path:

```bash
# DANGEROUS: This wipes /dev/sda1 without warning
sudo mkfs.ext4 /dev/sda1

# SAFER: Verify with lsblk first
lsblk -f
sudo mkfs.ext4 /dev/sdb1
```

### 2. Forcing `fsck` on a Mounted Filesystem

The kernel caches writes. Running `fsck` on a mounted, writable filesystem can cause the kernel's in-memory state to diverge from what `fsck` writes, leading to catastrophic corruption. If you must check a mounted filesystem, mount it read-only:

```bash
sudo mount -o remount,ro /dev/sdb1
sudo fsck /dev/sdb1
sudo mount -o remount,rw /dev/sdb1
```

### 3. Ignoring the Reserved Blocks Percentage

The default `-m 5` reserves 5% of blocks for root. On a 1 TB drive, that's 50 GB of unusable space. For data-only partitions, set `-m 0.1` or even `-m 0`:

```bash
sudo mkfs.ext4 -m 0.1 /dev/sdb1
```

## Try It Yourself

1. **Create and inspect a filesystem**: Attach a spare disk or USB drive. Use `lsblk` to identify it, then create an ext4 filesystem with `-m 0.1 -L mytest`. Run `dumpe2fs -h /dev/sdX1` to inspect the superblock—look for block count, inode count, and reserved blocks.

2. **Simulate corruption and repair**: Create a small ext4 filesystem in a file (`dd if=/dev/zero of=test.img bs=1M count=100 && mkfs.ext4 test.img`). Use `debugfs` to corrupt the superblock (`debugfs -w test.img` then `set_super_value s_magic 0`). Run `fsck` and observe the recovery process.

3. **Compare filesystem creation times**: Time the creation of ext4, XFS, and Btrfs on a 1 GB file image. Use `time mkfs.ext4 test.img` and repeat for `mkfs.xfs` and `mkfs.btrfs`. Note the differences—XFS is often fastest for large volumes.

## Next Up

Tomorrow I'll cover how to actually use these filesystems: mounting with `mount`, unmounting with `umount`, and configuring persistent mounts in `/etc/fstab`. We'll look at mount options, bind mounts, and how to avoid the dreaded "mount: wrong fs type" error.
