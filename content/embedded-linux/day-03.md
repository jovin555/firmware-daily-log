---
title: "Day 03: U-Boot Bootloader: Build, Configure & Boot Scripts"
date: 2026-06-15
tags: ["til", "embedded-linux", "uboot", "bootloader"]
---

## What I Explored Today

Today I dove into U-Boot, the "Universal Bootloader" that's the de facto standard for embedded Linux systems. I built it from source for a QEMU ARM target, configured the device tree, and wrote a boot script that loads a kernel and rootfs from TFTP. The goal was to understand the full boot flow from power-on to kernel handoff, not just copy-paste a defconfig. I came away with a much clearer picture of how U-Boot stages work, where the device tree blob (DTB) fits in, and why boot scripts are the glue that makes embedded systems boot reliably.

## The Core Concept

U-Boot is a two-stage bootloader. The first stage (SPL, or Secondary Program Loader) initializes minimal hardware—clock, DRAM, serial console—then loads the full U-Boot image (u-boot.img) into memory. The full U-Boot then reads its environment, parses boot scripts, and ultimately loads the Linux kernel and DTB into RAM before jumping to the kernel entry point.

The "why" is critical: embedded systems have no BIOS. U-Boot provides the hardware abstraction layer that Linux depends on. Without it, you'd need to hardcode memory timings, pin muxing, and peripheral initialization into the kernel itself. By handling these in the bootloader, you keep the kernel portable across board revisions.

The boot script (`boot.scr`) is a compiled U-Boot script that automates the boot sequence. Instead of typing commands at the U-Boot prompt every time, you store a script in flash or load it over the network. This is what production systems use—no serial console required.

## Key Commands / Configuration / Code

### Building U-Boot for QEMU ARM (vexpress-a9)

```bash
# Clone the official U-Boot repository
git clone https://source.denx.de/u-boot/u-boot.git
cd u-boot

# Check out a stable release (v2024.01 as of this writing)
git checkout v2024.01

# Clean build artifacts from any previous build
make distclean

# Configure for the QEMU ARM Versatile Express target
make vexpress_ca9x4_defconfig

# Build U-Boot (SPL + full U-Boot + tools)
make -j$(nproc)
```

After building, you'll have:
- `u-boot` — ELF binary for debugging
- `u-boot.bin` — raw binary for flashing
- `u-boot.img` — full U-Boot with header (loaded by SPL)
- `tools/mkimage` — tool to create boot scripts

### Creating a Boot Script

The boot script is a text file compiled with `mkimage`. Here's a typical one for TFTP boot:

```bash
# File: boot.cmd
# Set up network (assumes DHCP or static IP configured in environment)
setenv autoload no
dhcp

# Load kernel, device tree, and rootfs from TFTP server
tftp ${kernel_addr_r} zImage
tftp ${fdt_addr_r} vexpress-v2p-ca9.dtb
tftp ${ramdisk_addr_r} rootfs.cpio.uboot

# Set bootargs for the kernel (console, root device, init)
setenv bootargs console=ttyAMA0,115200 root=/dev/ram0 rw init=/init

# Boot the kernel with device tree and initramfs
bootz ${kernel_addr_r} ${ramdisk_addr_r} ${fdt_addr_r}
```

Compile it:

```bash
# -A arm: architecture ARM
# -O linux: operating system
# -T script: type is script
# -C none: no compression
# -n "Boot script": image name (arbitrary)
# -d boot.cmd: input file
# boot.scr: output file
mkimage -A arm -O linux -T script -C none -n "Boot script" -d boot.cmd boot.scr
```

### Running U-Boot in QEMU

```bash
# Run QEMU with U-Boot as the -kernel (acts as firmware)
qemu-system-arm -M vexpress-a9 \
    -kernel u-boot \
    -nographic \
    -netdev user,id=net0,tftp=/path/to/tftp/root \
    -device virtio-net-device,netdev=net0
```

At the U-Boot prompt, load and execute the boot script:

```
# Load boot.scr from TFTP
U-Boot> tftp ${loadaddr} boot.scr
# Source (execute) the script
U-Boot> source ${loadaddr}
```

## Common Pitfalls & Gotchas

1. **Address conflicts between load addresses** — U-Boot defines `kernel_addr_r`, `fdt_addr_r`, `ramdisk_addr_r`, and `scriptaddr` in its environment. These are board-specific. If you load the kernel to `0x60000000` but the DTB overlaps at `0x61000000` and the kernel is 20MB, you'll corrupt the DTB. Always check the default addresses with `printenv` and ensure your load regions don't overlap. For vexpress-a9, typical addresses are `0x60000000` for kernel, `0x61000000` for FDT, `0x62000000` for ramdisk.

2. **mkimage not found or wrong architecture** — The `mkimage` tool is built as part of U-Boot. If you run `make` without building tools, you won't have it. Use `make tools-only` if you only need the host tools. Also, ensure you use the correct `-A` flag (arm, arm64, x86, etc.) matching your target. An ARM script on an x86 U-Boot will fail silently.

3. **DTB mismatch with kernel** — The device tree must match the kernel version and board revision. Using a vexpress-v2p-ca9.dtb from kernel 5.10 with a 6.6 kernel may work, but using a DTB for a different board (e.g., vexpress-v2p-ca15) will cause the kernel to panic immediately. Always compile the DTB from the same kernel source tree you're booting.

## Try It Yourself

1. **Build U-Boot for a different QEMU target** — Try `make qemu_arm64_defconfig` and build for ARM64. Note the differences in the build output (e.g., no SPL by default). Boot it with `qemu-system-aarch64 -M virt -cpu cortex-a57`.

2. **Write a boot script that falls back to MMC** — Modify `boot.cmd` to first try loading from MMC (`mmc dev 0; ext4load mmc 0:1 ${kernel_addr_r} /boot/zImage`), and if that fails, fall back to TFTP. Use `if` / `else` / `fi` in U-Boot scripting.

3. **Debug a boot failure** — Intentionally corrupt the DTB by loading it to an overlapping address. Observe the kernel panic message. Then fix the address and verify the boot succeeds. This teaches you to read U-Boot's memory map.

## Next Up

Tomorrow I'll explore the U-Boot environment in depth: persistent variables, the `env` command family, scripting with `if`/`then`/`else`, and how to create a custom boot menu. Understanding the environment is what separates a U-Boot user from a U-Boot integrator.
