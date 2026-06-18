---
title: "Day 06: Templates for Zero-Cost Abstraction in Drivers"
date: 2026-06-18
tags: ["til", "cpp-embedded", "templates", "zero-cost", "drivers"]
---

## What I Explored Today

Today I dug into C++ templates as a mechanism for building hardware abstraction layers that incur zero runtime overhead. In embedded systems, every byte and cycle counts, yet we still need clean, reusable driver code. Templates let us parameterize behavior at compile time, so the compiler generates specialized code for each hardware instance without virtual function tables, function pointers, or runtime dispatch. I applied this to GPIO, SPI, and timer drivers on an ARM Cortex-M4 target, verifying that the generated assembly matched hand-optimized C.

## The Core Concept

The fundamental tension in embedded driver design is between abstraction and performance. Traditional C approaches use function pointers or structs of callbacks to support multiple hardware instances, but each indirect call costs cycles and prevents the compiler from inlining. C++ virtual functions add vtable overhead and inhibit many optimizations.

Templates solve this by moving polymorphism to compile time. When you write `SPI<SPI1_BASE, 1000000> spi;`, the compiler generates a distinct type with all methods specialized for that exact peripheral and configuration. The resulting code is identical to writing separate, hand-tuned functions for each instance — but you write it once. This is "zero-cost abstraction": you pay only for what you use, and the abstraction disappears after compilation.

For hardware drivers, this means:
- No runtime type dispatch
- Full inlining of register access sequences
- Compile-time validation of peripheral configurations
- The ability to compose drivers without overhead

## Key Commands / Configuration / Code

Here's a practical GPIO output driver using templates for zero-cost abstraction:

```cpp
#include <cstdint>
#include <type_traits>

// Hardware register layout (STM32-style)
struct GPIO_Regs {
    volatile uint32_t MODER;    // 0x00
    volatile uint32_t OTYPER;   // 0x04
    volatile uint32_t OSPEEDR;  // 0x08
    volatile uint32_t PUPDR;    // 0x0C
    volatile uint32_t IDR;      // 0x10
    volatile uint32_t ODR;      // 0x14
    volatile uint32_t BSRR;     // 0x18
    volatile uint32_t LCKR;     // 0x1C
    volatile uint32_t AFR[2];   // 0x20, 0x24
};

// Template base: parameterized by base address and pin number
template <uintptr_t BASE, uint8_t PIN>
class GpioOutput {
    static_assert(PIN < 16, "GPIO pin must be 0-15");
    
    static GPIO_Regs* const regs = reinterpret_cast<GPIO_Regs*>(BASE);
    
public:
    // Initialize pin as push-pull output, no pull-up/down
    static void init() {
        // Clear mode bits for this pin (2 bits per pin)
        regs->MODER &= ~(0x3u << (PIN * 2));
        // Set to output mode (01)
        regs->MODER |=  (0x1u << (PIN * 2));
        // Push-pull output type
        regs->OTYPER &= ~(0x1u << PIN);
        // No pull-up/down
        regs->PUPDR  &= ~(0x3u << (PIN * 2));
    }
    
    static void set() {
        regs->BSRR = (1u << PIN);          // Set bit in BSRR
    }
    
    static void clear() {
        regs->BSRR = (1u << (PIN + 16));   // Reset bit in BSRR
    }
    
    static void toggle() {
        regs->ODR ^= (1u << PIN);          // XOR the output data register
    }
};

// Usage: instantiate at compile time
using LedRed   = GpioOutput<0x40020000, 5>;  // GPIOA, pin 5
using LedGreen = GpioOutput<0x40020400, 1>;  // GPIOB, pin 1

void app_init() {
    LedRed::init();
    LedGreen::init();
}

void app_loop() {
    LedRed::set();
    LedGreen::clear();
    // Compiler generates: *(0x40020018) = 0x20; *(0x40020418) = 0x20000;
}
```

For a more complex example, here's a compile-time SPI configuration:

```cpp
template <uintptr_t BASE, uint32_t FREQ_HZ>
class SpiMaster {
    struct SpiRegs {
        volatile uint32_t CR1;
        volatile uint32_t CR2;
        volatile uint32_t SR;
        volatile uint32_t DR;
        volatile uint32_t CRCPR;
        volatile uint32_t RXCRCR;
        volatile uint32_t TXCRCR;
        volatile uint32_t I2SCFGR;
        volatile uint32_t I2SPR;
    };
    
    static constexpr uint32_t PCLK = 48000000;  // Peripheral clock
    static constexpr uint16_t BR_VAL = []() {
        // Compute baud rate divisor at compile time
        for (uint16_t div = 2; div <= 256; div *= 2) {
            if (PCLK / div <= FREQ_HZ) return (div >> 1) - 1;
        }
        return 7;  // Max divisor
    }();
    
    static SpiRegs* const regs = reinterpret_cast<SpiRegs*>(BASE);
    
public:
    static void init() {
        regs->CR1 = (BR_VAL << 3) | (1 << 2) | (1 << 6);  // BR, master mode, SPI enable
    }
    
    static uint8_t transfer(uint8_t data) {
        regs->DR = data;
        while (!(regs->SR & (1 << 1)));  // Wait for TXE
        while (!(regs->SR & (1 << 0)));  // Wait for RXNE
        return regs->DR;
    }
};
```

## Common Pitfalls & Gotchas

1. **Code Bloat from Template Instantiations**: Each unique combination of template parameters generates a separate function. If you instantiate `GpioOutput<0x40020000, 0>` through `GpioOutput<0x40020000, 15>`, you get 16 copies of every method. Mitigate by factoring common logic into non-template base classes or using `constexpr` helper functions.

2. **`static` vs `constexpr` for Register Pointers**: Declaring the register pointer as `static const` inside a template class works, but the linker may emit a symbol for it. Use `static constexpr` (C++17) or inline the cast in each method to guarantee zero data memory overhead. In C++14, prefer `static constexpr auto regs = ...` with a lambda or constexpr function.

3. **Reinterpret_cast at Global Scope**: Casting an integer literal to a pointer at namespace scope is technically a reinterpret_cast in a constant expression, which is undefined behavior in some standards. Wrap the cast in a `constexpr` function or use a `volatile` pointer inside each method. On embedded targets with known memory maps, this is safe in practice, but static analyzers may complain.

## Try It Yourself

1. **Extend the GPIO driver**: Add a template parameter for output type (push-pull vs open-drain) and speed. Use `static_assert` to validate valid combinations at compile time.

2. **Build a compile-time pin mapping**: Create a template `DigitalPin<Port, Pin>` that resolves to the correct base address using a constexpr lookup table. Instantiate `DigitalPin<'A', 5>` and verify the compiler generates the correct address.

3. **Profile the overhead**: Write a non-template SPI driver using function pointers and compare the generated assembly (use `-S` flag) with the template version. Count the instructions for a single `transfer()` call — the template version should be identical to a hand-written inline function.

## Next Up

Tomorrow, we'll explore **Type Traits & SFINAE for Hardware-Specific Code** — using `std::enable_if`, `std::is_same`, and Substitution Failure Is Not An Error to select different driver implementations based on hardware capabilities at compile time, without runtime checks.
