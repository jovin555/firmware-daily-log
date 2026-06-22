---
title: "Day 09: Regulator Framework: Managing Power Rails in Drivers"
date: 2026-06-22
tags: ["til", "power-management", "regulator", "rails", "framework"]
---

## What I Explored Today

Today I dug into the Linux Regulator Framework — the kernel subsystem that abstracts voltage and current regulators into a clean, consumer-driven API. I traced how a driver requests a regulator, sets voltage, enables/disables the rail, and handles constraints. I also wired up a dummy regulator in device tree and watched the framework enforce min/max voltage boundaries at runtime. The key takeaway: the regulator framework decouples power management policy from hardware control, letting drivers focus on "what voltage I need" while the regulator core handles "how to get it there."

## The Core Concept

Every embedded board has regulators: fixed LDOs, switch-mode converters, PMIC bucks, even GPIO-controlled enable pins. In the old days, drivers poked PMIC registers directly. That was fragile — a board spin with a different PMIC meant rewriting every driver that touched power.

The regulator framework solves this by introducing three roles:

- **Consumer** — a driver that needs power (e.g., an I2C sensor, an SDIO controller)
- **Regulator device** — the hardware that provides power (e.g., a TPS6598x buck)
- **Regulator core** — the in-kernel manager that enforces constraints, handles dependencies, and serializes access

The consumer never touches hardware registers. It calls `regulator_get()`, `regulator_set_voltage()`, `regulator_enable()`, and the core translates those into regulator-ops callbacks (e.g., `.set_voltage_sel`, `.enable`). Constraints — min/max voltage, always-on, boot-on — are defined in device tree or board files and enforced by the core.

This matters because modern SoCs have dozens of power rails. A GPU driver might need 0.9V for idle, 1.1V for 3D rendering. The regulator framework lets you change voltage without knowing whether the PMIC uses I2C, SPI, or a GPIO-controlled LDO.

## Key Commands / Configuration / Code

### Device Tree binding for a consumer

```dts
&i2c1 {
    temperature_sensor: sensor@4c {
        compatible = "ti,tmp102";
        reg = <0x4c>;
        vcc-supply = <&ldo3>;          // regulator phandle
        vio-supply = <&vcc_3v3>;       // second rail
    };
};
```

The `-supply` suffix is the convention. The regulator core parses `vcc-supply` and creates a mapping for the consumer driver.

### Consumer driver: requesting and controlling a regulator

```c
#include <linux/regulator/consumer.h>

struct priv_data {
    struct regulator *vcc;
    struct regulator *vio;
};

static int sensor_probe(struct platform_device *pdev)
{
    struct priv_data *priv;
    int ret;

    priv = devm_kzalloc(&pdev->dev, sizeof(*priv), GFP_KERNEL);
    if (!priv)
        return -ENOMEM;

    // Get regulators — devm_ handles cleanup on remove/error
    priv->vcc = devm_regulator_get(&pdev->dev, "vcc");
    if (IS_ERR(priv->vcc))
        return dev_err_probe(&pdev->dev, PTR_ERR(priv->vcc),
                             "failed to get vcc regulator\n");

    priv->vio = devm_regulator_get(&pdev->dev, "vio");
    if (IS_ERR(priv->vio))
        return dev_err_probe(&pdev->dev, PTR_ERR(priv->vio),
                             "failed to get vio regulator\n");

    // Set voltage (microvolts) — core checks constraints
    ret = regulator_set_voltage(priv->vcc, 1800000, 1800000);
    if (ret)
        dev_warn(&pdev->dev, "vcc voltage set failed: %d\n", ret);

    // Enable the rail
    ret = regulator_enable(priv->vcc);
    if (ret)
        return ret;

    // Check if rail is already enabled (e.g., boot-on)
    if (regulator_is_enabled(priv->vcc))
        dev_info(&pdev->dev, "vcc was already enabled\n");

    return 0;
}

static void sensor_shutdown(struct platform_device *pdev)
{
    struct priv_data *priv = platform_get_drvdata(pdev);

    // Disable in reverse order of enable
    regulator_disable(priv->vio);
    regulator_disable(priv->vcc);
}
```

### Debugfs: inspecting regulator state at runtime

```bash
# List all registered regulators and their consumers
cat /sys/kernel/debug/regulator/regulator_summary

# Output looks like:
# regulator                      use open bypass voltage   min     max
# ----------------------------------------------------------------------
# ldo3                           1   1   0      1800000  1800000 3300000
#    sensor@4c                      0mA
# vcc_3v3                        2   2   0      3300000  3300000 3300000
#    mmc0                            0mA
#    sensor@4c                      0mA
```

### Adding a fixed regulator in device tree (for testing)

```dts
/ {
    vcc_3v3: regulator-vcc-3v3 {
        compatible = "regulator-fixed";
        regulator-name = "vcc_3v3";
        regulator-min-microvolt = <3300000>;
        regulator-max-microvolt = <3300000>;
        regulator-always-on;          // core keeps it enabled
        gpio = <&gpio1 5 GPIO_ACTIVE_HIGH>; // optional enable GPIO
        enable-active-high;
    };
};
```

## Common Pitfalls & Gotchas

1. **Regulator get/set ordering** — Always call `regulator_set_voltage()` *before* `regulator_enable()`. Some regulators can't change voltage while enabled, and the core will return `-EINVAL` or silently fail. If you must change voltage at runtime, disable the consumer first, change voltage, then re-enable.

2. **Devres vs. manual cleanup** — `devm_regulator_get()` is almost always the right choice. It automatically releases the regulator on driver unbind. If you use `regulator_get()` directly, you must call `regulator_put()` in your remove callback — and if probe fails halfway, you leak. Devres handles partial failure correctly.

3. **Regulator constraints are enforced, not advisory** — If your device tree says `regulator-min-microvolt = <1800000>` and `regulator-max-microvolt = <1800000>`, the core will reject any call to `regulator_set_voltage(1900000)` with `-EINVAL`. This catches bugs early, but it also means you must audit your DT constraints before writing driver code.

4. **Shared rails and reference counting** — `regulator_enable()` increments a use count; `regulator_disable()` decrements it. The rail is physically turned off only when the count reaches zero. If two drivers share a rail and one calls `disable()` while the other still needs it, the rail stays on. This is correct behavior, but it can mask power bugs — always check `regulator_summary` to see who's holding references.

## Try It Yourself

1. **Add a regulator consumer to a simple driver** — Take an existing platform driver (e.g., a GPIO LED driver) and add a `vcc-supply` property. In probe, call `devm_regulator_get()` and `regulator_enable()`. Verify the rail appears in `/sys/kernel/debug/regulator/regulator_summary`.

2. **Test voltage constraint enforcement** — Create a fixed regulator with `regulator-min-microvolt = <1800000>` and `regulator-max-microvolt = <1800000>`. In your driver, try `regulator_set_voltage(2500000)`. Observe the `-EINVAL` return and the kernel warning in `dmesg`.

3. **Simulate a shared rail** — Register two consumers for the same regulator phandle. Enable both, then disable one. Use `regulator_summary` to confirm the rail stays on. Then disable the second consumer and watch the rail turn off.

## Next Up

Tomorrow: **Clock Gating & Power Domains** — how the clock framework and generic power domain (genpd) work together to gate clocks and collapse power islands when peripherals are idle. We'll walk through a real PM domain driver and measure the current draw difference.
