---
title: "Day 02: Layered Firmware Architecture: BSP, HAL, Middleware & App Layers"
date: 2026-07-02
tags: ["til", "hal-patterns", "layered-architecture"]
---

## What I Explored Today

Today I mapped out the canonical layered firmware architecture that separates a microcontroller project into four distinct tiers: Board Support Package (BSP), Hardware Abstraction Layer (HAL), Middleware, and Application. I’ve seen too many projects where GPIO toggles and TCP/IP stack calls live in the same file, creating a dependency nightmare. This layering isn’t just about neat folders—it’s about portability, testability, and keeping your sanity when the hardware changes mid-project.

## The Core Concept

Layered architecture enforces a strict dependency rule: **each layer can only call into the layer directly below it**. The Application layer talks to Middleware, Middleware talks to HAL, HAL talks to BSP, and BSP talks to the hardware registers. No skipping layers. No Application code poking a UART data register directly.

Why does this matter? Three concrete reasons:

1. **Hardware swap without rewrite**: If you change MCU vendors, you only rewrite the BSP and maybe part of the HAL. Your application code stays untouched.
2. **Testability**: You can stub the HAL layer in a unit test environment and run your application logic on a host PC.
3. **Reusability**: A well-written HAL for I²C can be reused across projects, even if the BSP changes from STM32 to NXP.

The layers, from bottom to top:

- **BSP**: Board-specific pin mappings, clock tree configuration, and peripheral initialization sequences. Knows the exact PCB layout.
- **HAL**: Peripheral driver API (e.g., `hal_i2c_write()`, `hal_gpio_set()`). Hides register details but exposes functional interfaces.
- **Middleware**: Protocol stacks (TCP/IP, USB, FATFS), RTOS wrappers, or crypto libraries. Depends on HAL, not on hardware.
- **Application**: Business logic, state machines, user workflows. Should never include a `#include <stm32f4xx.h>`.

## Key Commands / Configuration / Code

Let’s build a minimal example for an STM32L4 project. We’ll implement a BSP that sets up a UART pin, a HAL that provides a `send_string()` function, and an Application that uses it.

**bsp_uart.h** — Board-specific pin mapping
```c
#ifndef BSP_UART_H
#define BSP_UART_H

#include "stm32l4xx.h"  // MCU-specific header, only in BSP

// Board: custom PCB rev 2.1
// UART2: TX=PA2, RX=PA3, AF7
#define BSP_UART_TX_PORT GPIOA
#define BSP_UART_TX_PIN  GPIO_PIN_2
#define BSP_UART_RX_PORT GPIOA
#define BSP_UART_RX_PIN  GPIO_PIN_3
#define BSP_UART_AF      GPIO_AF7_USART2
#define BSP_UART_INST    USART2

void bsp_uart_init(void);  // Sets up clocks, GPIO, and USART2

#endif
```

**bsp_uart.c** — Implementation with register-level access
```c
#include "bsp_uart.h"

void bsp_uart_init(void) {
    // Enable clocks for GPIOA and USART2
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN;
    RCC->APB1ENR1 |= RCC_APB1ENR1_USART2EN;

    // Configure PA2, PA3 as alternate function
    GPIOA->MODER &= ~(GPIO_MODER_MODE2 | GPIO_MODER_MODE3);
    GPIOA->MODER |= (GPIO_ALTERNATE << GPIO_MODER_MODE2_Pos) |
                    (GPIO_ALTERNATE << GPIO_MODER_MODE3_Pos);
    GPIOA->AFR[0] |= (BSP_UART_AF << GPIO_AFRL_AFSEL2_Pos) |
                     (BSP_UART_AF << GPIO_AFRL_AFSEL3_Pos);

    // USART2: 115200 baud, 8N1, enable TX/RX
    USART2->BRR = 8000000 / 115200;  // Assuming 8 MHz clock
    USART2->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}
```

**hal_uart.h** — Hardware abstraction layer
```c
#ifndef HAL_UART_H
#define HAL_UART_H

#include <stdint.h>

// Pure functional API — no register names, no MCU headers
void hal_uart_init(void);
void hal_uart_send_string(const char *str);

#endif
```

**hal_uart.c** — Delegates to BSP
```c
#include "hal_uart.h"
#include "bsp_uart.h"

void hal_uart_init(void) {
    bsp_uart_init();  // Only BSP knows the hardware details
}

void hal_uart_send_string(const char *str) {
    while (*str) {
        // Wait until TX buffer empty
        while (!(BSP_UART_INST->ISR & USART_ISR_TXE));
        BSP_UART_INST->TDR = *str++;
    }
}
```

**app_main.c** — Application layer
```c
#include "hal_uart.h"

void app_main(void) {
    hal_uart_init();
    hal_uart_send_string("Hello from Application layer!\r\n");
    // No register access, no MCU includes — pure logic
}
```

Notice: `app_main.c` never includes `stm32l4xx.h`. If we move to an NXP LPC55xx, we rewrite `bsp_uart.c` and `bsp_uart.h`, update `hal_uart.c` if the status register bit changes, but `app_main.c` stays identical.

## Common Pitfalls & Gotchas

1. **Leaky abstractions in the HAL**: I’ve seen HAL functions that return raw register values (e.g., `uint32_t hal_spi_get_status()` that returns `SPI_SR`). This forces the Application to know register bit positions. Fix: return an enum or a bool. The HAL should abstract, not just rename.

2. **BSP includes in Middleware**: Someone includes `stm32f4xx_hal.h` in a TCP/IP stack port file because they need `HAL_GetTick()`. Now that middleware is tied to STM32. Instead, pass a function pointer or use a weak symbol for the time source.

3. **Circular dependencies between layers**: If your Application calls a Middleware function that calls back into Application code, you’ve created a cycle. Use callback registration or event queues to break the loop. The dependency graph must be a directed acyclic graph (DAG).

## Try It Yourself

1. **Audit your current project**: Find one file that includes both an MCU header (like `stm32f4xx.h`) and application logic. Refactor it into three files: `bsp_xxx.c`, `hal_xxx.c`, and move the logic to `app_xxx.c`. Verify the app file compiles without the MCU header.

2. **Write a HAL stub for testing**: Create a `hal_uart_stub.c` that logs sent strings to a buffer instead of hardware. Link it in a test build and write a simple test that checks `hal_uart_send_string("test")` populates the buffer correctly.

3. **Add a Middleware layer**: Implement a simple command-line parser (Middleware) that calls `hal_uart_send_string()` for output. Your Application should only call `middleware_cli_process(char c)`. No direct HAL calls from app code.

## Next Up

Tomorrow: **Register Abstraction: Memory-Mapped I/O & volatile Correctness**. We’ll dissect why `*(volatile uint32_t*)0x40020000 = 0x1;` is both powerful and dangerous, and how to wrap it safely.
