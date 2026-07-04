---
title: "Day 04: Designing a Clean HAL API: Function Pointers vs Structs"
date: 2026-07-04
tags: ["til", "hal-patterns", "hal-api", "function-pointers"]
---

## What I Explored Today

Today I dug into the two dominant approaches for structuring Hardware Abstraction Layer (HAL) APIs in C: raw function pointers and structs of function pointers. I’ve seen both in production code—from tiny bootloaders to full RTOS drivers—and the choice has real consequences for testability, maintainability, and code size. I wanted to understand the trade-offs clearly, not just from theory but from actual embedded projects I’ve worked on.

## The Core Concept

A HAL’s job is to decouple application logic from hardware specifics. You want to write `spi_transfer(handle, data, len)` without caring if it’s an STM32, NXP, or a simulated SPI on your host. The question is: how do you represent that “handle” and its associated operations?

**Raw function pointers** are the simplest approach. You declare a callback signature and assign a function pointer at runtime. This is great for single-instance peripherals or when you need extreme flexibility (like an interrupt vector table). But it falls apart when you have multiple instances of the same peripheral—you end up with a mess of global pointers or manual context passing.

**Structs of function pointers** (often called “virtual tables” or vtables in C) group all operations for a peripheral into one struct. Each instance gets its own struct, and you pass the struct pointer to every API call. This gives you clean instance management, easy mocking for tests, and a natural way to support multiple hardware variants.

The real insight: function pointers give you *behavioral* abstraction, but structs give you *structural* abstraction. For a HAL, you almost always need both—the struct organizes the operations, and the function pointers inside it provide the indirection.

## Key Commands / Configuration / Code

Let’s compare both approaches with a concrete SPI driver.

### Approach 1: Raw Function Pointers (Single Instance)

```c
// spi_raw.h
typedef void (*spi_init_t)(void);
typedef uint8_t (*spi_xfer_t)(uint8_t tx_byte);

extern spi_init_t spi_init;
extern spi_xfer_t spi_xfer;

// spi_raw.c
#include "spi_raw.h"

spi_init_t spi_init = NULL;
spi_xfer_t spi_xfer = NULL;

void spi_register_impl(spi_init_t init_fn, spi_xfer_t xfer_fn) {
    spi_init = init_fn;
    spi_xfer = xfer_fn;
}

// Application code
spi_register_impl(stm32_spi_init, stm32_spi_xfer);
spi_init();
uint8_t rx = spi_xfer(0xAA);
```

**Problem**: Only one SPI instance possible. No way to have SPI1 and SPI2 simultaneously.

### Approach 2: Struct of Function Pointers (Multi-Instance)

```c
// spi_hal.h
typedef struct spi_ops {
    void (*init)(void* hw_regs);
    uint8_t (*xfer)(void* hw_regs, uint8_t tx_byte);
} spi_ops_t;

typedef struct spi_handle {
    const spi_ops_t* ops;   // Pointer to vtable
    void* hw_regs;          // Hardware register base
    uint32_t baud;          // Instance-specific config
} spi_handle_t;

// Inline helper for clean API
static inline void spi_init(spi_handle_t* handle) {
    handle->ops->init(handle->hw_regs);
}

static inline uint8_t spi_xfer(spi_handle_t* handle, uint8_t tx) {
    return handle->ops->xfer(handle->hw_regs, tx);
}

// stm32_spi.c
static void stm32_spi_init(void* hw) {
    // Cast to STM32 SPI registers
    SPI_TypeDef* spi = (SPI_TypeDef*)hw;
    spi->CR1 |= SPI_CR1_SPE;
}

static uint8_t stm32_spi_xfer(void* hw, uint8_t tx) {
    SPI_TypeDef* spi = (SPI_TypeDef*)hw;
    while(!(spi->SR & SPI_SR_TXE));
    spi->DR = tx;
    while(!(spi->SR & SPI_SR_RXNE));
    return (uint8_t)spi->DR;
}

const spi_ops_t stm32_spi_ops = {
    .init = stm32_spi_init,
    .xfer = stm32_spi_xfer,
};

// Application: two instances
spi_handle_t spi1 = { .ops = &stm32_spi_ops, .hw_regs = (void*)SPI1_BASE, .baud = 1000000 };
spi_handle_t spi2 = { .ops = &stm32_spi_ops, .hw_regs = (void*)SPI2_BASE, .baud = 500000 };

spi_init(&spi1);
uint8_t rx = spi_xfer(&spi1, 0xAA);
```

**Key advantages**: The `spi_handle_t` holds both the operations and the hardware context. You can have 10 SPI instances, each with its own ops table (even different hardware families). The inline helpers give you a clean, type-safe API without function call overhead.

## Common Pitfalls & Gotchas

1. **Forgetting const on the ops table**  
   If you don’t declare `const spi_ops_t stm32_spi_ops`, the linker puts it in RAM. On a Cortex-M, that’s 8–16 bytes per ops table that could be in flash. Always use `const`—it also prevents accidental modification at runtime.

2. **Mixing instance data with ops data**  
   I’ve seen code that puts `baud` and `cs_pin` inside the ops struct. That breaks the pattern—ops should be shared across all instances of the same hardware type. Instance-specific config belongs in the handle. Otherwise you can’t have two SPI instances at different baud rates.

3. **Over-abstracting with function pointers for everything**  
   Not every peripheral needs a vtable. If you only have one UART and never plan to change it, raw function pointers (or even direct calls) are simpler and produce smaller code. The struct pattern shines when you have multiple instances or need to mock for testing. Know when to keep it simple.

## Try It Yourself

1. **Refactor a raw-pointer driver**: Take a single-instance GPIO driver that uses global function pointers. Convert it to a struct-of-pointers pattern that supports at least two GPIO ports (e.g., PORTA and PORTB). Verify both can be used independently.

2. **Add a mock for testing**: Create a `mock_spi_ops` struct where `xfer` returns a fixed pattern and `init` just sets a flag. Write a test that initializes a `spi_handle_t` with the mock ops and verifies the flag is set after `spi_init()`.

3. **Measure the cost**: On your target MCU, compile both the raw-pointer and struct-of-pointers versions. Compare flash usage and call overhead (cycles per `spi_xfer`). Document the trade-off for your specific hardware.

## Next Up

Tomorrow I’ll explore **The vtable Pattern in C: Simulating Polymorphism for Drivers**—how to build a full polymorphic driver framework where you can swap entire peripheral families (e.g., STM32 SPI vs. NXP FlexSPI) at runtime with zero conditional logic. We’ll look at inheritance in C and why it’s not as scary as it sounds.
