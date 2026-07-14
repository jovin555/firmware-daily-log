---
title: "Day 32: Full Review & Project: BLE Sensor Node"
date: 2026-07-14
tags: ["til", "zephyr", "review", "project"]
---

## What I Explored Today

After 31 days of building up Zephyr concepts piece by piece—from threads and semaphores to BLE advertising and sensor drivers—today I pulled everything together into a single, real-world project: a BLE sensor node that reads temperature from an onboard sensor and broadcasts it over Bluetooth Low Energy. This wasn't just a "hello world" with BLE; it was a complete, production-style integration that exercises device tree bindings, sensor API, BLE advertising with manufacturer-specific data, power management hooks, and a custom shell command for debugging. The result is a node that an nRF Connect app can scan and display live temperature readings.

## The Core Concept

The reason this project matters is that embedded systems rarely live in isolation. A sensor that can't communicate is just a paperweight. BLE is the de facto wireless standard for low-power sensor nodes, and Zephyr's stack is mature enough to handle the full pipeline: sensor acquisition, data formatting, advertising payload construction, and periodic broadcast. The "why" here is about understanding the data flow from hardware register to radio packet. You don't just call `sensor_sample_fetch()` and `bt_le_adv_start()`—you need to ensure the sensor is powered, the BLE stack is initialized, the advertising data is properly encoded (especially for manufacturer-specific fields), and that the timing doesn't starve other system tasks. This project forces you to think about the entire vertical slice.

## Key Commands / Configuration / Code

### 1. Device Tree Overlay (for a simulated sensor on nRF52840 DK)

```dts
// boards/nrf52840dk_nrf52840.overlay
/ {
    temp-sensor {
        compatible = "fake,temp-sensor";
        status = "okay";
        label = "TEMP0";
    };
};
```

*Note: Replace with your actual sensor compatible, e.g., `bosch,bme280` for a real I2C sensor.*

### 2. prj.conf — Minimal BLE + Sensor Config

```kconfig
# General
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_DEVICE_NAME="ZephyrTempNode"

# Sensor
CONFIG_SENSOR=y
CONFIG_FAKE_TEMP_SENSOR=y   # or your sensor driver Kconfig

# Power management (optional but good practice)
CONFIG_PM=y
CONFIG_PM_DEVICE=y

# Shell for debugging
CONFIG_SHELL=y
```

### 3. Main Application Code (core logic)

```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/sys/printk.h>

#define ADV_PERIOD_MS 1000

static const struct device *temp_sensor;
static int16_t last_temp;  // in 0.01°C

/* Callback for BLE connected/disconnected */
static void connected(struct bt_conn *conn, uint8_t err) {
    if (err) {
        printk("Connection failed (err %u)\n", err);
    } else {
        printk("Connected\n");
    }
}

static void disconnected(struct bt_conn *conn, uint8_t reason) {
    printk("Disconnected (reason %u)\n", reason);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
};

/* Build advertising packet with manufacturer-specific data */
static int update_adv_data(int16_t temp) {
    uint8_t mfg_data[3] = {
        0x59, 0x00,          // Company ID: Nordic Semiconductor (0x0059)
        (uint8_t)(temp & 0xFF) // LSB of temperature
    };
    // In real code, encode full int16_t across 2 bytes

    struct bt_data ad[] = {
        BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
        BT_DATA(BT_DATA_MANUFACTURER_DATA, mfg_data, sizeof(mfg_data)),
    };

    return bt_le_adv_start(BT_LE_ADV_NCONN, ad, ARRAY_SIZE(ad), NULL, 0);
}

void main(void) {
    int err;

    /* Initialize BLE */
    err = bt_enable(NULL);
    if (err) {
        printk("Bluetooth init failed (err %d)\n", err);
        return;
    }
    printk("Bluetooth initialized\n");

    /* Get sensor device */
    temp_sensor = DEVICE_DT_GET_ANY(fake_temp_sensor);
    if (!temp_sensor || !device_is_ready(temp_sensor)) {
        printk("Sensor not found or not ready\n");
        return;
    }

    /* Main loop: fetch sensor, update advertising */
    while (1) {
        struct sensor_value val;

        err = sensor_sample_fetch(temp_sensor);
        if (err) {
            printk("Sensor fetch failed (err %d)\n", err);
            k_sleep(K_MSEC(ADV_PERIOD_MS));
            continue;
        }

        sensor_channel_get(temp_sensor, SENSOR_CHAN_AMBIENT_TEMP, &val);
        last_temp = (int16_t)(val.val1 * 100 + val.val2 / 10000); // to 0.01°C

        err = update_adv_data(last_temp);
        if (err) {
            printk("Advertising update failed (err %d)\n", err);
        }

        printk("Broadcasting temp: %d.%02d °C\n", last_temp / 100, abs(last_temp % 100));
        k_sleep(K_MSEC(ADV_PERIOD_MS));
    }
}
```

### 4. Build & Flash

```bash
west build -b nrf52840dk_nrf52840 . -p
west flash
```

## Common Pitfalls & Gotchas

1. **Advertising data too large**  
   BLE advertising packets have a 31-byte limit. If you pack manufacturer data, name, and service UUIDs, you'll hit `-EINVAL` silently. Always check `bt_le_adv_start()` return value. Use `BT_DATA_BYTES` for fixed-size fields and avoid `BT_DATA_NAME_COMPLETE` if you're tight.

2. **Sensor not ready at boot**  
   Some sensors (especially I2C/SPI) need time to power up. `device_is_ready()` returns false if the driver probe hasn't completed. Add a small `k_sleep(K_MSEC(100))` after `bt_enable()` if your sensor is on an external bus.

3. **BLE stack not started before advertising**  
   `bt_enable()` is asynchronous; the `BT_READY` callback fires when the stack is up. If you call `bt_le_adv_start()` before that, you get `-EAGAIN`. The code above uses `bt_enable(NULL)` (blocking) to avoid this, but if you use the async variant, guard with a semaphore.

## Try It Yourself

1. **Extend the advertising data** to include battery level. Add a voltage divider on an ADC pin, read it with `adc_read()`, and encode the percentage in the manufacturer data alongside temperature.  
2. **Add a shell command** to manually trigger a sensor read and print the raw value. Use `SHELL_CMD_REGISTER(temp, ...)` and call `sensor_sample_fetch()` from the shell handler.  
3. **Implement power management**: In `main()`, after advertising, call `pm_device_action_run(temp_sensor, PM_DEVICE_ACTION_SUSPEND)` and resume only before the next fetch. Measure current draw with a power profiler.

## Next Up

Tomorrow, Day 33: **Full Review: Zephyr Power Management & Energy Profiling** — we'll dissect the PM subsystem, learn how to profile real power consumption with a Nordic PPK2, and optimize the sensor node for months of battery life.
