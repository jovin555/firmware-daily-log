---
title: "Day 12: I2C Driver API: Controller & Target Mode"
date: 2026-06-24
tags: ["til", "zephyr", "i2c", "drivers"]
---

## What I Explored Today

Today I dove into Zephyr's I2C driver API, focusing on both controller (master) and target (slave) modes. I2C is the backbone of sensor and peripheral communication in embedded systems, and Zephyr provides a clean, asynchronous-capable API that abstracts the hardware specifics. I wired up an I2C temperature sensor as a controller and configured a second board as a target to understand the bidirectional flow. The API is consistent across all supported SoCs, but the devicetree binding and runtime configuration have some sharp edges worth documenting.

## The Core Concept

I2C is a two-wire, multi-controller, multi-target bus. In Zephyr, the API is split into two logical roles: **controller** (initiates transactions, generates clock) and **target** (responds to controller requests). Why does this matter? Because many embedded systems need to both read sensors (controller mode) and expose data to an external host (target mode). Zephyr's API handles both with the same `struct i2c_dt_spec` device handle, but the configuration differs significantly.

The key insight is that Zephyr's I2C API is **transaction-based**, not register-based. You don't write to a register address directly; you construct a `struct i2c_msg` array that describes the bus transaction. This allows for combined transfers (write-then-read without a stop condition), which is essential for devices like IMUs and ADCs that use register-based protocols. The API also supports asynchronous transfers via callbacks, though the synchronous `i2c_write_read_dt()` is the workhorse for most applications.

## Key Commands / Configuration / Code

### Devicetree Binding (Controller Mode)
```dts
&i2c1 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;  /* 400 kHz */
    temp_sensor: tmp117@48 {
        compatible = "ti,tmp117";
        reg = <0x48>;  /* 7-bit address */
    };
};
```

### Controller: Reading a Sensor Register
```c
#include <zephyr/drivers/i2c.h>

static const struct i2c_dt_spec dev_i2c = I2C_DT_SPEC_GET(DT_NODELABEL(temp_sensor));

uint16_t read_temperature(void) {
    uint8_t reg_addr = 0x00;  // TMP117 temperature register
    uint8_t rx_buf[2] = {0};

    /* Combined transfer: write reg addr, then read 2 bytes */
    struct i2c_msg msgs[] = {
        {
            .buf = &reg_addr,
            .len = 1,
            .flags = I2C_MSG_WRITE,
        },
        {
            .buf = rx_buf,
            .len = 2,
            .flags = I2C_MSG_READ | I2C_MSG_STOP,
        },
    };

    int ret = i2c_transfer_dt(&dev_i2c, msgs, 2);
    if (ret < 0) {
        printk("I2C transfer failed: %d\n", ret);
        return 0;
    }

    return (rx_buf[0] << 8) | rx_buf[1];
}
```

### Target Mode Configuration
```c
#include <zephyr/drivers/i2c.h>

/* Target buffer: 4 bytes that the controller can read/write */
static uint8_t target_buf[4] = {0xAA, 0xBB, 0xCC, 0xDD};

/* Callback when controller writes to us */
static int target_write_requested(struct i2c_target_config *config,
                                  struct i2c_target_data *data) {
    data->buf = target_buf;
    data->len = sizeof(target_buf);
    return 0;
}

/* Callback when controller reads from us */
static int target_read_requested(struct i2c_target_config *config,
                                 struct i2c_target_data *data) {
    data->buf = target_buf;
    data->len = sizeof(target_buf);
    return 0;
}

static const struct i2c_target_callbacks target_cb = {
    .write_requested = target_write_requested,
    .read_requested = target_read_requested,
};

static struct i2c_target_config target_cfg = {
    .address = 0x48,
    .callbacks = &target_cb,
};

/* In your init */
const struct device *i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c1));
i2c_target_register(i2c_dev, &target_cfg);
```

### Kconfig Dependencies
```kconfig
CONFIG_I2C=y
CONFIG_I2C_TARGET=y          # Required for target mode
CONFIG_I2C_INIT_PRIORITY=80  # Default, adjust if needed
```

## Common Pitfalls & Gotchas

1. **Devicetree address mismatch**: The `reg` property in devicetree must match the 7-bit I2C address. Many datasheets list an 8-bit address (shifted left by 1). Always use the 7-bit address in devicetree. For example, a sensor with datasheet address `0x90` (write) / `0x91` (read) uses `reg = <0x48>`.

2. **Missing `I2C_MSG_STOP` on last message**: If you forget to set `I2C_MSG_STOP` on the final message in a transfer, the bus will be held in a repeated-start condition. This locks the bus until a timeout or reset. Always ensure the last message has `I2C_MSG_STOP` set.

3. **Target mode buffer ownership**: In target mode, the buffer you provide in the callback must remain valid until the transfer completes. If you use a stack-allocated buffer, the callback returns, the stack frame is popped, and the I2C controller will DMA into garbage. Always use static or heap-allocated buffers for target mode.

## Try It Yourself

1. **Read a sensor with combined transfer**: Wire up a TMP117 or BME280 sensor. Implement a function that reads the device ID register (0x0F for TMP117) using a combined write-read transfer. Verify the returned ID matches the datasheet.

2. **Implement a target echo server**: Configure a second board as an I2C target at address 0x40. When the controller writes a byte, echo it back on the next read. Use the `write_received` and `read_requested` callbacks.

3. **Debug with logic analyzer**: Connect a logic analyzer to SDA/SCL. Trigger a burst of 100 reads from your controller. Capture the waveform and verify: start condition, address byte (7-bit + R/W), ACK/NACK, data bytes, stop condition. Compare with the I2C specification timing diagram.

## Next Up

Tomorrow, we tackle **SPI Driver API: Full-Duplex & DMA Transfers**. SPI's simultaneous send/receive capability and high-speed DMA integration make it the go-to for ADCs, displays, and flash memory. We'll cover the `spi_transceive()` API, circular DMA buffers, and the devicetree quirks that trip up even experienced engineers.
