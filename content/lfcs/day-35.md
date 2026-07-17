---
title: "Day 35: LVM: PVs, VGs, LVs & Snapshots"
date: 2026-07-17
tags: ["til", "lfcs", "lvm", "storage"]
---

## What I Explored Today

Today I dove deep into Logical Volume Manager (LVM) — the standard for flexible storage management on Linux. I worked through the full lifecycle: initializing physical volumes (PVs), aggregating them into volume groups (VGs), carving out logical volumes (LVs), and then testing snapshot-based recovery. LVM is one of those tools that, once you understand the abstraction layers, changes how you think about disk management entirely.

## The Core Concept

LVM solves a fundamental problem: traditional partitions are rigid. Once you create a partition, resizing it means repartitioning the disk, which often requires downtime and data migration. LVM inserts an abstraction layer between the physical disk and the filesystem, allowing you to resize, move, and snapshot volumes without touching the underlying hardware.

The hierarchy is simple:
- **Physical Volume (PV)** — a disk or partition initialized for LVM (e.g., `/dev/sdb1`).
- **Volume Group (VG)** — a pool of storage created from one or more PVs.
- **Logical Volume (LV)** — a virtual block device carved from a VG, formatted with a filesystem, and mounted.

The real power comes from the fact that you can add PVs to a VG to expand the pool, then extend an LV (and its filesystem) online. Snapshots let you capture an LV's state at a point in time — invaluable for backups or testing risky operations.

## Key Commands / Configuration / Code

I used a 10GB virtual disk (`/dev/sdb`) for this exercise. Here's the exact workflow:

```bash
# Step 1: Create partitions (optional but recommended for clarity)
sudo fdisk /dev/sdb
# Created two 5GB partitions: /dev/sdb1, /dev/sdb2

# Step 2: Initialize Physical Volumes
sudo pvcreate /dev/sdb1 /dev/sdb2
# Output: Physical volume "/dev/sdb1" successfully created.

# Step 3: Create Volume Group
sudo vgcreate myvg /dev/sdb1 /dev/sdb2
# Output: Volume group "myvg" successfully created

# Step 4: Verify VG status
sudo vgdisplay myvg
# Shows: VG Size 9.99 GiB, PE Size 4.00 MiB, Total PE 2559

# Step 5: Create a Logical Volume (4GB)
sudo lvcreate -L 4G -n mylv myvg
# Output: Logical volume "mylv" created.

# Step 6: Format and mount
sudo mkfs.ext4 /dev/myvg/mylv
sudo mkdir /mnt/lvm_test
sudo mount /dev/myvg/mylv /mnt/lvm_test

# Step 7: Create a snapshot (for backup/testing)
# First, create some test data
sudo dd if=/dev/urandom of=/mnt/lvm_test/testfile bs=1M count=100

# Create snapshot LV (500MB thin provisioned)
sudo lvcreate -L 500M -s -n mylv_snap /dev/myvg/mylv
# Output: Logical volume "mylv_snap" created.

# Step 8: Simulate data corruption, then restore from snapshot
sudo rm /mnt/lvm_test/testfile
sudo umount /mnt/lvm_test

# Merge snapshot back to original LV
sudo lvconvert --merge /dev/myvg/mylv_snap
# Output: Merging of snapshot mylv_snap will start on next activation.

# Reactivate the LV to trigger merge
sudo lvchange -an /dev/myvg/mylv   # deactivate
sudo lvchange -ay /dev/myvg/mylv   # reactivate (merge happens here)

# Mount and verify the file is back
sudo mount /dev/myvg/mylv /mnt/lvm_test
ls -la /mnt/lvm_test/testfile
# File is restored!
```

**Key commands at a glance:**

| Command | Purpose |
|---------|---------|
| `pvcreate` | Initialize a disk/partition as PV |
| `vgcreate` | Create VG from one or more PVs |
| `lvcreate -L` | Create LV with fixed size |
| `lvcreate -s` | Create a snapshot of an LV |
| `lvconvert --merge` | Merge snapshot back to origin |
| `pvs`, `vgs`, `lvs` | Quick status views |

## Common Pitfalls & Gotchas

1. **Snapshot space exhaustion** — Snapshots are not free. If you allocate a 500MB snapshot and the original LV changes by more than 500MB, the snapshot becomes invalid (`COW` — copy-on-write — space runs out). Always monitor snapshot usage with `lvs -o+snap_percent`. For production, use thin provisioning pools to avoid this.

2. **Forgetting to extend the filesystem after LV extend** — `lvextend -L +1G /dev/myvg/mylv` grows the LV, but the filesystem doesn't know about it. You must run `resize2fs /dev/myvg/mylv` (for ext4) or `xfs_growfs /mountpoint` (for XFS) afterward. I've seen engineers panic when `df -h` shows no change.

3. **Snapshot merge requires deactivation** — The `--merge` operation doesn't happen immediately. It schedules the merge for the next time the LV is deactivated and reactivated. If the LV is your root filesystem, you'll need to reboot or use a live environment. For non-root LVs, always `umount`, `lvchange -an`, then `lvchange -ay`.

## Try It Yourself

1. **Create a RAID-0 style VG** — Use two 2GB disks (or partitions) to create a VG, then create a 3GB LV. Notice that LVM stripes data across both PVs by default (linear mapping). Verify with `lvdisplay -m`.

2. **Online resize experiment** — Create a 1GB LV, format with ext4, mount it, and write a large file. While the filesystem is mounted, extend the LV to 2GB, then resize the filesystem. Confirm the new space is visible with `df -h` without unmounting.

3. **Snapshot rollback drill** — Create a 2GB LV with a 500MB snapshot. Write 300MB of data, delete it, then merge the snapshot. Time the process. Then try writing 600MB of new data after the snapshot — watch the snapshot fill up and become invalid. This teaches you the COW limit the hard way.

## Next Up

Tomorrow I'm tackling swap management (swap files vs. swap partitions, tuning swappiness), RAID basics (software RAID with `mdadm` — levels 0, 1, 5, 10), and NFS client mounts (autofs, `fstab` options, troubleshooting). Storage is the backbone of every Linux system — getting these right separates a sysadmin from an engineer.
