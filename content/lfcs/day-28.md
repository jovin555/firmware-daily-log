---
title: "Day 28: Kernel Modules: lsmod, modprobe, insmod"
date: 2026-07-10
tags: ["til", "lfcs", "kernel", "modules"]
---

## What I Explored Today

Today I dove into the Linux kernel's modular architecture—specifically how to inspect, load, and unload kernel modules at runtime. The kernel isn't a monolithic blob; it's a collection of loadable modules that extend functionality without rebooting. I focused on three essential tools: `lsmod` for listing loaded modules, `modprobe` for intelligent module loading with dependency resolution, and `insmod` for raw insertion of a single module file. Understanding these commands is critical for diagnosing hardware issues, enabling filesystem support, or adding network protocols without a kernel rebuild.

## The Core Concept

Kernel modules are pieces of code that can be loaded into the running kernel to add support for hardware drivers, filesystems, system calls, or network protocols. The kernel's module loader handles symbol resolution, dependency ordering, and memory allocation for these extensions.

Why does this matter? In production, you rarely rebuild the kernel. You need to add a driver for a new NIC, enable an encryption module, or load a filesystem module for a mounted USB drive—all without downtime. The module system makes this possible. `lsmod` shows you what's currently loaded (and how many other modules depend on it). `modprobe` is the smart loader: it reads `/lib/modules/$(uname -r)/modules.dep` to resolve dependencies automatically. `insmod` is the low-level tool—it inserts a single `.ko` file and fails if any symbols are missing. You'll use `modprobe` 90% of the time; `insmod` is for debugging or custom modules.

## Key Commands / Configuration / Code

### 1. List loaded modules with `lsmod`

```bash
# Show all loaded modules, their size, and usage count
lsmod

# Example output:
# Module                  Size  Used by
# vfio_pci               57344  0
# vfio                   49152  1 vfio_pci
# nvidia_uvm           1236992  0
# ext4                  761856  1
```

The `Used by` column is critical: it shows how many other modules or processes depend on this module. A non-zero value means you can't unload it without first removing dependents.

### 2. Load a module with `modprobe`

```bash
# Load the module and all its dependencies
sudo modprobe vfio_pci

# Load with options (e.g., for a network driver)
sudo modprobe e1000e InterruptThrottleRate=1,1,1

# Remove a module and its unused dependencies
sudo modprobe -r vfio_pci
```

`modprobe` reads `/etc/modprobe.d/*.conf` for default options and blacklists. Always use `modprobe` for production—it handles dependency chains automatically.

### 3. Insert a single module with `insmod`

```bash
# Insert a .ko file directly (no dependency resolution)
sudo insmod /lib/modules/$(uname -r)/kernel/drivers/net/ethernet/intel/e1000e/e1000e.ko

# Check if it loaded
lsmod | grep e1000e
```

`insmod` will fail with `Unknown symbol` if dependencies aren't already loaded. Use `modprobe` unless you're testing a custom module you compiled yourself.

### 4. Module information with `modinfo`

```bash
# Show module metadata, parameters, and dependencies
modinfo e1000e

# Output excerpt:
# filename:       /lib/modules/.../e1000e.ko
# version:        3.8.7-NAPI
# license:        GPL v2
# description:    Intel(R) PRO/1000 Network Driver
# depends:        ptp, mii
# parm:           InterruptThrottleRate:...
```

Always check `depends` before loading—this tells you what `modprobe` will pull in automatically.

### 5. Persistent module loading

```bash
# Add module to load at boot
echo "vfio_pci" | sudo tee /etc/modules-load.d/vfio.conf

# Blacklist a module (prevent auto-load)
echo "blacklist nouveau" | sudo tee /etc/modprobe.d/blacklist-nvidia.conf
```

Place module load configs in `/etc/modules-load.d/` and blacklists in `/etc/modprobe.d/`. The initramfs may need regeneration if the module is needed early in boot.

## Common Pitfalls & Gotchas

1. **`modprobe` fails with "Module not found"** — This usually means the module isn't installed for your running kernel version. Check `uname -r` and verify the `.ko` file exists under `/lib/modules/$(uname -r)/`. If you just installed a new kernel, reboot first.

2. **Module won't unload (rmmod/modprobe -r fails)** — The `Used by` column in `lsmod` shows dependents. You must unload dependent modules first. Also, a process might hold a file descriptor on a device backed by the module. Use `lsof /dev/<device>` to find the culprit.

3. **`insmod` succeeds but module doesn't appear** — `insmod` doesn't resolve dependencies. If the module depends on symbols from another module that isn't loaded, the insertion might silently fail or the module may be in a "tainted" state. Always check `dmesg | tail` after insertion for error messages.

## Try It Yourself

1. **Inspect your current modules**: Run `lsmod` and identify a module with a non-zero `Used by` count. Trace the dependency chain: which modules depend on it, and what hardware or feature does it support? Use `modinfo` to confirm.

2. **Load a filesystem module**: If you have a USB drive with a filesystem not currently loaded (e.g., `exfat` or `ntfs`), try `sudo modprobe exfat` then mount the drive. Verify with `lsmod | grep exfat` and `dmesg | tail`.

3. **Blacklist a module**: Pick a module you don't need (e.g., `pcspkr` for the PC speaker), create a blacklist file in `/etc/modprobe.d/`, and verify it doesn't load after reboot. Use `modprobe -c | grep pcspkr` to confirm the blacklist is active.

## Next Up

Tomorrow, I'll tackle system performance monitoring with `top`, `vmstat`, `iostat`, and `sar`—the tools every engineer needs to identify CPU, memory, I/O, and process bottlenecks in real time.
