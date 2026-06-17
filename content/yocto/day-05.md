---
title: "Day 05: Your First Image: core-image-minimal from Scratch"
date: 2026-06-17
tags: ["til", "yocto", "image", "core-image"]
---

## What I Explored Today

Today I built my first complete Yocto image from scratch using `core-image-minimal`. After days of setting up layers, understanding recipes, and wrestling with configuration, I finally ran `bitbake core-image-minimal` and watched the build system assemble a bootable Linux image for my target hardware. The process took about 45 minutes on my machine (first build with no sstate cache), and the result was a ~12 MB root filesystem tarball and a kernel image ready to deploy. This is the moment where all the abstract concepts—layers, recipes, tasks, and dependencies—become tangible.

## The Core Concept

An "image" in Yocto is not a binary you download; it's a recipe that describes *what* to include in a root filesystem and *how* to assemble it. `core-image-minimal` is the simplest reference image: it includes just enough to boot a Linux system with a shell, basic utilities (busybox), and networking support. Think of it as the embedded equivalent of a minimal Debian install—no GUI, no package manager, just the kernel and a working userland.

Why build from scratch instead of using a prebuilt image? Because the entire point of Yocto is *reproducibility and customization*. When you build from scratch, every component—from the toolchain to the kernel configuration—is built from source under your control. You can later add your own applications, change kernel options, or strip the image down further. The `core-image-minimal` is your baseline; everything else is additive.

The build process follows a strict dependency graph:
1. Toolchain (cross-compiler, libc, binutils) is built first
2. Kernel and bootloader are compiled against that toolchain
3. Root filesystem packages (busybox, base-files, etc.) are built
4. The image recipe collects all packages and assembles the final filesystem

## Key Commands / Configuration / Code

### Setting Up the Build Environment

```bash
# Source the environment setup script from your Poky directory
# This sets up PATH, bitbake, and creates a build directory
source poky/oe-init-build-env build-minimal
```

### Configuring the Build (local.conf)

The default `local.conf` needs minimal changes for a first build. Here's what I adjusted:

```bash
# conf/local.conf - critical settings for first build

# Target machine - change to your hardware (e.g., qemuarm64, raspberrypi3)
MACHINE ?= "qemux86-64"

# Number of parallel build threads (match your CPU cores)
BB_NUMBER_THREADS = "8"
PARALLEL_MAKE = "-j 8"

# Download directory (shared between builds, persists across cleans)
DL_DIR = "${TOPDIR}/../downloads"

# Shared state cache (speeds up rebuilds dramatically)
SSTATE_DIR = "${TOPDIR}/../sstate-cache"

# Enable build history for debugging
INHERIT += "buildhistory"
BUILDHISTORY_COMMIT = "1"
```

### Building the Image

```bash
# The main command - this triggers the entire dependency chain
bitbake core-image-minimal

# After successful build, output is in:
# tmp/deploy/images/${MACHINE}/
# Key files:
#   core-image-minimal-${MACHINE}.tar.bz2  (rootfs tarball)
#   bzImage                                 (kernel image)
#   core-image-minimal-${MACHINE}.qemuboot.conf (QEMU boot config)
```

### Testing with QEMU

```bash
# Run the image directly in QEMU (no manual setup needed)
runqemu qemux86-64

# Or specify the image type
runqemu core-image-minimal
```

## Common Pitfalls & Gotchas

**1. Disk Space Underestimation**
A first build consumes 30-50 GB of disk space. The build directory alone can exceed 20 GB. Always check `df -h` before starting. If you run out of space mid-build, you'll need to clean (`bitbake -c cleanall`) and restart—Yocto doesn't handle partial builds gracefully.

**2. Network Timeouts During Fetch**
The first build downloads hundreds of source tarballs from various mirrors. If you're behind a corporate proxy or have a slow connection, fetches can timeout. Set `BB_GENERATE_MIRROR_TARBALLS = "1"` in `local.conf` to create local mirrors, or use `PREMIRRORS` to point to a local cache.

**3. Mismatched Machine Configuration**
If you set `MACHINE = "qemux86-64"` but your host is ARM, the build will still work (that's the point of cross-compilation). However, if you accidentally set `MACHINE` to something unsupported by your layer configuration, you'll get cryptic errors about missing `MACHINE` overrides. Always verify with `bitbake -s | grep ${MACHINE}` that your machine is recognized.

**4. The "Nothing PROVIDES" Error**
If you run `bitbake core-image-minimal` and get `ERROR: Nothing PROVIDES 'core-image-minimal'`, you likely forgot to source the environment script, or you're in the wrong directory. The `oe-init-build-env` script must be sourced from the Poky directory, and it creates a `build/` subdirectory where you must run all bitbake commands.

## Try It Yourself

1. **Build and boot `core-image-minimal` for QEMU**: Follow the steps above, then use `runqemu` to verify the image boots to a login prompt (root with no password). Run `uname -a` and `df -h` inside the emulated system.

2. **Inspect the image contents**: After the build, extract the rootfs tarball: `tar -xvf tmp/deploy/images/qemux86-64/core-image-minimal-qemux86-64.tar.bz2 -C /tmp/rootfs-test`. List the contents and identify which binaries are provided by busybox vs. standalone packages.

3. **Add a package to the image**: Edit `conf/local.conf` and add `IMAGE_INSTALL:append = " strace"`. Rebuild with `bitbake core-image-minimal` (this will be faster thanks to sstate). Boot the image and verify `strace` is available.

## Next Up

Tomorrow we dive into the heart of Yocto: **Writing a Recipe: .bb File Anatomy & Variables**. We'll dissect a real recipe, understand `SRC_URI`, `do_compile`, and the variable expansion system that makes recipes so powerful. You'll write your first `.bb` file from scratch.
