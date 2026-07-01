---
title: "Day 19: Embedded Filesystems: JFFS2, UBIFS, SquashFS"
date: 2026-07-01
tags: ["til", "embedded-linux", "filesystem", "ubifs"]
---

## What I Explored Today

Today I dug into the three filesystems that dominate embedded Linux storage: JFFS2, UBIFS, and SquashFS. While a desktop user reaches for ext4 or XFS, embedded systems have radically different constraints—NOR/NAND flash with erase blocks, limited RAM, and the need for atomic updates. I spent the day building root filesystems with each, measuring their behavior on a 256MB NAND flash part, and understanding when to reach for which one.

## The Core Concept

Flash memory is not a hard drive. You can't overwrite a single byte—you must erase an entire block (typically 128KB for NAND) before writing. This "erase-before-write" constraint breaks traditional filesystem assumptions. JFFS2, UBIFS, and SquashFS each solve this differently:

- **JFFS2 (Journaling Flash File System v2)**: The old guard. It logs every change to a circular buffer on flash, then garbage-collects stale blocks. Works on raw NOR/NAND but has terrible mount times—it must scan the entire flash to rebuild the file tree. For a 256MB partition, expect 30+ seconds.
- **UBIFS (UBI File System)**: The modern replacement. It sits on top of UBI (Unsorted Block Images), which handles wear leveling and bad block management. UBIFS uses a tree structure (B-tree) for metadata, so mount is near-instant. It also supports write-back caching and compression (LZO, zlib).
- **SquashFS**: A read-only, compressed filesystem. You build it once on your host, then flash it. No writes allowed at runtime. Perfect for the rootfs partition where you never modify binaries. It compresses aggressively—a 100MB rootfs often fits in 40MB.

The key insight: **choose based on write patterns**. Read-only rootfs? SquashFS. Read-write data partition on NAND? UBIFS. Legacy system with ancient kernel? JFFS2.

## Key Commands / Configuration / Code

### Building a SquashFS rootfs
```bash
# Create a compressed, read-only filesystem from a directory
# -comp xz gives best compression, -b 128K matches flash erase block
mksquashfs /path/to/rootfs rootfs.squashfs \
    -comp xz \
    -b 128K \
    -noappend \
    -all-root

# Check the result
unsquashfs -s rootfs.squashfs
# Output: "Compression: xz", "Block size: 131072"
```

### Creating a UBIFS image for NAND
```bash
# Step 1: Create UBIFS image from directory
# -m 2048: minimum I/O size (page size for NAND)
# -e 126976: logical erase block size (128KB minus 1KB UBI header)
# -c 2047: maximum number of LEBs (partition size / erase block)
mkfs.ubifs -r /path/to/rootfs \
    -m 2048 \
    -e 126976 \
    -c 2047 \
    -o rootfs.ubi

# Step 2: Attach UBI volume to the NAND partition
# This is done in the kernel bootargs or init script
ubiattach -m 4  # Attach MTD partition 4 as UBI device
ubimkvol /dev/ubi0 -N rootfs -s 256MiB  # Create volume

# Mount it
mount -t ubifs ubi0:rootfs /mnt/rootfs
```

### Kernel configuration for all three
```c
// In your kernel .config (make menuconfig -> File systems -> Miscellaneous filesystems)
CONFIG_JFFS2_FS=y
CONFIG_JFFS2_COMPRESSION_OPTIONS=y
CONFIG_JFFS2_LZO=y

CONFIG_UBIFS_FS=y
CONFIG_UBIFS_FS_LZO=y
CONFIG_UBIFS_FS_ZLIB=y

CONFIG_SQUASHFS=y
CONFIG_SQUASHFS_XZ=y
CONFIG_SQUASHFS_LZO=y
```

### Bootargs comparison
```
# JFFS2 (slow mount, no UBI layer)
root=/dev/mtdblock4 rootfstype=jffs2

# UBIFS (fast mount, requires UBI)
ubi.mtd=4 root=ubi0:rootfs rootfstype=ubifs

# SquashFS (read-only, often combined with overlay)
root=/dev/mtdblock4 rootfstype=squashfs
```

## Common Pitfalls & Gotchas

1. **JFFS2 mount time scales linearly with partition size.** I once waited 90 seconds for a 512MB JFFS2 partition to mount on a 400MHz ARM9. The kernel must scan every node. UBIFS mounts in under a second regardless of size. If you're stuck on an old kernel without UBIFS support, keep JFFS2 partitions under 64MB.

2. **UBIFS needs the correct LEB size calculation.** If you pass `-e 126976` but your NAND has 128KB erase blocks, you'll get corruption. The formula: `LEB_size = erase_block_size - (2 * page_size)` for NAND with sub-page writes. For NOR, it's just `erase_block_size - 64`. Always check `mtdinfo /dev/mtdX` before building.

3. **SquashFS + overlayfs requires careful tmpfs sizing.** The common pattern is SquashFS rootfs with an overlay on tmpfs for writable `/etc` and `/var`. If you don't allocate enough tmpfs space (default is 50% of RAM), your system will mysteriously fail when logs fill up. Set `tmpfs-size=32M` in your init script.

## Try It Yourself

1. **Compare mount times**: Create a 64MB JFFS2 image and a 64MB UBIFS image from the same directory. Flash both to separate MTD partitions and time `mount` with `time mount -t jffs2 ...` vs `time mount -t ubifs ...`. Note the difference.

2. **Build a SquashFS+overlay rootfs**: Create a minimal rootfs directory, squash it, then write a boot script that mounts the squashfs read-only, creates a tmpfs for `/overlay`, and uses `mount -t overlay overlay -o lowerdir=/mnt/root,upperdir=/overlay/upper,workdir=/overlay/work /mnt/merged`. Test that you can modify `/etc/hostname` and it persists until reboot.

3. **Recover a corrupted UBIFS**: Force a power loss while writing to a UBIFS partition, then remount. Run `ubinfo -a /dev/ubi0` to check for corruption. Try `ubifsck /dev/ubi0_0` (if available) or `echo 1 > /sys/kernel/debug/ubifs/ubi0_0/recover` to trigger recovery.

## Next Up: Sysfs & Debugfs: Kernel-Userspace Interface

Tomorrow I'll explore how sysfs and debugfs expose kernel internals to userspace—the filesystems that let you control GPIOs, inspect driver state, and debug hardware without writing a single kernel module. We'll build a custom sysfs attribute and use debugfs to dump a driver's internal buffer.
