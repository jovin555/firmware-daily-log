---
title: "Day 17: Device Tree in Yocto: KERNEL_DEVICETREE & DTBO"
date: 2026-06-29
tags: ["til", "devicetree", "yocto", "kernel", "dtbo"]
---

## What I Explored Today

Today I dug into how Yocto handles Device Tree compilation and overlay integration at the kernel level. The two key variables—`KERNEL_DEVICETREE` and `KERNEL_DEVICETREE_BUNDLE`—control which `.dtb` and `.dtbo` files get built and installed into the kernel image. I also looked at how to include Device Tree Overlays (DTBOs) in a Yocto recipe, which is essential when you're shipping a board that supports runtime reconfiguration via overlays.

## The Core Concept

Yocto's kernel build system (`kernel.bbclass`) automates Device Tree compilation using the kernel's own build infrastructure. When you set `KERNEL_DEVICETREE` in a machine configuration file, the build system invokes `make dtbs` for the specified targets. The resulting `.dtb` files are installed into the kernel's boot directory (`/boot/devicetree-<kernel-version>/`).

The critical insight: Yocto does **not** compile Device Tree files from scratch. It relies on the kernel source tree's `arch/arm/boot/dts/` (or `arch/arm64/boot/dts/`) directory structure. If your `.dts` file isn't in the kernel tree, you must add it via a kernel patch or a `devicetree.bbappend` recipe.

For overlays, the `KERNEL_DEVICETREE_BUNDLE` variable (or manually listing `.dtbo` files) tells the build system to compile `.dts` files with the `-@` flag (symbol generation) and install the resulting `.dtbo` files. This is crucial for systems that use `configfs` to apply overlays at runtime.

## Key Commands / Configuration / Code

### 1. Machine Configuration (e.g., `meta-myboard/conf/machine/myboard.conf`)

```bitbake
# Include base DTBs
KERNEL_DEVICETREE = " \
    myboard.dtb \
    myboard-rev2.dtb \
"

# Include overlays (DTBOs)
KERNEL_DEVICETREE += " \
    myboard-spi1.dtbo \
    myboard-uart2.dtbo \
"

# If using kernel 5.10+, you can use the bundle mechanism
# KERNEL_DEVICETREE_BUNDLE = "1"
```

**Explanation**: The first assignment sets the baseline DTBs. The `+=` appends overlay targets. The commented `KERNEL_DEVICETREE_BUNDLE` is a newer feature that automatically builds all `.dts` files in the kernel tree that have the `-overlay.dts` suffix.

### 2. Adding Custom Device Trees via Recipe Append

Create `recipes-kernel/linux/linux-yocto_%.bbappend` in your layer:

```bitbake
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI += " \
    file://myboard.dts \
    file://myboard-spi1-overlay.dts \
"

do_configure:append() {
    # Copy custom DTS files into kernel source tree
    cp ${WORKDIR}/*.dts ${S}/arch/arm64/boot/dts/mycompany/
}

do_compile:append() {
    # Ensure overlays are compiled with symbols
    oe_runmake dtbs
}
```

**Explanation**: The `FILESEXTRAPATHS` ensures Yocto finds your `.dts` files. The `do_configure:append` copies them into the kernel tree. The `do_compile:append` forces a rebuild of all DTBs after the copy.

### 3. Verifying Installed DTBs in the Root Filesystem

After building, check the image contents:

```bash
# List installed DTBs in the rootfs
ls -la tmp/work/myboard-poky-linux/linux-yocto/*/image/lib/firmware/devicetree/
# or for kernel boot partition:
ls -la tmp/deploy/images/myboard/*.dtb
```

**Expected output**: You should see both `.dtb` and `.dtbo` files. Overlays typically go into `/lib/firmware/devicetree/overlays/` in the rootfs.

### 4. Runtime Overlay Application (on target)

```bash
# On the target board (assuming overlays are installed)
mkdir -p /configfs/device-tree/overlays/spi1
cat /lib/firmware/devicetree/overlays/myboard-spi1.dtbo > /configfs/device-tree/overlays/spi1/dtbo
```

**Explanation**: This uses the kernel's configfs interface to apply an overlay at runtime. The overlay file must have been compiled with symbols (`-@` flag), which Yocto does automatically when you list `.dtbo` files in `KERNEL_DEVICETREE`.

## Common Pitfalls & Gotchas

1. **Missing `-@` flag for overlays**: If your DTBO doesn't compile with symbols, the kernel will reject it with "overlay must have symbols". Ensure your `.dts` file has `/plugin/;` at the top and that Yocto's kernel build system detects it as an overlay. The safest approach is to name the file with `-overlay.dts` suffix (e.g., `myboard-spi1-overlay.dts`) and use `KERNEL_DEVICETREE_BUNDLE = "1"`.

2. **Path mismatches**: Yocto expects the DTS path relative to the kernel tree's `arch/*/boot/dts/`. If you put your custom `.dts` in a subdirectory (e.g., `mycompany/`), you must reference it as `mycompany/myboard.dtb` in `KERNEL_DEVICETREE`. Forgetting this leads to "no rule to make target" errors during `do_compile`.

3. **Overlays not installed to rootfs**: By default, Yocto installs DTBs to the kernel boot partition, not the root filesystem. If your runtime overlay mechanism expects files in `/lib/firmware/`, you need to add a custom install step or use `IMAGE_INSTALL:append = " kernel-devicetree"` to ensure the package is included in the rootfs.

## Try It Yourself

1. **Add a custom overlay to an existing machine**: Take any Yocto BSP layer (e.g., `meta-raspberrypi`), create a simple overlay that enables an unused SPI bus, and add it to the machine configuration. Verify the `.dtbo` appears in the deploy directory.

2. **Debug a missing DTB**: Intentionally set `KERNEL_DEVICETREE` to a non-existent path, run `bitbake linux-yocto`, and examine the error log. Fix the path by checking the kernel tree's `arch/arm64/boot/dts/` structure.

3. **Build a kernel with bundled overlays**: Set `KERNEL_DEVICETREE_BUNDLE = "1"` in your machine config, then inspect the resulting kernel image (`arch/arm64/boot/Image`) to confirm overlays are appended. Use `dtc -I dtb -O dts` to dump the kernel and look for overlay fragments.

## Next Up

Tomorrow, we'll compare Device Tree handling in Zephyr vs Linux. While both use DTS syntax, the build systems, runtime models, and overlay mechanisms differ significantly—especially in how Zephyr's devicetree.h macros interact with the C preprocessor. We'll explore the key differences that matter when porting drivers between the two ecosystems.
