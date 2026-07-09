---
title: "Day 27: Type Traits & SFINAE for Hardware-Specific Code"
date: 2026-07-09
tags: ["til", "cpp-embedded", "type-traits", "sfinae"]
---

## What I Explored Today

Today I dug into how C++ type traits and SFINAE (Substitution Failure Is Not An Error) can eliminate runtime branching in hardware abstraction layers. On embedded targets, every `if` statement checking a peripheral type or register width costs cycles and flash. By moving these decisions to compile time, we get zero-overhead polymorphism and safer code that simply won’t compile for unsupported hardware configurations. I applied this to a register-access abstraction that adapts to 8-bit, 16-bit, and 32-bit MCU peripherals without a single runtime check.

## The Core Concept

Hardware-specific code is full of conditional compilation (`#ifdef`) and runtime type checks. Both are fragile. `#ifdef` scatters platform logic across files, and runtime checks bloat the binary. Type traits let us query properties of types at compile time (e.g., `std::is_integral_v<T>`, `std::is_same_v<T, U>`). SFINAE is the mechanism that lets the compiler silently discard template overloads that would be ill-formed — instead of emitting an error, it just removes that candidate from overload resolution.

For embedded engineers, this means you can write a single template function that works for `uint8_t`, `uint16_t`, and `uint32_t` registers, but only compiles the version that matches the actual hardware. No runtime dispatch, no preprocessor spaghetti. The compiler selects the correct implementation based on the type you pass, and if you pass an unsupported type (like a float), the code simply doesn’t compile.

## Key Commands / Configuration / Code

Here’s a practical register-writer that uses `std::enable_if` and type traits to enforce alignment and width constraints at compile time.

```cpp
#include <type_traits>
#include <cstdint>

// Base template: disabled for all types by default
template<typename T, typename = void>
struct RegisterWriter;

// Specialization for 8-bit registers
template<typename T>
struct RegisterWriter<T, std::enable_if_t<std::is_same_v<T, uint8_t>>>
{
    static void write(volatile T* reg, T value) noexcept
    {
        *reg = value;
    }
};

// Specialization for 16-bit registers (must be 2-byte aligned)
template<typename T>
struct RegisterWriter<T, std::enable_if_t<std::is_same_v<T, uint16_t>>>
{
    static void write(volatile T* reg, T value) noexcept
    {
        // Compile-time alignment check
        static_assert(alignof(T) >= 2, "16-bit register must be 2-byte aligned");
        *reg = value;
    }
};

// Specialization for 32-bit registers (must be 4-byte aligned)
template<typename T>
struct RegisterWriter<T, std::enable_if_t<std::is_same_v<T, uint32_t>>>
{
    static void write(volatile T* reg, T value) noexcept
    {
        static_assert(alignof(T) >= 4, "32-bit register must be 4-byte aligned");
        *reg = value;
    }
};

// Convenience function using SFINAE on return type
template<typename T>
auto write_register(volatile T* reg, T value)
    -> std::enable_if_t<std::is_integral_v<T> && (sizeof(T) <= 4)>
{
    RegisterWriter<T>::write(reg, value);
}

// Usage on an STM32-like target
volatile uint32_t* GPIO_BSRR = reinterpret_cast<volatile uint32_t*>(0x40020018);
write_register(GPIO_BSRR, 0x00010001);  // OK: uint32_t

volatile uint8_t* UART_DR = reinterpret_cast<volatile uint8_t*>(0x40004400);
write_register(UART_DR, 0x55);          // OK: uint8_t

// write_register(GPIO_BSRR, 3.14f);    // ERROR: float is not integral
```

The key is `std::enable_if_t<condition>` — when the condition is false, the template specialization is removed from overload resolution. The `static_assert` inside each specialization catches alignment violations at compile time, not at runtime during a hard fault.

For a more advanced pattern, here’s how to detect whether a type has a specific member function (e.g., `reset()`) using SFINAE:

```cpp
template<typename T, typename = void>
struct has_reset : std::false_type {};

template<typename T>
struct has_reset<T, std::void_t<decltype(std::declval<T>().reset())>>
    : std::true_type {};

template<typename T>
void safe_reset(T& device)
{
    if constexpr (has_reset<T>::value) {
        device.reset();
    } else {
        // Fallback: power-cycle via GPIO or do nothing
    }
}
```

This pattern is invaluable for writing generic driver code that works across multiple MCU families.

## Common Pitfalls & Gotchas

**1. SFINAE only works in the immediate context of template instantiation.** If you try to `static_assert` inside a function body that’s never instantiated, the assert still fires. Always put SFINAE conditions in the template parameter list or return type, not inside the function body. Use `static_assert` only inside specializations that you know will be selected.

**2. Overusing `std::enable_if` on function return types can make error messages unreadable.** When a call fails, the compiler lists every disabled overload. Prefer `if constexpr` inside a single template function when the logic is simple — it’s much easier to debug. Reserve SFINAE for cases where you truly need different function signatures or class specializations.

**3. Forgetting `volatile` on register pointers.** Hardware registers must be accessed through `volatile` pointers to prevent the compiler from optimizing away reads/writes. Your type traits and SFINAE code must propagate `volatile` correctly. A common mistake is to define `write_register(T* reg, T value)` without `volatile`, then wonder why the peripheral doesn’t respond.

## Try It Yourself

1. **Extend the RegisterWriter** to support `uint64_t` registers (common on Cortex-M7 with D-Cache). Add a `static_assert` that alignment must be at least 8 bytes. Verify that passing a misaligned pointer fails to compile.

2. **Write a type trait `is_peripheral_register<T>`** that returns `true_type` only for `uint8_t`, `uint16_t`, and `uint32_t`. Use it to guard a generic `read_register()` function so it rejects `float` and `double` types.

3. **Implement a SFINAE-based dispatcher** for two different GPIO libraries: one that uses `BSRR` registers (STM32) and one that uses `OUT` registers (AVR). The dispatcher should detect which struct layout is passed and call the correct `set_pin()` implementation.

## Next Up

Tomorrow we’ll look at `std::variant` and `std::optional` — two tools that replace error codes and sentinel values with type-safe, no-overhead error handling. Perfect for those peripheral initialization sequences where a register read might fail or a DMA channel might be busy.
