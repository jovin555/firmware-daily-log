---
title: "Day 09: of_* API: Reading Device Tree from Kernel Drivers"
date: 2026-06-22
tags: ["til", "devicetree", "of-api", "driver", "kernel"]
---

## What I Explored Today

Today I dug into the `of_*` API family — the core set of functions that kernel drivers use to read properties and resources from the Device Tree. After writing overlays and understanding the DT structure, the next logical step is actually consuming that data in a driver. I spent the day tracing through `of_match_device`, `of_property_read_u32`, `of_get_named_gpio`, and `of_iomap` in real drivers to see how they translate DT descriptions into runtime resources.

## The Core Concept

The Device Tree is a static data structure passed to the kernel at boot. Your driver needs a way to query that structure without knowing the exact hardware configuration at compile time. The `of_*` (Open Firmware) API provides that bridge. Think of it as a query language for the flattened device tree blob (FDT) that lives in memory.

Why not just use platform data or hardcoded values? Because DT enables a single kernel binary to support multiple board variants. The same driver can read a different clock frequency, GPIO pin, or register offset depending on which DT node it binds to. The `of_*` API is how your driver asks "what did the DT author put in my node?"

The key insight: every driver that matches against a DT compatible string receives a `struct device_node *` pointer (usually via `pdev->dev.of_node`). That pointer is your entry point. From it, you can walk up to parents, down to children, or read arbitrary properties.

## Key Commands / Configuration / Code

Here's a minimal I2C controller driver reading DT properties. This is the pattern you'll see in thousands of kernel drivers.

```c
#include <linux/of.h>
#include <linux/of_gpio.h>
#include <linux/of_address.h>

static int my_i2c_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct device_node *np = dev->of_node;  // our DT node
    struct resource res;
    void __iomem *base;
    u32 clock_freq;
    int gpio, ret;

    // 1. Match against compatible string (handled by platform core)
    // The matching is done before probe() is called, but you can
    // access the matched entry:
    const struct of_device_id *match = of_match_device(pdev->dev.driver->of_match_table, dev);
    if (match)
        dev_info(dev, "Matched: %s\n", match->compatible);

    // 2. Read a simple u32 property with default fallback
    ret = of_property_read_u32(np, "clock-frequency", &clock_freq);
    if (ret) {
        // Property not found — use a safe default
        clock_freq = 100000;  // 100 kHz default
        dev_warn(dev, "clock-frequency not found, using default %u\n", clock_freq);
    }

    // 3. Get a GPIO from the "reset-gpios" property (phandle + GPIO specifier)
    gpio = of_get_named_gpio(np, "reset-gpios", 0);
    if (gpio < 0) {
        dev_err(dev, "Failed to get reset GPIO: %d\n", gpio);
        return gpio;
    }
    // Request and configure the GPIO
    ret = devm_gpio_request_one(dev, gpio, GPIOF_OUT_INIT_LOW, "my-reset");
    if (ret)
        return ret;

    // 4. Map the first memory region (reg = <0x... 0x...>)
    base = of_iomap(np, 0);
    if (!base) {
        dev_err(dev, "Failed to iomap registers\n");
        return -ENOMEM;
    }

    // 5. Read a child node property (e.g., a sub-device configuration)
    struct device_node *child;
    for_each_child_of_node(np, child) {
        u32 addr;
        if (of_property_read_u32(child, "reg", &addr) == 0) {
            dev_info(dev, "Child at address 0x%x\n", addr);
        }
    }

    // 6. Check for a boolean property (presence = true)
    if (of_property_read_bool(np, "dmas"))
        dev_info(dev, "DMA is enabled\n");

    // ... register I2C adapter, etc.

    iounmap(base);
    return 0;
}

static const struct of_device_id my_i2c_of_match[] = {
    { .compatible = "vendor,my-i2c-controller", },
    { /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, my_i2c_of_match);

static struct platform_driver my_i2c_driver = {
    .probe  = my_i2c_probe,
    .driver = {
        .name = "my_i2c",
        .of_match_table = my_i2c_of_match,
    },
};
module_platform_driver(my_i2c_driver);
```

The corresponding DT node would look like:

```dts
my_i2c: i2c@f0004000 {
    compatible = "vendor,my-i2c-controller";
    reg = <0x0 0xf0004000 0x0 0x1000>;
    interrupts = <0 42 4>;
    clock-frequency = <400000>;
    reset-gpios = <&gpio2 5 GPIO_ACTIVE_LOW>;
    dmas;
    
    sensor@48 {
        reg = <0x48>;
    };
};
```

## Common Pitfalls & Gotchas

1. **`of_iomap` vs `platform_get_resource`**: Both can map memory regions, but `of_iomap` works directly from the DT node and doesn't require a `struct resource`. However, `platform_get_resource` is preferred in platform drivers because it also populates the resource flags (IORESOURCE_MEM, IORESOURCE_IRQ). Use `of_iomap` only when you're not in a platform driver context (e.g., an early init function).

2. **Property name mismatches**: DT property names use hyphens (`clock-frequency`), but kernel variable names use underscores (`clock_freq`). The `of_property_read_*` functions expect the exact DT property name. A typo here silently returns `-EINVAL` — always check the return value.

3. **Forgetting the sentinel**: The `of_device_id` table must end with an empty entry `{ /* sentinel */ }`. Without it, the kernel will walk past the end of the array, causing undefined behavior or crashes during module loading.

4. **`of_get_named_gpio` returns raw number**: This function returns the global GPIO number, not a descriptor. For new code, prefer `devm_gpiod_get()` and the gpiod descriptor API, which is cleaner and handles inversion flags automatically.

## Try It Yourself

1. **Read a string array property**: In your DT node, add `clock-names = "core", "bus", "periph";`. In your driver, use `of_property_count_strings()` and `of_property_read_string_index()` to print each clock name. This is exactly how the clk framework discovers clock inputs.

2. **Walk the interrupt tree**: Given an interrupt-parent phandle, use `of_irq_parse_one()` to extract the interrupt specifier (controller phandle, IRQ number, flags). Compare it to what `platform_get_irq()` returns — they should match.

3. **Debug with /proc/device-tree**: After loading your driver, cat `/proc/device-tree/<your-node-path>/clock-frequency` to verify the kernel parsed your property correctly. Then add `#define DEBUG` at the top of your driver and watch `dev_dbg()` output from `of_property_read_*` calls.

## Next Up

Tomorrow: **devm_* Functions: Managed Resources from DT** — we'll explore how the managed device resource API (`devm_`) automatically handles cleanup of DT-derived resources like mapped memory, GPIOs, and interrupts, eliminating the need for error-path cleanup in your probe function.
