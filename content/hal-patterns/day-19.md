---
title: "Day 19: Error Handling Patterns Across HAL Layers: Codes vs Exceptions"
date: 2026-07-19
tags: ["til", "hal-patterns", "error-handling"]
---

## What I Explored Today

Today I dug into the perennial debate in embedded HAL design: how to propagate errors across abstraction layers without leaking implementation details or creating fragile code. I compared three dominant patterns—error codes, exceptions (C++/Rust), and out-of-band error signaling—and evaluated where each belongs in a layered HAL architecture. The key insight: mixing patterns across layers is not only acceptable but often necessary, provided you define clear boundaries and translation rules.

## The Core Concept

A HAL exists to decouple application logic from hardware specifics. Error handling is the most common place this decoupling breaks. If your SPI driver returns `-5` for a NACK and your I2C driver returns `0xFE` for arbitration loss, the upper layers must know both sets of semantics. That’s a leaky abstraction.

The fundamental trade-off is between **determinism** (error codes) and **expressiveness** (exceptions). In bare-metal or RTOS contexts, error codes dominate because they have zero runtime overhead, no stack unwinding, and work in ISRs. Exceptions (C++ `throw`, Rust `panic`/`Result`) offer richer context but introduce latency variance and memory overhead for unwind tables.

The winning pattern I’ve seen in production: **use error codes at the lowest HAL layer (register access), translate to domain-specific codes at the mid-layer (bus abstraction), and optionally convert to exceptions only at the application boundary.** This keeps the hot path deterministic while giving application code clean error handling.

## Key Commands / Configuration / Code

### Pattern 1: Layered Error Codes (C, bare-metal)

```c
// hal_spi.h — Low-level driver returns raw status
typedef enum {
    HAL_SPI_OK       = 0,
    HAL_SPI_BUSY     = -1,
    HAL_SPI_TIMEOUT  = -2,
    HAL_SPI_NACK     = -3,
    HAL_SPI_CRC_ERR  = -4
} hal_spi_status_t;

hal_spi_status_t hal_spi_transfer(SPI_TypeDef *spi, uint8_t *tx, uint8_t *rx, uint32_t len);

// bus_abstraction.c — Mid-layer translates to generic bus errors
typedef enum {
    BUS_OK       = 0,
    BUS_COMM_ERR = -10,
    BUS_TIMEOUT  = -11,
    BUS_PROTOCOL = -12
} bus_status_t;

bus_status_t bus_write_register(uint8_t dev_addr, uint8_t reg, uint8_t val) {
    hal_spi_status_t st = hal_spi_transfer(SPI1, &txbuf, NULL, 2);
    switch (st) {
        case HAL_SPI_OK:      return BUS_OK;
        case HAL_SPI_TIMEOUT: return BUS_TIMEOUT;
        case HAL_SPI_NACK:
        case HAL_SPI_CRC_ERR: return BUS_COMM_ERR;
        default:              return BUS_PROTOCOL;
    }
}
```

### Pattern 2: Error Code + Out-of-Band (callback for async)

```c
// hal_uart.h — Asynchronous driver with error callback
typedef void (*hal_uart_error_cb_t)(hal_uart_t *huart, uint32_t error_flags);

typedef struct {
    UART_TypeDef        *instance;
    uint8_t             *rx_buf;
    uint32_t            rx_len;
    volatile uint32_t   error_flags;  // Set in ISR, cleared by user
    hal_uart_error_cb_t on_error;
} hal_uart_t;

// User sets callback during init
hal_uart_status_t hal_uart_receive_it(hal_uart_t *huart, uint8_t *buf, uint32_t len);

// In ISR:
void UART_IRQHandler(void) {
    if (LL_USART_IsActiveFlag_PE(USART1)) {
        huart1.error_flags |= HAL_UART_ERROR_PARITY;
        if (huart1.on_error) huart1.on_error(&huart1, HAL_UART_ERROR_PARITY);
    }
}
```

### Pattern 3: Exceptions at Application Boundary (C++)

```cpp
// app_sensor.cpp — Application layer wraps bus calls with exceptions
#include <stdexcept>

class SensorDriver {
public:
    float read_temperature() {
        bus_status_t st = bus_write_register(addr, REG_CMD, 0x01);
        if (st != BUS_OK) {
            throw std::runtime_error("Sensor comm failed: " + std::to_string(st));
        }
        // ... read data ...
    }
};

// main.cpp — Catch at task level
void sensor_task(void*) {
    SensorDriver sensor;
    while (1) {
        try {
            float temp = sensor.read_temperature();
            process_temp(temp);
        } catch (const std::exception& e) {
            log_error("Sensor error: %s", e.what());
            recover_sensor();
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
```

## Common Pitfalls & Gotchas

1. **Mixing error code domains without translation** — Returning `HAL_SPI_NACK` directly from a `bus_read()` function forces callers to include SPI headers. Always translate at layer boundaries. I’ve seen codebases where a single `-3` meant three different things depending on which header you included.

2. **Exceptions in ISRs or time-critical paths** — In C++, throwing from an ISR is undefined behavior on most platforms (no exception handler installed). Even in Rust, `panic!` in an ISR typically triggers a hard fault. Reserve exceptions for task-level code where you can afford the stack unwind.

3. **Ignoring the error return on HAL init** — Many HALs return a status from `HAL_Init()` or `HAL_xxx_Init()`. Engineers often cast the return to `void` during prototyping. This hides failures like clock configuration errors that will manifest as mysterious hangs later. Always check init returns, even in prototype code.

## Try It Yourself

1. **Refactor a flat driver** — Take a driver that returns raw hardware status codes (e.g., STM32 HAL’s `HAL_StatusTypeDef`) and wrap it in a mid-layer that returns only three generic errors: `OK`, `BUSY`, `FAIL`. Verify the translation covers all possible return values.

2. **Add an error callback to an existing driver** — Pick a UART or SPI driver you’ve written. Add a user-registerable error callback that fires on framing errors, overrun, or NACK. Ensure the callback is called from the ISR context (keep it minimal—just set a flag).

3. **Compare code size** — Implement the same error handling logic twice: once with error codes and once with C++ exceptions. Compile for your target with `-Os` and compare the `.text` section size. Note the difference in stack usage (use `-fstack-usage` in GCC).

## Next Up

Tomorrow: **Testing HALs: Mocking Hardware with Fakes & Hardware-in-the-Loop** — I’ll walk through building a mock SPI peripheral in software, using it to unit-test your driver without touching real hardware, then validating with HIL on an oscilloscope.
