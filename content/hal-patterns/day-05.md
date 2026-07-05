---
title: "Day 05: The vtable Pattern in C: Simulating Polymorphism for Drivers"
date: 2026-07-05
tags: ["til", "hal-patterns", "vtable", "polymorphism"]
---

## What I Explored Today

Today I dug into the vtable (virtual table) pattern in C—a technique that brings object-oriented polymorphism to plain C firmware. While C++ gives us `virtual` keywords and inheritance for free, embedded C often demands the same flexibility without the C++ runtime overhead. The vtable pattern lets us define driver interfaces that multiple hardware implementations can satisfy, enabling clean HAL layers that swap out cleanly when the silicon changes.

## The Core Concept

The fundamental problem: you have two I2C peripherals from different vendors, or you're writing a driver that must work on both STM32 and NXP silicon. You want to call `i2c_write(handle, data, len)` regardless of which chip is underneath. A switch-case on a hardware ID works for two targets, but it's a maintenance nightmare at ten.

The vtable pattern solves this by storing function pointers in a struct—the vtable—and having each driver instance carry a pointer to its vtable. When you call a method, you go through the vtable indirection. This is exactly what C++ does under the hood, but we do it explicitly, with full control over memory layout and allocation.

For HAL drivers, this means:
- The interface contract lives in a header as a struct of function pointers.
- Each hardware backend fills in that struct with its own implementations.
- Application code never needs to know which backend is active.

The cost is one extra pointer dereference per call and a few bytes of ROM per vtable instance. On modern MCUs with flash to spare, this is almost always acceptable.

## Key Commands / Configuration / Code

Let's build a minimal SPI driver interface using the vtable pattern.

First, the interface definition in `spi_hal.h`:

```c
// spi_hal.h
#ifndef SPI_HAL_H
#define SPI_HAL_H

#include <stdint.h>
#include <stddef.h>

// Forward declaration: the driver instance is opaque to users
struct spi_device;

// The vtable struct: each entry is a function pointer
struct spi_vtable {
    int32_t (*transmit)(struct spi_device *self, const uint8_t *data, size_t len);
    int32_t (*receive)(struct spi_device *self, uint8_t *data, size_t len);
    int32_t (*exchange)(struct spi_device *self, const uint8_t *tx, uint8_t *rx, size_t len);
    void    (*set_mode)(struct spi_device *self, uint8_t mode);
};

// The device struct: carries vtable pointer + per-instance state
struct spi_device {
    const struct spi_vtable *vtable;  // must be first field for casting tricks
    void *hw_context;                 // opaque pointer to hardware registers
    uint32_t baudrate;
};

// Inline helper functions for ergonomic calls
static inline int32_t spi_transmit(struct spi_device *dev, const uint8_t *data, size_t len) {
    return dev->vtable->transmit(dev, data, len);
}

static inline int32_t spi_receive(struct spi_device *dev, uint8_t *data, size_t len) {
    return dev->vtable->receive(dev, data, len);
}

static inline int32_t spi_exchange(struct spi_device *dev, const uint8_t *tx, uint8_t *rx, size_t len) {
    return dev->vtable->exchange(dev, tx, rx, len);
}

#endif
```

Now, a concrete implementation for an STM32 SPI peripheral in `spi_stm32.c`:

```c
// spi_stm32.c
#include "spi_hal.h"
#include "stm32f4xx_hal.h"  // vendor HAL

// Per-instance data, stored in the hw_context
struct stm32_spi_context {
    SPI_HandleTypeDef hspi;
    GPIO_TypeDef *cs_port;
    uint16_t cs_pin;
};

// Implementation of transmit for STM32
static int32_t stm32_spi_transmit(struct spi_device *dev, const uint8_t *data, size_t len) {
    struct stm32_spi_context *ctx = (struct stm32_spi_context *)dev->hw_context;
    HAL_GPIO_WritePin(ctx->cs_port, ctx->cs_pin, GPIO_PIN_RESET);
    HAL_StatusTypeDef status = HAL_SPI_Transmit(&ctx->hspi, (uint8_t *)data, len, HAL_MAX_DELAY);
    HAL_GPIO_WritePin(ctx->cs_port, ctx->cs_pin, GPIO_PIN_SET);
    return (status == HAL_OK) ? 0 : -1;
}

// ... similar implementations for receive, exchange, set_mode ...

// The vtable instance for STM32 backend — const so it lives in flash
static const struct spi_vtable stm32_spi_vtable = {
    .transmit = stm32_spi_transmit,
    .receive  = stm32_spi_receive,
    .exchange = stm32_spi_exchange,
    .set_mode = stm32_spi_set_mode,
};

// Initialization function: populates the generic spi_device
int32_t spi_stm32_init(struct spi_device *dev, SPI_TypeDef *instance, GPIO_TypeDef *cs_port, uint16_t cs_pin) {
    // Allocate context from a pool or static memory
    static struct stm32_spi_context ctx;
    ctx.cs_port = cs_port;
    ctx.cs_pin  = cs_pin;

    // Initialize vendor HAL handle
    ctx.hspi.Instance = instance;
    // ... configure SPI parameters ...

    dev->vtable     = &stm32_spi_vtable;
    dev->hw_context = &ctx;
    dev->baudrate   = 1000000;  // 1 MHz default
    return 0;
}
```

Application code then uses the generic interface:

```c
// main.c
#include "spi_hal.h"

struct spi_device spi1;  // generic device handle

void app_init(void) {
    spi_stm32_init(&spi1, SPI1, GPIOB, GPIO_PIN_6);
}

void app_loop(void) {
    uint8_t tx_data[] = {0xAA, 0xBB};
    uint8_t rx_data[2];
    spi_exchange(&spi1, tx_data, rx_data, 2);
}
```

To add a second backend (e.g., bit-banged SPI on a different MCU), you write another `spi_bitbang.c` with its own vtable and init function. The application code never changes.

## Common Pitfalls & Gotchas

**1. Vtable must be const and in flash.** If you forget `const`, the vtable ends up in RAM. On memory-constrained MCUs, this wastes precious SRAM and can cause hard faults if the linker places it in a read-only region. Always declare vtables as `static const`.

**2. The `self` pointer must be the first field.** Many patterns rely on casting the device struct to access the vtable. If `vtable` isn't the first member, pointer casts between base and derived types break silently. Some compilers will let you get away with it until you change optimization flags.

**3. Function pointer signatures must match exactly.** A mismatch in calling convention (e.g., `__attribute__((fastcall))` on one function but not the vtable declaration) will corrupt the stack. Use typedefs for the function pointer types to ensure consistency across backends.

**4. Beware of initialization order.** If your vtable pointers are filled during init functions that run from `.init_array` (constructor-style), the order relative to other hardware init is undefined. Explicitly call init functions in `main()` to maintain control.

## Try It Yourself

1. **Extend the SPI interface** with an `abort()` method. Add it to the vtable struct, implement it for the STM32 backend (calling `HAL_SPI_Abort`), and verify the inline helper compiles and works.

2. **Write a second backend** for a bit-banged SPI using GPIO toggling. Implement all four vtable methods, create a `spi_bitbang_init()` function, and swap the device handle in `app_init()` without changing any application logic.

3. **Measure the overhead.** On your target MCU, write a benchmark that calls `spi_transmit()` 1000 times through the vtable, then directly. Compare cycle counts. Is the indirection acceptable for your throughput requirements?

## Next Up

Tomorrow, we'll explore **Opaque Handles & Pimpl-Style Encapsulation in C**—how to hide implementation details from users while maintaining type safety, and why this pattern is essential for library distribution and ABI stability in firmware.
