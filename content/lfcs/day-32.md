---
title: "Day 32: Disk Partitioning: fdisk, gdisk"
date: 2026-07-14
tags: ["til", "lfcs", "partitions", "disks"]
---

## What I Explored Today

Today I dug into the two most essential partitioning tools on Linux: `fdisk` for MBR (Master Boot Record) and `gdisk` for GPT (GUID Partition Table). While both tools manipulate partition tables, the underlying data structures and modern requirements (like disks larger than 2TB or UEFI boot) make knowing when to use each critical. I walked through creating, deleting, resizing, and inspecting partitions on both a virtual disk and a spare SSD, paying close attention to sector alignment and partition type codes.

## The Core Concept

Partitioning is the act of dividing a physical disk into logical regions that the operating system treats as separate devices (e.g., `/dev/sda1`, `/dev/sda2`). The partition table—stored in the first few sectors of the disk—defines these regions. There are two dominant standards:

- **MBR (Master Boot Record)**: Legacy standard, limited to 4 primary partitions (or 3 primary + 1 extended containing logical partitions), and a maximum disk size of 2TB. Uses 4-byte partition type codes (e.g., `83` for Linux, `82` for swap).
- **GPT (GUID Partition Table)**: Modern standard, supports up to 128 partitions by default, disks larger than 2TB, and redundant partition table headers for robustness. Uses 16-byte GUID type codes (e.g., `0FC63DAF-8483-4772-8E79-3D69D8477DE4` for Linux filesystem).

The key insight: **never use MBR on a disk >2TB**—you will lose data. Conversely, some older BIOS systems cannot boot from GPT without a special "BIOS boot" partition. As an engineer, you must choose the right tool for the hardware and firmware.

`fdisk` handles MBR (and can read GPT but not write it). `gdisk` handles GPT exclusively. Both are interactive, but they also support scripted operations via `-c` or `<<EOF` for automation.

## Key Commands / Configuration / Code

### 1. Inspecting Existing Partitions

```bash
# List all disks and their partition tables
sudo fdisk -l

# Focus on a specific disk (MBR or GPT)
sudo fdisk -l /dev/sda

# For GPT-only inspection, gdisk -l is more detailed
sudo gdisk -l /dev/sda
```

### 2. Creating an MBR Partition Table with fdisk

```bash
sudo fdisk /dev/sdb

# Inside fdisk interactive mode:
# m    - help
# p    - print current partition table
# n    - new partition
#   Partition type: p (primary) or e (extended)
#   Partition number: 1
#   First sector: (press Enter for default, usually 2048)
#   Last sector: +10G  (creates a 10GB partition)
# t    - change partition type
#   83   - Linux filesystem
# w    - write changes and exit
```

**Scripted version (non-interactive):**

```bash
# Create a single 10GB primary partition on /dev/sdc
echo -e "n\np\n1\n\n+10G\nt\n83\nw" | sudo fdisk /dev/sdc
```

### 3. Creating a GPT Partition Table with gdisk

```bash
sudo gdisk /dev/sdd

# Inside gdisk interactive mode:
# ?    - help
# p    - print table
# o    - create new GPT table (wipes old table)
# n    - new partition
#   Partition number: 1
#   First sector: (Enter for default)
#   Last sector: +20G
#   Hex code: 8300  (Linux filesystem)
# w    - write changes and exit
```

**Scripted GPT creation:**

```bash
# Create a 20GB partition with Linux filesystem type
echo -e "o\nn\n1\n\n+20G\n8300\nw\nY" | sudo gdisk /dev/sdd
```

### 4. Deleting and Recreating

```bash
# Delete partition 2 from /dev/sda
sudo fdisk /dev/sda
# d    - delete
# 2    - partition number
# w    - write

# For GPT, same process with gdisk
sudo gdisk /dev/sda
# d    - delete
# 2    - partition number
# w    - write
```

### 5. Verifying Alignment (Critical for SSDs)

```bash
# Check that partition starts on a 4K-aligned boundary
sudo fdisk -l /dev/sda | grep "sda1"
# Look at "Start" sector — should be divisible by 8 (512-byte sectors)
# or 1 (4K-native sectors). Modern fdisk defaults to sector 2048, which is safe.

# For detailed alignment check
sudo blockdev --getalignoff /dev/sda1
# Output "0" means perfectly aligned
```

## Common Pitfalls & Gotchas

1. **Writing changes without verifying**: `fdisk` and `gdisk` buffer changes until you type `w`. If you exit with `q`, nothing is saved. But once you write, the old partition table is overwritten. **Always double-check with `p` before `w`.** I once wiped a production disk because I typed `w` instead of `q` after a dry-run inspection.

2. **Forgetting to re-read the partition table**: After partitioning, the kernel may not immediately see the new layout. Run `sudo partprobe` or `sudo blockdev --rereadpt /dev/sdX` to force a re-read. On some systems, you may need to reboot if the disk is in use.

3. **Using MBR on disks >2TB**: The MBR partition table uses 32-bit sector addresses, capping at 2^32 * 512 bytes = 2TB. If you create an MBR table on a 4TB disk, you'll only see 2TB. Always use `gdisk` for disks >2TB or if you need more than 4 primary partitions.

4. **Partition type codes matter for boot**: For UEFI boot, you need an EFI System Partition (type `EF00` in gdisk, or `1` in fdisk for MBR). For BIOS boot with GPT, you need a BIOS boot partition (type `EF02`). Using the wrong type code will prevent booting.

## Try It Yourself

1. **Create a GPT partition on a USB stick**: Plug in a spare USB drive (warning: data will be lost). Use `gdisk` to create a new GPT table, then add a single partition of 1GB with type `8300`. Verify with `gdisk -l`. Write the partition table, then run `partprobe` and check `/dev/sdX1` appears.

2. **Script a multi-partition layout**: Write a bash script that uses `echo` piped to `fdisk` to create three partitions on a virtual disk (`/dev/vdb`): 5GB Linux, 2GB swap (type `82`), and 10GB Linux. Verify the layout with `fdisk -l`.

3. **Check alignment on your root disk**: Run `sudo fdisk -l /dev/sda` and note the "Start" sector of each partition. Calculate if it's divisible by 8 (for 4K alignment). Then run `sudo blockdev --getalignoff /dev/sda1` and confirm the output is `0`.

## Next Up

Tomorrow I'll dive into **Filesystems: mkfs, fsck & Filesystem Types**—taking those raw partitions and turning them into usable filesystems with `ext4`, `XFS`, and `btrfs`, plus how to check and repair them when things go wrong.
