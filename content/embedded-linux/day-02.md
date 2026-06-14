---
title: "Day 02: Cross-Compilation Toolchain: crosstool-NG & Linaro"
date: 2026-06-14
tags: ["til", "embedded-linux", "cross-compilation", "toolchain"]
---

## What I Explored Today

Today I dove deep into the two dominant approaches for obtaining a cross-compilation toolchain for embedded Linux development: building your own with `crosstool-NG` and using a pre-built Linaro toolchain. I set up both on my x86_64 workstation targeting ARM Cortex-A9, compared the resulting binaries, and learned why choosing the right toolchain strategy matters more than most engineers initially think. The hands-on work included configuring crosstool-NG from scratch, verifying the Linaro GCC version, and running a simple test program on QEMU.

## The Core Concept

A cross-compilation toolchain is the bridge between your development machine and your target hardware. It includes a compiler, assembler, linker, and C library — all configured to produce binaries for a different architecture. The "why" behind choosing between building your own vs. using a pre-built toolchain comes down to three factors: **control, reproducibility, and ecosystem alignment**.

Building with `crosstool-NG` gives you surgical control over every detail — glibc vs. uClibc vs. musl, kernel headers version, threading model (NPTL vs. LinuxThreads), and even the exact GCC patch level. This is critical when your BSP requires a specific combination that no pre-built toolchain provides. However, it takes 30–60 minutes per build and demands deep knowledge of the target's hardware capabilities.

Pre-built Linaro toolchains, on the other hand, are the "batteries included" option. Linaro engineers optimize them for ARM Cortex-A and Cortex-R series, they're tested against real hardware, and you can download and use them in under five minutes. The trade-off: you're locked into Linaro's configuration choices. For most production projects, this is perfectly fine — Linaro's defaults are sane and well-tested. The real danger is mixing toolchains: building your kernel with one toolchain and your applications with another, which can lead to subtle ABI mismatches.

## Key Commands / Configuration / Code

### Building a Toolchain with crosstool-NG

First, install crosstool-NG and configure for ARM Cortex-A9:

```bash
# Clone and bootstrap crosstool-NG (v1.26.0 used here)
git clone https://github.com/crosstool-ng/crosstool-ng.git
cd crosstool-ng
./bootstrap
./configure --enable-local
make -j$(nproc)

# Create a build directory and configure
mkdir ../ct-ng-build && cd ../ct-ng-build
../crosstool-ng/ct-ng arm-cortexa9_neon-linux-gnueabihf

# Customize configuration (opens menuconfig)
../crosstool-ng/ct-ng menuconfig
```

Inside menuconfig, key settings to verify:
- **Paths and misc options**: Set `CT_LOCAL_TARBALLS_DIR` to a shared cache directory
- **Target options**: Ensure `CT_ARCH_ARM_TUPLE` is `arm-cortexa9_neon-linux-gnueabihf`
- **Toolchain options**: Enable `CT_CC_LANG_CXX` for C++ support
- **C-library**: Default glibc is fine; for smaller footprint, switch to musl

Then build (this takes 30–60 minutes):

```bash
# Build the toolchain (output in ~/x-tools/)
../crosstool-ng/ct-ng build
# Output path: ~/x-tools/arm-cortexa9_neon-linux-gnueabihf/
```

### Using a Pre-built Linaro Toolchain

Download and extract the Linaro GCC 7.5-2019.12 release:

```bash
# Download Linaro toolchain (ARMv7-A hard-float)
wget https://releases.linaro.org/components/toolchain/binaries/7.5-2019.12/arm-linux-gnueabihf/gcc-linaro-7.5.0-2019.12-x86_64_arm-linux-gnueabihf.tar.xz
tar -xf gcc-linaro-7.5.0-2019.12-x86_64_arm-linux-gnueabihf.tar.xz
export PATH=$PWD/gcc-linaro-7.5.0-2019.12-x86_64_arm-linux-gnueabihf/bin:$PATH

# Verify it works
arm-linux-gnueabihf-gcc --version
# Output: arm-linux-gnueabihf-gcc (Linaro GCC 7.5-2019.12) 7.5.0
```

### Test Program and Verification

Write a simple test to verify both toolchains produce working binaries:

```c
// test.c - Simple ARM test program
#include <stdio.h>
#include <unistd.h>

int main(void) {
    printf("Hello from ARM! PID: %d\n", getpid());
    return 0;
}
```

Compile with both toolchains and inspect:

```bash
# Compile with crosstool-NG toolchain
~/x-tools/arm-cortexa9_neon-linux-gnueabihf/bin/arm-cortexa9_neon-linux-gnueabihf-gcc \
    -static -o test_ctng test.c

# Compile with Linaro toolchain
arm-linux-gnueabihf-gcc -static -o test_linaro test.c

# Compare binaries
file test_ctng test_linaro
# Both should show: ELF 32-bit LSB executable, ARM, version 1 (SYSV), statically linked

# Check for ABI differences
readelf -A test_ctng | grep Tag_ABI_VFP_args
readelf -A test_linaro | grep Tag_ABI_VFP_args
# Both should show: Tag_ABI_VFP_args: VFP registers (hard-float ABI)
```

## Common Pitfalls & Gotchas

1. **Mismatched Kernel Headers**: When building with crosstool-NG, you must match the kernel headers version to the kernel you'll run. Using headers newer than your target kernel can introduce syscalls that don't exist, causing runtime `ENOSYS` errors. Always set `CT_KERNEL_LINUX_HEADERS_VERSION` to match your target kernel version.

2. **Hard-float vs. Soft-float ABI**: ARM has two incompatible floating-point ABIs. The Linaro toolchain above uses `arm-linux-gnueabihf` (hard-float), but if your target CPU lacks a hardware FPU, you need `arm-linux-gnueabi` (soft-float). Mixing them causes linker errors or silent corruption. Check your target's `/proc/cpuinfo` for `Features: fp` or `vfp`.

3. **Sysroot Pollution**: When using pre-built toolchains, the sysroot (where libraries and headers live) is fixed. If you need to add custom libraries, you must either rebuild the toolchain or use `--sysroot` carefully. A common mistake is installing libraries into `/usr/arm-linux-gnueabihf/lib` manually, which breaks when the toolchain is updated. Use a dedicated staging directory instead.

## Try It Yourself

1. **Build a minimal crosstool-NG toolchain targeting ARM Cortex-M4 (no MMU)**: Configure with `CT_ARCH_ARM_CORTEX_M4=y`, disable MMU support (`CT_ARCH_ARM_MMU=n`), and use `newlib` instead of glibc. This is what you'd use for bare-metal or FreeRTOS projects.

2. **Compare binary sizes**: Compile the test program with both toolchains using `-Os` (optimize for size) and `-O2` (optimize for speed). Use `size test_ctng test_linaro` to compare the `.text`, `.data`, and `.bss` sections. Which toolchain produces smaller code? Why?

3. **Verify ABI compatibility**: Write a small shared library that exports a function using `double` arguments. Compile it with the Linaro toolchain, then try to link it with an application compiled using the crosstool-NG toolchain. Does it work? Use `readelf -d` to check the `NEEDED` entries and `readelf -A` to confirm both use the same ABI tags.

## Next Up

Tomorrow, we'll tackle the U-Boot bootloader — building it from source, configuring for a specific board (BeagleBone Black), and writing boot scripts that actually boot a Linux kernel. We'll cover the boot flow, environment variables, and how to debug boot failures with early UART output.
