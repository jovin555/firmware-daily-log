---
title: "Day 10: HAL Design in C++: Templates & Zero-Cost Abstraction"
date: 2026-07-10
tags: ["til", "hal-patterns", "cpp-templates", "zero-cost"]
---

## What I Explored Today

Today I dug into using C++ templates to build a Hardware Abstraction Layer that achieves zero-cost abstraction — meaning the compiler eliminates all runtime overhead from the abstraction layer, producing the same machine code as a hand-written C implementation. I focused on template-based peripheral access, compile-time register mapping, and policy-based design for GPIO and UART drivers.

## The Core Concept

The fundamental tension in HAL design is abstraction vs. performance. Virtual functions give us clean interfaces but add vtable overhead, indirect calls, and prevent inlining. Templates solve this by moving polymorphism to compile time: the compiler generates specialized code for each concrete type, then optimizes it away.

The key insight is that hardware peripherals are known at compile time. The MCU has a fixed set of UARTs, SPIs, and GPIO ports. There's no runtime polymorphism needed — we know exactly which peripheral we're using. Templates let us encode this knowledge into the type system, producing code that's as efficient as direct register access but with the safety and readability of a high-level API.

A template-based HAL works by making the peripheral's base address a template parameter. This turns register offsets into compile-time constants, and all register accesses become direct memory-mapped I/O with zero indirection. The compiler sees through the abstraction and generates the same LDR/STR instructions you'd write by hand.

## Key Commands / Configuration / Code

Here's a practical template-based GPIO output driver:

```cpp
// gpio.hpp - Template-based GPIO HAL
#include <cstdint>
#include <type_traits>

// Compile-time register map
template<uint32_t BASE_ADDR>
struct GpioRegisters {
    static volatile uint32_t& MODER  = *reinterpret_cast<uint32_t*>(BASE_ADDR);
    static volatile uint32_t& OTYPER = *reinterpret_cast<uint32_t*>(BASE_ADDR + 0x04);
    static volatile uint32_t& OSPEEDR= *reinterpret_cast<uint32_t*>(BASE_ADDR + 0x08);
    static volatile uint32_t& PUPDR  = *reinterpret_cast<uint32_t*>(BASE_ADDR + 0x0C);
    static volatile uint32_t& IDR    = *reinterpret_cast<uint32_t*>(BASE_ADDR + 0x10);
    static volatile uint32_t& ODR    = *reinterpret_cast<uint32_t*>(BASE_ADDR + 0x14);
    static volatile uint32_t& BSRR   = *reinterpret_cast<uint32_t*>(BASE_ADDR + 0x18);
};

// Policy-based pin configuration
enum class OutputType : uint32_t { PUSH_PULL = 0, OPEN_DRAIN = 1 };
enum class Speed : uint32_t { LOW = 0, MEDIUM = 1, HIGH = 2, VERY_HIGH = 3 };

template<uint32_t BASE, uint8_t PIN, OutputType OT = OutputType::PUSH_PULL>
class GpioOutput {
    static_assert(PIN < 16, "GPIO pins 0-15 only");
    
public:
    static void init() {
        // Set mode to output (01) for this pin
        GpioRegisters<BASE>::MODER = 
            (GpioRegisters<BASE>::MODER & ~(0x3 << (PIN * 2))) | (0x1 << (PIN * 2));
        
        // Set output type
        GpioRegisters<BASE>::OTYPER = 
            (GpioRegisters<BASE>::OTYPER & ~(0x1 << PIN)) | 
            (static_cast<uint32_t>(OT) << PIN);
    }
    
    static void set() { 
        GpioRegisters<BASE>::BSRR = (1 << PIN); 
    }
    
    static void reset() { 
        GpioRegisters<BASE>::BSRR = (1 << (PIN + 16)); 
    }
    
    static void toggle() {
        auto& odr = GpioRegisters<BASE>::ODR;
        odr ^= (1 << PIN);
    }
};

// Usage - zero-cost, no runtime overhead
using LedRed   = GpioOutput<0x40020C00, 12>;  // GPIOD, pin 12
using LedGreen = GpioOutput<0x40020C00, 13>;  // GPIOD, pin 13

void blink_example() {
    LedRed::init();
    LedGreen::init();
    
    while(1) {
        LedRed::set();
        LedGreen::reset();
        delay_ms(500);
        LedRed::reset();
        LedGreen::set();
        delay_ms(500);
    }
}
```

For a more complex example, here's a template-based UART with configurable baud rate calculated at compile time:

```cpp
// uart.hpp - Compile-time baud rate calculation
template<uint32_t BASE, uint32_t CLOCK_HZ, uint32_t BAUD>
class Uart {
    static_assert(BAUD <= CLOCK_HZ / 16, "Baud rate too high for given clock");
    
    // Compile-time baud rate divisor calculation
    static constexpr uint32_t DIVISOR = (CLOCK_HZ + BAUD/2) / (16 * BAUD);
    
public:
    static void init() {
        // Enable UART, 8N1, enable TX/RX
        regs()->CR1 = 0x0000200C;  // UE=1, TE=1, RE=1
        regs()->BRR = DIVISOR;
    }
    
    static void putchar(char c) {
        while(!(regs()->SR & (1 << 7)));  // Wait for TXE
        regs()->DR = c;
    }
    
private:
    struct RegMap {
        volatile uint32_t SR;   // 0x00
        volatile uint32_t DR;   // 0x04
        volatile uint32_t BRR;  // 0x08
        volatile uint32_t CR1;  // 0x0C
    };
    
    static RegMap* regs() { 
        return reinterpret_cast<RegMap*>(BASE); 
    }
};

// Usage
using DebugUart = Uart<0x40004400, 80000000, 115200>;
DebugUart::init();
DebugUart::putchar('A');  // Compiles to direct register writes
```

## Common Pitfalls & Gotchas

1. **Template bloat from excessive specializations**: Each unique combination of template parameters generates a separate function. If you have 16 pins × 2 ports × 3 output types, that's 96 instantiations. Use `constexpr` functions for runtime-variant parts to reduce code size. Profile with `-fbloat` flags.

2. **Register access ordering and volatile**: The compiler can reorder template-inlined register accesses. Always use `volatile` on register pointers, and insert `asm volatile("" ::: "memory")` barriers between sequences that must occur in order (like setting MODER before OTYPER). Some compilers need `__DSB()` intrinsics for strongly-ordered peripherals.

3. **Static initialization order fiasco**: Template static members are initialized on first use, which is fine. But if your `init()` function depends on RCC clock configuration done elsewhere, ensure that clock init happens before any peripheral template instantiation. Use explicit init sequences, not global constructors.

## Try It Yourself

1. **Extend the GPIO template** to support interrupt configuration. Add a `configure_interrupt()` static method that sets the rising/falling edge trigger registers and enables the NVIC line. Verify the generated assembly has zero function call overhead.

2. **Build a compile-time SPI divider**: Create a template `Spi<BASE, CLOCK_HZ, FREQ>` that calculates the clock divider at compile time. Add a static assertion that rejects invalid divider values (e.g., odd numbers on controllers that require even dividers).

3. **Measure the abstraction cost**: Write a benchmark that calls `GpioOutput::toggle()` in a tight loop. Compile with `-Os` and `-S` to generate assembly. Compare against a raw `*(uint32_t*)0x40020C14 ^= (1<<12)` implementation. They should be identical.

## Next up

Tomorrow: **CRTP for Compile-Time Polymorphic Drivers** — using the Curiously Recurring Template Pattern to create interface contracts without vtables, enabling mix-and-match driver policies for SPI, I2C, and custom protocols.
