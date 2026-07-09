---
title: "Day 27: Regulator Framework: Managing Power Rails in Drivers"
date: 2026-07-09
tags: ["til", "power-management", "regulator", "rails", "framework"]
---

## What I Explored Today

Today I dug into the Linux kernel's regulator framework — the subsystem that lets drivers control voltage and current rails without hardcoding regulator-specific details. I traced how a display driver requests a 1.8V rail, how the framework handles voltage negotiation with the PMIC, and what happens when a regulator can't meet the exact voltage request. The key insight: the regulator framework abstracts the physical power management IC (PMIC) into a consumer-provider model, letting driver authors focus on what voltage they need, not how to set it.

## The Core Concept

The regulator framework solves a fundamental tension in embedded systems: a single PMIC might supply 3.3V to an SD card slot, 1.2V to a CPU core, and 1.8V to an I2C bus, all from different regulators. Without a framework, every driver would need to know the exact register map of the PMIC, handle voltage ramp timing, and manage exclusive access. That's a recipe for race conditions and fragile code.

Instead, the kernel provides a **consumer-provider** architecture:
- **Providers**: PMIC drivers (e.g., `pca9450-regulator`) register regulator devices with the framework, describing voltage ranges, current limits, and ramp delays.
- **Consumers**: Peripheral drivers (e.g., an MMC controller) request a regulator by name or supply alias, then call `regulator_set_voltage()` and `regulator_enable()`.

The framework handles:
- Voltage selection (finding the nearest supported voltage within tolerance)
- Exclusive access (only one consumer can change voltage on a shared rail)
- Sequencing (enabling/disabling in the right order for power-up/down)
- Debugging via sysfs and tracepoints

This means a driver writer never touches the PMIC's I2C registers directly. The framework translates `regulator_set_voltage(reg, 1800000, 1800000)` into the appropriate PMIC register writes, including any necessary voltage ramp delays.

## Key Commands / Configuration / Code

### Device Tree Binding (Consumer Side)

In your device tree node, you declare which power rails your device needs:

```dts
&mmc0 {
    status = "okay";
    vmmc-supply = <&reg_3v3>;      /* SD card slot power */
    vqmmc-supply = <&reg_1v8>;     /* I/O line voltage */
    no-1-8-v;                      /* Signal that 1.8V not supported */
};
```

The `-supply` suffix is the convention. The framework matches these to regulator nodes in the PMIC section.

### Driver Code (Consumer)

Here's how a driver requests and controls a regulator:

```c
#include <linux/regulator/consumer.h>

struct my_device {
    struct regulator *vdd_reg;
    struct regulator *vccio_reg;
};

static int my_probe(struct platform_device *pdev)
{
    struct my_device *dev;
    int ret;

    dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
    
    /* Get the regulator by supply name from DT */
    dev->vdd_reg = devm_regulator_get(&pdev->dev, "vdd");
    if (IS_ERR(dev->vdd_reg))
        return PTR_ERR(dev->vdd_reg);  /* -EPROBE_DEFER if not ready */

    dev->vccio_reg = devm_regulator_get(&pdev->dev, "vccio");
    if (IS_ERR(dev->vccio_reg))
        return PTR_ERR(dev->vccio_reg);

    /* Set voltage: min=1.8V, max=1.8V (exact) */
    ret = regulator_set_voltage(dev->vdd_reg, 1800000, 1800000);
    if (ret)
        dev_warn(&pdev->dev, "Failed to set VDD to 1.8V: %d\n", ret);

    /* Enable the rail */
    ret = regulator_enable(dev->vdd_reg);
    if (ret)
        return ret;

    return 0;
}

static void my_remove(struct platform_device *pdev)
{
    struct my_device *dev = platform_get_drvdata(pdev);
    
    /* Disable in reverse order */
    regulator_disable(dev->vccio_reg);
    regulator_disable(dev->vdd_reg);
}
```

### Debugging via sysfs

```bash
# List all registered regulators
ls /sys/class/regulator/

# Check a specific regulator's status
cat /sys/class/regulator/regulator.1/microvolts
cat /sys/class/regulator/regulator.1/state

# See what consumers are using it
cat /sys/kernel/debug/regulator/regulator_summary
```

The `regulator_summary` debugfs file is invaluable — it shows the entire tree of regulators, their voltages, and which drivers are consuming them.

## Common Pitfalls & Gotchas

### 1. EPROBE_DEFER: The Silent Stall

If your driver calls `regulator_get()` before the PMIC driver has registered its regulators, you get `-EPROBE_DEFER`. Many new engineers treat this as an error and return failure. **Always propagate EPROBE_DEFER** — the kernel will retry your probe later. If you swallow it, your device never initializes.

```c
/* WRONG: treats defer as fatal */
if (IS_ERR(reg))
    return -ENODEV;

/* RIGHT: let the kernel retry */
if (PTR_ERR(reg) == -EPROBE_DEFER)
    return -EPROBE_DEFER;
```

### 2. Voltage Tolerance Mismatch

When you call `regulator_set_voltage(reg, min_uV, max_uV)`, the framework selects the nearest voltage the regulator can provide within that range. If no voltage fits, it returns `-EINVAL`. Always check the return value, and consider using `regulator_set_voltage_triplet()` if you need to negotiate with other consumers.

### 3. Shared Rails and Reference Counting

If two drivers enable the same regulator, the framework uses reference counting. The regulator stays on until the last consumer disables it. But if one driver calls `regulator_force_disable()`, it bypasses the count and shuts down the rail immediately — potentially crashing the other consumer. Never use `force_disable` in production code.

## Try It Yourself

1. **Inspect your board's regulator tree**: Boot your target and run `cat /sys/kernel/debug/regulator/regulator_summary`. Identify which regulators are enabled and which drivers are consuming them. Note the voltage ranges.

2. **Add a regulator consumer to a driver**: Pick a simple driver in your kernel tree (e.g., a GPIO expander). Add a `vdd-supply` property to its device tree node, then modify the driver to call `devm_regulator_get()` and `regulator_enable()` in probe. Verify the regulator appears in `regulator_summary`.

3. **Simulate a voltage negotiation failure**: Write a small test module that requests a voltage outside the regulator's range (e.g., request 5V from a 3.3V rail). Observe the `-EINVAL` return and check dmesg for the regulator framework's error message.

## Next Up

Tomorrow: **Clock Gating & Power Domains** — how the kernel manages clock trees and power islands to shut down unused blocks at the hardware level, and why `clk_enable()` is only half the story.
