---
title: "Day 19: Standard SDK: populate_sdk & Cross-Development"
date: 2026-07-01
tags: ["til", "yocto", "sdk", "populate-sdk"]
---

## What I Explored Today

Today I dove into the Yocto Project's Standard SDK generation workflow, specifically the `populate_sdk` task and how it enables cross-development outside the build environment. After weeks of building images and debugging recipes inside the Yocto build system, I needed a way to let application developers work independently without requiring a full Yocto setup. The Standard SDK is the answer: a relocatable, self-contained toolchain and sysroot that mirrors the target root filesystem, allowing developers to compile, link, and debug applications for the embedded target on their workstations.

## The Core Concept

The Standard SDK solves a fundamental tension in embedded development: the build system (where you craft the OS image) and the application development workflow (where you write user-space code) have different requirements. Yocto's build environment is powerful but heavyweight—it pulls in hundreds of recipes, runs extensive dependency resolution, and can take hours for a full build. Application developers don't need that. They need a compiler, linker, headers, and libraries that match the target exactly.

The `populate_sdk` task generates exactly this: a tarball containing a cross-toolchain (e.g., `aarch64-poky-linux-gcc`), a sysroot with all target libraries and headers, and an environment setup script. When the application developer sources that script, their shell gains the correct `PATH`, `CC`, `CXX`, `LD`, `CFLAGS`, and `LDFLAGS` to cross-compile against the exact same libraries that will be on the final device. This eliminates the "it compiled on my machine" problem because the SDK sysroot is a snapshot of the target rootfs.

The key distinction from the Extensible SDK (eSDK) is that the Standard SDK is read-only and static—you cannot modify recipes or rebuild packages from within it. It's a pure consumption tool, ideal for teams where application developers don't need to modify the OS itself.

## Key Commands / Configuration / Code

### Generating the Standard SDK

The simplest way to generate an SDK for your image:

```bash
# From your build directory, after a successful image build
bitbake core-image-minimal -c populate_sdk
```

This produces a self-extracting script in `tmp/deploy/sdk/`:

```bash
ls -lh tmp/deploy/sdk/*.sh
# Example output:
# -rw-r--r-- 1 user user 89M Jul  1 10:23 poky-glibc-x86_64-core-image-minimal-cortexa53-toolchain-4.0.2.sh
```

### Installing and Using the SDK

```bash
# Install to default location (/opt/poky/)
./poky-glibc-x86_64-core-image-minimal-cortexa53-toolchain-4.0.2.sh

# Source the environment setup script
source /opt/poky/4.0.2/environment-setup-cortexa53-poky-linux

# Verify the toolchain is active
echo $CC
# Output: aarch64-poky-linux-gcc --sysroot=/opt/poky/4.0.2/sysroots/cortexa53-poky-linux

# Cross-compile a simple C program
$CC -o hello hello.c
file hello
# Output: ELF 64-bit LSB executable, ARM aarch64, version 1 (SYSV), dynamically linked
```

### Customizing SDK Content

You can control which packages land in the SDK sysroot via your image recipe or local.conf:

```bash
# In your image recipe (e.g., core-image-minimal.bbappend)
TOOLCHAIN_TARGET_TASK:append = " libssl-dev libcurl-dev"
TOOLCHAIN_HOST_TASK:append = " nativesdk-cmake"

# Or in local.conf for quick testing
echo 'TOOLCHAIN_TARGET_TASK:append = " python3-dev"' >> conf/local.conf
```

The `TOOLCHAIN_TARGET_TASK` variable lists packages installed into the target sysroot (what your application links against). `TOOLCHAIN_HOST_TASK` adds tools that run on the host (like `cmake`, `make`, or debuggers).

### Generating SDK for a Specific Recipe (Minimal SDK)

If you only need to build one application, you can generate a minimal SDK containing just that recipe's dependencies:

```bash
bitbake my-custom-app -c populate_sdk
```

This produces a smaller SDK tarball (often 30-50MB instead of 200MB+) containing only what `my-custom-app` needs.

## Common Pitfalls & Gotchas

1. **Sysroot mismatch with running target**: The SDK sysroot is a snapshot from when you ran `populate_sdk`. If you update packages in your image afterward (e.g., `libssl` gets a security fix), the SDK becomes stale. Always regenerate the SDK after significant image changes, or document the exact image build timestamp for your application team.

2. **Missing development packages by default**: The Standard SDK only includes runtime libraries, not their `-dev` counterparts. If your application needs headers or static libraries (e.g., `libssl-dev`, `libcurl-dev`), you must explicitly add them via `TOOLCHAIN_TARGET_TASK`. I've spent hours debugging linker errors only to realize the header was missing from the sysroot.

3. **Relocation path issues**: The SDK is designed to be installed anywhere, but some autotools-based projects hardcode paths during configure. Always use the environment variables (`$CC`, `$CFLAGS`, `$LDFLAGS`) provided by the setup script rather than manually specifying toolchain paths. If you move the SDK after installation, re-run the setup script—it adjusts internal paths.

## Try It Yourself

1. **Generate and test a Standard SDK**: Build `core-image-minimal` for your target machine (e.g., `qemuarm64`), then run `bitbake core-image-minimal -c populate_sdk`. Install the resulting `.sh` script, source the environment, and cross-compile a simple "Hello, World" in C. Verify the binary runs on your target (or QEMU).

2. **Add a development package**: Modify `local.conf` to include `libssl-dev` in `TOOLCHAIN_TARGET_TASK`. Regenerate the SDK, reinstall it, and write a small program that uses OpenSSL's `SHA256` function. Compile it with `$CC` and confirm it links against the sysroot's `libssl`.

3. **Create a minimal per-recipe SDK**: Write a simple recipe (e.g., `hello-sdk.bb` that installs a binary to `/usr/bin`). Build it, then run `bitbake hello-sdk -c populate_sdk`. Compare the tarball size to the full image SDK. Install and use it to rebuild the same application outside the Yocto build tree.

## Next Up

Tomorrow, I'll tackle the **Shared State Cache (sstate)**—Yocto's secret weapon for incremental builds. After watching `bitbake` rebuild the world from scratch one too many times, I'm diving into how sstate caches task outputs, enables build farms, and can cut your rebuild times from hours to minutes. We'll cover sstate mirrors, cache pruning, and how to debug "why is this rebuilding?" with `bitbake-diffsigs`.
