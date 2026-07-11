---
title: "Day 11: CRTP for Compile-Time Polymorphic Drivers"
date: 2026-07-11
tags: ["til", "hal-patterns", "crtp"]
---

## What I Explored Today

Virtual functions are the default go-to for polymorphism in C++ embedded drivers, but they come with a hidden tax: vtable pointer overhead, indirect dispatch, and—critically—the optimizer often cannot inline virtual calls. Today I dug into the Curiously Recurring Template Pattern (CRTP) as a zero-overhead alternative for compile-time polymorphism in peripheral drivers. Instead of a base class with `virtual` methods, CRTP uses a template base class that casts `this` to the derived type, enabling the compiler to resolve method calls at compile time while still providing a uniform interface.

## The Core Concept

The fundamental problem: you have multiple hardware peripherals (SPI, I2C, UART) that share a common interface—`init()`, `write()`, `read()`, `deinit()`—but each has completely different register layouts and initialization sequences. A traditional approach uses an abstract base class with pure virtual functions, then derives concrete drivers. This works, but every call goes through the vtable, and the compiler cannot inline across the virtual boundary.

CRTP flips this: the base class is a template parameterized on the derived type. The base class provides the interface, but instead of virtual dispatch, it uses `static_cast<Derived*>(this)` to call derived methods directly. The derived class implements the hardware-specific logic. The result: no vtable, no runtime dispatch, and the compiler can inline everything. The "polymorphism" happens at compile time through template instantiation.

This pattern is especially valuable in tight loops (e.g., bit-banging or register polling) where every cycle matters, and in memory-constrained systems where the vtable pointer per object is non-trivial.

## Key Commands / Configuration / Code

Here's a minimal CRTP driver base for a GPIO-like peripheral:

```cpp
// crtp_gpio_base.hpp
template<typename Derived>
class GpioBase {
public:
    // Interface: derived class MUST implement these
    void init() {
        static_cast<Derived*>(this)->init_impl();
    }
    
    void set(bool state) {
        static_cast<Derived*>(this)->set_impl(state);
    }
    
    bool read() {
        return static_cast<Derived*>(this)->read_impl();
    }
    
    // Optional: default implementation in base
    void toggle() {
        static_cast<Derived*>(this)->set_impl(
            !static_cast<Derived*>(this)->read_impl()
        );
    }
};

// stm32_gpio_driver.hpp
#include "crtp_gpio_base.hpp"
#include <cstdint>

class Stm32Gpio : public GpioBase<Stm32Gpio> {
public:
    explicit Stm32Gpio(volatile uint32_t* reg_base) 
        : reg_base_(reg_base) {}
    
    // Required implementations
    void init_impl() {
        // Enable clock, set mode, pull-up, etc.
        *(reg_base_ + 0x00) = 0x01; // MODER: output
        *(reg_base_ + 0x0C) = 0x00; // PUPDR: no pull
    }
    
    void set_impl(bool state) {
        if (state) {
            *(reg_base_ + 0x14) = 0x01; // BSRR: set
        } else {
            *(reg_base_ + 0x18) = 0x01; // BRR: reset
        }
    }
    
    bool read_impl() {
        return (*(reg_base_ + 0x10) & 0x01) != 0; // IDR
    }
    
private:
    volatile uint32_t* reg_base_;
};

// Usage: zero-cost abstraction
Stm32Gpio led((volatile uint32_t*)0x40020000);
led.init();          // Inlined to direct register writes
led.set(true);       // Inlined to BSRR write
led.toggle();        // Inlined to read + write
```

For a more complex example, here's a CRTP SPI driver with compile-time chip select management:

```cpp
template<typename Derived>
class SpiBase {
public:
    void transfer(const uint8_t* tx, uint8_t* rx, size_t len) {
        auto* self = static_cast<Derived*>(this);
        self->cs_low_impl();
        for (size_t i = 0; i < len; ++i) {
            self->write_impl(tx ? tx[i] : 0xFF);
            if (rx) rx[i] = self->read_impl();
        }
        self->cs_high_impl();
    }
    
    void write_register(uint8_t addr, uint8_t val) {
        auto* self = static_cast<Derived*>(this);
        self->cs_low_impl();
        self->write_impl(addr);
        self->write_impl(val);
        self->cs_high_impl();
    }
};

class Stm32Spi1 : public SpiBase<Stm32Spi1> {
public:
    void cs_low_impl() { /* GPIO write */ }
    void cs_high_impl() { /* GPIO write */ }
    void write_impl(uint8_t byte) { /* SPI DR write */ }
    uint8_t read_impl() { /* SPI DR read */ return 0; }
};
```

## Common Pitfalls & Gotchas

1. **Forgetting to qualify `this->` in template base methods**: Inside the base class template, member names from the base are not automatically visible during two-phase lookup. You must use `this->` or `Derived::` to make them dependent names. Without it, the compiler will complain about undeclared identifiers.

2. **Accidental slicing or copy of CRTP objects**: If you pass a CRTP object by value to a function expecting the base type, you slice off the derived part. Always pass by reference or pointer. Better yet, make the base class non-copyable.

3. **Over-constraining the interface**: CRTP tempts you to put everything in the base class. Resist. Only put truly common operations there. If one derived class needs a completely different method signature, don't force it into the base—use a separate CRTP base for that variant or SFINAE to conditionally include methods.

## Try It Yourself

1. **Implement a CRTP UART driver**: Create a `UartBase<Derived>` with `putchar()`, `getchar()`, and `puts()`. Then derive `Stm32Uart2` that writes to `USART2->DR` and polls `USART2->SR`. Verify the generated assembly has no function calls.

2. **Add a compile-time pin mapping**: Modify the GPIO CRTP example to accept the pin number as a template parameter (e.g., `Stm32Gpio<'A', 5>`). Use `static_assert` to validate pin ranges at compile time. This eliminates all runtime configuration for fixed pins.

3. **Benchmark vs virtual**: Write a tight loop that toggles a GPIO 100,000 times using both CRTP and virtual dispatch. Compare the cycle count with a logic analyzer or `DWT->CYCCNT`. You should see CRTP being 2-5x faster due to inlining.

## Next Up

Tomorrow we tackle the **Strategy Pattern: Swappable Communication Backends (SPI/I2C/UART)**. We'll build a sensor driver that can use any transport protocol at runtime without conditional compilation—perfect for hardware abstraction layers that need to support multiple board revisions.
