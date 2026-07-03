---
title: "Day 21: Full Review & Project: DT Overlay for a Custom Sensor"
date: 2026-07-03
tags: ["til", "devicetree", "review", "project", "overlay"]
---

## What I Explored Today

Today I pulled together everything from the past three weeks into a single, real-world project: writing a complete Device Tree overlay for a custom environmental sensor (a BME280 on I2C bus 1, with an interrupt pin for data-ready signaling). This isn't a trivial "hello world" overlay — it requires proper pinmux, interrupt mapping, regulator references, and a compatible driver binding. I compiled, applied, and tested the overlay on a BeagleBone Black running Linux 6.1, and I'll walk through every step, including the inevitable debugging session when the interrupt didn't fire.

## The Core Concept

An overlay is not just a fragment of a Device Tree — it's a *targeted modification* to the live tree. The kernel's `configfs` interface (`/sys/kernel/config/device-tree/overlays`) treats each overlay as a separate object that can be loaded and unloaded at runtime. The critical insight is that an overlay must resolve its phandles (references to nodes in the base tree) at load time, which means the base tree must already have those nodes defined. For a custom sensor, you typically need:

- An I2C or SPI bus node (already in the base tree)
- A GPIO controller for the interrupt pin
- A regulator (often a fixed regulator for VDD)
- The sensor's compatible string, which must match a driver in the kernel

The overlay's job is to add a child node to the bus, link it to the interrupt controller, and optionally enable any needed pinmux or regulators. The kernel's `of_overlay_apply()` function then merges this into the live tree, triggering driver probing if the device is present.

## Key Commands / Configuration / Code

Here's the complete overlay for a BME280 on i2c-1 (pins P9_17 and P9_18 on BBB), with data-ready on GPIO3_19 (P9_27):

```dts
// bme280-overlay.dts
/dts-v1/;
/plugin/;

/ {
    compatible = "ti,am335x-boneblack", "ti,am335x-bone", "ti,am33xx";

    fragment@0 {
        target = <&i2c1>;          // i2c-1 bus (P9_17 SCL, P9_18 SDA)
        __overlay__ {
            #address-cells = <1>;
            #size-cells = <0>;
            status = "okay";

            bme280@76 {              // BME280 I2C address (0x76 or 0x77)
                compatible = "bosch,bme280";
                reg = <0x76>;
                pinctrl-names = "default";
                pinctrl-0 = <&bme280_pins>;
                interrupt-parent = <&gpio3>;   // GPIO3 bank
                interrupts = <19 2>;           // pin 19, IRQ_TYPE_EDGE_FALLING
                vdd-supply = <&vdd_3v3>;
                vddio-supply = <&vdd_3v3>;
            };
        };
    };

    fragment@1 {
        target = <&am33xx_pinmux>;
        __overlay__ {
            bme280_pins: bme280_pins {
                pinctrl-single,pins = <
                    0x1a4 0x27  // P9_27 (GPIO3_19) as input with pullup
                >;
            };
        };
    };
};
```

Compile and load:

```bash
# Compile to .dtbo
dtc -@ -I dts -O dtb -o bme280-bbb.dtbo bme280-overlay.dts

# Copy to /lib/firmware (optional, for configfs)
sudo cp bme280-bbb.dtbo /lib/firmware/

# Load via configfs
sudo mkdir /sys/kernel/config/device-tree/overlays/bme280
sudo sh -c 'cat /lib/firmware/bme280-bbb.dtbo > /sys/kernel/config/device-tree/overlays/bme280/dtbo'

# Verify
cat /sys/kernel/config/device-tree/overlays/bme280/status
# Should print "applied"

# Check the device is probed
ls /sys/bus/i2c/devices/1-0076/
# Should show driver, power, etc.
```

If the interrupt isn't working, check the pinmux and interrupt mapping:

```bash
# Verify pinmux
cat /sys/kernel/debug/pinctrl/44e10800.pinmux/pinmux-pins | grep 1a4
# Should show 0x27 (input, pullup)

# Check interrupt
cat /proc/interrupts | grep bme280
# Should show an interrupt count incrementing on data-ready
```

## Common Pitfalls & Gotchas

1. **Phandle resolution failure**: If your overlay references a node (like `&i2c1`) that doesn't exist in the base tree, the kernel will silently fail to apply. Always check the base tree first: `dtc -I fs -O dts /sys/firmware/devicetree/base` and grep for your target. On BBB, `i2c1` is often disabled by default — you may need to enable it in u-boot or use a different bus.

2. **Interrupt type mismatch**: The `interrupts` property uses the second cell for flags (e.g., `2` for falling edge). If your sensor uses a different trigger (e.g., rising edge or level), the driver may never see interrupts. Use `cat /proc/interrupts` and `evtest` (if it's a GPIO) to confirm. I spent 30 minutes debugging a BME280 that was actually using `IRQ_TYPE_EDGE_RISING` (flag `1`), not falling.

3. **Regulator not available**: If your overlay references a regulator like `&vdd_3v3` that isn't defined in the base tree, the kernel will defer probing indefinitely. Check `dmesg | grep bme280` for "probe deferred" messages. On BBB, the 3.3V rail is usually `&vdd_3v3` in the cape manager, but you might need to add a fixed-regulator node in a separate fragment.

## Try It Yourself

1. **Adapt the overlay for a different I2C bus**: Change `target = <&i2c1>` to `target = <&i2c2>` (P9_19, P9_20 on BBB). Recompile, load, and verify the device appears under `/sys/bus/i2c/devices/2-0076/`. You'll need to adjust the pinmux fragment accordingly.

2. **Add a second sensor on the same bus**: Extend the overlay to include an additional node for a TMP102 temperature sensor at address 0x48. Use `compatible = "ti,tmp102"` and a separate interrupt pin. Load both overlays (or combine into one) and verify both devices probe.

3. **Debug a failed overlay**: Intentionally break the overlay (e.g., use a wrong phandle like `&i2c5` or a bad interrupt flag). Load it and check `dmesg | tail -20` for error messages. Then fix it and reload — note that you must remove the overlay directory (`rmdir`) before reapplying.

## Next Up

Tomorrow: **Day 22: Full Review — The Complete Device Tree & Overlay Workflow**. We'll walk through the entire lifecycle: from base tree inspection, to overlay design, to compilation, loading, debugging, and finally removal. I'll share a reusable checklist and a decision tree for choosing between overlays, cape manager, and u-boot modifications.
