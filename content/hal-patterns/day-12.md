---
title: "Day 12: Strategy Pattern: Swappable Communication Backends (SPI/I2C/UART)"
date: 2026-07-12
tags: ["til", "hal-patterns", "strategy-pattern"]
---

## What I Explored Today

Today I tackled a problem that’s been nagging me on a multi-sensor project: how to write a single driver that can talk to the same sensor over SPI, I2C, or UART without duplicating the entire logic. The answer was the Strategy Pattern. I implemented a transport-layer abstraction where the communication backend is a swappable “strategy” object, allowing the sensor driver to remain completely agnostic to the physical bus. This is a game-changer for firmware reuse across hardware revisions.

## The Core Concept

The Strategy Pattern (from GoF) defines a family of algorithms, encapsulates each one, and makes them interchangeable. In embedded systems, this maps perfectly to communication backends. Your sensor driver shouldn’t care if it’s talking to an STM32’s I2C peripheral or a SPI bus — it just needs to send and receive bytes.

Why do this? Because hardware changes. A prototype might use I2C for simplicity, but production switches to SPI for speed. Or you support multiple board revisions. Without the pattern, you end up with `#ifdef` spaghetti or three separate driver files. With the Strategy Pattern, you write one driver that takes a `CommInterface` pointer. The backend (SPI, I2C, UART) is injected at runtime or compile-time via a function table.

The key insight: the driver owns the *what* (protocol logic), and the strategy owns the *how* (bus transactions). This decoupling makes unit testing trivial — you can mock the strategy.

## Key Commands / Configuration / Code

Here’s the C implementation I used today. First, the abstract interface (function pointer struct):

```c
// comm_strategy.h
typedef struct {
    int32_t (*init)(void* handle);
    int32_t (*write)(void* handle, uint8_t* data, uint16_t len);
    int32_t (*read)(void* handle, uint8_t* data, uint16_t len);
    int32_t (*write_read)(void* handle, uint8_t* tx, uint8_t* rx, uint16_t len);
} CommStrategy_t;
```

Now, a concrete SPI strategy. Note the `spi_handle` is a void pointer — the strategy owns its peripheral-specific context:

```c
// spi_strategy.c
#include "comm_strategy.h"
#include "stm32f4xx_hal.h"  // Real HAL includes

static SPI_HandleTypeDef* hspi;

static int32_t spi_write(void* handle, uint8_t* data, uint16_t len) {
    // handle is unused here; we use a static handle for simplicity
    // In production, cast handle to SPI_HandleTypeDef*
    return HAL_SPI_Transmit(hspi, data, len, 100);
}

static int32_t spi_write_read(void* handle, uint8_t* tx, uint8_t* rx, uint16_t len) {
    return HAL_SPI_TransmitReceive(hspi, tx, rx, len, 100);
}

const CommStrategy_t SPI_Strategy = {
    .init = NULL,  // SPI init done externally
    .write = spi_write,
    .read = NULL,  // SPI is full-duplex; use write_read
    .write_read = spi_write_read
};
```

And the I2C strategy (note the different function signatures internally):

```c
// i2c_strategy.c
#include "comm_strategy.h"
#include "stm32f4xx_hal.h"

static I2C_HandleTypeDef* hi2c;
static uint16_t dev_addr = 0x76;  // Example sensor address

static int32_t i2c_write(void* handle, uint8_t* data, uint16_t len) {
    return HAL_I2C_Master_Transmit(hi2c, dev_addr, data, len, 100);
}

static int32_t i2c_read(void* handle, uint8_t* data, uint16_t len) {
    return HAL_I2C_Master_Receive(hi2c, dev_addr, data, len, 100);
}

const CommStrategy_t I2C_Strategy = {
    .init = NULL,
    .write = i2c_write,
    .read = i2c_read,
    .write_read = NULL  // I2C uses separate write/read
};
```

Now the sensor driver — completely backend-agnostic:

```c
// sensor_bme280.c
#include "comm_strategy.h"

typedef struct {
    const CommStrategy_t* comm;
    void* handle;  // Peripheral handle (SPI/I2C/UART)
} BME280_t;

int32_t bme280_read_temp(BME280_t* dev, float* temp) {
    uint8_t reg = 0xFA;  // Temperature MSB register
    uint8_t rx[3] = {0};
    
    // Strategy handles the bus specifics
    if (dev->comm->write_read) {
        // Full-duplex (SPI)
        dev->comm->write_read(dev->handle, &reg, rx, 1);
        dev->comm->write_read(dev->handle, NULL, rx, 3);
    } else {
        // Half-duplex (I2C/UART)
        dev->comm->write(dev->handle, &reg, 1);
        dev->comm->read(dev->handle, rx, 3);
    }
    
    // Convert raw to temperature (unchanged)
    int32_t raw = ((int32_t)rx[0] << 12) | ((int32_t)rx[1] << 4) | (rx[2] >> 4);
    *temp = raw * 0.0025f;
    return 0;
}
```

Usage in `main.c`:

```c
BME280_t sensor;
sensor.comm = &SPI_Strategy;   // or &I2C_Strategy
sensor.handle = &hspi1;        // or &hi2c1

bme280_read_temp(&sensor, &temp);
```

## Common Pitfalls & Gotchas

1. **Ignoring bus-specific timing constraints.** SPI might need CS toggling between transactions; I2C has repeated-start conditions. Your strategy must handle these internally, not leak them to the driver. I wasted an hour debugging an I2C NACK because the strategy didn’t manage the stop condition correctly.

2. **Mixing synchronous vs. asynchronous strategies.** If one backend uses DMA (async) and another uses polling (sync), your driver’s state machine will break. Either force all strategies to be synchronous, or add a completion callback to the interface. I recommend starting synchronous — it’s simpler and sufficient for most sensor reads.

3. **Forgetting that `write_read` isn’t universal.** SPI is inherently full-duplex; I2C is not. Your driver must check which functions are available (as I did above) or provide a default fallback. Never assume all three function pointers are non-NULL.

## Try It Yourself

1. **Add a UART strategy.** Implement a `CommStrategy_t` for a UART-based sensor (e.g., using a simple binary protocol with a start byte and CRC). Ensure the strategy handles framing, not the driver.

2. **Mock the strategy for testing.** Write a `mock_strategy.c` that logs all calls to a buffer. Use it to verify your sensor driver sends the correct register addresses and handles the response bytes.

3. **Refactor an existing driver.** Take a driver you’ve written that hardcodes SPI or I2C. Extract the bus calls into a strategy struct. Verify it still works on hardware, then swap the backend to the other bus and test.

## Next Up

Tomorrow: **Factory Pattern for Peripheral Driver Instantiation**. We’ll build a factory that creates the correct strategy (SPI/I2C/UART) based on a board ID or configuration table — no more manual `if-else` chains at startup.
