---
title: "Day 24: OTA with Yocto: SWUpdate & A/B Image Strategy"
date: 2026-07-06
tags: ["til", "yocto", "ota", "swupdate"]
---

## What I Explored Today

Today I integrated SWUpdate into a Yocto-based embedded Linux build and implemented a full A/B update strategy for a production device. The goal was to move beyond flashing images over JTAG or USB and enable robust over-the-air updates with automatic rollback on failure. I worked through the SWUpdate recipe integration, dual-copy partition layout, bootloader integration with U-Boot, and the signing/verification pipeline. This is the foundation for any IoT or edge device that needs to update itself in the field without bricking.

## The Core Concept

OTA updates in embedded systems are fundamentally different from desktop or server updates. You cannot assume a stable network connection, a user to intervene, or a recovery console. The device must update itself atomically and recover if something goes wrong mid-update.

The A/B strategy solves this by maintaining two root filesystem partitions: one active (A) and one inactive (B). The bootloader selects which partition to boot. During an update, SWUpdate writes the new image to the inactive partition, marks it as the next boot target, and reboots. If the new system fails to boot or the application crashes, the bootloader detects the failure and falls back to the previous partition.

SWUpdate is the de facto open-source solution for this in the Yocto ecosystem. It handles image streaming, integrity verification, signature validation, and post-update scripts. Combined with a bootloader that supports redundant boot logic (U-Boot's `bootcount` mechanism), you get a production-grade OTA pipeline.

## Key Commands / Configuration / Code

### 1. Adding SWUpdate to Your Yocto Build

In `conf/local.conf` or your distro config:

```bitbake
# Enable SWUpdate and its tools
IMAGE_INSTALL:append = " swupdate swupdate-www"

# Required for signed updates
PACKAGECONFIG:append:pn-swupdate = " signed-images"

# Set the hardware compatibility string (must match swupdate.cfg)
SWUPDATE_HW_COMPATIBILITY = "myboard-rev2"
```

### 2. Partition Layout (WIC Kickstart File)

Create `recipes-bsp/images/myboard.wks`:

```
# Boot partition (vfat, 64MB)
part /boot --source bootimg-partition --fstype=vfat --label boot --size 64M

# Root A (ext4, 512MB)
part / --source rootfs --fstype=ext4 --label rootfs_a --size 512M --align 4096

# Root B (ext4, 512MB)
part / --source rootfs --fstype=ext4 --label rootfs_b --size 512M --align 4096

# Data partition (ext4, 256MB)
part /data --fstype=ext4 --label data --size 256M --align 4096

# Bootloader
bootloader --ptable gpt --append="console=ttyS0,115200 rootwait"
```

### 3. SWUpdate Configuration (`recipes-support/swupdate/swupdate/swupdate.cfg`)

```c
globals : {
    hw_compatibility = "myboard-rev2";
    bootloader = "uboot";
    bootloader_extra = "bootcount";
};

software : {
    version = "2.1.0";
    description = "Production firmware for myboard";

    images : (
        {
            filename = "core-image-base-myboard.ext4";
            device = "/dev/mmcblk0p2";  // rootfs_a
            type = "raw";
            compressed = "zlib";
            sha256 = "auto";
        }
    );

    scripts : (
        {
            filename = "post_update.sh";
            type = "postinstall";
            sha256 = "auto";
        }
    );
};
```

### 4. U-Boot Integration for A/B Boot

In your U-Boot environment (set via `fw_env.config` or boot script):

```bash
# Bootcount mechanism: max 3 attempts before fallback
setenv bootcount_limit 3
setenv bootcount 0

# Determine which partition to boot
if test "${bootpart}" = "rootfs_a"; then
    setenv bootpart_next "rootfs_b"
    setenv mmcdev 0
    setenv mmcpart 2
else
    setenv bootpart_next "rootfs_a"
    setenv mmcdev 0
    setenv mmcpart 3
fi

# Boot the kernel
ext4load mmc ${mmcdev}:${mmcpart} ${kernel_addr_r} /boot/zImage
ext4load mmc ${mmcdev}:${mmcpart} ${fdt_addr_r} /boot/devicetree.dtb
bootz ${kernel_addr_r} - ${fdt_addr_r}
```

### 5. Post-Update Script (marks boot successful)

Create `recipes-support/swupdate/swupdate/post_update.sh`:

```bash
#!/bin/sh
# Called by SWUpdate after writing the image
# Reset bootcount so the new partition boots first time
fw_setenv bootcount 0
fw_setenv bootpart ${bootpart_next}
echo "SWUpdate: next boot will use ${bootpart_next}"
```

### 6. Building and Signing the Update Image

```bash
# Build the SWUpdate .swu file
bitbake swupdate-image

# Sign the update (RSA key pair)
openssl dgst -sha256 -sign private.pem -out core-image-base.swu.sig core-image-base.swu

# Verify on device (SWUpdate does this automatically)
swupdate -v -i core-image-base.swu -k public.pem
```

## Common Pitfalls & Gotchas

1. **Bootloader environment persistence** — If your U-Boot environment is stored on the same eMMC as the rootfs, a full flash erase can wipe it. Always keep a redundant copy in SPI flash or use a separate environment partition. I lost a board this way when the `fw_setenv` command silently failed after a bad flash.

2. **Filesystem label mismatch** — The WIC kickstart uses labels like `rootfs_a`, but SWUpdate's `device` field points to a raw block device. If the partition numbering changes (e.g., after resizing), the update writes to the wrong partition. Use `by-label` symlinks in your SWUpdate config: `device = "/dev/disk/by-label/rootfs_a"`.

3. **Bootcount not reset on successful boot** — If your init system doesn't reset `bootcount` to 0 after a successful boot, the device will fall back after 3 boots even if everything is fine. Add a systemd service or init script that runs `fw_setenv bootcount 0` once the application stack is healthy.

## Try It Yourself

1. **Add SWUpdate to your existing Yocto build** — Add `IMAGE_INSTALL:append = " swupdate"` to your local.conf, rebuild, and verify the `swupdate` binary is on the target. Run `swupdate -h` to see available options.

2. **Create a dual-partition WIC image** — Write a `.wks` file with two rootfs partitions and a data partition. Build the image, flash it to an SD card, and manually switch between partitions by changing the U-Boot `bootpart` variable.

3. **Sign and verify an update** — Generate an RSA key pair, build a minimal `.swu` file with a single rootfs image, sign it, and then verify the signature on the target using `swupdate -k public.pem -i update.swu` (use `-v` for verbose output).

## Next Up

Tomorrow, we'll dive into **Creating a Custom BSP Layer: meta-mybsp** — how to structure a board support package layer from scratch, including kernel configuration, device tree overlays, and bootloader recipes that are portable across Yocto releases.
