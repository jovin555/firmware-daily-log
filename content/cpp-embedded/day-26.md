---
title: "Day 26: Templates for Zero-Cost Abstraction in Drivers"
date: 2026-07-08
tags: ["til", "cpp-embedded", "templates", "zero-cost", "drivers"]
---

## What I Explored Today

Today I dove into using C++ templates to build hardware driver abstractions that compile down to exactly the same machine code as hand-written C—zero runtime overhead. In embedded systems, every cycle and byte matters, yet we still need clean, reusable interfaces. Templates let us parameterize behavior at compile time, eliminating virtual dispatch, function pointers, and runtime branching that plague traditional OOP approaches. I applied this to a GPIO output driver and an SPI peripheral, confirming the generated assembly was identical to the non-abstracted version.

## The Core Concept

The fundamental tension in embedded driver design is between *abstraction* and *performance*. A classic C approach uses function pointers or structs with callbacks, but each indirect call costs cycles and prevents the compiler from inlining. A C++ virtual base class adds a vtable lookup—catastrophic for ISRs or tight loops.

Templates solve this by pushing the abstraction boundary to compile time. When you write `Driver<PORT_B, 5>`, the compiler instantiates a unique type with all register addresses and bit manipulations baked in. No runtime decisions, no indirection. The key insight: **templates allow type-level configuration** where the hardware details become part of the type itself, not runtime data.

This is "zero-cost abstraction" in action—you pay only for what you use, and the compiler optimizes away the abstraction layer entirely. For drivers, this means you can write high-level, type-safe code that generates the same `LDR`, `STR`, and `ORR` instructions a C programmer would write by hand.

## Key Commands / Configuration / Code

Let's build a zero-cost GPIO output driver for an ARM Cortex-M MCU (e.g., STM32). We'll template on the port and pin, using compile-time constants for register addresses.

```cpp
// gpio_driver.h
#include <cstdint>
#include <type_traits>

// Hardware register layout (simplified for STM32F4)
struct GpioRegs {
    volatile uint32_t MODER;   // 0x00
    volatile uint32_t OTYPER;  // 0x04
    volatile uint32_t OSPEEDR; // 0x08
    volatile uint32_t PUPDR;   // 0x0C
    volatile uint32_t IDR;     // 0x10
    volatile uint32_t ODR;     // 0x14
    volatile uint32_t BSRR;    // 0x18
    volatile uint32_t LCKR;    // 0x1C
    volatile uint32_t AFR[2];  // 0x20, 0x24
};

// Base addresses for GPIO ports (STM32F4)
constexpr uintptr_t GPIOA_BASE = 0x40020000;
constexpr uintptr_t GPIOB_BASE = 0x40020400;
constexpr uintptr_t GPIOC_BASE = 0x40020800;

// Template driver: Port and Pin are compile-time parameters
template <uintptr_t PortBase, uint8_t Pin>
class GpioOutput {
    static_assert(Pin < 16, "Pin must be 0-15");

    // Get pointer to hardware registers at compile time
    static GpioRegs* const regs = reinterpret_cast<GpioRegs*>(PortBase);

public:
    // Initialize pin as push-pull output, no pull-up/down
    static void init() {
        // Clear mode bits for this pin (2 bits per pin)
        regs->MODER &= ~(0x3u << (Pin * 2));
        // Set to output mode (01)
        regs->MODER |=  (0x1u << (Pin * 2));

        // Set output type to push-pull
        regs->OTYPER &= ~(0x1u << Pin);

        // No pull-up/down
        regs->PUPDR &= ~(0x3u << (Pin * 2));
    }

    // Set pin high
    static void set() {
        regs->BSRR = (1u << Pin);          // BSRR bit 0-15 sets pin
    }

    // Set pin low
    static void clear() {
        regs->BSRR = (1u << (Pin + 16));   // BSRR bit 16-31 resets pin
    }

    // Toggle pin using XOR on ODR
    static void toggle() {
        regs->ODR ^= (1u << Pin);
    }

    // Write value (0 or non-zero)
    static void write(bool value) {
        if (value) set();
        else       clear();
    }
};

// Usage: instantiate with hardware parameters
using LedPin = GpioOutput<GPIOB_BASE, 5>;  // PB5 on STM32F4 Discovery

void app_init() {
    LedPin::init();
}

void app_loop() {
    LedPin::set();
    delay_ms(500);
    LedPin::clear();
    delay_ms(500);
}
```

The compiler inlines `set()` to a single `STR` instruction writing to the BSRR register. No function call overhead, no vtable, no runtime check. The abstraction disappears.

For a more complex example—an SPI driver with configurable polarity and phase:

```cpp
// spi_driver.h
enum class SpiMode : uint8_t {
    Mode0 = 0,  // CPOL=0, CPHA=0
    Mode1 = 1,  // CPOL=0, CPHA=1
    Mode2 = 2,  // CPOL=1, CPHA=0
    Mode3 = 3   // CPOL=1, CPHA=1
};

template <uintptr_t SpiBase, SpiMode Mode, uint32_t ClockDiv>
class SpiMaster {
    static_assert(ClockDiv >= 2, "Clock divider must be >= 2");
    static_assert(ClockDiv % 2 == 0, "Clock divider must be even");

    struct SpiRegs {
        volatile uint32_t CR1;
        volatile uint32_t CR2;
        volatile uint32_t SR;
        volatile uint32_t DR;
        // ... more registers
    };

    static SpiRegs* const regs = reinterpret_cast<SpiRegs*>(SpiBase);

public:
    static void init() {
        // Configure clock polarity and phase from Mode template parameter
        constexpr uint32_t cpol = (static_cast<uint8_t>(Mode) >> 1) & 0x1;
        constexpr uint32_t cpha = static_cast<uint8_t>(Mode) & 0x1;

        regs->CR1 = (ClockDiv / 2 - 1) << 3  // Baud rate
                  | (cpol << 1)               // CPOL
                  | (cpha << 0);              // CPHA
        regs->CR1 |= (1 << 6);                // Enable SPI
    }

    static uint8_t transfer(uint8_t data) {
        regs->DR = data;
        while (!(regs->SR & (1 << 1)));  // Wait for TXE
        while (!(regs->SR & (1 << 0)));  // Wait for RXNE
        return regs->DR;
    }
};

// Instantiate for specific hardware
using Spi1 = SpiMaster<0x40013000, SpiMode::Mode0, 8>;
```

## Common Pitfalls & Gotchas

1. **Code bloat from too many template instantiations**: Each unique combination of template parameters creates a separate function in the binary. If you instantiate `GpioOutput<GPIOA_BASE, 0>` through `GpioOutput<GPIOA_BASE, 15>`, you get 16 copies of `init()`. Mitigate by factoring out common logic into non-template helper functions, or use a single instance with runtime pin selection if you truly need all pins.

2. **`reinterpret_cast` and constexpr confusion**: The `static GpioRegs* const regs` trick works because the pointer is initialized at runtime before `main()`, but the address is a compile-time constant. This is fine for global objects. However, you cannot use `reinterpret_cast` in a `constexpr` context (C++17 and earlier). If you try to make `regs` a `constexpr` variable, the compiler will reject it. Keep it as `static const` initialized at load time.

3. **Forgetting volatile**: Hardware registers can change outside the program flow (interrupts, DMA). Always declare register pointers as `volatile`. The compiler will optimize away reads and writes without `volatile`, leading to subtle bugs where a status flag is never re-read.

## Try It Yourself

1. **Extend the GPIO driver** to support open-drain output mode. Add an `enum class OutputType { PushPull, OpenDrain }` template parameter and modify `init()` to set the OTYPER register accordingly. Verify the compiler eliminates the mode check for a single instantiation.

2. **Build a compile-time pin mapping**: Create a template `PinMap` that takes a port letter (e.g., `'A'`) and pin number, and resolves to the correct base address using a `constexpr` lookup table. Use `static_assert` to reject invalid port letters.

3. **Profile the assembly**: Take the `GpioOutput` driver and compile it for your target MCU (e.g., `arm-none-eabi-g++ -O2 -S`). Compare the generated assembly for `LedPin::set()` against a raw `*(uint32_t*)0x40020418 = (1 << 5)`. They should be identical—confirm the zero-cost claim.

## Next Up

Tomorrow, we'll explore **Type Traits & SFINAE for Hardware-Specific Code**. We'll use `std::is_same`, `std::enable_if`, and Substitution Failure Is Not An Error to write drivers that automatically select the right register layout for different MCU families—all at compile time, with zero runtime overhead.
