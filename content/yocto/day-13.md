---
title: "Day 13: Image Configuration: IMAGE_FEATURES & Packages"
date: 2026-06-25
tags: ["til", "yocto", "image", "image-features"]
---

## What I Explored Today

Today I dug into the mechanics of image configuration in Yocto, specifically how `IMAGE_FEATURES` and package groups control what ends up on the target root filesystem. I’ve been hand-editing `local.conf` to add packages, but that’s fragile and not portable. The proper way is to use `IMAGE_FEATURES` for high-level capabilities (like SSH or package management) and `IMAGE_INSTALL` for explicit packages. I also learned how `PACKAGE_CLASSES` and `IMAGE_INSTALL_append` interact, and why you should never use `+=` in an image recipe.

## The Core Concept

An image recipe (`.bb` file in `meta/recipes-core/images/`) is just a BitBake recipe that inherits `core-image`. The magic is in the variables it sets. `IMAGE_FEATURES` is a list of strings that map to feature groups—each feature expands to a set of packages via `FEATURE_PACKAGES_<feature>`. For example, `IMAGE_FEATURES += "ssh-server-dropbear"` pulls in `dropbear`, `openssh-sftp-server`, and their dependencies. This is the “why” of image features: they provide composable, testable capability bundles.

`IMAGE_INSTALL` is the raw list of packages. You can override it in your image recipe, but the recommended pattern is to use `IMAGE_INSTALL_append` in a `.bbappend` or `local.conf`. The distinction matters because `IMAGE_FEATURES` is processed *before* `IMAGE_INSTALL`, and features can add or remove packages from the install list. If you just dump packages into `IMAGE_INSTALL`, you lose that abstraction layer.

## Key Commands / Configuration / Code

### 1. Checking available IMAGE_FEATURES
```bash
# List all features defined in your layer stack
grep -r "FEATURE_PACKAGES" meta/classes-recipe/ | head -20
# Example output:
# meta/classes-recipe/core-image.bbclass:FEATURE_PACKAGES_ssh-server-dropbear = "dropbear openssh-sftp-server"
# meta/classes-recipe/core-image.bbclass:FEATURE_PACKAGES_hwcodecs = "libavcodec libpostproc"
```

### 2. A minimal custom image recipe
File: `meta-custom/recipes-core/images/custom-image.bb`
```bitbake
# Inherit the core-image class
inherit core-image

# Start with a minimal base
IMAGE_FEATURES = "debug-tweaks ssh-server-dropbear package-management"

# Add your own packages explicitly
IMAGE_INSTALL = " \
    packagegroup-core-boot \
    packagegroup-core-full-cmdline \
    ${CORE_IMAGE_EXTRA_INSTALL} \
"

# Append more packages (safe in .bbappend or local.conf)
IMAGE_INSTALL_append = " strace gdb i2c-tools"
```

### 3. Using IMAGE_FEATURES in local.conf
```bitbake
# In conf/local.conf
IMAGE_FEATURES_append = " hwcodecs tools-sdk"
# This adds development headers and codec libraries
```

### 4. Inspecting what a feature expands to
```bash
# Use bitbake -e to see resolved variables
bitbake -e core-image-minimal | grep ^FEATURE_PACKAGES_ssh-server-dropbear
# Output: FEATURE_PACKAGES_ssh-server-dropbear="dropbear openssh-sftp-server"
```

### 5. Package group example
File: `meta-custom/recipes-core/packagegroups/packagegroup-custom-tools.bb`
```bitbake
SUMMARY = "Custom debugging tools"
LICENSE = "MIT"

inherit packagegroup

RDEPENDS_${PN} = " \
    htop \
    iperf3 \
    tcpdump \
    ethtool \
"
```
Then add to image: `IMAGE_INSTALL_append = " packagegroup-custom-tools"`

## Common Pitfalls & Gotchas

### 1. `IMAGE_INSTALL` vs `IMAGE_INSTALL_append` in image recipes
Never use `IMAGE_INSTALL += "foo"` inside an image recipe. The `+=` operator appends at recipe parse time, but `IMAGE_INSTALL` is often reset by the `core-image` class. Use `IMAGE_INSTALL_append` (with a leading space) or `CORE_IMAGE_EXTRA_INSTALL` instead. The latter is the safest way to add packages from `local.conf`.

### 2. Feature conflicts and ordering
If you add both `ssh-server-dropbear` and `ssh-server-openssh`, BitBake will happily install both. The SSH daemon that runs depends on init system configuration. Use `ssh-server-openssh` for production (more features) and `ssh-server-dropbear` for constrained devices. There’s no automatic conflict resolution—you must choose one.

### 3. Package group dependencies are runtime-only
When you create a custom package group, the `RDEPENDS` are runtime dependencies, not build-time. If your package group pulls in a library, it won’t be available during image build unless it’s also in `DEPENDS` or `IMAGE_INSTALL`. This is fine for most tools, but if you need headers at build time, add them explicitly.

## Try It Yourself

1. **Inspect your current image’s feature set**: Run `bitbake -e core-image-minimal | grep ^IMAGE_FEATURES` and `bitbake -e core-image-minimal | grep ^IMAGE_INSTALL`. Compare the two lists. Which packages come from features vs. direct install?

2. **Create a custom package group**: Write a `packagegroup-custom-debug.bb` that includes `gdb`, `valgrind`, `ltrace`, and `strace`. Add it to your image via `IMAGE_INSTALL_append` in `local.conf`. Rebuild and verify the packages are present on the target.

3. **Toggle a feature and observe the size change**: Add `IMAGE_FEATURES_append = " tools-sdk"` to `local.conf`, rebuild, and check the rootfs size with `du -sh tmp/deploy/images/<machine>/<image>.rootfs.tar.bz2`. Remove it and rebuild—note the difference. This shows the cost of development features.

## Next Up

Tomorrow we dive into kernel recipes: how to configure `linux-yocto` with `KBRANCH`, `SRC_URI`, and kernel config fragments. You’ll learn how to pin a specific kernel version, apply out-of-tree patches, and avoid the “kernel config drift” that plagues long-lived projects.
