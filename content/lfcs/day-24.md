---
title: "Day 24: The Linux Boot Process: BIOS to GRUB to Kernel"
date: 2026-07-06
tags: ["til", "lfcs", "boot", "kernel"]
---

## What I Explored Today

Today I traced the Linux boot process from the moment the power button is pressed to the point where the kernel hands control to `init`. While most engineers interact with boot only when something breaks, understanding the handoff between firmware, bootloader, and kernel is essential for diagnosing boot failures, customizing kernel parameters, and building embedded systems. I walked through each stage with real configs and commands, focusing on what you can actually inspect on a running system.

## The Core Concept

The boot process is a chain of trust: each stage validates and loads the next. The firmware (BIOS or UEFI) knows nothing about filesystems or kernels—it only knows how to read a fixed block from a disk. The bootloader (GRUB) understands filesystems and can parse configuration files, but it doesn't manage hardware. The kernel initializes hardware and mounts the root filesystem, then hands off to userspace. Understanding this layering helps you reason about where failures occur: a "disk not found" error at GRUB is different from a kernel panic during root mount.

## Key Commands / Configuration / Code

### Inspecting the current boot path

```bash
# Check if system booted via BIOS (legacy) or UEFI
[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"

# View kernel command-line parameters passed by GRUB
cat /proc/cmdline
# Example output: BOOT_IMAGE=/vmlinuz-6.1.0-17-amd64 root=/dev/sda2 ro quiet

# See which kernel is currently running
uname -r
```

### GRUB configuration essentials

The primary GRUB config file is `/etc/default/grub`. After editing, regenerate the bootloader config with `update-grub` (Debian/Ubuntu) or `grub2-mkconfig -o /boot/grub2/grub.cfg` (RHEL).

```bash
# Typical /etc/default/grub
GRUB_DEFAULT=0              # Boot first entry by default
GRUB_TIMEOUT=5              # Seconds before automatic boot
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"  # Kernel parameters for all entries
GRUB_CMDLINE_LINUX=""       # Additional params for recovery mode

# Example: add 'nomodeset' to fix display issues on some GPUs
# Edit /etc/default/grub, then:
sudo update-grub
```

### Kernel boot parameters you'll actually use

```bash
# Common kernel parameters passed via GRUB_CMDLINE_LINUX_DEFAULT:
#   root=/dev/sda2        - Specify root filesystem
#   ro                    - Mount root read-only initially
#   quiet                 - Suppress most kernel messages
#   splash                - Show splash screen
#   nomodeset             - Disable kernel mode setting (fixes GPU boot hangs)
#   single                - Boot into single-user mode (recovery)
#   systemd.unit=rescue.target - Boot into systemd rescue target

# Temporarily add a parameter at boot (no config change needed):
# At GRUB menu, press 'e' to edit entry, append parameter to linux line, then Ctrl+X
```

### Understanding the boot stages with dmesg

```bash
# Filter kernel messages for boot-related events
dmesg | grep -E "BIOS|UEFI|GRUB|kernel|init"

# See how long each boot stage took (systemd-based systems)
systemd-analyze blame | head -10
```

## Common Pitfalls & Gotchas

**1. Forgetting to regenerate GRUB config after changes**
Editing `/etc/default/grub` does nothing until you run `update-grub` or `grub2-mkconfig`. I've seen engineers waste hours debugging a kernel parameter that was never applied. Always verify with `cat /proc/cmdline` after reboot.

**2. BIOS vs UEFI boot mode mismatch**
If you install GRUB in BIOS mode on a UEFI system (or vice versa), the firmware won't find the bootloader. Check `/sys/firmware/efi` before troubleshooting. On dual-boot systems, this mismatch is a common cause of "no bootable device" errors.

**3. Root filesystem not found during kernel boot**
The kernel needs the root filesystem driver built-in (not as a module) or an initramfs. If you compile a custom kernel and forget to include the storage driver (e.g., `CONFIG_EXT4_FS=y`), you'll get a kernel panic with "VFS: Unable to mount root fs". Always verify your initramfs contains necessary modules with `lsinitramfs /boot/initrd.img-$(uname -r)`.

## Try It Yourself

1. **Inspect your boot chain**: Run `[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"` and `cat /proc/cmdline`. Identify which kernel parameters are active and what each does. Check your GRUB config at `/etc/default/grub` and see if the parameters match.

2. **Add a temporary kernel parameter**: Reboot, press 'e' at the GRUB menu, append `systemd.log_level=debug` to the `linux` line, then boot with Ctrl+X. After login, check `journalctl -b | grep -i "systemd"` to see verbose logging. This is invaluable for debugging boot-time services.

3. **Trace the initramfs contents**: Run `lsinitramfs /boot/initrd.img-$(uname -r) | head -30` to see what modules and scripts are packed into your initial ramdisk. Find the `init` script at the top of the archive—this is the kernel's first userspace process.

## Next Up

Tomorrow we dive into **systemd: Units, Targets & Dependency Graph**. We'll explore how systemd replaces SysV init, the anatomy of unit files, and how to trace the dependency graph that determines service startup order. Bring your `systemctl` skills—we're going beyond start/stop/status.
