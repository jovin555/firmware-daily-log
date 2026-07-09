---
title: "Day 27: Full Review: Build a Complete Embedded Image"
date: 2026-07-09
tags: ["til", "yocto", "review", "project"]
---

## What I Explored Today

After 26 days of incremental Yocto Project learning—from setting up layers to writing recipes, configuring kernels, and debugging build failures—today I performed a full end-to-end build of a complete embedded Linux image targeting a Raspberry Pi 3. This wasn't a toy example; it included a custom application layer, a patched kernel, a read-only root filesystem, and a production-ready init system. The goal was to validate that every component I've studied actually works together in a real, bootable image. I ran the full `bitbake core-image-minimal` pipeline, then extended it to a custom image with networking, a Python runtime, and a hardware-specific device tree overlay.

## The Core Concept

The Yocto Project's power isn't in any single recipe or layer—it's in the *composition* of layers, configurations, and recipes into a coherent, reproducible system image. A complete embedded image is more than the sum of its parts: it's a carefully orchestrated build where the toolchain, kernel, rootfs, bootloader, and device-specific configurations all align. The "why" behind a full review build is to catch integration failures that individual component testing misses. For example, a kernel module might compile fine in isolation but fail to load because the rootfs lacks the correct firmware, or a custom recipe might depend on a library that's excluded by the image's package group. By building the complete image, you validate the dependency graph end-to-end, ensuring that `bitbake` resolves every `RDEPENDS`, `RRECOMMENDS`, and `IMAGE_INSTALL` correctly. This is the difference between a "works on my host" prototype and a deployable embedded system.

## Key Commands / Configuration / Code

Below is the exact sequence I used, with inline explanations. I started from a clean `poky` checkout (kirkstone branch) and added my custom layer.

```bash
# 1. Initialize build environment (assumes poky is cloned)
cd poky
source oe-init-build-env build-rpi3

# 2. Add meta-raspberrypi layer (BSP layer for RPi3)
bitbake-layers add-layer ../meta-raspberrypi

# 3. Add my custom application layer (created earlier)
bitbake-layers add-layer ../meta-myapp

# 4. Configure local.conf for RPi3 target
cat >> conf/local.conf << 'EOF'
MACHINE = "raspberrypi3"
# Enable UART console for debugging
ENABLE_UART = "1"
# Use systemd as init manager
DISTRO_FEATURES:append = " systemd"
VIRTUAL-RUNTIME_init_manager = "systemd"
# Set rootfs to read-only for production hardening
IMAGE_FEATURES += "read-only-rootfs"
# Add my custom application and Python to the image
IMAGE_INSTALL:append = " my-app python3"
# Reduce build time by reusing sstate cache
SSTATE_DIR = "/opt/yocto/sstate-cache"
EOF

# 5. Build the complete image (takes ~2 hours first time)
bitbake core-image-minimal
```

After the base image built, I created a custom image recipe to include additional packages:

```bitbake
# File: meta-myapp/recipes-core/images/my-image.bb
SUMMARY = "Custom embedded image with my-app and networking tools"

# Inherit from core-image-minimal to get base functionality
require recipes-core/images/core-image-minimal.bb

# Add packages specific to my application
IMAGE_INSTALL:append = " \
    my-app \
    python3 \
    python3-pip \
    dropbear \
    i2c-tools \
    device-tree-overlays \
    "

# Ensure kernel modules for RPi3 GPIO are included
KERNEL_MODULE_AUTOLOAD:rpi += "i2c-bcm2708 spi-bcm2835"
```

To verify the build output:

```bash
# Check the generated image files
ls -lh tmp/deploy/images/raspberrypi3/
# Expected output includes:
# core-image-minimal-raspberrypi3.wic.bz2  (SD card image)
# core-image-minimal-raspberrypi3.tar.bz2  (rootfs tarball)
# zImage (kernel)
# bcm2710-rpi-3-b.dtb (device tree blob)

# Flash to SD card (replace /dev/sdX with your device)
sudo bmaptool copy tmp/deploy/images/raspberrypi3/core-image-minimal-raspberrypi3.wic.bz2 /dev/sdX

# Boot the RPi3 and verify
# On boot, login as root (no password by default)
# Check my-app is running
systemctl status my-app
# Verify Python is available
python3 --version
```

## Common Pitfalls & Gotchas

1. **Machine Override Mismatch**: When adding machine-specific overrides (like `KERNEL_MODULE_AUTOLOAD:rpi`), the override must exactly match the `MACHINE` variable value. I spent 30 minutes debugging why kernel modules weren't autoloading—turns out I used `:raspberrypi3` but the machine was set to `raspberrypi3-64` in an earlier test. Always double-check `MACHINE` in `local.conf` and match overrides precisely.

2. **Read-Only Rootfs Surprises**: Enabling `read-only-rootfs` breaks any recipe that tries to write to `/var` or `/etc` at runtime. My `my-app` recipe had a systemd service that created a log file in `/var/log`. I had to refactor it to use `/tmp` (tmpfs) or add a `volatile-binds` recipe. The build succeeds, but the first boot fails silently—always test with `read-only-rootfs` early.

3. **Layer Order in bblayers.conf**: The order of layers in `bblayers.conf` matters for recipe priority. If `meta-myapp` is listed before `meta-raspberrypi`, a recipe with the same name in my layer will shadow the BSP's version. I accidentally overrode the RPi3's device tree recipe, causing a non-bootable image. Use `bitbake-layers show-recipes` to verify which layer provides each recipe.

## Try It Yourself

1. **Build a custom image with your own application**: Create a new layer (e.g., `meta-myapp`) with a simple C or Python "hello world" recipe. Add it to `IMAGE_INSTALL` in a custom image recipe, then build and boot on a Raspberry Pi 3 or QEMU. Verify the application runs at startup.

2. **Add read-only rootfs and fix a runtime issue**: Enable `read-only-rootfs` in `local.conf` and rebuild. Boot the image and identify any service that fails because it tries to write to a non-volatile location. Fix it by either moving writes to `/tmp` or adding a `volatile-binds` recipe.

3. **Debug a dependency resolution failure**: Intentionally add a package to `IMAGE_INSTALL` that doesn't exist in any layer (e.g., `IMAGE_INSTALL:append = " nonexistent-pkg"`). Run `bitbake my-image` and observe the error message. Use `bitbake -s | grep nonexistent` to confirm it's missing, then find the correct package name using `bitbake -s | grep <keyword>`.

## Next Up

Tomorrow, we'll dive into **Day 28: Full Review: Build a Complete Embedded Image**—a deeper exploration of optimizing build performance with shared state cache, creating a minimal production image, and automating the build pipeline with CI/CD integration. We'll also cover how to strip down the image size by 40% using `PACKAGE_EXCLUDE` and custom `IMAGE_FEATURES`.
