---
title: "Day 22: Migrating a Product Line to a New MCU: A HAL Case Study"
date: 2026-07-22
tags: ["til", "hal-patterns", "migration", "case-study"]
---

## What I Explored Today

Today I walked through a real migration of a three-product line from an STM32F4 series to an STM32G4 series MCU. The goal was not just a port, but a clean separation of hardware-dependent code from business logic using a HAL abstraction layer. The project involved 47 source files, 6 peripheral drivers, and a custom RTOS tick implementation. The migration took 3 engineers 4 weeks, but the HAL design we used cut that estimate by 40% compared to a direct register-level rewrite.

## The Core Concept

The fundamental insight is that **a HAL is not a driver, it's a contract**. When migrating MCU families, the temptation is to write new drivers for every peripheral. Instead, you define a set of abstract interfaces that capture *what* the hardware does, not *how*. The HAL sits between your application code and the silicon, providing:

- **Functional equivalence**: The same logical operation (e.g., `hal_spi_transfer(buffer, len)`) works across MCUs.
- **Performance isolation**: Timing-critical paths are documented and tested, not hidden.
- **Configuration decoupling**: Pin muxing, clock trees, and DMA channels are handled in board-specific files, not scattered through application code.

For our migration, we defined a `hal_t` struct containing function pointers for each peripheral category. The application code calls through these pointers, never directly touching registers. The linker then resolves the correct implementation based on the target MCU.

## Key Commands / Configuration / Code

Here's the core abstraction we used. Note the use of weak symbols and linker groups to allow board-specific overrides.

```c
// hal_interface.h — the contract
#ifndef HAL_INTERFACE_H
#define HAL_INTERFACE_H

#include <stdint.h>
#include <stddef.h>

typedef struct {
    void (*init)(void);
    int  (*read)(uint8_t *buf, size_t len);
    int  (*write)(uint8_t *buf, size_t len);
    void (*set_baud)(uint32_t baud);
} hal_uart_t;

typedef struct {
    void (*init)(void);
    int  (*transfer)(uint8_t *tx, uint8_t *rx, size_t len);
    void (*cs_assert)(void);
    void (*cs_deassert)(void);
} hal_spi_t;

// Global HAL instance — weak default
extern hal_uart_t hal_uart0 __attribute__((weak));
extern hal_spi_t  hal_spi0  __attribute__((weak));

#endif
```

```c
// hal_stm32g4_uart.c — G4 implementation
#include "hal_interface.h"
#include "stm32g4xx_hal.h"

static UART_HandleTypeDef huart1;

static void uart_init(void) {
    huart1.Instance = USART1;
    huart1.Init.BaudRate = 115200;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    HAL_UART_Init(&huart1);
}

static int uart_read(uint8_t *buf, size_t len) {
    return HAL_UART_Receive(&huart1, buf, len, HAL_MAX_DELAY);
}

static int uart_write(uint8_t *buf, size_t len) {
    return HAL_UART_Transmit(&huart1, buf, len, HAL_MAX_DELAY);
}

static void uart_set_baud(uint32_t baud) {
    huart1.Init.BaudRate = baud;
    HAL_UART_Init(&huart1);
}

// Instantiate the weak symbol
hal_uart_t hal_uart0 = {
    .init = uart_init,
    .read = uart_read,
    .write = uart_write,
    .set_baud = uart_set_baud
};
```

```c
// main.c — application code, MCU-agnostic
#include "hal_interface.h"

void process_sensor_data(void) {
    uint8_t cmd[] = {0xAA, 0x01, 0x00};
    uint8_t resp[8];

    // No MCU-specific calls here
    hal_spi0.cs_assert();
    hal_spi0.transfer(cmd, resp, 3);
    hal_spi0.cs_deassert();

    // Log via UART
    hal_uart0.write(resp, 8);
}
```

The linker command to ensure weak symbols are resolved correctly:

```makefile
# Linker flags for weak symbol resolution
LDFLAGS += -Wl,--whole-archive -lhal_stm32g4 -Wl,--no-whole-archive
```

## Common Pitfalls & Gotchas

1. **Weak symbol ordering**: If you have multiple implementations (e.g., `hal_stm32f4_uart.o` and `hal_stm32g4_uart.o`), the linker picks the first strong symbol. We use `--whole-archive` to force the correct library to be searched first. Without this, you might silently link the wrong driver.

2. **Clock tree assumptions**: The STM32F4 uses a different PLL configuration than the G4. Our `hal_uart_init()` assumed a 16 MHz HSI, but the G4 board used 8 MHz HSE. This caused UART baud rate errors that only appeared at 921600 baud. Always add a `hal_clock_get_hclk()` helper to your HAL interface.

3. **DMA channel mapping**: The F4 has DMA1 with 8 streams; the G4 has DMA1 with 7 channels and a different request mapping. We abstracted DMA as a separate HAL module with channel allocation functions, not raw register writes. The migration caught three DMA channel conflicts that were invisible in the original code.

## Try It Yourself

1. **Extract the HAL interface from an existing project**: Pick a product with at least two UART peripherals. Create a `hal_uart_t` struct and refactor one UART driver to use it. Verify the application code compiles without any `USART1` or `USART2` references.

2. **Write a test harness for your HAL**: Create a mock `hal_uart_t` that echoes data to a ring buffer. Write a unit test that sends a command and checks the response. This catches HAL contract violations before hardware is available.

3. **Port a single peripheral between MCU families**: Take your `hal_spi_t` implementation from an STM32F4 to an STM32G4. Use the same `hal_interface.h` header. Time how long it takes to get the first byte through — if it's more than 2 hours, your abstraction is too leaky.

## Next Up

Tomorrow we'll look at **Anti-Patterns: God Objects, Leaky Abstractions & Over-Engineering** — the mistakes that turn a clean HAL into a maintenance nightmare. We'll dissect a real-world "HAL" that was really just a register dump wrapped in a struct, and show how to refactor it without breaking existing firmware.
