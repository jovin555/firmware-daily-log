---
title: "Day 14: Device Driver Model: Init, Configure, Read/Write, Deinit Contracts"
date: 2026-07-14
tags: ["til", "hal-patterns", "driver-model"]
---

## What I Explored Today

Today I formalized the lifecycle contract that every device driver in a production HAL must follow: **Init → Configure → Read/Write → Deinit**. I’ve been guilty of writing drivers that skip configuration steps or leak resources on deinit, so I spent the day studying how RTOS vendors (FreeRTOS+IO), Linux kernel drivers, and bare-metal libraries like STM32 HAL enforce this sequence. The key insight: a driver is not just a set of functions—it’s a state machine with well-defined transitions.

## The Core Concept

The Init/Configure/ReadWrite/Deinit contract exists for one reason: **resource ownership and deterministic behavior**. Without it, you get:

- **Init**: Allocate peripheral clock, GPIO pins, DMA channels, interrupt vectors. If this fails, the driver must not pretend it’s ready.
- **Configure**: Set runtime parameters (baud rate, resolution, filter coefficients). This can be called multiple times after init, but never before.
- **Read/Write**: The actual data transfer. Must check that the driver is in a configured state.
- **Deinit**: Reverse every allocation from init. Disable clock, release pins, free DMA, detach interrupts. Must be idempotent.

Why enforce this? Because embedded systems have limited resources. A driver that doesn’t release a timer on deinit will starve the next driver that needs that timer. A driver that allows `read()` before `init()` will crash on a null pointer. The contract makes the driver’s behavior predictable across all call sites.

## Key Commands / Configuration / Code

Here’s a concrete implementation of a UART driver following the contract. I’m using a hypothetical HAL layer that wraps a UART peripheral on an ARM Cortex-M4.

```c
// driver_uart.h
typedef enum {
    UART_STATE_UNINIT = 0,
    UART_STATE_INIT,
    UART_STATE_CONFIGURED,
    UART_STATE_DEINIT
} uart_state_t;

typedef struct {
    USART_TypeDef *instance;  // e.g., USART1
    uint32_t baudrate;
    uint8_t data_bits;
    uart_state_t state;
    void (*tx_callback)(void);
} uart_handle_t;

// driver_uart.c
#include "driver_uart.h"
#include "hal_rcc.h"
#include "hal_gpio.h"

// Must be called before any other function
hal_status_t uart_init(uart_handle_t *huart) {
    if (huart->state != UART_STATE_UNINIT) {
        return HAL_ERROR;  // Prevent double init
    }
    // Enable peripheral clock (vendor-specific)
    hal_rcc_enable_peripheral(huart->instance);
    // Configure GPIO pins: TX=AF push-pull, RX=AF input
    hal_gpio_config_t gpio_cfg = {
        .mode = GPIO_MODE_AF,
        .pull = GPIO_PULLUP,
        .speed = GPIO_SPEED_HIGH,
        .alternate = GPIO_AF7_USART1
    };
    hal_gpio_init(GPIOA, 9, &gpio_cfg);  // TX
    hal_gpio_init(GPIOA, 10, &gpio_cfg); // RX
    // Allocate interrupt (NVIC)
    NVIC_EnableIRQ(USART1_IRQn);
    huart->state = UART_STATE_INIT;
    return HAL_OK;
}

// Configure runtime parameters (can be called multiple times)
hal_status_t uart_configure(uart_handle_t *huart, uint32_t baudrate, uint8_t data_bits) {
    if (huart->state < UART_STATE_INIT) {
        return HAL_ERROR;  // Not initialized
    }
    // Disable UART before changing config
    huart->instance->CR1 &= ~USART_CR1_UE;
    // Set baudrate (assuming 16 MHz clock)
    huart->instance->BRR = 16000000 / baudrate;
    // Set data bits (8 or 9)
    if (data_bits == 9) {
        huart->instance->CR1 |= USART_CR1_M;
    } else {
        huart->instance->CR1 &= ~USART_CR1_M;
    }
    // Enable UART
    huart->instance->CR1 |= USART_CR1_UE;
    huart->baudrate = baudrate;
    huart->data_bits = data_bits;
    huart->state = UART_STATE_CONFIGURED;
    return HAL_OK;
}

// Blocking write (polling for simplicity)
hal_status_t uart_write(uart_handle_t *huart, const uint8_t *data, uint32_t len) {
    if (huart->state != UART_STATE_CONFIGURED) {
        return HAL_ERROR;
    }
    for (uint32_t i = 0; i < len; i++) {
        // Wait until TX buffer empty
        while (!(huart->instance->SR & USART_SR_TXE));
        huart->instance->DR = data[i];
    }
    return HAL_OK;
}

// Reverse everything from init
hal_status_t uart_deinit(uart_handle_t *huart) {
    if (huart->state == UART_STATE_UNINIT) {
        return HAL_OK;  // Idempotent
    }
    // Disable UART
    huart->instance->CR1 &= ~USART_CR1_UE;
    // Disable interrupt
    NVIC_DisableIRQ(USART1_IRQn);
    // Deinit GPIO (set to analog mode for low power)
    hal_gpio_deinit(GPIOA, 9);
    hal_gpio_deinit(GPIOA, 10);
    // Disable peripheral clock
    hal_rcc_disable_peripheral(huart->instance);
    // Clear handle
    memset(huart, 0, sizeof(uart_handle_t));
    huart->state = UART_STATE_DEINIT;
    return HAL_OK;
}
```

**Usage pattern**:
```c
uart_handle_t uart1 = {.instance = USART1};
uart_init(&uart1);
uart_configure(&uart1, 115200, 8);
uart_write(&uart1, (uint8_t*)"Hello", 5);
uart_deinit(&uart1);
```

## Common Pitfalls & Gotchas

1. **Skipping state checks in ISRs**: I’ve seen drivers where the interrupt handler calls `uart_read()` without checking `state == CONFIGURED`. If a spurious interrupt fires during deinit, you’ll write to freed memory. Always guard ISR code with a state check.

2. **Deinit not being idempotent**: If `uart_deinit()` is called twice, the second call should not crash. I’ve debugged systems where a driver’s deinit disables a clock that another peripheral shares, then the second deinit tries to disable it again—result: hard fault. Use the state machine to skip if already deinitialized.

3. **Forgetting to disable the peripheral before reconfiguration**: Changing baud rate or data bits while the UART is transmitting causes undefined behavior. Always disable the peripheral (`UE=0`), change config, then re-enable. This is documented in every reference manual but often missed.

## Try It Yourself

1. **Extend the driver**: Add a `uart_read()` function that uses the RXNE flag. Ensure it returns `HAL_ERROR` if the driver is not in `UART_STATE_CONFIGURED`. Test with a loopback.

2. **Add a timeout**: Modify `uart_write()` to include a timeout counter. If the TX buffer doesn’t empty within 100ms, return `HAL_TIMEOUT` and leave the driver in a recoverable state.

3. **Write a deinit test**: Create a test harness that calls `uart_init()`, `uart_configure()`, `uart_deinit()`, then `uart_deinit()` again. Verify the second call returns `HAL_OK` and doesn’t fault.

## Next Up

Tomorrow: **Porting a HAL Across Vendors: STM32 HAL vs MCUXpresso vs nRFx** — I’ll compare how three major vendors implement the same contract (init/configure/read/deinit) for a UART, and show a portable abstraction layer that hides the differences. Spoiler: the state machine pattern is the key to vendor-agnostic drivers.
