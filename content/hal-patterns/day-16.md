---
title: "Day 16: Zephyr Device Driver Model: device_api & DEVICE_DT_DEFINE"
date: 2026-07-16
tags: ["til", "hal-patterns", "zephyr", "device-model"]
---

## What I Explored Today

Today I dug into the Zephyr RTOS device driver model—specifically how `struct device_api` and the `DEVICE_DT_DEFINE` macro work together to create portable, hardware-abstracted drivers. I've been writing bare-metal HALs for years, and Zephyr's approach is a masterclass in decoupling driver logic from hardware specifics. The key insight: the device model isn't just about initialization ordering; it's about providing a stable API contract that lets application code work identically across MCUs, as long as the devicetree describes the hardware.

## The Core Concept

Zephyr's device model solves a fundamental portability problem: how do you write a driver that works on STM32, NXP, and Silabs parts without `#ifdef` hell? The answer is a two-part pattern:

1. **`struct device_api`** — a vtable-like structure of function pointers that defines the *interface* a driver exposes (e.g., `read`, `write`, `configure`). Every driver of a given class (I2C, SPI, UART) implements the same `device_api` struct, so application code calls `dev->api->read(...)` without caring which silicon is underneath.

2. **`DEVICE_DT_DEFINE`** — a macro that instantiates the driver instance, linking the devicetree node to the driver's init function, API struct, and private data. It handles init priority, power management, and dependency ordering automatically.

The beauty: you never hardcode base addresses or IRQ numbers. Everything comes from the devicetree via macros like `DT_REG_ADDR(node_id)` and `DT_IRQN(node_id)`. The driver code becomes a pure translation layer between the devicetree-provided hardware description and the `device_api` contract.

## Key Commands / Configuration / Code

### 1. Defining the API struct (in a header, e.g., `my_sensor.h`)

```c
// This is the contract every sensor driver must fulfill
struct my_sensor_api {
    int (*sample_fetch)(const struct device *dev, enum sensor_channel chan);
    int (*channel_get)(const struct device *dev,
                       enum sensor_channel chan,
                       struct sensor_value *val);
    int (*attr_set)(const struct device *dev,
                    enum sensor_channel chan,
                    enum sensor_attribute attr,
                    const struct sensor_value *val);
};
```

### 2. Implementing the driver (e.g., `my_bme280.c`)

```c
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/devicetree.h>

// Private data per-instance
struct bme280_data {
    int16_t temperature;
    uint16_t pressure;
    const struct device *i2c_dev;
    uint16_t i2c_addr;
};

// API function implementations
static int bme280_sample_fetch(const struct device *dev,
                                enum sensor_channel chan)
{
    struct bme280_data *data = dev->data;
    // Use devicetree-derived I2C bus and address
    uint8_t reg = 0xFA; // temperature MSB
    uint8_t buf[3];
    i2c_burst_read(data->i2c_dev, data->i2c_addr, reg, buf, 3);
    data->temperature = (buf[0] << 8) | buf[1];
    return 0;
}

static int bme280_channel_get(const struct device *dev,
                               enum sensor_channel chan,
                               struct sensor_value *val)
{
    struct bme280_data *data = dev->data;
    val->val1 = data->temperature / 100;
    val->val2 = (data->temperature % 100) * 10000;
    return 0;
}

// The API vtable — must match struct my_sensor_api exactly
static const struct sensor_api bme280_api = {
    .sample_fetch = bme280_sample_fetch,
    .channel_get = bme280_channel_get,
    .attr_set = NULL, // optional, can be NULL
};

// Init function — called at boot by Zephyr's init system
static int bme280_init(const struct device *dev)
{
    struct bme280_data *data = dev->data;
    // Get I2C bus from devicetree binding
    data->i2c_dev = DEVICE_DT_GET(DT_BUS(DT_NODELABEL(bme280)));
    data->i2c_addr = DT_REG_ADDR(DT_NODELABEL(bme280));
    // Perform hardware reset, check ID register
    return 0;
}

// Instantiate the driver — this is the magic macro
#define BME280_INIT(n)                                                        \
    static struct bme280_data bme280_data_##n;                                \
    DEVICE_DT_DEFINE(DT_DRV_INST(n),                                          \
                     bme280_init,                                             \
                     NULL,                                                    \
                     &bme280_data_##n,                                        \
                     NULL,                                                    \
                     POST_KERNEL,                                             \
                     CONFIG_SENSOR_INIT_PRIORITY,                             \
                     &bme280_api)

// Generate instances for each compatible node in devicetree
DT_INST_FOREACH_STATUS_OKAY(BME280_INIT)
```

### 3. Devicetree overlay (e.g., `boards/my_board.overlay`)

```dts
/ {
    sensors {
        compatible = "bosch,bme280";
        reg = <0x76>;
        status = "okay";
    };
};
```

## Common Pitfalls & Gotchas

1. **API struct field order must match exactly.** If your header declares `sample_fetch` first but your implementation puts `channel_get` first, the function pointer cast will invoke the wrong function at runtime. No compiler warning, just silent corruption. Always use designated initializers (C99) to avoid this.

2. **`DEVICE_DT_DEFINE` init priority is tricky.** If your driver depends on another driver (e.g., I2C), your init priority must be *lower* (higher number) than the dependency's init priority. Zephyr's `POST_KERNEL` is 40, `APPLICATION` is 50. Use `CONFIG_SENSOR_INIT_PRIORITY` (default 60) for sensors that need I2C/SPI ready. Getting this wrong causes silent hangs at boot.

3. **`DT_INST_FOREACH_STATUS_OKAY` generates code for *every* compatible node.** If you have two BME280s on the same bus, you get two driver instances with separate data structs. But if you forget to make `bme280_data` static per-instance (using the `n` token), both instances share the same memory—disaster. Always use the `##n` tokenization to create unique symbols.

## Try It Yourself

1. **Trace the macro expansion.** In your Zephyr project, add `-save-temps` to `EXTRA_CFLAGS` in `CMakeLists.txt`. Compile a driver that uses `DEVICE_DT_DEFINE`, then inspect the preprocessed `.i` file. See how the macro expands to `Z_DEVICE_DEFINE` and eventually to a `struct device` in the linker section.

2. **Add a custom API function.** Extend the `my_sensor_api` header with a `calibrate` function pointer. Implement it in the BME280 driver (e.g., write a calibration coefficient to EEPROM). Update the `bme280_api` struct and call it from an application via `dev->api->calibrate(dev)`.

3. **Port a bare-metal driver to Zephyr.** Take any simple peripheral driver you've written (e.g., a GPIO-based LED driver). Replace hardcoded base addresses with `DT_REG_ADDR(DT_NODELABEL(my_led))` and wrap it in `DEVICE_DT_DEFINE`. Verify it works on a different board by changing only the devicetree overlay.

## Next Up

Tomorrow: **Board Support Packages: Structuring Board-Specific Code** — we'll explore how Zephyr's BSP model organizes pinmux, clock config, and board-level init into reusable `board.c` files, and how to avoid the "board spaghetti" anti-pattern when supporting multiple hardware revisions.
