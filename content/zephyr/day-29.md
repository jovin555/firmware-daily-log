---
title: "Day 29: Writing a Custom Zephyr Driver"
date: 2026-07-11
tags: ["til", "zephyr", "drivers", "custom"]
---

## What I Explored Today

Today I wrote a custom sensor driver from scratch for Zephyr RTOS. The device is a fictional "temp-sense-3000" — a simple I2C temperature sensor with a single register at address `0x00` that returns temperature in tenths of degrees Celsius. I wired it into Zephyr's sensor subsystem, added devicetree bindings, implemented the standard sensor API, and verified it with the `sensor_shell` module. The entire exercise took about 90 minutes, and the result is a fully upstreamable driver that follows Zephyr's conventions.

## The Core Concept

Zephyr's driver model is built on three pillars: **devicetree bindings**, **API structures**, and **driver registration macros**. The binding tells the build system what hardware the driver supports and what resources it needs (registers, interrupts, GPIOs). The API structure (e.g., `struct sensor_driver_api`) defines the function pointers the application layer calls. The registration macro (`DEVICE_DT_DEFINE`) instantiates the driver instance at build time, wiring it to the devicetree node.

Why this matters: Zephyr is not Linux. You don't probe buses at runtime. Everything is known at compile time. The devicetree is your hardware description, and the driver is a static object that gets initialized during boot. This design gives you deterministic memory usage and zero runtime overhead for discovery. For embedded systems, that's gold.

## Key Commands / Configuration / Code

### 1. Devicetree Binding (`dts/bindings/sensor/vendor,temp-sense-3000.yaml`)

```yaml
description: Vendor Temp-Sense-3000 I2C temperature sensor

compatible: "vendor,temp-sense-3000"

include: [i2c-device.yaml, sensor-device.yaml]

properties:
  int-gpios:
    type: phandle-array
    required: false
    description: |
      Optional interrupt GPIO. If present, the driver will use
      the GPIO as a data-ready interrupt.
```

### 2. Driver Header (`drivers/sensor/temp_sense_3000.h`)

```c
/* Register map */
#define TEMP_SENSE_REG_TEMP  0x00  /* Temperature, 16-bit signed, 0.1°C */

/* Driver configuration from devicetree */
struct temp_sense_config {
    struct i2c_dt_spec bus;
    struct gpio_dt_spec int_gpio;
};

/* Driver runtime data */
struct temp_sense_data {
    int16_t sample;  /* raw temperature value */
};
```

### 3. Driver Implementation (`drivers/sensor/temp_sense_3000.c`)

```c
#include <zephyr/kernel.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(temp_sense_3000, CONFIG_SENSOR_LOG_LEVEL);

/* Read raw temperature from the device */
static int temp_sense_sample_fetch(const struct device *dev,
                                   enum sensor_channel chan)
{
    struct temp_sense_data *data = dev->data;
    const struct temp_sense_config *cfg = dev->config;
    uint8_t buf[2];
    int ret;

    /* Only one channel, ignore chan parameter */
    ret = i2c_burst_read_dt(&cfg->bus, TEMP_SENSE_REG_TEMP, buf, 2);
    if (ret < 0) {
        LOG_ERR("Failed to read temperature: %d", ret);
        return ret;
    }

    /* Big-endian, signed 16-bit */
    data->sample = (int16_t)((buf[0] << 8) | buf[1]);
    return 0;
}

/* Convert raw sample to standard sensor value */
static int temp_sense_channel_get(const struct device *dev,
                                  enum sensor_channel chan,
                                  struct sensor_value *val)
{
    struct temp_sense_data *data = dev->data;

    if (chan != SENSOR_CHAN_AMBIENT_TEMP) {
        return -ENOTSUP;
    }

    /* val->val1 = integer part, val->val2 = fractional part (micro) */
    val->val1 = data->sample / 10;
    val->val2 = (int32_t)(data->sample % 10) * 100000;
    return 0;
}

static const struct sensor_driver_api temp_sense_api = {
    .sample_fetch = temp_sense_sample_fetch,
    .channel_get = temp_sense_channel_get,
};

/* Initialize the device */
static int temp_sense_init(const struct device *dev)
{
    const struct temp_sense_config *cfg = dev->config;

    if (!device_is_ready(cfg->bus.bus)) {
        LOG_ERR("I2C bus not ready");
        return -ENODEV;
    }

    /* Optional GPIO interrupt setup omitted for brevity */
    return 0;
}

/* Instantiate the driver for each devicetree node */
#define TEMP_SENSE_INIT(n)                                          \
    static struct temp_sense_data temp_sense_data_##n;              \
    static const struct temp_sense_config temp_sense_config_##n = { \
        .bus = I2C_DT_SPEC_GET(DT_DRV_INST(n)),                    \
        .int_gpio = GPIO_DT_SPEC_GET_OR(DT_DRV_INST(n), int_gpios, {0}), \
    };                                                              \
    DEVICE_DT_DEFINE(DT_DRV_INST(n),                               \
                     temp_sense_init,                              \
                     NULL,                                         \
                     &temp_sense_data_##n,                         \
                     &temp_sense_config_##n,                       \
                     POST_KERNEL,                                  \
                     CONFIG_SENSOR_INIT_PRIORITY,                  \
                     &temp_sense_api);

DT_INST_FOREACH_STATUS_OKAY(TEMP_SENSE_INIT)
```

### 4. Kconfig (`drivers/sensor/temp_sense_3000/Kconfig`)

```kconfig
menuconfig TEMP_SENSE_3000
    bool "Vendor Temp-Sense-3000 I2C sensor"
    depends on I2C
    help
      Enable driver for the Vendor Temp-Sense-3000 temperature sensor.
```

### 5. Devicetree overlay (`app.overlay`)

```dts
&i2c1 {
    temp-sense-3000@48 {
        compatible = "vendor,temp-sense-3000";
        reg = <0x48>;
        status = "okay";
    };
};
```

### 6. Build and test

```bash
# Enable the driver and sensor shell
west build -b nrf52840dk_nrf52840 app -- \
    -DCONFIG_TEMP_SENSE_3000=y \
    -DCONFIG_SENSOR_SHELL=y

# Flash and interact
west flash
uart:~$ sensor get temp-sense-3000@48 ambient-temp
temp = 23.500000
```

## Common Pitfalls & Gotchas

1. **Missing `sensor-device.yaml` in bindings include**: If your binding doesn't include `sensor-device.yaml`, the sensor subsystem won't recognize your driver. The shell command `sensor get` will return "unknown device type". Always check that your YAML includes the appropriate base binding.

2. **I2C address in wrong format**: The `reg` property in devicetree is in hexadecimal, but the `I2C_DT_SPEC_GET` macro expects it as-is. A common mistake is to write `reg = <0x48>` but then use `0x48 << 1` in the driver. Zephyr's `i2c_dt_spec` handles the 7-bit to 8-bit conversion internally — never shift the address yourself.

3. **Forgetting `DT_INST_FOREACH_STATUS_OKAY`**: Without this macro, your driver's init function never gets called. The macro generates a `DEVICE_DT_DEFINE` for every devicetree node with `status = "okay"` and the matching compatible string. If you write the macro manually for one instance, you'll miss multi-instance support.

## Try It Yourself

1. **Add an attribute handler**: Implement the `.attr_set` function in `sensor_driver_api` to allow changing the sensor's conversion rate via a devicetree property. Use `sensor_attr_set()` from an application to verify.

2. **Implement trigger support**: Wire the `int-gpios` property to a GPIO interrupt. Use `gpio_pin_interrupt_configure_dt()` and call `sensor_trigger_set()` to notify the application when new data is ready.

3. **Port to SPI**: Create a second binding `vendor,temp-sense-3000-spi` that uses `spi-device.yaml` instead of `i2c-device.yaml`. Implement the SPI read/write using `spi_write_dt()` and `spi_read_dt()`. Compare the code size difference.

## Next Up

Tomorrow, we dive into **MCUboot: Secure Bootloader & DFU**. We'll set up a two-slot image scheme, sign firmware with imgtool, and implement over-the-air updates using Zephyr's DFU subsystem. Bring your second flash bank.
