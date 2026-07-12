---
title: "Day 30: GRUB2 Configuration & Boot Recovery"
date: 2026-07-12
tags: ["til", "lfcs", "grub", "boot-recovery"]
---

## What I Explored Today

Today I dove deep into GRUB2 configuration and boot recovery—the safety net every Linux engineer needs when a system refuses to boot. I worked through the GRUB2 configuration file hierarchy, learned how to regenerate the bootloader configuration after kernel updates, and practiced recovering from a corrupted GRUB installation using a live USB. This is the kind of hands-on knowledge that separates someone who panics during a boot failure from someone who calmly fixes it in under five minutes.

## The Core Concept

GRUB2 (GRand Unified Bootloader version 2) is the default bootloader for most modern Linux distributions. Its job is simple: load the Linux kernel into memory and hand off control. But the *why* behind its configuration architecture matters more than the *what*.

GRUB2 uses a two-stage design. The first stage (boot.img) lives in the Master Boot Record (MBR) or GPT protective MBR—it's tiny, 446 bytes, and knows only how to load the second stage. The second stage (core.img) contains filesystem drivers and the actual GRUB2 menu logic. This separation means that if your kernel updates, you don't need to reinstall the bootloader—you just regenerate the configuration file that tells GRUB2 where the new kernel lives.

The configuration file itself (`/boot/grub/grub.cfg`) is **never edited directly**. Instead, you modify scripts in `/etc/default/grub` and snippets in `/etc/grub.d/`, then run `update-grub` (or `grub-mkconfig -o /boot/grub/grub.cfg`). This design prevents syntax errors from bricking your boot process—a lesson learned the hard way by many sysadmins.

## Key Commands / Configuration / Code

### Viewing and modifying GRUB2 defaults

```bash
# Check current GRUB2 settings
cat /etc/default/grub

# Typical output:
# GRUB_DEFAULT=0          # Boot first entry by default
# GRUB_TIMEOUT=5          # Wait 5 seconds before auto-boot
# GRUB_CMDLINE_LINUX=""   # Kernel parameters for all entries
# GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"  # Kernel params for default boot
```

### Regenerating the GRUB2 configuration

```bash
# After any change to /etc/default/grub or /etc/grub.d/
sudo update-grub

# Equivalent manual command:
sudo grub-mkconfig -o /boot/grub/grub.cfg

# Verify the new config lists the correct kernels
grep 'menuentry' /boot/grub/grub.cfg | head -5
```

### Reinstalling GRUB2 to disk (boot recovery from live USB)

```bash
# Boot from live USB, mount root partition
sudo mount /dev/sda1 /mnt          # Adjust partition as needed
sudo mount --bind /dev /mnt/dev
sudo mount --bind /proc /mnt/proc
sudo mount --bind /sys /mnt/sys

# Chroot into the broken system
sudo chroot /mnt

# Reinstall GRUB2 to the MBR (BIOS systems)
grub-install /dev/sda

# For UEFI systems, reinstall to EFI System Partition
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=GRUB

# Regenerate config inside chroot
update-grub

# Exit and reboot
exit
sudo umount -R /mnt
sudo reboot
```

### Booting into rescue mode from GRUB2 menu

```bash
# At GRUB2 menu, press 'e' to edit the boot entry
# Find the line starting with 'linux' and append:
systemd.unit=rescue.target

# Or for single-user mode (root shell):
single

# Press Ctrl+X or F10 to boot with these parameters
```

### Adding a custom kernel parameter permanently

```bash
# Edit the defaults file
sudo nano /etc/default/grub

# Change this line to disable IPv6 at kernel level
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash ipv6.disable=1"

# Regenerate config
sudo update-grub
```

## Common Pitfalls & Gotchas

**1. Editing grub.cfg directly instead of using update-grub**
This is the #1 mistake. If you manually edit `/boot/grub/grub.cfg`, your changes will be overwritten the next time `update-grub` runs (e.g., after a kernel update). Worse, a syntax error in the file can make your system unbootable. Always edit `/etc/default/grub` or add scripts to `/etc/grub.d/`.

**2. Forgetting to mount /dev, /proc, and /sys during chroot recovery**
When you chroot into a broken system from a live USB, those pseudo-filesystems must be mounted. Without them, `grub-install` will fail because it can't access block devices, and `update-grub` won't find your kernels. The `mount --bind` commands in the recovery section above are not optional.

**3. Confusing BIOS/legacy with UEFI installation targets**
Running `grub-install /dev/sda` on a UEFI system will silently fail or produce a non-bootable system. Always check your firmware type with `[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"`. For UEFI, you must specify `--target=x86_64-efi` and point to the EFI System Partition.

## Try It Yourself

1. **Add a kernel parameter to debug boot issues**: Edit `/etc/default/grub` and add `systemd.log_level=debug` to `GRUB_CMDLINE_LINUX_DEFAULT`. Run `sudo update-grub`, then reboot. Check `journalctl -b` to see the verbose boot logs. Remove the parameter when done.

2. **Simulate a broken GRUB and recover it**: In a VM, corrupt the MBR with `dd if=/dev/zero of=/dev/sda bs=446 count=1`. Reboot—you'll get a "No bootable device" error. Boot from a live ISO, mount the root partition, chroot, and reinstall GRUB using the commands from the recovery section above.

3. **Create a custom GRUB2 menu entry**: Add a new script file at `/etc/grub.d/40_custom` that boots into recovery mode by default. Run `update-grub`, then verify your entry appears in the menu with `grep 'menuentry' /boot/grub/grub.cfg`.

## Next up

Tomorrow we tackle **Package Management: apt, dpkg, rpm, dnf**—the tools that keep your system's software in order. We'll cover how to install, remove, query, and troubleshoot packages across Debian and Red Hat families, including dependency resolution, package verification, and when to use dpkg vs apt.
