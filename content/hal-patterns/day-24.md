---
title: "Day 24: Full Review & Project: Vendor-Agnostic SPI Sensor Driver"
date: 2026-07-24
tags: ["til", "hal-patterns", "review", "project"]
---

## What I Explored Today

Today I wrapped up the SPI sensor driver series by building a complete, vendor-agnostic driver for a generic SPI temperature sensor (modeled after the ADT7310 but abstracted). The goal was to take every pattern from the past 23 days—HAL abstraction, register maps, error propagation, DMA vs. polling, and callback design—and fuse them into a single production-ready module. I wrote the driver in C, targeting any MCU with a standard SPI HAL, and validated the design against both STM32 and NXP LPC platforms. The result is a driver that compiles unchanged across vendors, with only a platform-specific HAL init file needed.

## The Core Concept

The fundamental insight behind vendor-agnostic SPI drivers is that the SPI protocol itself is standardized—only the MCU's register access mechanism differs. By defining a thin abstraction layer over the HAL's SPI transmit/receive functions, we decouple the sensor logic from the silicon. This means the same `sensor_read_temperature()` function works whether you're on an STM32 using `HAL_SPI_TransmitReceive()` or an NXP LPC using `LPC_SPI_Transfer()`. The abstraction is a struct of function pointers, often called a "HAL interface" or "SPI bus handle." The sensor driver never calls a vendor HAL directly; it calls through the interface. This pattern eliminates vendor lock-in, simplifies porting, and makes unit testing possible by swapping in mock interfaces.

## Key Commands / Configuration / Code

Below is the core of the vendor-agnostic SPI sensor driver. The critical piece is the `spi_bus_t` struct that encapsulates the platform-specific calls.

```c
// spi_sensor_hal.h — The abstraction layer
#ifndef SPI_SENSOR_HAL_H
#define SPI_SENSOR_HAL_H

#include <stdint.h>
#include <stddef.h>

typedef struct {
    // Platform-specific context (e.g., SPI_HandleTypeDef* on STM32)
    void* bus_handle;
    // Function pointers for SPI operations
    int (*transmit)(void* handle, const uint8_t* tx_data, size_t len);
    int (*receive)(void* handle, uint8_t* rx_data, size_t len);
    int (*transmit_receive)(void* handle, const uint8_t* tx_data,
                            uint8_t* rx_data, size_t len);
    // Optional: chip select control (if not handled by HAL)
    void (*cs_control)(void* handle, uint8_t assert);
} spi_bus_t;

#endif // SPI_SENSOR_HAL_H
```

```c
// spi_sensor.c — Vendor-agnostic driver
#include "spi_sensor.h"
#include "spi_sensor_hal.h"

// Register map for ADT7310-like sensor
#define REG_TEMP_MSB      0x01
#define REG_CONFIG        0x03
#define REG_ID            0x0F

// Configuration: 16-bit temperature, continuous conversion
#define CONFIG_VAL        0x00A0

static const spi_bus_t* bus = NULL;

int sensor_init(const spi_bus_t* spi_bus) {
    if (!spi_bus || !spi_bus->transmit_receive) return -1;
    bus = spi_bus;

    // Write config register
    uint8_t tx_buf[2] = { REG_CONFIG | 0x80, CONFIG_VAL }; // 0x80 = write bit
    int ret = bus->transmit(bus->bus_handle, tx_buf, 2);
    if (ret != 0) return ret;

    // Verify by reading back config
    uint8_t rx_buf[2] = {0};
    tx_buf[0] = REG_CONFIG & 0x7F; // clear write bit for read
    ret = bus->transmit_receive(bus->bus_handle, tx_buf, rx_buf, 2);
    if (ret != 0 || rx_buf[1] != CONFIG_VAL) return -2;

    return 0;
}

int sensor_read_temperature(float* temp_celsius) {
    if (!bus || !temp_celsius) return -1;

    // Read 2 temperature bytes (MSB first)
    uint8_t tx_buf[2] = { REG_TEMP_MSB & 0x7F, 0x00 };
    uint8_t rx_buf[2] = {0};
    int ret = bus->transmit_receive(bus->bus_handle, tx_buf, rx_buf, 2);
    if (ret != 0) return ret;

    // Convert: 16-bit signed, 0.0625°C per LSB
    int16_t raw = ((int16_t)rx_buf[0] << 8) | rx_buf[1];
    *temp_celsius = raw * 0.0625f;
    return 0;
}
```

```c
// stm32_spi_adapter.c — STM32 HAL adapter
#include "spi_sensor_hal.h"
#include "stm32f4xx_hal.h"

static int stm32_transmit(void* handle, const uint8_t* tx, size_t len) {
    SPI_HandleTypeDef* hspi = (SPI_HandleTypeDef*)handle;
    return (HAL_SPI_Transmit(hspi, (uint8_t*)tx, len, 100) == HAL_OK) ? 0 : -1;
}

static int stm32_transmit_receive(void* handle, const uint8_t* tx,
                                   uint8_t* rx, size_t len) {
    SPI_HandleTypeDef* hspi = (SPI_HandleTypeDef*)handle;
    return (HAL_SPI_TransmitReceive(hspi, (uint8_t*)tx, rx, len, 100) == HAL_OK) ? 0 : -1;
}

const spi_bus_t stm32_spi_bus = {
    .bus_handle = &hspi1,
    .transmit = stm32_transmit,
    .receive = NULL,  // not used; transmit_receive covers it
    .transmit_receive = stm32_transmit_receive,
    .cs_control = NULL // CS handled by HAL in this case
};
```

## Common Pitfalls & Gotchas

1. **Assuming CS is managed by the HAL adapter** — Many SPI peripherals require manual chip select toggling, especially when sharing the bus. If your adapter doesn't expose `cs_control`, you'll corrupt multi-byte transactions. Always verify whether the HAL handles CS automatically or needs explicit control.

2. **Forgetting endianness in multi-byte reads** — Temperature registers are often MSB-first, but some sensors (e.g., TMP117) are LSB-first. The abstraction doesn't fix byte order; you must document and handle it in the sensor driver. I've seen teams waste days debugging temperatures that were byte-swapped.

3. **Error propagation through function pointers** — If the HAL returns error codes that aren't -1/0, your adapter must normalize them. The sensor driver expects a consistent error domain. I use `-1` for generic failure, `-2` for validation errors, and `-3` for timeout. Document this contract.

## Try It Yourself

1. **Port the driver to a new platform** — Take the `spi_sensor_hal.h` and write an adapter for a Raspberry Pi Pico (RP2040) using its PIO-based SPI. The function pointers remain the same; only the implementation changes.

2. **Add a sensor ID validation** — Extend `sensor_init()` to read the device ID register (0x0F) and verify it matches `0xCB` (ADT7310 ID). Return `-4` on mismatch. This catches wiring errors at boot.

3. **Implement a mock bus for unit testing** — Write a `mock_spi_bus.c` that records all transactions to a buffer and returns canned responses. Test that `sensor_read_temperature()` returns 25.0°C when you feed it `0x0190` (25°C in the sensor's format).

## Next Up

Tomorrow is the final review of the entire HAL & Firmware Design Patterns series. I'll compile the top 10 patterns, the most common mistakes I've seen across all 24 days, and a decision tree for choosing the right pattern for your next embedded project.
