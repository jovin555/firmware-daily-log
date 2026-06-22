---
title: "Day 10: devm_* Functions: Managed Resources from DT"
date: 2026-06-22
tags: ["til", "devicetree", "devm", "managed", "resources"]
---

## What I Explored Today

Today I dug into the `devm_*` (device-managed) API family and how it integrates with Device Tree probing. The core question: when your driver's `probe()` function parses DT properties and allocates resources (GPIOs, clocks, regulators, memory), who cleans up on error or removal? The `devm_*` functions automate that cleanup by tying resource lifetimes to the `struct device` — and they work seamlessly with DT-derived resources.

## The Core Concept

Every embedded engineer has written a `probe()` that looks like this: allocate A, allocate B, if B fails, free A. Then in `remove()`, free B, free A. It's tedious, error-prone, and if you miss a goto label, you leak resources forever.

The `devm_*` API solves this by registering a devres (device resource) group with the kernel's driver core. When `probe()` succeeds, the resources are "moved" to the device. When `probe()` fails or the device is unbound, the kernel automatically calls the release functions in reverse order.

For DT-based drivers, this is a game-changer. You typically parse `gpios`, `clocks`, `regulators`, or `interrupts` from the device node, then request them. With `devm_*`, you skip the manual teardown entirely. The resource is released when the device is detached — no `remove()` callback needed for cleanup.

The key insight: `devm_*` functions take a `struct device *` as the first argument. In a platform driver, that's `&pdev->dev`. The kernel internally stores a list of devres nodes per device. When the device disappears, it walks that list and calls the destructor for each.

## Key Commands / Configuration / Code

Let's look at a real platform driver snippet that uses DT and `devm_*`:

```c
#include <linux/platform_device.h>
#include <linux/gpio/consumer.h>
#include <linux/clk.h>
#include <linux/regulator/consumer.h>
#include <linux/module.h>

static int my_driver_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct gpio_desc *reset_gpio;
    struct clk *bus_clk;
    struct regulator *vdd;

    // devm_gpiod_get_index() parses "gpios" from DT
    // Returns a descriptor, or ERR_PTR. No free needed.
    reset_gpio = devm_gpiod_get_index(dev, "reset", 0, GPIOD_OUT_LOW);
    if (IS_ERR(reset_gpio))
        return PTR_ERR(reset_gpio);

    // devm_clk_get() looks for "clocks" in DT
    // Managed: automatically disabled and released
    bus_clk = devm_clk_get(dev, "bus");
    if (IS_ERR(bus_clk))
        return PTR_ERR(bus_clk);

    // devm_regulator_get() from DT "regulators" property
    // Managed: automatically disabled on remove
    vdd = devm_regulator_get(dev, "vdd");
    if (IS_ERR(vdd))
        return PTR_ERR(vdd);

    // Enable clock and regulator
    clk_prepare_enable(bus_clk);
    regulator_enable(vdd);

    // devm_kzalloc: memory freed automatically
    // No kfree() needed in remove()
    pdev->dev.driver_data = devm_kzalloc(dev, sizeof(struct my_priv), GFP_KERNEL);
    if (!pdev->dev.driver_data)
        return -ENOMEM;

    // devm_request_irq: interrupt handler unregistered automatically
    // Uses platform_get_irq() which reads "interrupts" from DT
    int irq = platform_get_irq(pdev, 0);
    if (irq < 0)
        return irq;

    return devm_request_irq(dev, irq, my_isr, IRQF_TRIGGER_RISING,
                            "my_device", pdev);
}

static int my_driver_remove(struct platform_device *pdev)
{
    // No manual cleanup needed for devm resources
    // But you still need to disable what you enabled
    struct my_priv *priv = platform_get_drvdata(pdev);
    // ... hardware-specific disable sequence ...
    return 0;
}

static const struct of_device_id my_dt_ids[] = {
    { .compatible = "vendor,my-device" },
    { }
};
MODULE_DEVICE_TABLE(of, my_dt_ids);

static struct platform_driver my_driver = {
    .probe  = my_driver_probe,
    .remove = my_driver_remove,
    .driver = {
        .name = "my_device",
        .of_match_table = my_dt_ids,
    },
};
module_platform_driver(my_driver);
```

The corresponding DT node:

```dts
my_device: my-device@1c00000 {
    compatible = "vendor,my-device";
    reg = <0x1c00000 0x1000>;
    interrupts = <GIC_SPI 42 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&clkctrl 0x10>;
    reset-gpios = <&gpio3 7 GPIO_ACTIVE_LOW>;
    vdd-supply = <&reg_3v3>;
};
```

Notice: `devm_gpiod_get_index(dev, "reset", 0, ...)` automatically appends `-gpios` to the property name, so it matches `reset-gpios` in DT. The `devm_regulator_get(dev, "vdd")` matches `vdd-supply`.

## Common Pitfalls & Gotchas

1. **devm_* does not undo hardware state changes.** If you call `clk_prepare_enable()` or `regulator_enable()` after getting the managed resource, you must still call `clk_disable_unprepare()` and `regulator_disable()` in your `remove()` callback. The devm layer only releases the *resource handle* — it doesn't know you changed hardware state. Many engineers assume devm handles everything, then wonder why the clock stays on after unbind.

2. **devm_kzalloc vs regular kzalloc in probe.** If you allocate memory with `kzalloc()` and then a later `devm_*` call fails, you must `kfree()` that memory in your error path. Mixing managed and unmanaged allocations is a common source of leaks. Best practice: use `devm_kzalloc()` for everything in probe, or nothing.

3. **devm_request_irq() and shared IRQs.** If your DT specifies a shared interrupt (`interrupts-extended` with a shared controller), `devm_request_irq()` works fine, but the `dev_id` argument must be unique per device. If you pass `pdev` (the platform device pointer), that's guaranteed unique. Passing `NULL` or a static pointer will cause `-EBUSY` on the second probe.

## Try It Yourself

1. **Convert a legacy driver to devm_*:** Find a simple platform driver in your kernel tree (e.g., `drivers/misc/`) that uses manual `gpio_request()` / `gpio_free()` in probe/remove. Rewrite it using `devm_gpiod_get()` and remove the `remove()` cleanup. Verify with `insmod` / `rmmod` that no leaks occur (check `/sys/kernel/debug/devres`).

2. **Add a managed clock to a DT node:** Take an existing DT node that has no `clocks` property. Add one, then in the driver, use `devm_clk_get()` and `clk_prepare_enable()`. Confirm that after `rmmod`, the clock is disabled by checking `/sys/kernel/debug/clk/clk_summary`.

3. **Test error path with devm_*:** Intentionally make a devm call fail (e.g., request a non-existent GPIO name like `"nonexistent-gpios"`). Verify that all previously allocated devm resources are released automatically. Use `printk` or `dev_dbg` to trace the probe failure path.

## Next Up

Tomorrow we dive into **Device Tree Overlays (DTBO): Syntax & Structure**. We'll look at the `.dts` overlay format, how to compile with `dtc -@`, and the fragment/node-target syntax that makes runtime DT modification possible. Bring a Raspberry Pi or BeagleBone — we're going to load an overlay live.
