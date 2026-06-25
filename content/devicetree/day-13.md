---
title: "Day 13: Runtime Overlays: configfs & dtoverlay"
date: 2026-06-25
tags: ["til", "devicetree", "configfs", "dtoverlay", "runtime"]
---

## What I Explored Today

Today I dove into the two primary mechanisms for applying Device Tree overlays at runtime on Linux systems: the `configfs` interface (used on mainline kernels) and the `dtoverlay` utility (the Raspberry Pi ecosystem's approach). While both achieve the same goal—injecting overlay data into the live tree without a reboot—their architectures, kernel dependencies, and user-space APIs differ significantly. I built a test rig with an I2C EEPROM overlay to compare both methods end-to-end.

## The Core Concept

Why runtime overlays? In production embedded systems, you often need to reconfigure hardware without a full reboot. Think hot-pluggable expansion boards, FPGA reconfiguration that changes the bus topology, or field-upgradable sensor arrays. Rebooting a headless industrial controller might take 30 seconds—unacceptable for uptime-critical applications.

The kernel maintains a single, global Device Tree that is immutable once booted. Overlays work by applying a "diff" to that tree: they add new nodes, update properties, or change status from `disabled` to `okay`. The kernel's OF (Open Firmware) overlay system handles the dynamic memory allocation, symbol resolution, and bus rescanning.

Two user-space interfaces emerged:
- **configfs** (`/sys/kernel/config/device-tree/overlays/`): A filesystem-based API where you create a directory, write the overlay `.dtbo` blob, and trigger application. This is the mainline kernel's standard.
- **dtoverlay** (Raspberry Pi): A userspace tool that wraps `configfs` or the proprietary `bcm2835-v4l2` overlay mechanism, adding convenience features like parameter parsing and dependency resolution.

## Key Commands / Configuration / Code

### 1. configfs Method (Mainline Linux)

First, ensure `CONFIG_OF_OVERLAY` and `CONFIG_CONFIGFS_FS` are enabled in your kernel. Mount configfs if not already mounted:

```bash
# Mount configfs (usually at /sys/kernel/config)
mount -t configfs configfs /sys/kernel/config

# Verify the overlay directory exists
ls /sys/kernel/config/device-tree/overlays/
```

Now apply an overlay. We'll use a simple I2C EEPROM overlay (assume `eeprom.dtbo` is compiled):

```bash
# Create a new overlay slot (name is arbitrary)
mkdir /sys/kernel/config/device-tree/overlays/my-eeprom

# Write the overlay binary blob
cat eeprom.dtbo > /sys/kernel/config/device-tree/overlays/my-eeprom/dtbo

# Check for errors (dmesg will show success or failure)
dmesg | tail -5
# Expected: "OF: overlay: apply changes for 'my-eeprom'"

# Verify the new node appeared in /proc/device-tree
ls /proc/device-tree/i2c@7e804000/eeprom@50/
```

To remove the overlay:

```bash
# Simply rmdir the overlay slot
rmdir /sys/kernel/config/device-tree/overlays/my-eeprom

# dmesg will show: "OF: overlay: destroy changes for 'my-eeprom'"
# The kernel removes the nodes and unbinds any drivers
```

### 2. dtoverlay Method (Raspberry Pi / Raspberry Pi OS)

On Raspberry Pi, `dtoverlay` is the preferred tool. It handles the configfs details and adds parameter support:

```bash
# List available overlays (compiled .dtbo files in /boot/overlays/)
dtoverlay -a | grep i2c

# Apply an overlay with parameters
dtoverlay i2c-rtc ds1307=1
# This applies /boot/overlays/i2c-rtc.dtbo with addr=0x68 param

# Check what's applied
dtoverlay -l
# Output: "0: i2c-rtc  ds1307=1"

# Remove the overlay
dtoverlay -r i2c-rtc
```

The magic is in the overlay source. Here's a minimal I2C EEPROM overlay (`eeprom.dts`):

```dts
/dts-v1/;
/plugin/;

/ {
    compatible = "brcm,bcm2835";

    fragment@0 {
        target = <&i2c1>;
        __overlay__ {
            #address-cells = <1>;
            #size-cells = <0>;
            eeprom@50 {
                compatible = "atmel,24c02";
                reg = <0x50>;
                pagesize = <8>;
                status = "okay";
            };
        };
    };
};
```

Compile it:

```bash
dtc -@ -I dts -O dtb -o eeprom.dtbo eeprom.dts
```

The `-@` flag is critical—it generates the overlay symbols table that the kernel needs for dynamic resolution.

## Common Pitfalls & Gotchas

1. **Missing `-@` flag during compilation**: Without `-@`, the `.dtbo` lacks the symbols table. The kernel will reject the overlay with `-EINVAL` and a cryptic `overlay: failed to resolve tree` in dmesg. Always compile overlays with `-@`.

2. **Configfs overlay directory naming**: The directory name under `/sys/kernel/config/device-tree/overlays/` becomes the overlay's "label". If you create a directory with a name that conflicts with an existing overlay (e.g., same label), the kernel will refuse to apply the new one. Use unique, descriptive names.

3. **Driver probe order after overlay application**: When you apply an overlay, the kernel triggers a bus rescan. However, if the overlay adds a device that depends on a parent driver that hasn't probed yet (e.g., an I2C device on a bus that's still `disabled`), the child device won't bind. Always ensure parent nodes are `status = "okay"` before applying child overlays.

## Try It Yourself

1. **Compile and apply a GPIO-key overlay via configfs**: Write a simple overlay that adds a GPIO button (e.g., `gpio-keys` on pin 17). Compile with `-@`, apply via configfs, and verify the input device appears in `/dev/input/`. Remove it and confirm the device disappears.

2. **Use dtoverlay to toggle an SPI device**: On a Raspberry Pi, apply the `spi-gpio35-35` overlay to enable a software SPI bus. Use `dtoverlay -l` to list active overlays, then remove it. Check `/dev/spidev*` before and after.

3. **Debug a failed overlay application**: Intentionally compile an overlay without `-@`, try to apply it via configfs, and capture the dmesg output. Then fix the compilation and reapply. Note the error message format—this will save you hours in production.

## Next Up

Tomorrow we tackle **Pinmux & Pincontrol: Configuring Pin Functions via DT**—how to map those abstract overlay nodes to actual physical pins on the SoC, and why `pinctrl-0` and `pinctrl-names` are the secret sauce behind every working peripheral.
