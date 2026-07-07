---
title: "Day 25: Creating a Custom BSP Layer: meta-mybsp"
date: 2026-07-07
tags: ["til", "yocto", "bsp", "custom-layer"]
---

## What I Explored Today

Today I built a complete Board Support Package (BSP) layer from scratch for a hypothetical ARM Cortex-A7 SoC. While Yocto ships with official BSP layers for reference boards (like `meta-raspberrypi` or `meta-ti`), real embedded products almost always require a custom BSP layer to handle non-discoverable hardware, custom kernel configurations, and board-specific device trees. I walked through the entire process: layer skeleton, machine configuration, kernel recipe append, device tree integration, and bootloader configuration.

## The Core Concept

A BSP layer in Yocto is not just a collection of kernel patches—it's a structured encapsulation of every board-specific decision. The `meta-mybsp` layer tells BitBake: "Here is how to build a kernel for this particular SoC, which device tree to use, which bootloader to flash, and which rootfs features to enable."

Why a dedicated BSP layer instead of cramming everything into `meta-custom`? Separation of concerns. Your application layer (`meta-myapp`) should never need to know about kernel config fragments or U-Boot patches. When you upgrade the kernel from 5.10 to 6.1, you only touch the BSP layer. When you change the rootfs filesystem type from ext4 to squashfs, you only touch the distro or image layer. This modularity is what makes Yocto maintainable at scale.

The key files in a BSP layer are:
- `conf/machine/<machine>.conf` — defines the machine architecture, kernel provider, serial console, and bootloader
- `recipes-kernel/linux/` — kernel recipe appends for defconfigs, patches, and device trees
- `recipes-bsp/u-boot/` — bootloader configuration
- `recipes-bsp/device-tree/` — custom device tree source files (if not bundled with kernel)

## Key Commands / Configuration / Code

### 1. Layer Skeleton

```bash
# Create the layer structure
mkdir -p meta-mybsp/conf/machine
mkdir -p meta-mybsp/recipes-kernel/linux
mkdir -p meta-mybsp/recipes-bsp/u-boot
mkdir -p meta-mybsp/recipes-bsp/device-tree
mkdir -p meta-mybsp/recipes-core/images

# Create layer.conf
cat > meta-mybsp/conf/layer.conf << 'EOF'
# We have a conf and classes directory, add BBFILES
BBPATH .= ":${LAYERDIR}"
BBFILES += "${LAYERDIR}/recipes-*/*/*.bb \
            ${LAYERDIR}/recipes-*/*/*.bbappend"

BBFILE_COLLECTIONS += "mybsp"
BBFILE_PATTERN_mybsp = "^${LAYERDIR}/"
BBFILE_PRIORITY_mybsp = "6"

# This layer depends on core and kernel layers
LAYERDEPENDS_mybsp = "core"
LAYERSERIES_COMPAT_mybsp = "kirkstone"
EOF
```

### 2. Machine Configuration

```bash
cat > meta-mybsp/conf/machine/myboard.conf << 'EOF'
# @TYPE: Machine
# @NAME: myboard
# @DESCRIPTION: Custom ARM Cortex-A7 board

# Target architecture
DEFAULTTUNE ?= "cortexa7thf-neon-vfpv4"
require conf/machine/include/arm/armv7a/tune-cortexa7.inc

# Kernel and bootloader
PREFERRED_PROVIDER_virtual/kernel ?= "linux-yocto"
PREFERRED_PROVIDER_virtual/bootloader ?= "u-boot"
PREFERRED_PROVIDER_u-boot ?= "u-boot"

# Serial console (ttyS0 at 115200 baud)
SERIAL_CONSOLES ?= "115200;ttyS0"
SERIAL_CONSOLES_CHECK = "${SERIAL_CONSOLES}"

# Kernel image type (zImage for ARM)
KERNEL_IMAGETYPE = "zImage"
KERNEL_DEVICETREE = "myboard.dtb"

# Root filesystem type
IMAGE_FSTYPES += "tar.bz2 ext4"

# U-Boot configuration
UBOOT_MACHINE = "myboard_defconfig"
UBOOT_ENTRYPOINT = "0x82000000"
UBOOT_LOADADDRESS = "0x82000000"

# Append to MACHINE_FEATURES
MACHINE_FEATURES += "rtc wifi bluetooth"
EOF
```

### 3. Kernel Recipe Append

```bash
cat > meta-mybsp/recipes-kernel/linux/linux-yocto_%.bbappend << 'EOF'
# Override kernel source to use our custom tree
# In practice, you'd use a git repo or tarball
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Custom defconfig for our board
SRC_URI += "file://defconfig \
            file://myboard.dts \
            file://0001-myboard-gpio-fix.patch"

# Device tree compilation
do_configure:append() {
    # Copy our custom device tree into kernel source
    cp ${WORKDIR}/myboard.dts ${S}/arch/arm/boot/dts/
}

do_compile:append() {
    # Ensure our device tree is built
    oe_runmake dtbs
}
EOF
```

### 4. Custom Device Tree (simplified)

```dts
// meta-mybsp/recipes-kernel/linux/files/myboard.dts
/dts-v1/;
#include "imx6ul.dtsi"

/ {
    model = "MyCustomBoard";
    compatible = "mycompany,myboard", "fsl,imx6ul";

    chosen {
        stdout-path = &uart1;
    };

    memory@80000000 {
        device_type = "memory";
        reg = <0x80000000 0x20000000>; /* 512 MB */
    };

    &uart1 {
        status = "okay";
    };

    &usdhc1 {
        pinctrl-names = "default";
        status = "okay";
        bus-width = <4>;
    };
};
```

### 5. Building

```bash
# Add layer to bblayers.conf
bitbake-layers add-layer ../meta-mybsp

# Build the image
MACHINE=myboard bitbake core-image-minimal

# Verify output
ls tmp/deploy/images/myboard/
# Should show: zImage, myboard.dtb, u-boot.bin, core-image-minimal-myboard.tar.bz2
```

## Common Pitfalls & Gotchas

1. **Missing `MACHINE` variable during build**: If you forget to set `MACHINE=myboard`, BitBake defaults to `qemuarm` and your custom machine config is ignored. Always export `MACHINE` in your build script or set it in `local.conf`.

2. **Device tree not included in kernel build**: The `KERNEL_DEVICETREE` variable in the machine config only works if the `.dts` file is actually compiled. If your device tree is not in the kernel source tree, you must add it via `SRC_URI` and ensure `do_compile` appends call `oe_runmake dtbs`. Otherwise, you'll get a "No rule to make target" error.

3. **Layer priority conflicts**: If another layer (like `meta-raspberrypi`) has a higher `BBFILE_PRIORITY` and also provides a `linux-yocto` bbappend, your changes may be silently overridden. Always check with `bitbake-layers show-recipes linux-yocto` to verify which layer's version is being used.

## Try It Yourself

1. **Create a minimal BSP layer** for a virtual ARM machine (qemuarm). Add a machine config that sets `SERIAL_CONSOLES = "115200;ttyAMA0"` and builds `core-image-minimal`. Verify the output with `runqemu`.

2. **Add a custom kernel config fragment** to enable a GPIO driver. Create `recipes-kernel/linux/files/gpio.cfg` with `CONFIG_GPIO_SYSFS=y` and add it to `SRC_URI` in your bbappend. Verify with `bitbake -c kernel_configcheck linux-yocto`.

3. **Integrate a custom U-Boot board file**: Create `recipes-bsp/u-boot/u-boot_%.bbappend` that adds a patch for a new board defconfig. Build with `bitbake u-boot` and verify the `u-boot.bin` is in `tmp/deploy/images/myboard/`.

## Next Up

Tomorrow we tackle CI/CD for Yocto: automating builds with KAS, containerizing the build environment with Docker, and running everything in GitHub Actions. No more "works on my machine" excuses.
