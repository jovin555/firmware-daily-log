---
title: "Day 16: Device Tree in Yocto: KERNEL_DEVICETREE"
date: 2026-06-28
tags: ["til", "yocto", "devicetree", "kernel"]
---

## What I Explored Today

Today I dug into how Yocto handles Device Tree compilation and deployment through the `KERNEL_DEVICETREE` variable. After weeks of building kernels that booted on reference platforms, I hit a wall when my custom board's `.dts` file wasn't being compiled or installed into the boot partition. The fix wasn't in the kernel config or the device tree source itself—it was in my Yocto recipe metadata. Understanding `KERNEL_DEVICETREE` is the difference between a kernel that boots and one that silently hangs because no matching `dtb` was deployed.

## The Core Concept

Device Tree (DT) is the hardware description language that tells the Linux kernel what peripherals exist, their memory addresses, interrupts, and clock configurations. In a Yocto build, the kernel recipe (`linux-yocto` or custom) compiles `.dts` files into `.dtb` (Device Tree Blob) binaries. But the kernel source tree often contains hundreds of device trees for every supported SoC and board.

The `KERNEL_DEVICETREE` variable is your filter. It tells the build system: "Of all the `.dts` files in the kernel tree, only compile and deploy these specific ones." Without it, you get either nothing (if you're using a custom kernel recipe) or every device tree in the kernel tree (wasting build time and storage). For production systems, you want exactly one `.dtb` per board variant.

The variable is typically set in your machine configuration file (`conf/machine/<machine>.conf`) or in a distribution policy. It accepts a space-separated list of device tree paths relative to the kernel's `arch/<arch>/boot/dts/` directory, with or without the `.dts` or `.dtb` extension.

## Key Commands / Configuration / Code

**Setting KERNEL_DEVICETREE in your machine config:**

```bitbake
# conf/machine/myboard.conf
# Include both base board and overlay for production variant
KERNEL_DEVICETREE = " \
    vendor/myboard.dtb \
    vendor/myboard-pcie.dtb \
"

# For ARM64, paths are relative to arch/arm64/boot/dts/
# For ARM32, relative to arch/arm/boot/dts/
```

**Verifying what gets built:**

```bash
# After a build, check the deploy directory
ls -la tmp/deploy/images/myboard/*.dtb

# You should see only the files you specified
# Expected output:
# myboard.dtb
# myboard-pcie.dtb
```

**Custom device tree in a kernel recipe append:**

```bitbake
# recipes-kernel/linux/linux-yocto_%.bbappend
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://myboard.dts"

# Ensure the custom DTS is compiled and deployed
KERNEL_DEVICETREE:append = " myboard.dtb"
```

**Device tree overlays (DTBO):**

```bitbake
# For overlays, set the variable differently
KERNEL_DEVICETREE = " \
    vendor/myboard.dtb \
    vendor/myboard-overlay.dtbo \
"

# Overlays require CONFIG_OF_OVERLAY=y in kernel config
```

**Checking the compiled output in the kernel build directory:**

```bash
# Inspect the kernel build artifacts
find tmp/work/myboard-poky-linux/linux-yocto/*/git/arch/arm64/boot/dts/vendor/ -name "*.dtb"
# Only the ones in KERNEL_DEVICETREE will be present
```

**Using device tree includes in your custom DTS:**

```dts
// myboard.dts
/dts-v1/;
#include "vendor/soc-common.dtsi"

/ {
    model = "My Custom Board";
    compatible = "vendor,myboard", "vendor,soc";

    &uart0 {
        status = "okay";
        clock-frequency = <1843200>;
    };
};
```

## Common Pitfalls & Gotchas

**1. Path Mismatch Between Kernel Versions**
The directory structure under `arch/*/boot/dts/` changes between kernel versions. In 5.x, many vendors had flat directories. In 6.x, they moved to vendor subdirectories. If you specify `myboard.dtb` but the kernel has it at `vendor/myboard.dtb`, the build silently skips it. Always verify the actual path in your kernel source tree.

**2. Forgetting to Set KERNEL_DEVICETREE in the Machine Config**
If you set it in a `.bbappend` or local.conf but your machine config doesn't inherit it, the variable may be empty. The kernel recipe's `do_deploy` task will then deploy nothing. I've spent hours debugging why a freshly built image had no `.dtb` files—only to find the variable was unset.

**3. Device Tree Overlays Require Special Handling**
Overlays (`.dtbo`) need `KERNEL_DEVICETREE` to include them, but they also need `KERNEL_DEVICETREE_OVERLAY` set to "1" in some Yocto versions. Additionally, the kernel must have `CONFIG_OF_OVERLAY=y`. Without it, the overlay compiles but the kernel can't apply it at runtime.

**4. Multiple Device Trees Increase Build Time**
If you accidentally set `KERNEL_DEVICETREE` to a wildcard pattern or include all vendor DTs, the kernel build compiles hundreds of device trees. For a clean build, this adds 5-10 minutes. Always be explicit.

## Try It Yourself

1. **Inspect your current machine config**: Find your machine's `.conf` file and check if `KERNEL_DEVICETREE` is set. If not, add a single device tree path for your board. Rebuild the kernel and verify the `.dtb` appears in `tmp/deploy/images/<machine>/`.

2. **Add a custom device tree**: Create a minimal `.dts` file that includes the SoC's `.dtsi`, enables a UART, and sets a custom `model` string. Add it via `SRC_URI` in a kernel `.bbappend`, set `KERNEL_DEVICETREE` to include it, and verify the compiled DTB contains your changes using `dtc -I dtb -O dts myboard.dtb | grep model`.

3. **Build a device tree overlay**: Write a simple overlay that disables an unused I2C controller. Add it to `KERNEL_DEVICETREE` as a `.dtbo`, ensure `CONFIG_OF_OVERLAY=y` in your kernel config, and verify the overlay compiles without errors.

## Next Up

Tomorrow we tackle U-Boot integration: how `UBOOT_MACHINE` selects the correct board configuration, and how to chain the bootloader build with your kernel and device tree into a bootable image. We'll cover the `u-boot.inc` recipe flow and common pitfalls when your U-Boot doesn't find the DTB.
