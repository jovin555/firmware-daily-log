---
title: "Day 18: Peripheral Drivers as Reusable Components: Versioning & APIs"
date: 2026-07-18
tags: ["til", "hal-patterns", "reusability", "api-versioning"]
---

## What I Explored Today

Today I dug into the practical mechanics of making peripheral drivers truly reusable across projects—specifically how to version them and design stable APIs that don't break when the underlying hardware changes. After refactoring a UART driver for the third time this year, I realized that without explicit versioning and API contracts, "reusable" just means "copy-paste with a different filename." I explored semantic versioning for firmware libraries, API surface design patterns, and how to decouple driver internals from the interface exposed to application code.

## The Core Concept

Most embedded engineers write drivers that are tightly coupled to a specific MCU, a specific board revision, and a specific application. The moment you try to reuse that driver, you hit a wall: the register map changed, the pin assignment is different, or the application needs a different initialization sequence.

The solution is to treat your driver as a **versioned component** with a **stable API contract**. The API is the promise—it defines how application code talks to the driver. The version tells you what changed when that promise breaks. This is standard practice in desktop and web development, but in embedded, we often skip it because "it's just a microcontroller."

The payoff is real: when you upgrade to a new MCU family, you only rewrite the HAL layer beneath the API. The application code stays untouched. When you fix a bug in the I2C driver, the version bump tells every project using it whether they can safely drop in the new binary.

## Key Commands / Configuration / Code

### 1. Semantic Versioning for Driver Headers

Embed the version directly in the driver's public header. Use macros so the preprocessor can enforce compatibility.

```c
// uart_driver.h — Public API header
#ifndef UART_DRIVER_H
#define UART_DRIVER_H

#include <stdint.h>
#include <stddef.h>

// Semantic version: MAJOR.MINOR.PATCH
#define UART_DRIVER_VERSION_MAJOR 2
#define UART_DRIVER_VERSION_MINOR 1
#define UART_DRIVER_VERSION_PATCH 0

// Compile-time check: application must declare its required version
#ifndef UART_DRIVER_REQUIRED_MAJOR
#error "UART_DRIVER_REQUIRED_MAJOR must be defined before including this header"
#endif

#if UART_DRIVER_REQUIRED_MAJOR != UART_DRIVER_VERSION_MAJOR
#error "UART driver major version mismatch. Required: " 
       #UART_DRIVER_REQUIRED_MAJOR ", Found: " #UART_DRIVER_VERSION_MAJOR
#endif

// Public API — stable across MINOR and PATCH bumps
typedef struct {
    uint32_t baud_rate;
    uint8_t  data_bits;    // 5, 6, 7, 8
    uint8_t  stop_bits;    // 1 or 2
    uint8_t  parity;       // 0=none, 1=odd, 2=even
} uart_config_t;

// Returns actual baud rate set (may differ from requested)
uint32_t uart_init(uart_config_t *config);

// Blocking send — returns number of bytes sent
size_t uart_send(const uint8_t *data, size_t len);

// Non-blocking receive — returns bytes received, 0 if none
size_t uart_receive(uint8_t *buffer, size_t max_len);

#endif // UART_DRIVER_H
```

### 2. Version Query at Runtime

Sometimes you need to check version at runtime (e.g., for diagnostics or OTA updates).

```c
// uart_driver.c
#include "uart_driver.h"

typedef struct {
    uint8_t major;
    uint8_t minor;
    uint8_t patch;
} driver_version_t;

static const driver_version_t kVersion = {
    .major = UART_DRIVER_VERSION_MAJOR,
    .minor = UART_DRIVER_VERSION_MINOR,
    .patch = UART_DRIVER_VERSION_PATCH
};

// Public function to query version at runtime
void uart_get_version(uint8_t *major, uint8_t *minor, uint8_t *patch) {
    *major = kVersion.major;
    *minor = kVersion.minor;
    *patch = kVersion.patch;
}
```

### 3. API Contract via Opaque Handles

Hide the driver's internal state behind an opaque handle. This prevents application code from touching registers directly.

```c
// uart_driver.h — continued
// Opaque handle — application never sees the struct
typedef struct uart_device uart_device_t;

// Factory function: creates and initializes a UART device
uart_device_t* uart_create(uart_config_t *config);

// All operations take the handle
void uart_send_async(uart_device_t *dev, const uint8_t *data, size_t len);
uint32_t uart_get_status(uart_device_t *dev);
```

```c
// uart_driver.c — internal implementation
struct uart_device {
    UART_TypeDef *regs;          // Hardware register base
    uint32_t      clock_hz;      // Peripheral clock for baud calculation
    uint8_t       tx_pin;
    uint8_t       rx_pin;
    uint8_t       initialized;
};

uart_device_t* uart_create(uart_config_t *config) {
    // Allocate from a static pool (no malloc in embedded)
    static uart_device_t pool[UART_MAX_DEVICES];
    static uint8_t next = 0;
    if (next >= UART_MAX_DEVICES) return NULL;
    
    uart_device_t *dev = &pool[next++];
    // ... configure registers based on config ...
    dev->initialized = 1;
    return dev;
}
```

## Common Pitfalls & Gotchas

**1. Breaking the API with "Minor" Changes**
Adding a new parameter to `uart_init()` is a MAJOR change, not a minor one. Every caller must update their code. Instead, add a new function (e.g., `uart_init_ex()`) and deprecate the old one. Patch the old function to call the new one internally.

**2. Forgetting the Compile-Time Check**
Without `#error` guards, a project might silently link against the wrong driver version. I've seen a UART driver v1.2.0 get replaced with v2.0.0, and the application compiled fine because the function signatures were identical—but the register layout changed. The result: silent data corruption. Always enforce major version at compile time.

**3. Exposing Hardware Details in the API**
If your `uart_config_t` includes fields like `USART_CR1_UE` or `GPIO_AF7`, you've failed. Application code should never see register bit definitions. Abstract everything: baud rate as a number, parity as an enum, pins as logical port numbers (0, 1, 2) mapped internally to hardware.

## Try It Yourself

1. **Add versioning to an existing driver**: Pick a driver you've written (SPI, I2C, GPIO). Add `VERSION_MAJOR`, `VERSION_MINOR`, `VERSION_PATCH` macros to its header. Add a compile-time check that requires the application to define the required major version before including the header.

2. **Refactor a register-exposing API**: Find a driver where the config struct contains hardware register values (e.g., `SPI_CR1_SPE`). Replace them with logical enums (e.g., `spi_mode_t { SPI_MODE_0, SPI_MODE_1 }`). Update the internal implementation to map enums to registers.

3. **Implement an opaque handle**: Take a driver that uses global state (e.g., `static` variables for TX/RX buffers). Refactor it to use an opaque `struct` handle returned by a `_create()` function. Move all global state into the struct.

## Next Up

Tomorrow: **Error Handling Patterns Across HAL Layers: Codes vs Exceptions** — when to return error codes, when to assert, and how to propagate errors from register-level failures up to application callbacks without bloating your code.
