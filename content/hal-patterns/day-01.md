---
title: "Day 01: Why Hardware Abstraction Matters: Coupling & Portability"
date: 2026-07-01
tags: ["til", "hal-patterns", "hal", "portability"]
---

## What I Explored Today

Today I dug into the foundational question every firmware engineer eventually faces: why can't we just write to registers directly? After years of patching `#ifdef` blocks and maintaining separate codebases for STM32, NXP, and ESP32 variants, I finally committed to understanding proper Hardware Abstraction Layers (HAL). The core insight is that coupling your application logic to hardware registers creates a brittle system that collapses under the weight of even minor silicon revisions. Today’s deep dive focused on decoupling strategies that actually work in production.

## The Core Concept

Hardware abstraction is not about adding layers for the sake of architecture porn. It’s about defining a contract between your application and the hardware that survives chip shortages, vendor migrations, and errata workarounds. The key metric is **coupling**: how many lines of code must change when you swap a peripheral or a microcontroller.

Consider a simple GPIO toggle. Without abstraction, you write `GPIOA->BSRR = (1 << 5)` directly in your application. That line is coupled to:
- The exact memory address of `GPIOA` (0x40020000 on STM32)
- The bit position of pin 5
- The register layout (BSRR high/low semantics)
- The vendor’s naming convention

When you move to an NXP LPC series, every single one of those assumptions breaks. A proper HAL replaces that with `hal_gpio_write(PORT_A, PIN_5, HIGH)`. The implementation changes per platform, but the interface stays constant. This is the **portability** payoff.

But there’s a deeper point: abstraction also enables testability. You can mock the HAL in a host-based test environment and verify application logic without flashing hardware. Try doing that with register-level code.

## Key Commands / Configuration / Code

Here’s a minimal but production-worthy HAL pattern for GPIO. I’m using C with function pointers for the abstraction layer, which avoids the overhead of virtual tables while keeping the interface clean.

**hal_gpio.h** — The contract (never changes across platforms)
```c
#ifndef HAL_GPIO_H
#define HAL_GPIO_H

#include <stdint.h>
#include <stdbool.h>

typedef enum {
    HAL_GPIO_OK = 0,
    HAL_GPIO_ERR_INVALID_PIN,
    HAL_GPIO_ERR_INVALID_PORT
} hal_gpio_status_t;

typedef enum {
    HAL_GPIO_DIR_INPUT,
    HAL_GPIO_DIR_OUTPUT
} hal_gpio_dir_t;

typedef enum {
    HAL_GPIO_PULL_NONE,
    HAL_GPIO_PULL_UP,
    HAL_GPIO_PULL_DOWN
} hal_gpio_pull_t;

// Opaque handle — implementation hides register details
typedef struct hal_gpio_ctx hal_gpio_ctx_t;

// Pure interface — no hardware dependencies
hal_gpio_status_t hal_gpio_init(hal_gpio_ctx_t *ctx, uint8_t port, uint8_t pin);
hal_gpio_status_t hal_gpio_set_direction(hal_gpio_ctx_t *ctx, hal_gpio_dir_t dir);
hal_gpio_status_t hal_gpio_write(hal_gpio_ctx_t *ctx, bool state);
bool hal_gpio_read(hal_gpio_ctx_t *ctx);
hal_gpio_status_t hal_gpio_set_pull(hal_gpio_ctx_t *ctx, hal_gpio_pull_t pull);

#endif
```

**hal_gpio_stm32.c** — STM32 implementation (one of many)
```c
#include "hal_gpio.h"
#include "stm32f4xx.h"  // Vendor-specific header

struct hal_gpio_ctx {
    GPIO_TypeDef *port;   // e.g., GPIOA, GPIOB
    uint16_t pin;         // e.g., GPIO_PIN_5
};

hal_gpio_status_t hal_gpio_init(hal_gpio_ctx_t *ctx, uint8_t port, uint8_t pin) {
    // Map logical port number to STM32 peripheral base address
    static GPIO_TypeDef *port_map[] = {GPIOA, GPIOB, GPIOC};
    if (port >= 3 || pin > 15) return HAL_GPIO_ERR_INVALID_PORT;

    ctx->port = port_map[port];
    ctx->pin = (1 << pin);

    // Enable clock — platform-specific detail hidden from caller
    RCC->AHB1ENR |= (1 << (port + 0)); // RCC_AHB1ENR_GPIOAEN etc.

    return HAL_GPIO_OK;
}

hal_gpio_status_t hal_gpio_write(hal_gpio_ctx_t *ctx, bool state) {
    if (!ctx->port) return HAL_GPIO_ERR_INVALID_PORT;
    if (state) {
        ctx->port->BSRR = ctx->pin;      // Set bit
    } else {
        ctx->port->BSRR = (ctx->pin << 16); // Reset bit
    }
    return HAL_GPIO_OK;
}
```

**main.c** — Application code (portable across any HAL implementation)
```c
#include "hal_gpio.h"

int main(void) {
    hal_gpio_ctx_t led;
    hal_gpio_init(&led, 0, 5);  // Port 0, pin 5
    hal_gpio_set_direction(&led, HAL_GPIO_DIR_OUTPUT);

    while (1) {
        hal_gpio_write(&led, true);
        delay_ms(500);
        hal_gpio_write(&led, false);
        delay_ms(500);
    }
}
```

The application never touches a register. To port to NXP, you only rewrite `hal_gpio_nxp.c`. Zero changes to `main.c`.

## Common Pitfalls & Gotchas

1. **Leaking hardware assumptions into the interface.** I’ve seen HAL headers that expose `GPIO_TypeDef *` in the struct definition. That instantly couples every user to STM32 register maps. Always use opaque handles (`hal_gpio_ctx_t` is a forward declaration in the header) to enforce encapsulation.

2. **Abstraction that’s too thick.** Some HALs wrap every register access in 5 layers of macros, turning `GPIOA->ODR ^= (1<<5)` into `HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5)`. That’s not abstraction—it’s renaming. Real abstraction changes the *semantics* (e.g., `write` vs `toggle`), not just the syntax. If your HAL doesn’t simplify the mental model, you’re just adding indirection.

3. **Ignoring initialization dependencies.** A common bug: the HAL init function enables a peripheral clock but the application calls it after a delay that relies on that same clock. The HAL must document its ordering constraints. I now add a `hal_init()` call at the very top of `main()` that initializes all platform basics (clock tree, FPU, vector table remap) before any peripheral HAL calls.

## Try It Yourself

1. **Audit your current project.** Find three places where you write to a hardware register directly (e.g., `UART1->DR`, `GPIOA->ODR`). Write a minimal HAL function for each peripheral (e.g., `hal_uart_send_byte`, `hal_gpio_set`). How many lines of application code change? That’s your coupling metric.

2. **Build a mock HAL.** Create a `hal_gpio_mock.c` that stores state in a plain array instead of registers. Write a test that toggles a pin 100 times and verifies the final state. Run it on your host PC (no hardware required). This is the fastest way to validate application logic.

3. **Port a simple blinky.** Take the code above and implement `hal_gpio_nxp.c` for an LPC845 or similar. Compile it with the NXP SDK. If you can run the same `main.c` on both STM32 and NXP without changes, you’ve succeeded. If you had to modify `main.c`, your HAL interface is leaking.

## Next Up

Tomorrow I’ll break down **Layered Firmware Architecture: BSP, HAL, Middleware & App Layers**. We’ll map where each abstraction lives, how they communicate, and why a well-defined BSP is the difference between a 3-month port and a 3-day one.
