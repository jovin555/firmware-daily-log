---
title: "Day 36: Swap, RAID Basics & NFS Client Mounts"
date: 2026-07-18
tags: ["til", "lfcs", "swap", "raid", "nfs"]
---

## What I Explored Today

Today I tackled three storage management topics that every Linux engineer must own: swap space management, software RAID fundamentals, and NFS client-side mounting. While these seem like separate concerns, they share a common thread—reliable, performant storage under pressure. I walked through creating and resizing swap files, assembling a RAID 1 array with `mdadm`, and mounting an NFS export from a remote server. Each required careful attention to state persistence across reboots.

## The Core Concept

Swap is your system's safety net when physical RAM runs out. Without it, the OOM killer starts terminating processes arbitrarily. But swap isn't a performance crutch—it's a last resort. On a server, you typically want swap to be roughly equal to RAM for hibernation support, or 1-2 GB for crash dump capture. Modern systems often use swap *files* instead of partitions because they're resizable without repartitioning.

RAID (Redundant Array of Independent Disks) is about trading capacity or performance for reliability. RAID 1 (mirroring) writes identical data to two disks—you lose half your raw capacity but gain full redundancy. RAID 0 (striping) gives you speed but zero fault tolerance. For the LFCS, you need to know how to create, assemble, and monitor software RAID arrays using `mdadm`.

NFS (Network File System) lets you mount a remote directory as if it were local. The client-side setup is straightforward—`mount -t nfs` with the right options—but the gotchas are in the details: NFS versions, mount options like `hard` vs `soft`, and proper fstab entries for persistence.

## Key Commands / Configuration / Code

### Swap File Management

```bash
# Create a 2 GB swap file
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
# Set secure permissions (root only)
sudo chmod 600 /swapfile
# Format as swap
sudo mkswap /swapfile
# Enable it immediately
sudo swapon /swapfile
# Verify it's active
swapon --show
# Make permanent in /etc/fstab
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Software RAID 1 with mdadm

```bash
# Install mdadm if missing
sudo apt install mdadm -y   # Debian/Ubuntu
# Create a RAID 1 array from two partitions (sdb1, sdc1)
sudo mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/sdb1 /dev/sdc1
# Wait for resync, then create filesystem
sudo mkfs.ext4 /dev/md0
# Mount it
sudo mkdir /mnt/raid1
sudo mount /dev/md0 /mnt/raid1
# Save the array config so it reassembles on boot
sudo mdadm --detail --scan | sudo tee -a /etc/mdadm/mdadm.conf
# Update initramfs
sudo update-initramfs -u
```

### NFS Client Mount

```bash
# Install NFS client
sudo apt install nfs-common -y   # Debian/Ubuntu
# Mount an NFS share (server: 192.168.1.100, export: /srv/nfs_share)
sudo mount -t nfs -o rw,hard,intr,timeo=600 192.168.1.100:/srv/nfs_share /mnt/nfs
# Verify with mount and df
mount | grep nfs
df -h /mnt/nfs
# Persistent mount in /etc/fstab
echo '192.168.1.100:/srv/nfs_share /mnt/nfs nfs rw,hard,intr,timeo=600 0 0' | sudo tee -a /etc/fstab
```

## Common Pitfalls & Gotchas

1. **Swap file permissions**: If you forget `chmod 600 /swapfile`, `swapon` will refuse with a "insecure permissions" warning. The kernel requires swap files to be readable only by root—otherwise any user could read memory pages that were swapped out.

2. **RAID array not reassembling after reboot**: This is the #1 LFCS exam trap. You must run `mdadm --detail --scan` and append the output to `/etc/mdadm/mdadm.conf`, then update initramfs. Without this, the array won't auto-assemble and you'll see degraded or missing devices.

3. **NFS hard mount hangs**: Using `hard` mount option (default) means processes will hang indefinitely if the NFS server goes down. This is usually what you want for critical data (no silent corruption), but it can lock up your system. Always pair with `intr` (interruptible) or use `soft` for non-critical mounts. Also, never forget `timeo=600`—the default 0.7-second timeout is absurdly short for real networks.

## Try It Yourself

1. **Create a 512 MB swap file** on a test VM, enable it, then verify with `swapon --show`. Remove it with `swapoff /swapfile` and delete the file. Do not modify your production swap without understanding the implications.

2. **Build a RAID 1 array** using two loopback devices (or spare partitions). Create an ext4 filesystem, mount it, write a test file, then simulate a disk failure with `mdadm --fail /dev/md0 /dev/sdb1`. Observe the array state with `cat /proc/mdstat` and `mdadm --detail /dev/md0`. Remove the failed device and re-add it.

3. **Mount an NFS share** from a colleague's machine or a lab server. Use `showmount -e <server_ip>` to list available exports. Mount it with `hard,intr` options, then test what happens when you stop the NFS server (`sudo systemctl stop nfs-server` on the server side). Time how long the client hangs before timeout.

## Next Up

Tomorrow we shift from storage to networking fundamentals: **Network Interfaces: ip, ifconfig & Link Management**. We'll cover the modern `ip` command suite, legacy `ifconfig`, link state management, and how to configure persistent interface settings without NetworkManager.
