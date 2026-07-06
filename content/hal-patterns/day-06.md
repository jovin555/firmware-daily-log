---
title: "Day 06: Opaque Handles & Pimpl-Style Encapsulation in C"
date: 2026-07-06
tags: ["til", "hal-patterns", "opaque-handle", "encapsulation"]
---

## What I Explored Today

Today I dug into one of the most powerful yet underused encapsulation techniques in C firmware: **opaque handles** combined with the **Pointer-to-Implementation (Pimpl)** idiom. While C++ developers lean on `private` keywords and header-only libraries, we C engineers have to get creative. The opaque handle pattern lets us hide implementation details from the caller, enforce API contracts at compile time, and swap out hardware backends without touching a single line of application code. I implemented a minimal UART driver using this pattern and saw firsthand how it eliminates header pollution and accidental struct member access.

## The Core Concept

The idea is brutally simple: expose only a forward-declared struct pointer in your public header. The actual struct definition lives in the private `.c` file. The caller never sees the struct members—they only pass around a handle (a pointer to an incomplete type). This is the C equivalent of C++’s `pimpl` idiom.

Why bother? Three reasons:

1. **Compile-time firewall** — Changing a private struct member doesn’t force recompilation of every file that includes your header. In large firmware projects, this saves minutes per rebuild.
2. **API contract enforcement** — Callers cannot accidentally zero out a critical field or bypass initialization. If they can’t see it, they can’t touch it.
3. **Hardware abstraction** — The same handle type can point to different underlying implementations (e.g., UART on USART1 vs. LPUART1) without the caller knowing.

The tradeoff: heap allocation or a static pool for handle creation, and a slight indirection cost. On embedded MCUs, the indirection is usually free (one extra load), and the allocation can be managed with a fixed-size pool.

## Key Commands / Configuration / Code

Here’s a minimal but complete example. We’ll build a UART driver that hides its register map and buffer state.

**Public header (`uart_driver.h`):**
```c
#ifndef UART_DRIVER_H
#define UART_DRIVER_H

#include <stdint.h>
#include <stddef.h>

// Forward declaration — caller never sees the struct
typedef struct uart_handle uart_handle_t;

// Opaque handle: pointer to incomplete type
typedef uart_handle_t* uart_t;

// Configuration struct — caller must fill this
typedef struct {
    uint32_t base_addr;   // e.g., 0x40004400 for USART2
    uint32_t baud_rate;
    uint8_t  parity;      // 0=none, 1=even, 2=odd
} uart_config_t;

// Public API — all operations go through the handle
uart_t uart_init(const uart_config_t* config);
void   uart_send(uart_t handle, const uint8_t* data, size_t len);
void   uart_deinit(uart_t handle);

#endif
```

**Private implementation (`uart_driver.c`):**
```c
#include "uart_driver.h"
#include <stdlib.h>   // for malloc (or use static pool)

// Private struct — definition hidden from callers
struct uart_handle {
    volatile uint32_t* sr;    // status register
    volatile uint32_t* dr;    // data register
    volatile uint32_t* brr;   // baud rate register
    uint32_t           baud;
    uint8_t            tx_buf[64];  // internal buffer
    uint8_t            tx_head;
    uint8_t            tx_tail;
};

// Static pool for MCUs without malloc (common in embedded)
static struct uart_handle handles[4];
static uint8_t handle_count = 0;

uart_t uart_init(const uart_config_t* config) {
    if (handle_count >= 4) return NULL;  // pool exhausted

    struct uart_handle* h = &handles[handle_count++];
    // Map base address to peripheral registers
    h->sr  = (volatile uint32_t*)(config->base_addr + 0x00);
    h->dr  = (volatile uint32_t*)(config->base_addr + 0x04);
    h->brr = (volatile uint32_t*)(config->base_addr + 0x08);

    // Configure baud rate (simplified)
    *h->brr = (uint32_t)(16000000 / config->baud_rate);
    h->baud = config->baud_rate;

    // Enable UART (set UE bit in CR1)
    volatile uint32_t* cr1 = (volatile uint32_t*)(config->base_addr + 0x0C);
    *cr1 |= (1 << 13);  // UE enable

    return (uart_t)h;
}

void uart_send(uart_t handle, const uint8_t* data, size_t len) {
    struct uart_handle* h = (struct uart_handle*)handle;
    for (size_t i = 0; i < len; i++) {
        // Wait for TXE flag
        while (!(*h->sr & (1 << 7)));
        *h->dr = data[i];
    }
}

void uart_deinit(uart_t handle) {
    struct uart_handle* h = (struct uart_handle*)handle;
    volatile uint32_t* cr1 = (volatile uint32_t*)((uint32_t)h->sr - 0x0C);
    *cr1 &= ~(1 << 13);  // Disable UART
    // In a real driver, return handle to pool
}
```

**Usage in application code:**
```c
#include "uart_driver.h"

int main(void) {
    uart_config_t cfg = {
        .base_addr = 0x40004400,
        .baud_rate = 115200,
        .parity    = 0
    };

    uart_t uart = uart_init(&cfg);
    if (uart == NULL) {
        // handle error
    }

    const char msg[] = "Hello, opaque world!\r\n";
    uart_send(uart, (const uint8_t*)msg, sizeof(msg) - 1);

    uart_deinit(uart);
    // uart is now invalid — don't use it!
    return 0;
}
```

## Common Pitfalls & Gotchas

1. **Dereferencing the handle in the caller** — If someone includes the header and tries `uart->sr`, the compiler will error because `uart_handle_t` is incomplete. This is *good*. But if they cast the handle to a `uint32_t*` and poke around, all bets are off. Document that the handle is opaque.

2. **Static pool vs. malloc** — On bare-metal MCUs, `malloc` is often unavailable or dangerous (heap fragmentation). Use a static pool of pre-allocated handles. Track allocation with a bitmap or simple counter. The pool size becomes a compile-time constant—choose based on your max peripheral instances.

3. **Forgetting to cast in the implementation** — Inside `uart_send`, you *must* cast `handle` back to `struct uart_handle*`. If you accidentally use the opaque type, you’ll get incomplete type errors. Keep the cast explicit and local.

4. **Thread safety** — Opaque handles don’t magically become thread-safe. If you have an RTOS, protect the handle pool and any shared state with a mutex or critical section.

## Try It Yourself

1. **Extend the UART driver** — Add a `uart_receive` function that reads bytes into a caller-provided buffer. Use the same opaque handle. How do you handle the blocking vs. non-blocking decision without exposing the internal buffer?

2. **Implement a static pool allocator** — Replace the simple counter with a bitmap-based allocator. Add a `uart_free` function that returns the handle to the pool. Verify that double-free is detected.

3. **Swap the backend** — Create a second implementation of the same `uart_driver.h` API that uses a bit-banged GPIO for UART. The application code should compile and run identically with either backend. This is the power of opaque handles for HAL portability.

## Next Up

Tomorrow we tackle **Dependency Injection in Embedded C: Decoupling Drivers from Logic**. We’ll move from compile-time polymorphism (opaque handles) to runtime dependency injection using function pointers and configuration tables. You’ll learn how to write driver code that doesn’t care which SPI peripheral or GPIO pin it’s talking to—until runtime.
