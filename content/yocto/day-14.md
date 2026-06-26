---
title: "Day 14: Kernel Recipe: linux-yocto & KBRANCH"
date: 2026-06-26
tags: ["til", "yocto", "kernel", "linux-yocto"]
---

## What I Explored Today

Today I dug into the heart of Yocto's kernel build system: the `linux-yocto` recipe and the `KBRANCH` mechanism. I've been building custom kernels for years, but Yocto's approach to kernel source management is unique—it doesn't just pull a tarball and apply patches. Instead, it uses a Git-based workflow with branching strategies that map directly to kernel versions, board support packages (BSPs), and feature configurations. I traced how `KBRANCH` controls which kernel tree variant gets built, how `SRCREV` pins exact commits, and how the `linux-yocto.inc` include file orchestrates the entire process. The result is a system that lets you manage multiple kernel configurations for different machines from a single recipe.

## The Core Concept

The `linux-yocto` recipe is not a single kernel source tree—it's a meta-recipe that selects from a family of kernel Git branches maintained by the Yocto Project. The key insight is that Yocto doesn't treat kernel source as a static snapshot. Instead, it maintains a Git repository (`git://git.yoctoproject.org/linux-yocto.git`) with multiple branches, each representing a specific kernel version combined with a BSP or feature set. The `KBRANCH` variable selects which branch to build.

Why this complexity? Because embedded systems need kernel variants: one for a qemuarm machine, another for a BeagleBone Black, and yet another for a custom x86 board. Each variant may have different drivers, config options, and patches. Rather than maintaining separate recipes for each, Yocto uses `KBRANCH` to point to the right branch. The `SRCREV` variable then pins the exact commit on that branch, ensuring reproducible builds.

The `linux-yocto.inc` file (found in `meta/recipes-kernel/linux/linux-yocto.inc`) is the workhorse. It defines the `do_patch` task that uses `kgit-s2q` (a Git-based quilt-like tool) to apply patches from the branch's commit history. It also integrates with `KERNEL_FEATURES` to enable or disable kernel config fragments. This means you can have a single recipe that builds kernels for multiple machines, each with different features, all controlled by `KBRANCH` and `SRCREV`.

## Key Commands / Configuration / Code

**Inspecting available KBRANCH values for linux-yocto:**

```bash
# List all branches in the linux-yocto repository
git ls-remote git://git.yoctoproject.org/linux-yocto.git | grep -E "refs/heads/(standard|v5\.15|v6\.1)" | head -20

# Typical output shows branches like:
# standard/base
# standard/beaglebone
# standard/qemuarm64
# v5.15/standard/base
# v6.1/standard/base
```

**Setting KBRANCH in a machine configuration (e.g., meta-custom/conf/machine/myboard.conf):**

```bitbake
# Select the kernel branch for our custom ARM board
KBRANCH = "standard/custom-arm"

# Pin the exact commit for reproducibility
SRCREV_machine = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"

# Optionally, set SRCREV for the meta branch (config fragments)
SRCREV_meta = "f0e1d2c3b4a5f6e7d8c9a0b1c2d3e4f5a6b7c8d9"
```

**Custom kernel recipe inheriting linux-yocto (meta-custom/recipes-kernel/linux/linux-yocto_6.1.bbappend):**

```bitbake
# Append to the base linux-yocto recipe for our custom board
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

# Override the kernel source for our custom branch
SRC_URI = "git://git.yoctoproject.org/linux-yocto.git;protocol=https;nocheckout=1;branch=${KBRANCH};name=machine"

# Add a kernel config fragment for our hardware
SRC_URI += "file://myboard-config.cfg"

# Enable specific kernel features
KERNEL_FEATURES:append = " features/netfilter/netfilter.scc"
```

**Understanding the linux-yocto.inc patch mechanism:**

```bitbake
# From meta/recipes-kernel/linux/linux-yocto.inc (simplified)
do_patch() {
    cd ${S}
    # kgit-s2q applies patches from the branch's commit history
    # that are not in the base kernel version
    kgit-s2q --patches ${WORKDIR}/patches
}

# The branch contains commits that are patches on top of the base kernel
# Each commit message follows a specific format for quilt-style management
```

**Building a specific kernel variant:**

```bash
# Build the kernel for a machine that uses KBRANCH=standard/beaglebone
bitbake -c clean linux-yocto
MACHINE=beaglebone-yocto bitbake linux-yocto

# Inspect which kernel branch will be used for a given machine
bitbake -e linux-yocto | grep ^KBRANCH=
```

## Common Pitfalls & Gotchas

1. **Mismatched KBRANCH and SRCREV**: If you set `KBRANCH` to a branch that doesn't exist in the repository, or if `SRCREV` points to a commit not on that branch, BitBake will fail with a cryptic "unable to resolve reference" error. Always verify the branch exists and the commit is reachable. Use `git branch -a --contains <commit>` to check.

2. **Forgetting to set SRCREV for both machine and meta**: The `linux-yocto` recipe uses two separate `SRCREV` variables: `SRCREV_machine` for the kernel source branch and `SRCREV_meta` for the kernel config metadata branch. If you only set one, the other defaults to `AUTOINC`, which can lead to non-reproducible builds. Always pin both.

3. **Confusing KBRANCH with LINUX_VERSION**: `KBRANCH` selects the branch in the linux-yocto Git repository, while `LINUX_VERSION` is a string (e.g., "6.1.30") used for packaging. They must be consistent—a `v6.1/standard/base` branch corresponds to `LINUX_VERSION = "6.1%"`. Mismatch them and your kernel version string won't match the actual source.

## Try It Yourself

1. **Explore available branches**: Run `git ls-remote git://git.yoctoproject.org/linux-yocto.git` and identify three branches that correspond to different kernel versions (e.g., v5.15, v6.1, v6.6). For each, note the `standard/base` variant versus a BSP-specific variant like `standard/beaglebone`.

2. **Create a custom machine with a specific KBRANCH**: In your own layer, create a machine configuration file that sets `KBRANCH` to `standard/base` and `SRCREV_machine` to a known commit from the linux-yocto repository. Build the kernel for that machine and verify the kernel version matches your expectations.

3. **Add a kernel config fragment via SRC_URI**: Write a simple `.cfg` file (e.g., `enable-debug.cfg` with `CONFIG_DEBUG_KERNEL=y`) and add it to your kernel recipe's `SRC_URI`. Rebuild and verify the config is applied by checking `/proc/config.gz` on the target or using `bitbake -c menuconfig linux-yocto`.

## Next Up

Tomorrow, I'll dive into **Kernel Config Fragments & defconfig in Yocto**—how to use `.cfg` files and `KERNEL_FEATURES` to modularize kernel configuration, and how to integrate a custom `defconfig` without forking the entire kernel recipe. We'll also cover the `merge_config.sh` script that Yocto uses to combine fragments with the base configuration.
