---
title: "Day 08: Root Filesystem: BusyBox, initramfs & Filesystem Layout"
date: 2026-06-22
tags: ["til", "embedded-linux", "rootfs", "busybox"]
---

## What I Explored Today

Today I built a minimal root filesystem from scratch using BusyBox, packaged it as an initramfs, and booted it under QEMU. The goal was to understand exactly what happens after the kernel hands off control to userspace — the moment when `rootfs` becomes the living, breathing environment for init, shell, and all subsequent processes. I walked through the FHS (Filesystem Hierarchy Standard) layout, compiled BusyBox as a single static binary, created the essential device nodes, and wrote a minimal init script. The result: a fully functional Linux system in under 2 MB.

## The Core Concept

The root filesystem is not just a collection of files — it is the contract between the kernel and userspace. When the kernel finishes booting, it mounts a root filesystem (usually via `root=` parameter) and executes `/sbin/init` (or the binary pointed to by `init=`). If that filesystem is missing or broken, the kernel panics. In embedded systems, we often use an **initramfs** (initial RAM filesystem) — a compressed cpio archive embedded in the kernel image or loaded separately by the bootloader. The kernel extracts it into a tmpfs, runs `/init`, and that process becomes PID 1.

Why BusyBox? Because it's a single binary that provides hundreds of Unix utilities (`sh`, `ls`, `mount`, `cp`, `vi`, etc.) via symlinks or hardlinks. For embedded systems, this is gold: one binary, one set of dependencies, minimal storage. The trick is configuring it correctly — selecting the right applets, enabling static linking, and setting the installation prefix to match your target rootfs layout.

The filesystem layout matters because every tool and script expects certain paths. `/bin`, `/sbin`, `/usr/bin`, `/etc`, `/dev`, `/proc`, `/sys`, `/tmp` — these are not arbitrary. The kernel, BusyBox, and glibc all hardcode paths. Getting the layout wrong means broken `PATH` variables, missing shared libraries, or init failing silently.

## Key Commands / Configuration / Code

### 1. Building BusyBox with Static Linking

```bash
# Download and extract
wget https://busybox.net/downloads/busybox-1.36.1.tar.bz2
tar xf busybox-1.36.1.tar.bz2
cd busybox-1.36.1

# Configure for static build
make defconfig
make menuconfig

# In menuconfig, set:
#   Settings -> Build static binary (no shared libs) -> [*]
#   Settings -> Destination path for 'make install' -> ./_install
#   Coreutils -> [*] mount, [*] umount
#   Linux System Utilities -> [*] mdev (for device management)

# Build and install
make -j$(nproc)
make install
```

### 2. Creating the Root Filesystem Layout

```bash
# Create directory structure
mkdir -p rootfs/{bin,sbin,usr/bin,usr/sbin,etc,dev,proc,sys,tmp,root}
chmod 1777 rootfs/tmp

# Copy BusyBox and create symlinks
cp -a busybox-1.36.1/_install/* rootfs/

# Create essential device nodes (static, for early boot)
sudo mknod rootfs/dev/console c 5 1
sudo mknod rootfs/dev/null c 1 3
sudo mknod rootfs/dev/tty c 5 0
sudo mknod rootfs/dev/zero c 1 5
sudo chmod 666 rootfs/dev/null rootfs/dev/zero rootfs/dev/tty
```

### 3. The Init Script (`rootfs/init`)

```bash
#!/bin/sh

# Mount essential virtual filesystems
mount -t proc none /proc
mount -t sysfs none /sys
mount -t tmpfs none /tmp

# Populate /dev with mdev (dynamic device management)
echo /sbin/mdev > /proc/sys/kernel/hotplug
mdev -s

# Set up networking (loopback)
ip link set lo up
ip addr add 127.0.0.1/8 dev lo

# Start a shell on the console
exec /bin/sh
```

Make it executable: `chmod +x rootfs/init`

### 4. Packaging as initramfs

```bash
# Create cpio archive and compress
cd rootfs
find . | cpio -H newc -o | gzip > ../initramfs.cpio.gz
cd ..

# Boot with QEMU
qemu-system-x86_64 -kernel /path/to/bzImage \
    -initrd initramfs.cpio.gz \
    -nographic \
    -append "console=ttyS0"
```

You should see the kernel boot, then a shell prompt. Type `ls /bin` — you'll see BusyBox applets. Type `mount` — you'll see proc, sysfs, and tmpfs mounted.

## Common Pitfalls & Gotchas

1. **Missing `/dev/console` causes silent boot hang.** The kernel opens `/dev/console` as stdin/stdout/stderr for init. If the device node doesn't exist (or has wrong major/minor numbers), init will fail to start and you'll see nothing. Always create `c 5 1` with `mknod` before packaging.

2. **BusyBox applets not found due to missing symlinks.** `make install` creates symlinks in `_install`, but if you copy manually or use a different prefix, the symlinks break. Verify with `ls -la rootfs/bin/ | head`. If you see `sh -> /bin/busybox` but busybox is missing, your PATH is broken. Use `make CONFIG_PREFIX=<path> install` to get correct symlinks.

3. **Init script not executable or wrong shebang.** The kernel executes `/init` directly — it must have the executable bit set and a valid shebang (`#!/bin/sh`). A common mistake: the script is a symlink to BusyBox's `sh`, but the symlink points to a relative path that doesn't exist at boot time. Use `exec /bin/busybox sh` as a fallback, or ensure the symlink is absolute.

4. **Missing `/proc` or `/sys` causes tools to fail.** Many BusyBox applets (like `mount`, `ps`, `kill`) read from `/proc` and `/sys`. If these aren't mounted in init, commands will hang or return garbage. Always mount them early in the init script.

## Try It Yourself

1. **Add a custom init service.** Modify the `init` script to start a simple HTTP server using BusyBox's `httpd` applet. Run `httpd -h /root -p 8080` in the background before dropping to shell. Test with `wget http://127.0.0.1:8080/` from another terminal.

2. **Reduce size further.** Rebuild BusyBox with only the applets you need (e.g., remove `vi`, `awk`, `sed`). Use `make allnoconfig` then manually select only `sh`, `mount`, `ls`, `cat`, `echo`, `mdev`. Compare the final initramfs size.

3. **Switch to dynamic linking.** Rebuild BusyBox without static linking, copy the required shared libraries (`ld-linux.so.*`, `libc.so.*`) into `rootfs/lib/`, and set `LD_LIBRARY_PATH` or use `patchelf` to set the rpath. Boot and verify with `ldd /bin/busybox`.

## Next Up

Tomorrow, we cross the boundary from userspace into kernel space. I'll write a **Linux Kernel Module** — starting with the classic "Hello World" and extending it to control a real GPIO pin on a Raspberry Pi. We'll cover the Makefile, module parameters, and the `printk` vs `printf` distinction. Bring your kernel headers.
