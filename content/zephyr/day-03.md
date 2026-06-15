---
title: "Day 03: Devicetree in Zephyr: DTS, DTSI & Overlays"
date: 2026-06-15
tags: ["til", "zephyr", "devicetree", "dts"]
---

## What I Explored Today

Today I dug into Zephyr's devicetree system — the hardware description layer that sits between your board's physical pins and your application code. I've worked with devicetree in Linux before, but Zephyr's approach is distinct: it's compile-time only, heavily macro-driven, and intimately tied to the build system. I spent the day understanding `.dts` files, `.dtsi` includes, and the critical role of overlays for application-specific hardware configuration.

## The Core Concept

Why does Zephyr use devicetree at all? Because embedded firmware must know exactly what hardware is present — which UART is on which pins, what memory-mapped peripherals exist, and how they're connected. Rather than hardcoding this in C or relying on runtime discovery (which most MCUs don't support), Zephyr uses devicetree source files to describe hardware at build time.

The key insight: **devicetree is not runtime configuration**. It's a compile-time hardware description that generates C macros and linker sections. When you change a devicetree property, you rebuild the entire application. This is fundamentally different from reading a config file at boot.

The hierarchy works like this:
- **`.dtsi` files** (devicetree source include) define SoC-level hardware — the CPU cores, interrupt controllers, and peripheral IP blocks. These are vendor-provided and rarely modified.
- **`.dts` files** define the board-level hardware — which pins are routed where, which peripherals are enabled, clock frequencies. These are board-specific.
- **Overlays** (`.overlay` files) let you modify the devicetree without touching the board's `.dts` file. This is how you add a sensor, change a pin assignment, or enable a second SPI bus for your application.

## Key Commands / Configuration / Code

### Understanding the devicetree structure

Let's look at a simplified excerpt from a typical board `.dts`:

```dts
/* boards/arm/nrf52840dk_nrf52840.dts */
#include <nordic/nrf52840_qiaa.dtsi>

/ {
    model = "Nordic nRF52840 DK";
    compatible = "nordic,nrf52840-dk";

    chosen {
        zephyr,console = &uart0;
        zephyr,shell-uart = &uart0;
    };

    leds {
        compatible = "gpio-leds";
        led0: led_0 {
            gpios = <&gpio0 13 GPIO_ACTIVE_LOW>;
            label = "Green LED 0";
        };
    };
};

&uart0 {
    compatible = "nordic,nrf-uarte";
    current-speed = <115200>;
    pinctrl-0 = <&uart0_default>;
    pinctrl-1 = <&uart0_sleep>;
    pinctrl-names = "default", "sleep";
    status = "okay";
};
```

Notice how `&uart0` references a node defined in the `.dtsi` file. The `.dtsi` provides the peripheral's register map and interrupts; the `.dts` sets pin control and enables it.

### Using overlays for application-specific hardware

Create `boards/nrf52840dk_nrf52840.overlay` in your project:

```dts
/* Enable SPI3 on the nRF52840 DK */
&spi3 {
    compatible = "nordic,nrf-spim";
    status = "okay";
    sck-pin = <17>;
    mosi-pin = <18>;
    miso-pin = <19>;
    cs-gpios = <&gpio0 20 GPIO_ACTIVE_LOW>;

    bme280: bme280@0 {
        compatible = "bosch,bme280";
        reg = <0>;
        spi-max-frequency = <1000000>;
    };
};
```

Then in your application code, access the sensor:

```c
#include <zephyr/devicetree.h>
#include <zephyr/drivers/sensor.h>

/* Get the node identifier from the devicetree */
#define BME280_NODE DT_NODELABEL(bme280)

void main(void)
{
    const struct device *dev = DEVICE_DT_GET(BME280_NODE);

    if (!device_is_ready(dev)) {
        printk("BME280 not ready\n");
        return;
    }

    struct sensor_value temp, press, humidity;
    sensor_sample_fetch(dev);
    sensor_channel_get(dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);
    printk("Temperature: %d.%06d C\n", temp.val1, temp.val2);
}
```

### Key build system integration

When you build, Zephyr's CMake system:
1. Reads the board's `.dts` file
2. Applies any `.overlay` files from your project
3. Runs `dtc` (devicetree compiler) to validate
4. Generates `include/generated/devicetree_generated.h` with macros

You can inspect the final merged devicetree with:

```bash
# After building, check the generated output
west build -t guiconfig  # Visual Kconfig + devicetree
# Or dump the final devicetree
west build -t devicetree
# The merged .dts is at build/zephyr/zephyr.dts
```

## Common Pitfalls & Gotchas

1. **Status = "okay" is mandatory** — Many peripherals are defined in `.dtsi` files with `status = "disabled"`. If you add an overlay that configures pins but forgets to set `status = "okay"`, the driver won't probe. This is the #1 devicetree bug I've seen.

2. **Pin conflicts are silent** — Devicetree won't warn you if two peripherals claim the same GPIO pin. The hardware will just behave unpredictably. Always cross-reference your board's pinout diagram.

3. **Overlay file naming matters** — Zephyr looks for overlays in specific locations. For a board named `nrf52840dk_nrf52840`, the overlay must be `boards/nrf52840dk_nrf52840.overlay` in your project root. A common mistake is naming it `nrf52840dk.overlay` (missing the variant suffix) or putting it in the wrong directory.

4. **DT macros are compile-time only** — You cannot change devicetree properties at runtime. If you need runtime reconfiguration (e.g., switching SPI pins), you need to implement that in your driver using pin control APIs, not devicetree.

## Try It Yourself

1. **Inspect your board's devicetree**: Build any sample for your board, then run `west build -t devicetree` and examine `build/zephyr/zephyr.dts`. Find the UART node and note its `current-speed` property and pin control configuration.

2. **Add an LED via overlay**: Create an overlay that adds a new LED node (use `gpio-leds` compatible) on an unused GPIO pin. Access it in code using `DT_NODELABEL()` and toggle it with `gpio_pin_set()`.

3. **Enable a disabled peripheral**: Find a peripheral in your board's `.dts` that has `status = "disabled"` (like I2C1 or SPI2). Write an overlay to enable it, configure its pins, and verify it appears in the generated `zephyr.dts` after rebuilding.

## Next Up

Tomorrow we'll dive into **Kconfig Deep Dive: Symbols, Dependencies & Menuconfig** — the configuration system that controls which drivers, subsystems, and features get compiled into your Zephyr build. We'll explore how Kconfig symbols interact with devicetree, how to trace dependency chains, and how to use `menuconfig` and `guiconfig` to untangle complex configurations.
