---
title: "Day 08: The compatible Property: How Drivers Match DT Nodes"
date: 2026-06-22
tags: ["til", "devicetree", "compatible", "probe", "matching"]
---

## What I Explored Today

Today I dug into the `compatible` property — the single most important string in any device tree node. Without it, the kernel has no idea which driver should claim a device. I traced the entire matching path from `.dts` to `probe()`, examined the `of_match_table` structure, and confirmed that the order of strings in `compatible` matters more than most tutorials admit. If you've ever wondered why your driver's probe never fires despite a seemingly correct node, this is the post for you.

## The Core Concept

The `compatible` property is the device tree's answer to PCI vendor/device IDs or USB VID/PID — it's the primary mechanism for driver-to-device matching on non-discoverable buses (I2C, SPI, platform, etc.). But unlike PCI's hardware-encoded identifiers, `compatible` is purely software-defined. The kernel doesn't read a register; it reads a string from the DT blob and compares it against a list of strings the driver claims to support.

Why does this matter? Because the matching logic is **ordered and fallback-aware**. The first string in `compatible` should be the exact, specific device model. Subsequent strings are more generic fallbacks. The kernel walks the driver's `of_match_table` and picks the **best** (most specific) match. If your driver only lists a generic fallback, it will match, but the kernel may have preferred a more specific driver — and you'll never know unless you check `dmesg` for deferred probing.

The matching happens in `drivers/of/device.c` via `of_match_device()`. It iterates over the driver's `of_device_id` table and calls `of_match_node()`, which does a string comparison against each `compatible` entry in the node. The first match wins, but the kernel also computes a "best match" score based on how many strings matched and their position.

## Key Commands / Configuration / Code

### 1. The DT node with compatible strings (in order of specificity)

```dts
/* i2c-device.dtsi */
&i2c1 {
    temperature_sensor: sensor@48 {
        compatible = "ti,tmp117", "ti,tmp116", "ti,tmp1xx";
        reg = <0x48>;
        /* ... */
    };
};
```

Here, `ti,tmp117` is the exact model. If a driver for `tmp116` exists but not `tmp117`, the kernel will fall back to `ti,tmp116`. The generic `ti,tmp1xx` is a last resort.

### 2. The driver's of_match_table (must match at least one string)

```c
// tmp1xx.c
#include <linux/of_device.h>
#include <linux/mod_devicetable.h>

static const struct of_device_id tmp1xx_of_match[] = {
    { .compatible = "ti,tmp117", .data = (void *)TMP117_ID },
    { .compatible = "ti,tmp116", .data = (void *)TMP116_ID },
    { .compatible = "ti,tmp1xx", .data = (void *)TMP1XX_GENERIC },
    { /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, tmp1xx_of_match);

static struct i2c_driver tmp1xx_driver = {
    .driver = {
        .name = "tmp1xx",
        .of_match_table = tmp1xx_of_match,
    },
    .probe = tmp1xx_probe,
    .id_table = tmp1xx_id,  // fallback for non-DT (ACPI, legacy)
};
```

**Critical detail**: The driver's `of_match_table` entries can be in any order — the kernel matches against the **device node's** `compatible` list, not the driver's table order. But the `.data` field lets you pass device-specific info to probe without string parsing.

### 3. How probe receives the match data

```c
static int tmp1xx_probe(struct i2c_client *client)
{
    const struct of_device_id *match;

    match = of_match_device(tmp1xx_of_match, &client->dev);
    if (!match) {
        dev_err(&client->dev, "no compatible match found\n");
        return -ENODEV;
    }

    // match->data is the enum/ID we passed above
    enum tmp1xx_model model = (enum tmp1xx_model)match->data;

    dev_info(&client->dev, "probed as model %d\n", model);
    return 0;
}
```

### 4. Debugging the match: check which compatible matched

```bash
# After driver loads, see the full match
cat /sys/bus/i2c/devices/1-0048/of_node/compatible
# Output: ti,tmp117\0ti,tmp116\0ti,tmp1xx\0

# Check driver binding
cat /sys/bus/i2c/devices/1-0048/driver
# Should show tmp1xx

# If probe fails, check dmesg for:
dmesg | grep -i "tmp1xx"
# Look for "probe deferred" or "ENODEV"
```

## Common Pitfalls & Gotchas

### 1. **Forgetting the sentinel entry**
The `of_device_id` array **must** end with an empty `{}` sentinel. Without it, the kernel will walk past your array into garbage memory, causing a crash or random match failures. The `MODULE_DEVICE_TABLE` macro does not add the sentinel — you must do it manually.

### 2. **Mismatched vendor prefix**
The vendor prefix in `compatible` (e.g., `ti,` or `nxp,`) must match exactly what's registered in `Documentation/devicetree/bindings/vendor-prefixes.yaml`. Using `mycompany,` without upstreaming the prefix is fine for out-of-tree, but the kernel will warn. Worse: a typo like `texas-instruments,tmp117` instead of `ti,tmp117` will silently fail to match.

### 3. **Order of compatible strings in the node matters for fallback**
If you put the generic fallback first:
```dts
compatible = "ti,tmp1xx", "ti,tmp117";  // WRONG
```
The kernel will match `ti,tmp1xx` first, even if a specific `tmp117` driver exists. The driver's `of_match_table` is searched in order, but the **device node's** first string is tried first. Always put the most specific string first.

## Try It Yourself

1. **Add a new compatible string to an existing driver**: Pick a simple I2C driver (e.g., `drivers/iio/temperature/tmp117.c`). Add a new `of_device_id` entry for a compatible string like `"ti,tmp118"` with a different `.data` value. Rebuild the kernel and verify the driver probes with the new string by checking `dmesg`.

2. **Debug a non-probing device**: Create a device tree overlay that adds a node with a deliberately wrong compatible string (e.g., `"no-such,vendor"`). Load it, then use `of_match_device()` in a kernel module to confirm the match fails. Fix the string and verify the probe fires.

3. **Inspect the match table at runtime**: Write a small kernel module that iterates over the `of_match_table` of a loaded driver and prints each compatible string. Use `for_each_matching_node()` to find all nodes that match a given driver. This is exactly what `drivers/of/base.c` does internally.

## Next Up

Tomorrow: **of_* API: Reading Device Tree from Kernel Drivers** — we'll move from matching to extracting data. How to read `reg`, `interrupts`, `gpios`, and custom properties using the `of_` function family, and why `of_property_read_u32()` is safer than manual parsing.
