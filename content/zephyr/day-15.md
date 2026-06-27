---
title: "Day 15: Sensor API: Generic Sensor Framework & SENSOR_CHAN"
date: 2026-06-27
tags: ["til", "zephyr", "sensors", "api"]
---

## What I Explored Today

Today I dove into Zephyr’s generic sensor driver framework, which provides a unified API for reading data from any sensor—whether it’s a temperature sensor, accelerometer, or magnetometer. The key abstraction is `SENSOR_CHAN`, an enum that maps physical measurements (like acceleration in m/s² or temperature in Celsius) to a standard channel identifier. I wired up an LSM6DSO IMU on an STM32 board, configured it via device tree, and read accelerometer and gyroscope data using the `sensor_sample_fetch()` and `sensor_channel_get()` API calls. The framework handles the hardware-specific details, letting me focus on application logic.

## The Core Concept

Why does Zephyr need a generic sensor framework? In embedded systems, sensors are everywhere, but their drivers are notoriously vendor-specific. One accelerometer might return raw ADC counts, another might return milli-g’s, and a third might require a complex SPI transaction just to get a reading. Without a standard API, swapping sensors means rewriting all the application code.

Zephyr’s sensor API solves this by defining a **channel-based abstraction**. Each physical measurement (e.g., acceleration on the X-axis) is a `SENSOR_CHAN` value. The driver handles the conversion from raw sensor data to SI units (or a standard representation). The application calls `sensor_sample_fetch()` to trigger a reading, then `sensor_channel_get()` to retrieve the value as a `struct sensor_value` (which contains an integer and fractional part). This decouples the application from the hardware: you can swap an LSM6DSO for an MPU6050 by changing only the device tree binding and driver Kconfig—the application code stays the same.

The framework also supports **triggers** (interrupt-driven sampling) and **attributes** (setting sensor configuration like sampling rate or range), but the core is the fetch-and-get pattern.

## Key Commands / Configuration / Code

### Device Tree Binding (for LSM6DSO on STM32)

```dts
&i2c1 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;

    lsm6dso: lsm6dso@6b {
        compatible = "st,lsm6dso";
        reg = <0x6b>;
        status = "okay";
        irq-gpios = <&gpioa 1 GPIO_ACTIVE_HIGH>;
    };
};
```

### Application Code: Reading Accelerometer and Gyroscope

```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>

void main(void)
{
    const struct device *sensor_dev = DEVICE_DT_GET_ONE(st_lsm6dso);
    struct sensor_value accel_x, accel_y, accel_z;
    struct sensor_value gyro_x, gyro_y, gyro_z;

    if (!device_is_ready(sensor_dev)) {
        printk("Sensor device not ready\n");
        return;
    }

    while (1) {
        // Trigger a sensor sample fetch (blocking)
        if (sensor_sample_fetch(sensor_dev) < 0) {
            printk("Sample fetch failed\n");
            continue;
        }

        // Retrieve accelerometer channels
        sensor_channel_get(sensor_dev, SENSOR_CHAN_ACCEL_X, &accel_x);
        sensor_channel_get(sensor_dev, SENSOR_CHAN_ACCEL_Y, &accel_y);
        sensor_channel_get(sensor_dev, SENSOR_CHAN_ACCEL_Z, &accel_z);

        // Retrieve gyroscope channels
        sensor_channel_get(sensor_dev, SENSOR_CHAN_GYRO_X, &gyro_x);
        sensor_channel_get(sensor_dev, SENSOR_CHAN_GYRO_Y, &gyro_y);
        sensor_channel_get(sensor_dev, SENSOR_CHAN_GYRO_Z, &gyro_z);

        // Print values: val1 is integer part, val2 is fractional (1e-6)
        printk("Accel: %d.%06d, %d.%06d, %d.%06d (m/s^2)\n",
               accel_x.val1, accel_x.val2,
               accel_y.val1, accel_y.val2,
               accel_z.val1, accel_z.val2);
        printk("Gyro:  %d.%06d, %d.%06d, %d.%06d (rad/s)\n",
               gyro_x.val1, gyro_x.val2,
               gyro_y.val1, gyro_y.val2,
               gyro_z.val1, gyro_z.val2);

        k_sleep(K_MSEC(100));
    }
}
```

### Kconfig (prj.conf)

```kconfig
CONFIG_I2C=y
CONFIG_SENSOR=y
CONFIG_LSM6DSO=y
```

## Common Pitfalls & Gotchas

1. **`sensor_sample_fetch()` is not always a one-shot**  
   For some sensors (e.g., those with FIFO buffers), `sensor_sample_fetch()` may retrieve multiple samples. If you call `sensor_channel_get()` once, you only get the latest. Always check the driver documentation—some drivers require `sensor_sample_fetch_chan()` to fetch a specific channel.

2. **`struct sensor_value` is not a float**  
   The `val1` and `val2` fields represent a fixed-point number: `val1 + val2 * 10^-6`. Printing it with `%f` will give garbage. Always use `%d.%06d` as shown above, or convert to float with `sensor_value_to_double()` (available in `<zephyr/drivers/sensor.h>`).

3. **Device tree alias vs. `DEVICE_DT_GET_ONE`**  
   `DEVICE_DT_GET_ONE(st_lsm6dso)` works only if exactly one node has that compatible. If you have multiple sensors of the same type, use `DEVICE_DT_GET(DT_NODELABEL(lsm6dso))` with a node label. Forgetting this leads to build errors about ambiguous matches.

## Try It Yourself

1. **Add a second sensor** (e.g., a DHT22 temperature/humidity sensor) to your board’s device tree and read `SENSOR_CHAN_AMBIENT_TEMP` and `SENSOR_CHAN_HUMIDITY`. Verify the values make sense with a known environment.

2. **Implement a trigger** (interrupt-driven sampling): Configure the LSM6DSO’s INT1 pin to fire on data ready. Use `sensor_trigger_set()` with `SENSOR_TRIG_DATA_READY` and a callback to avoid polling.

3. **Change the sensor’s output data rate (ODR)** using `sensor_attr_set()` with `SENSOR_ATTR_SAMPLING_FREQUENCY`. Measure the difference in power consumption with a current probe or by counting samples per second.

## Next Up

Tomorrow, we’ll tackle **Flash & NVS: Non-Volatile Storage in Zephyr**—how to store calibration data, settings, and logs in flash using the NVS (Non-Volatile Storage) subsystem, with wear-leveling and atomic writes.
