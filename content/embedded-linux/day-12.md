---
title: "Day 12: I2C Client Drivers: i2c_driver & Adapter API"
date: 2026-06-24
tags: ["til", "embedded-linux", "i2c", "driver"]
---

## What I Explored Today

Today I dug into writing an I2C client driver from scratch—not just reading/writing registers, but understanding how `i2c_driver` binds to a device, how the adapter layer abstracts the bus controller, and how to use the `i2c_transfer()` API correctly. I walked through the probe/remove lifecycle, message construction, and the subtle differences between SMBus and plain I2C transfers. This is the foundation for any sensor, EEPROM, or DAC driver on embedded Linux.

## The Core Concept

An I2C client driver lives on top of two layers: the **adapter** (the hardware controller, e.g., i.MX6 I2C, RPi BSC) and the **core** (i2c-core.c). Your driver doesn't touch adapter registers—it uses the `i2c_adapter`'s `master_xfer` callback via `i2c_transfer()`. The `i2c_driver` struct is your registration point; it declares which devices you support (via `id_table` or OF match) and provides `probe`/`remove` hooks.

Why not just use `i2c_smbus_read_byte_data()` everywhere? Because SMBus is a subset of I2C with stricter timing and protocol rules. Many sensors use plain I2C combined transactions (write address, then repeated start for read). The `i2c_msg` struct gives you full control: you can build a write-then-read sequence in one transfer, which is atomic on the bus. This matters for devices like the MPU6050 where you must set the register pointer before reading.

## Key Commands / Configuration / Code

### Minimal i2c_driver skeleton

```c
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>

static int my_probe(struct i2c_client *client, const struct i2c_device_id *id)
{
    dev_info(&client->dev, "Probed device %s at addr 0x%02x\n",
             client->name, client->addr);
    // Allocate private data, init hardware, register with subsystems
    return 0;
}

static void my_remove(struct i2c_client *client)
{
    dev_info(&client->dev, "Removing\n");
    // Free resources, power down
}

static const struct i2c_device_id my_id_table[] = {
    { "my-sensor", 0 },
    { }
};
MODULE_DEVICE_TABLE(i2c, my_id_table);

static const struct of_device_id my_of_match[] = {
    { .compatible = "vendor,my-sensor" },
    { }
};
MODULE_DEVICE_TABLE(of, my_of_match);

static struct i2c_driver my_driver = {
    .driver = {
        .name = "my-sensor",
        .of_match_table = my_of_match,
    },
    .probe    = my_probe,
    .remove   = my_remove,
    .id_table = my_id_table,
};
module_i2c_driver(my_driver);
MODULE_LICENSE("GPL");
```

### Building a combined write-read transfer

```c
static int sensor_read_reg(struct i2c_client *client, u8 reg, u8 *val)
{
    struct i2c_msg msgs[2];
    int ret;

    /* Message 0: write register address */
    msgs[0].addr = client->addr;
    msgs[0].flags = 0;                // write
    msgs[0].len = 1;
    msgs[0].buf = &reg;

    /* Message 1: read data (repeated start automatically) */
    msgs[1].addr = client->addr;
    msgs[1].flags = I2C_M_RD;        // read
    msgs[1].len = 1;
    msgs[1].buf = val;

    ret = i2c_transfer(client->adapter, msgs, 2);
    if (ret < 0)
        return ret;
    if (ret != 2)
        return -EIO;                  // incomplete transfer
    return 0;
}
```

### Using SMBus helpers (when appropriate)

```c
// Single-byte read (SMBus equivalent of above)
u8 val = i2c_smbus_read_byte_data(client, 0x1A);
if (val < 0)
    dev_err(&client->dev, "SMBus read failed: %d\n", val);

// Block read for EEPROM page
u8 buf[32];
int ret = i2c_smbus_read_i2c_block_data(client, 0x00, 32, buf);
```

### Device tree node

```dts
&i2c2 {
    status = "okay";
    clock-frequency = <100000>;

    my-sensor@48 {
        compatible = "vendor,my-sensor";
        reg = <0x48>;
    };
};
```

## Common Pitfalls & Gotchas

1. **Forgetting repeated start is automatic** — When you pass an array of `i2c_msg` to `i2c_transfer()`, the adapter inserts a repeated start (Sr) between messages. Do NOT insert a stop condition yourself. If you need a stop between messages, you must call `i2c_transfer()` twice. This trips up people coming from bare-metal I2C bit-banging.

2. **SMBus vs I2C protocol mismatch** — Some controllers (e.g., DesignWare I2C) implement SMBus in hardware and reject plain I2C transfers that violate SMBus timing. If your device needs clock stretching or combined transactions with >255 bytes, you must use `i2c_transfer()` with `I2C_M_NOSTART` carefully. Always check the adapter's `quirks` field: `i2c_check_quirks(adap, I2C_AQ_COMB_WRITE_THEN_READ)`.

3. **Probe ordering and deferred probing** — Your `probe()` can return `-EPROBE_DEFER` if a resource (regulator, GPIO, clock) isn't ready. The I2C core will retry later. But if your device is on a muxed bus (i2c-mux), the mux must probe first. Use `devm_*` APIs to avoid leaks on deferred probe.

4. **Not checking `i2c_transfer()` return value** — It returns the number of messages transferred, not a negative error for partial transfers. Always compare against the expected count. A return of 1 when you sent 2 messages means the read never happened.

## Try It Yourself

1. **Write a driver for a virtual EEPROM** — Use the `at24` driver as reference. Implement `probe` that reads the first 16 bytes using `i2c_smbus_read_i2c_block_data()` and prints them. Bind it to a device on your board's I2C bus.

2. **Add a combined read function** — Extend your driver to use `i2c_transfer()` with two messages. Compare the timing with `i2c_smbus_read_byte_data()` using a logic analyzer or `ftrace` on the I2C functions.

3. **Handle clock stretching** — Find a sensor that stretches the clock (e.g., BME280). Verify your adapter supports it via `/sys/bus/i2c/devices/i2c-N/`. If not, add `I2C_FUNC_PROTOCOL_MANGLING` to your adapter's functionality and test.

## Next up

Tomorrow: **SPI Client Drivers: spi_driver & Transfer API** — We'll cover the `spi_device` registration, `spi_message` construction, and how to handle chip-select deassertion timing. SPI is faster but trickier with its four-wire dance and full-duplex nature.
