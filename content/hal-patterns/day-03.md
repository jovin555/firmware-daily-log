---
title: "Day 03: Register Abstraction: Memory-Mapped I/O & volatile Correctness"
date: 2026-07-03
tags: ["til", "hal-patterns", "mmio", "volatile"]
---

## What I Explored Today

Today I dug into the bedrock of embedded firmware: memory-mapped I/O (MMIO) and the `volatile` keyword. While every embedded engineer knows you need `volatile` for hardware registers, I wanted to understand *why* the compiler optimizations break without it, and how to build a clean, type-safe abstraction layer that prevents the most common register-access bugs. I focused on ARM Cortex-M style MMIO, but the principles apply universally.

## The Core Concept

Hardware peripherals expose their control and status registers at fixed memory addresses. Unlike RAM, reading a register can have side effects (clearing an interrupt flag) and writing can trigger hardware actions (starting an ADC conversion). The compiler sees these addresses as plain memory locations and will optimize away redundant reads, reorder writes, or cache values in registers—all of which break hardware interaction.

The `volatile` qualifier tells the compiler: "This value can change outside the normal flow of execution, and every access must happen exactly as written." Without it, a polling loop like `while(!(UART_SR & TX_EMPTY));` might read the status register once and loop forever because the compiler cached the initial value.

But raw `volatile` pointers are error-prone. The real pattern is to wrap register maps in C structs with volatile members, then cast the base address to a pointer to that struct. This gives you:
- Type safety for register widths
- Offset calculations handled by the compiler
- Readable code like `UART1->DR = 'A'` instead of `*(volatile uint32_t*)(0x40001000) = 'A'`

## Key Commands / Configuration / Code

### The Wrong Way (raw pointer arithmetic)
```c
// BAD: No type safety, easy to get offset wrong
#define UART_BASE 0x40001000
#define UART_DR   (*(volatile uint32_t*)(UART_BASE + 0x000))
#define UART_SR   (*(volatile uint32_t*)(UART_BASE + 0x004))

void uart_send(char c) {
    while (!(UART_SR & (1 << 7)));  // Wait for TX ready
    UART_DR = c;
}
```

### The Right Way (struct-based MMIO)
```c
// GOOD: Compiler handles offsets, type-safe, readable
typedef struct {
    volatile uint32_t DR;      // 0x000 - Data Register
    volatile uint32_t SR;      // 0x004 - Status Register
    volatile uint32_t CR1;     // 0x008 - Control Register 1
    volatile uint32_t CR2;     // 0x00C - Control Register 2
} UART_Registers;

#define UART1 ((UART_Registers*)0x40001000)
#define UART2 ((UART_Registers*)0x40001400)

// Status register bit definitions
#define UART_SR_TXE (1 << 7)   // Transmit data register empty

void uart_send_char(UART_Registers* uart, char c) {
    while (!(uart->SR & UART_SR_TXE));  // Compiler must re-read SR each time
    uart->DR = c;
}
```

### Bit-band regions (Cortex-M3/M4 optimization)
```c
// For atomic bit manipulation without read-modify-write
// Bit-band alias: 0x42000000 + (byte_offset * 32) + (bit_number * 4)
#define BITBAND_SRAM(addr, bit)  ((volatile uint32_t*)(0x22000000 + ((uint32_t)(addr) - 0x20000000) * 32 + (bit) * 4))
#define BITBAND_PERIPH(addr, bit) ((volatile uint32_t*)(0x42000000 + ((uint32_t)(addr) - 0x40000000) * 32 + (bit) * 4))

// Set bit 7 of UART1->SR atomically
*BITBAND_PERIPH(&UART1->SR, 7) = 1;
```

### The const-volatile pattern for read-only registers
```c
typedef struct {
    volatile uint32_t DR;       // Read-write
    volatile const uint32_t SR; // Read-only status register
    volatile uint32_t CR1;      // Read-write
} UART_Registers;
// Now uart->SR = 0; will cause a compile error
```

## Common Pitfalls & Gotchas

1. **Forgetting `volatile` on struct members, not just the pointer**  
   `UART_Registers* const uart` only makes the pointer constant, not the registers. Each member must be `volatile` individually. A common mistake is `typedef struct { uint32_t DR; } UART_Registers;` then casting `(volatile UART_Registers*)`—this doesn't propagate to members in all compilers.

2. **Assuming `volatile` guarantees atomicity**  
   `volatile` prevents compiler optimizations but doesn't prevent a read-modify-write from being interrupted. On a single-core MCU, a `uart->CR1 |= 0x01;` compiles to a load, OR, store sequence. An ISR modifying the same register between load and store will corrupt the value. Use bit-banding or explicit critical sections.

3. **Over-using `volatile` on local variables**  
   Some engineers sprinkle `volatile` on every variable "just in case." This disables all compiler optimizations for that variable (register allocation, constant propagation). Only use `volatile` for memory that can change asynchronously: hardware registers, shared data between ISR and main loop, and memory-mapped peripherals.

## Try It Yourself

1. **Examine your MCU's header file** (e.g., `stm32f4xx.h`). Find the `GPIO_TypeDef` struct and verify all members are `volatile`. Count how many registers are marked `volatile const` (read-only).

2. **Write a register dump function** that prints all registers of a UART peripheral. Use the struct-based approach. Then try removing `volatile` from one member and observe the compiler output (use `-S` flag to generate assembly). Notice how the compiler reorders or eliminates reads.

3. **Implement a bit-band macro** for a GPIO output register. Toggle an LED using bit-band writes and compare the generated assembly to a traditional read-modify-write. Measure the cycle count difference (use DWT cycle counter on Cortex-M).

## Next Up

Tomorrow: **Designing a Clean HAL API: Function Pointers vs Structs** — we'll explore how to abstract hardware behind a stable interface, comparing the flexibility of function pointer tables against the simplicity of struct-based drivers, and when to use each pattern in production firmware.
