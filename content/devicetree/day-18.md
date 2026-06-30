---
title: "Day 18: Device Tree in Zephyr vs Linux: Key Differences"
date: 2026-06-30
tags: ["til", "devicetree", "zephyr", "linux", "comparison"]
---

## What I Explored Today

Today I dug into how Device Tree is used in two very different environments: Zephyr RTOS and Linux. While both use the same `.dts` syntax and share a common heritage, the *philosophy* and *runtime behavior* diverge significantly. I spent the morning cross-referencing Zephyr’s devicetree.h API against Linux’s `of_*` functions, and the afternoon building a minimal Zephyr driver that reads a custom property — then comparing it to the equivalent Linux driver. The differences are not just academic; they affect how you write, debug, and maintain device tree bindings across the two ecosystems.

## The Core Concept

At the highest level, both Zephyr and Linux consume `.dts` files and generate C structures. But the *when* and *how* of that consumption is fundamentally different.

**Linux** treats the Device Tree as a *runtime data structure*. The kernel parses the flattened device tree (FDT) blob at boot, populates a tree of `struct device_node` objects, and drivers query this tree dynamically using functions like `of_property_read_u32()`. The tree lives in memory for the entire system uptime. This means you can change the DTB without recompiling the kernel — a key feature for bootloaders like U-Boot.

**Zephyr** treats the Device Tree as a *compile-time code generator*. During the build, Zephyr’s `gen_defines.py` script processes the `.dts` and generates a massive header file (`devicetree_generated.h`) containing macros for every node, property, and alias. Drivers use macros like `DT_NODE_HAS_COMPAT(node_id, compatible)` and `DT_PROP(node_id, property)` — all resolved at compile time. There is no runtime tree. The generated macros expand to integer constants, struct initializers, or `#define` values. This makes Zephyr’s approach extremely lightweight (no memory allocation, no parsing), but it also means any DTS change requires a full rebuild.

The practical consequence: In Linux, you can write a driver that probes based on runtime conditions (e.g., "does this node have property X?"). In Zephyr, that same logic must be resolved at compile time — you can’t conditionally enable a driver based on a property that isn’t present in the DTS for that build.

## Key Commands / Configuration / Code

Let’s compare a simple I2C device driver snippet in both environments.

**Zephyr driver (reading a custom property):**
```c
#include <zephyr/devicetree.h>

/* Node identifier for the device with compatible "mydev,adc-sensor" */
#define MYDEV_NODE DT_COMPAT_GET_ANY_STATUS_OKAY(mydev_adc_sensor)

/* Read a property 'scale-microvolts' at compile time */
#define SCALE_MV DT_PROP(MYDEV_NODE, scale_microvolts)

/* Check if an optional property exists */
#if DT_NODE_HAS_PROP(MYDEV_NODE, reference_voltage)
   #define REF_VOLTAGE DT_PROP(MYDEV_NODE, reference_voltage)
#else
   #define REF_VOLTAGE 3300000  /* default 3.3V */
#endif

/* Driver init uses these macros directly */
int mydev_init(const struct device *dev)
{
    /* No runtime lookup — SCALE_MV is a constant */
    printk("Scale: %d uV, Ref: %d uV\n", SCALE_MV, REF_VOLTAGE);
    return 0;
}
```

**Linux driver (equivalent functionality):**
```c
#include <linux/of.h>
#include <linux/of_device.h>

static int mydev_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct device_node *np = dev->of_node;
    u32 scale_mv, ref_voltage;
    int ret;

    /* Runtime property read — returns error if missing */
    ret = of_property_read_u32(np, "scale-microvolts", &scale_mv);
    if (ret) {
        dev_err(dev, "missing scale-microvolts\n");
        return ret;
    }

    /* Optional property with default */
    ret = of_property_read_u32(np, "reference-voltage", &ref_voltage);
    if (ret)
        ref_voltage = 3300000;

    dev_info(dev, "Scale: %d uV, Ref: %d uV\n", scale_mv, ref_voltage);
    return 0;
}
```

Notice the key difference: Zephyr’s `DT_PROP()` is a macro that expands to a literal number. Linux’s `of_property_read_u32()` is a function that returns a value at runtime. This means Zephyr cannot handle "optional properties" in the same way — you must use `#if` preprocessor directives, which are evaluated before the C compiler even sees the code.

**Build-time vs runtime configuration:**
- Zephyr: `west build -b <board> -- -DDTC_OVERLAY_FILE=my_overlay.overlay` — triggers a full recompile.
- Linux: `cat my_overlay.dtbo > /sys/kernel/config/device-tree/overlays/my_overlay/dtbo` — applies overlay at runtime, no reboot needed.

## Common Pitfalls & Gotchas

1. **Zephyr’s `DT_COMPAT_GET_ANY_STATUS_OKAY` can fail silently.** If no node with that compatible has `status = "okay"`, the macro expands to an invalid node identifier. The build succeeds, but the driver’s `DT_PROP()` calls produce garbage values. Always pair with `#if DT_NODE_EXISTS(MYDEV_NODE)` to guard.

2. **Linux’s `of_property_read_*` returns -EINVAL if the property is missing, but -ENODATA if it’s present but empty.** Many engineers forget to check for `-ENODATA` and treat it as a missing property. Always check `ret < 0` and handle both cases.

3. **Zephyr’s `#define` pollution.** The generated `devicetree_generated.h` creates macros for *every* node and property in the tree. If your DTS has a node with label `foo`, you get `DT_NODE_foo`. If you also have a variable named `foo` in your driver, you get a macro expansion conflict. The fix: always use `DT_NODE_FROM_LABEL(foo)` or prefix your variables with `my_`.

## Try It Yourself

1. **Zephyr: Add an optional property to an existing driver.** Pick a sensor driver in Zephyr (e.g., `drivers/sensor/bme280.c`). Add a `#if DT_NODE_HAS_PROP(...)` block to read a custom property like `oversampling` from the DTS. Rebuild for the `nrf52840dk_nrf52840` board and verify the property is used.

2. **Linux: Write a minimal platform driver that reads a `clock-frequency` property.** Use `of_property_read_u32()` in the probe function. Compile it as a kernel module, load it on a Raspberry Pi, and verify the value matches the DTS.

3. **Compare the two: Create a DTS node with a `label` property.** In Zephyr, read it with `DT_LABEL(node_id)`. In Linux, read it with `of_get_property(np, "label", NULL)`. Note that Zephyr’s `DT_LABEL` returns a string literal at compile time, while Linux returns a `const char *` pointer to the FDT data.

## Next Up

Tomorrow we get our hands dirty with the Device Tree compiler itself: `dtc` and `fdtdump`. We’ll compile a `.dts` to `.dtb`, inspect the binary blob, and learn how to debug common DTC errors. If you’ve ever wondered what’s inside a `.dtb` file, that’s the post for you.
