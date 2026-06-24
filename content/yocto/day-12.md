---
title: "Day 12: Distro Configuration: DISTRO_FEATURES & Policies"
date: 2026-06-24
tags: ["til", "yocto", "distro", "policies"]
---

## What I Explored Today

Today I dove into the heart of distribution configuration in Yocto—specifically how `DISTRO_FEATURES` and policy variables shape the entire build. After weeks of tweaking individual recipes and machine configurations, I realized that the distro layer is where you define *what your system is*. It’s not just a list of features; it’s a policy decision about which capabilities your embedded Linux distribution will support, from systemd vs. sysvinit to whether you need X11, Wayland, or a headless system. I spent the day tracing how these flags propagate into package selections, kernel configurations, and even init system choices.

## The Core Concept

`DISTRO_FEATURES` is a space-separated list of strings that act as global toggles for the entire build system. Every recipe, class, and configuration file can check for these features using the `inherit` mechanism or conditional expressions. The real power—and the reason you must understand this—is that changing one feature can ripple through hundreds of recipes. For example, setting `DISTRO_FEATURES:append = " systemd"` doesn't just pull in systemd; it also disables sysvinit, changes how services are packaged, and alters the default target in the root filesystem.

Policies, on the other hand, are variables like `PREFERRED_PROVIDER`, `PACKAGE_CLASSES`, and `TCLIBC` that define *how* the build behaves. They determine which implementation of a virtual package (e.g., `virtual/libc`) gets used, or whether you build deb, rpm, or ipk packages. Together, `DISTRO_FEATURES` and policies form the contract between your distribution and the rest of the build system.

## Key Commands / Configuration / Code

### Defining DISTRO_FEATURES in your distro config

Create `meta-custom/conf/distro/custom.conf`:

```bitbake
# meta-custom/conf/distro/custom.conf
DISTRO = "custom"
DISTRO_NAME = "Custom Embedded Linux"
DISTRO_VERSION = "1.0"

# Core features: start minimal, then add what you need
DISTRO_FEATURES = "\
    acl \
    argp \
    ipv4 \
    ipv6 \
    largefile \
    pam \
    pci \
    usbgadget \
    usbhost \
    wifi \
    "

# Select systemd as init manager (removes sysvinit automatically)
DISTRO_FEATURES:append = " systemd"

# Enable Wayland for display (requires opengl)
DISTRO_FEATURES:append = " wayland opengl"

# Policy: use ipk packaging (smaller footprint for embedded)
PACKAGE_CLASSES = "package_ipk"

# Policy: use musl instead of glibc for smaller size
TCLIBC = "musl"

# Policy: prefer busybox over coreutils for base utilities
PREFERRED_PROVIDER_base-utils = "busybox"
```

### Checking features in a recipe

Inside any recipe, you can conditionally add dependencies or code:

```bitbake
# recipes-example/myapp/myapp_1.0.bb
inherit autotools

# Only enable Bluetooth support if DISTRO_FEATURES has bluetooth
PACKAGECONFIG ??= ""
PACKAGECONFIG:append = " ${@bb.utils.contains('DISTRO_FEATURES', 'bluetooth', 'bluetooth', '', d)}"

# Add systemd service only when systemd is the init
SYSTEMD_SERVICE:${PN} = "${@bb.utils.contains('DISTRO_FEATURES', 'systemd', 'myapp.service', '', d)}"
```

### Using features in classes

The `features_check` class is your friend for enforcing dependencies:

```bitbake
# recipes-bsp/bluez/bluez5_%.bbappend
inherit features_check
REQUIRED_DISTRO_FEATURES = "bluetooth"
ANY_OF_DISTRO_FEATURES = "bluez5"
```

### Inspecting the effective features

To see what features are actually active for your build:

```bash
# Show all DISTRO_FEATURES after parsing
bitbake -e | grep ^DISTRO_FEATURES=

# Show only the final value (no variable expansion)
bitbake-getvar DISTRO_FEATURES

# Check if a specific feature is enabled in a recipe context
bitbake -e myapp | grep ^DISTRO_FEATURES=
```

## Common Pitfalls & Gotchas

1. **Order of `:append` matters.** If you append `systemd` to `DISTRO_FEATURES` but your base distro config (like `poky.conf`) already sets `VIRTUAL-RUNTIME_init_manager = "sysvinit"`, you'll get a conflict. Always check that your policy variables align with your features. The correct pattern is to set both `DISTRO_FEATURES:append = " systemd"` and `VIRTUAL-RUNTIME_init_manager = "systemd"` together.

2. **Missing features can silently disable packages.** If you add `wayland` to `DISTRO_FEATURES` but forget `opengl`, the Wayland stack will be partially built but Weston may fail at runtime. Use `bitbake -s | grep wayland` to verify all expected packages are being built. The `features_check` class can catch this at parse time.

3. **Overrides in local.conf can override your distro.** If you set `DISTRO_FEATURES:append = " x11"` in `local.conf` but your distro config explicitly removes X11, the local.conf wins. This is by design, but it means your distro policy isn't enforced. For production, lock down `local.conf` or use a dedicated distro layer.

## Try It Yourself

1. **Create a minimal distro config** that enables only `systemd`, `ipv4`, `usbhost`, and `pam`. Build `core-image-minimal` and verify the init system is systemd by checking the running PID 1 inside the image.

2. **Add a custom feature flag** like `my-feature` to your distro config. Then create a simple recipe that conditionally installs an extra file only when `my-feature` is set. Use `bb.utils.contains()` in the recipe.

3. **Compare package sizes** between two builds: one with `TCLIBC = "glibc"` and one with `TCLIBC = "musl"`. Use `du -sh tmp/deploy/images/<machine>/<image>.rootfs.tar.bz2` to see the difference. Document which packages change.

## Next Up

Tomorrow, we shift focus from the distribution-level policies to image-level configuration. I'll explore `IMAGE_FEATURES` and how to control exactly which packages land in your final root filesystem—including the subtle differences between `IMAGE_INSTALL`, `IMAGE_FEATURES`, and package groups.
